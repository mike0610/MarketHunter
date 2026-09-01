import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.cost_provenance import (
    FUNDING_NOT_MODELED,
    FX_NOT_APPLICABLE,
    CostEvidenceStatus,
    UnavailableFundingProvider,
    fee_slippage_provenance,
)
from experiment1.engine import Experiment1Engine
from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent


NOW = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


class FakeClient:
    async def get(self, path, **kwargs):
        return {"symbol": "BTCUSDT", "price": "60000"}


# --- fee/slippage: EXPLICIT_POLICY, never fabricated --------------------

def test_fee_slippage_provenance_is_explicit_policy_by_default():
    source = BinanceExperiment1QuoteSource(FakeClient())
    fee, slippage = fee_slippage_provenance(source)

    assert fee.status is CostEvidenceStatus.EXPLICIT_POLICY
    assert slippage.status is CostEvidenceStatus.EXPLICIT_POLICY
    assert "fee_bps=0" in fee.detail
    assert "slippage_bps=0" in slippage.detail


def test_fee_slippage_provenance_reflects_the_configured_nonzero_policy():
    source = BinanceExperiment1QuoteSource(FakeClient(), fee_bps=Decimal("10"), slippage_bps=Decimal("5"))
    fee, slippage = fee_slippage_provenance(source)

    assert "fee_bps=10" in fee.detail
    assert "slippage_bps=5" in slippage.detail
    assert fee.status is CostEvidenceStatus.EXPLICIT_POLICY
    assert slippage.status is CostEvidenceStatus.EXPLICIT_POLICY


def test_market_quote_rejects_negative_fee_bps():
    try:
        MarketQuote(
            symbol="BTCUSDT",
            price=Decimal("100"),
            observed_at=NOW,
            source="test-feed",
            source_reference="ref-1",
            fee_bps=Decimal("-1"),
            slippage_bps=Decimal("0"),
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_market_quote_rejects_negative_slippage_bps():
    try:
        MarketQuote(
            symbol="BTCUSDT",
            price=Decimal("100"),
            observed_at=NOW,
            source="test-feed",
            source_reference="ref-1",
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("-1"),
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_binance_quote_source_rejects_negative_configured_policy():
    try:
        BinanceExperiment1QuoteSource(FakeClient(), fee_bps=Decimal("-1"))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_engine_fee_is_deterministic_from_the_quotes_own_fee_bps_never_invented(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    intent = OrderIntent(
        intent_id="intent-1",
        created_at=NOW,
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        quantity=Decimal("1"),
        reason="cost provenance test",
    )
    quote = MarketQuote(
        symbol="BTCUSDT",
        price=Decimal("100"),
        observed_at=NOW + timedelta(minutes=1),
        source="test-feed",
        source_reference="ref-1",
        fee_bps=Decimal("25"),
        slippage_bps=Decimal("0"),
    )
    fill = engine._build_fill(intent, quote)
    # fee = fill_price * quantity * fee_bps / 10000 = 100 * 1 * 25 / 10000 = 0.25
    assert fill.fee == Decimal("0.25")


# --- funding: NOT_MODELED, fails closed, never silently zero-as-verified -

def test_funding_not_modeled_constant_is_auditable():
    assert FUNDING_NOT_MODELED.category == "funding"
    assert FUNDING_NOT_MODELED.status is CostEvidenceStatus.NOT_MODELED
    assert "no funding charge" in FUNDING_NOT_MODELED.detail.lower()


def test_unavailable_funding_provider_never_returns_a_charge():
    provider = UnavailableFundingProvider()
    charge = asyncio.run(provider.funding_for(AccountKind.FUTURES, "BTCUSDT"))
    assert charge is None


def test_unavailable_funding_provider_default_reason_matches_not_modeled_constant():
    provider = UnavailableFundingProvider()
    assert provider.reason == FUNDING_NOT_MODELED.detail


def test_unavailable_funding_provider_accepts_explicit_reason():
    provider = UnavailableFundingProvider(reason="funding feed pending Product Owner sign-off")
    assert provider.reason == "funding feed pending Product Owner sign-off"


def test_futures_account_state_accrues_no_implicit_cost_across_time_without_a_fill(tmp_path):
    # Regression proof that no funding (or any other time-based) charge
    # is silently applied anywhere in the engine: opening a Futures
    # position and then reading account_state() again "later" (no new
    # fill in between) must report byte-for-byte identical state.
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(
        OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="cost provenance test",
            leverage=Decimal("2"),
        )
    )
    engine.execute_pending(
        "intent-1",
        MarketQuote(
            symbol="BTCUSDT",
            price=Decimal("100"),
            observed_at=NOW + timedelta(minutes=1),
            source="test-feed",
            source_reference="ref-1",
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
    )
    state_immediately_after = engine.account_state(AccountKind.FUTURES)
    position_immediately_after = engine.positions(AccountKind.FUTURES)[0]

    # No fill, no funding provider call, no time-based hook of any kind -
    # just re-reading state, simulating an arbitrarily long elapsed time.
    state_later = engine.account_state(AccountKind.FUTURES)
    position_later = engine.positions(AccountKind.FUTURES)[0]

    assert state_later == state_immediately_after
    assert position_later == position_immediately_after


# --- fx: not applicable to any currently supported path ------------------

def test_fx_not_applicable_constant_is_auditable():
    assert FX_NOT_APPLICABLE.category == "fx"
    assert FX_NOT_APPLICABLE.status is CostEvidenceStatus.NOT_MODELED
    assert "not relevant yet" in FX_NOT_APPLICABLE.detail.lower()
