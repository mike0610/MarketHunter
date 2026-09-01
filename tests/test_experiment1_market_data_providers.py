import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.engine import Experiment1Engine
from experiment1.market_data_providers import (
    AssetClass,
    FreshnessGuardedQuoteSource,
    MultiAssetQuoteSource,
    UnavailableQuoteProvider,
)
from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent
from experiment1.runtime import run_market_cycle


NOW = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, price="60000"):
        self.price = price

    async def get(self, path, **kwargs):
        return {"symbol": "BTCUSDT", "price": self.price}


class FakeSource:
    def __init__(self, quote):
        self.quote = quote

    async def quote_for(self, intent):
        return self.quote


def _intent(symbol="BTCUSDT", account=AccountKind.SPOT, intent_id="intent-1"):
    return OrderIntent(
        intent_id=intent_id,
        created_at=NOW,
        account=account,
        action=DecisionAction.BUY,
        symbol=symbol,
        quantity=Decimal("0.01"),
        reason="market data provider test",
    )


def _quote(observed_at=None, source="test-feed", source_reference="ref-1"):
    return MarketQuote(
        symbol="BTCUSDT",
        price=Decimal("60000"),
        observed_at=observed_at or NOW,
        source=source,
        source_reference=source_reference,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


# --- UnavailableQuoteProvider: unsupported symbols/classes fail closed --------

def test_unavailable_provider_never_returns_a_quote():
    for asset_class in (AssetClass.STOCK, AssetClass.ETF, AssetClass.METAL, AssetClass.US_INDEX):
        provider = UnavailableQuoteProvider(asset_class)
        quote = asyncio.run(provider.quote_for(_intent(symbol="AAPL")))
        assert quote is None


def test_unavailable_provider_default_reason_names_its_asset_class():
    provider = UnavailableQuoteProvider(AssetClass.STOCK)
    assert "STOCK" in provider.reason
    assert "no verified" in provider.reason.lower()


def test_unavailable_provider_accepts_explicit_reason():
    provider = UnavailableQuoteProvider(AssetClass.METAL, reason="XAUUSD feed pending Product Owner sign-off")
    assert provider.reason == "XAUUSD feed pending Product Owner sign-off"


# --- FreshnessGuardedQuoteSource: stale/unavailable evidence + provenance ----

def test_freshness_guard_passes_through_a_fresh_quote_with_provenance_intact():
    # observed_at is checked against the real wall clock inside the
    # guard, so "fresh" here must be relative to now() - not the fixed
    # NOW fixture used elsewhere for intent/engine ordering.
    fresh_observed_at = datetime.now(timezone.utc)
    quote = _quote(
        observed_at=fresh_observed_at,
        source="binance-public-rest",
        source_reference="spot:ticker-price:BTCUSDT",
    )
    guard = FreshnessGuardedQuoteSource(FakeSource(quote), max_age=timedelta(minutes=5))

    result = asyncio.run(guard.quote_for(_intent()))

    assert result is quote
    assert result.source == "binance-public-rest"
    assert result.source_reference == "spot:ticker-price:BTCUSDT"
    assert result.observed_at == fresh_observed_at


def test_freshness_guard_fails_closed_on_stale_quote():
    stale_quote = _quote(observed_at=datetime.now(timezone.utc) - timedelta(hours=1))
    guard = FreshnessGuardedQuoteSource(FakeSource(stale_quote), max_age=timedelta(minutes=5))

    result = asyncio.run(guard.quote_for(_intent()))

    assert result is None


def test_freshness_guard_passes_through_none_from_inner_unchanged():
    guard = FreshnessGuardedQuoteSource(FakeSource(None), max_age=timedelta(minutes=5))

    result = asyncio.run(guard.quote_for(_intent()))

    assert result is None


def test_freshness_guard_rejects_non_positive_max_age():
    try:
        FreshnessGuardedQuoteSource(FakeSource(None), max_age=timedelta(0))
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- MultiAssetQuoteSource: routing, and no regression to crypto ------------

def test_multi_asset_source_routes_crypto_through_the_unmodified_binance_path():
    client = FakeClient(price="60000")
    crypto_provider = BinanceExperiment1QuoteSource(client)
    router = MultiAssetQuoteSource(
        providers={AssetClass.CRYPTO: crypto_provider},
        classify=lambda intent: AssetClass.CRYPTO if intent.symbol.endswith("USDT") else None,
    )

    quote = asyncio.run(router.quote_for(_intent(symbol="BTCUSDT")))

    assert quote.price == Decimal("60000")
    assert quote.source == "binance-public-rest"


def test_multi_asset_source_fails_closed_for_unclassifiable_symbol():
    router = MultiAssetQuoteSource(
        providers={AssetClass.CRYPTO: FakeSource(_quote())},
        classify=lambda intent: None,
    )

    quote = asyncio.run(router.quote_for(_intent(symbol="AAPL")))

    assert quote is None


def test_multi_asset_source_fails_closed_when_class_has_no_registered_provider():
    router = MultiAssetQuoteSource(
        providers={},
        classify=lambda intent: AssetClass.STOCK,
    )

    quote = asyncio.run(router.quote_for(_intent(symbol="AAPL")))

    assert quote is None


def test_multi_asset_source_every_non_crypto_class_is_blocked_evidence_end_to_end():
    def classify(intent: OrderIntent) -> AssetClass | None:
        return {
            "AAPL": AssetClass.STOCK,
            "SPY": AssetClass.ETF,
            "XAUUSD": AssetClass.METAL,
            "US500": AssetClass.US_INDEX,
        }.get(intent.symbol)

    router = MultiAssetQuoteSource(
        providers={
            AssetClass.STOCK: UnavailableQuoteProvider(AssetClass.STOCK),
            AssetClass.ETF: UnavailableQuoteProvider(AssetClass.ETF),
            AssetClass.METAL: UnavailableQuoteProvider(AssetClass.METAL),
            AssetClass.US_INDEX: UnavailableQuoteProvider(AssetClass.US_INDEX),
        },
        classify=classify,
    )

    for symbol in ("AAPL", "SPY", "XAUUSD", "US500"):
        quote = asyncio.run(router.quote_for(_intent(symbol=symbol)))
        assert quote is None


# --- Integration: composes with the real engine + run_market_cycle unchanged -

def test_run_market_cycle_crypto_fills_while_stock_waits_for_evidence(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(_intent(symbol="BTCUSDT", intent_id="crypto-1"))
    engine.submit_intent(_intent(symbol="AAPL", intent_id="stock-1"))

    router = MultiAssetQuoteSource(
        providers={
            AssetClass.CRYPTO: FakeSource(_quote(observed_at=NOW + timedelta(minutes=1))),
            AssetClass.STOCK: UnavailableQuoteProvider(AssetClass.STOCK),
        },
        classify=lambda intent: AssetClass.CRYPTO if intent.symbol.endswith("USDT") else AssetClass.STOCK,
    )

    results = asyncio.run(run_market_cycle(engine, router))
    by_id = {result.intent_id: result.outcome for result in results}

    assert by_id["crypto-1"] == "PAPER_FILLED"
    assert by_id["stock-1"] == "WAITING_EVIDENCE"
    assert engine.pending_intent_ids() == ("stock-1",)
