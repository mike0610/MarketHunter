import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.market_data_providers import (
    AssetClass,
    FreshnessGuardedQuoteSource,
    MultiAssetQuoteSource,
    UnavailableQuoteProvider,
)
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent
from experiment1.mtm import run_mtm_cycle


NOW = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, quotes: dict[str, MarketQuote]):
        self.quotes = quotes

    async def quote_for(self, intent):
        return self.quotes.get(intent.symbol)


def _open(engine, intent_id, symbol, price, account=AccountKind.FUTURES, quantity=Decimal("1")):
    engine.submit_intent(
        OrderIntent(
            intent_id=intent_id,
            created_at=NOW,
            account=account,
            action=DecisionAction.LONG,
            symbol=symbol,
            quantity=quantity,
            reason="mtm test",
            leverage=Decimal("2"),
        )
    )
    engine.execute_pending(
        intent_id,
        MarketQuote(
            symbol=symbol,
            price=price,
            observed_at=NOW + timedelta(minutes=1),
            source="test-feed",
            source_reference=f"open-{symbol}",
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
    )


def _quote(symbol, price, observed_at=None, source="test-feed", ref="mtm-quote"):
    return MarketQuote(
        symbol=symbol,
        price=price,
        observed_at=observed_at or datetime.now(timezone.utc),
        source=source,
        source_reference=ref,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


# --- multi-symbol repricing + NAV/unrealized-pnl correctness --------------

def test_run_mtm_cycle_reprices_every_open_symbol_from_fresh_quotes(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))
    _open(engine, "intent-2", "ETHUSDT", Decimal("50"))

    source = FakeSource(
        {
            "BTCUSDT": _quote("BTCUSDT", Decimal("110")),
            "ETHUSDT": _quote("ETHUSDT", Decimal("40")),
        }
    )

    result = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    outcomes = {r.symbol: r.outcome for r in result.symbol_results}
    assert outcomes == {"BTCUSDT": "FRESH_EVIDENCE", "ETHUSDT": "FRESH_EVIDENCE"}
    # unrealized = (110-100)*1 + (40-50)*1 = 0
    assert result.unrealized_pnl == Decimal("0")
    assert result.equity == Decimal("2000")


# --- partial quote availability -------------------------------------------

def test_run_mtm_cycle_reports_waiting_evidence_for_a_symbol_with_no_quote(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))
    _open(engine, "intent-2", "ETHUSDT", Decimal("50"))

    # Only BTCUSDT has a quote this cycle.
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("120"))})

    result = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    outcomes = {r.symbol: r.outcome for r in result.symbol_results}
    assert outcomes == {"BTCUSDT": "FRESH_EVIDENCE", "ETHUSDT": "WAITING_EVIDENCE"}
    # ETHUSDT falls back to cost basis (50) - contributes 0 unrealized.
    # unrealized = (120-100)*1 + 0 = 20.
    assert result.unrealized_pnl == Decimal("20")


# --- stale evidence (via the existing freshness guard) --------------------

def test_run_mtm_cycle_reports_waiting_evidence_for_stale_quote(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))

    stale_quote = _quote("BTCUSDT", Decimal("999"), observed_at=datetime.now(timezone.utc) - timedelta(hours=1))
    guarded = FreshnessGuardedQuoteSource(FakeSource({"BTCUSDT": stale_quote}), max_age=timedelta(minutes=5))

    result = asyncio.run(run_mtm_cycle(engine, guarded, AccountKind.FUTURES))

    assert result.symbol_results[0].outcome == "WAITING_EVIDENCE"
    # Falls back to cost basis - no phantom mark from the stale quote.
    assert result.unrealized_pnl == Decimal("0")


# --- non-crypto BLOCKED-EVIDENCE semantics preserved -----------------------

def test_run_mtm_cycle_preserves_non_crypto_blocked_evidence_semantics(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))
    _open(engine, "intent-2", "AAPL", Decimal("200"))

    router = MultiAssetQuoteSource(
        providers={
            AssetClass.CRYPTO: FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("110"))}),
            AssetClass.STOCK: UnavailableQuoteProvider(AssetClass.STOCK),
        },
        classify=lambda intent: AssetClass.CRYPTO if intent.symbol.endswith("USDT") else AssetClass.STOCK,
    )

    result = asyncio.run(run_mtm_cycle(engine, router, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    outcomes = {r.symbol: r.outcome for r in result.symbol_results}
    assert outcomes == {"BTCUSDT": "FRESH_EVIDENCE", "AAPL": "WAITING_EVIDENCE"}


# --- monitoring only: never a decision, never a fill ------------------------

def test_run_mtm_cycle_never_submits_an_intent_or_creates_a_fill(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))
    pending_before = engine.pending_intent_ids()
    blocked_before = engine.blocked_intent_ids()
    closed_before = engine.closed_trades(AccountKind.FUTURES)

    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("500"))})
    asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    assert engine.pending_intent_ids() == pending_before
    assert engine.blocked_intent_ids() == blocked_before
    assert engine.closed_trades(AccountKind.FUTURES) == closed_before
    # Position quantity/avg/margin are untouched by repricing.
    assert engine.positions(AccountKind.FUTURES)[0].quantity == Decimal("1")
    assert engine.positions(AccountKind.FUTURES)[0].average_price == Decimal("100")


# --- restart-safe / idempotent / "persistently runnable" -------------------

def test_run_mtm_cycle_is_idempotent_across_repeated_calls(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("130"))})

    first = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))
    second = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=10)))
    third = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=15)))

    assert first.equity == second.equity == third.equity
    assert engine.account_state(AccountKind.FUTURES).max_drawdown == Decimal("0")


def test_run_mtm_cycle_is_restart_safe_across_a_fresh_engine_instance(tmp_path):
    db_path = tmp_path / "experiment1.db"
    first_engine = Experiment1Engine(db_path)
    _open(first_engine, "intent-1", "BTCUSDT", Decimal("100"))
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("150"))})
    asyncio.run(run_mtm_cycle(first_engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))
    state_before_restart = first_engine.account_state(AccountKind.FUTURES)

    # Simulate a process restart: a brand-new Engine instance over the
    # same db file continues the cycle with identical results, proving
    # no state lives anywhere but the database itself.
    second_engine = Experiment1Engine(db_path)
    result = asyncio.run(run_mtm_cycle(second_engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=10)))

    assert second_engine.account_state(AccountKind.FUTURES) == state_before_restart
    assert result.equity == state_before_restart.last_equity


# --- lifecycle interaction --------------------------------------------------

def test_run_mtm_cycle_after_a_protective_exit_reprices_only_still_open_symbols(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(
        OrderIntent(
            intent_id="entry-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="mtm lifecycle test",
            leverage=Decimal("2"),
            stop_loss=Decimal("90"),
        )
    )
    engine.execute_pending(
        "entry-1",
        _quote("BTCUSDT", Decimal("100"), observed_at=NOW + timedelta(minutes=1), ref="entry"),
    )
    _open(engine, "intent-2", "ETHUSDT", Decimal("50"))

    # Price drops through the stop-loss - the protective exit cycle
    # closes BTCUSDT entirely.
    exit_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("80"), observed_at=NOW + timedelta(minutes=2), ref="exit")})
    lifecycle_results = asyncio.run(run_protective_exit_cycle(engine, exit_source, ("entry-1",)))
    assert lifecycle_results[0].outcome == "STOP_LOSS"
    open_positions = engine.positions(AccountKind.FUTURES)
    assert len(open_positions) == 1  # only ETHUSDT remains open
    assert open_positions[0].symbol == "ETHUSDT"

    # A subsequent MTM cycle must only reprice the symbol still open -
    # the closed BTCUSDT position must not appear or error.
    mtm_source = FakeSource({"ETHUSDT": _quote("ETHUSDT", Decimal("55"), observed_at=NOW + timedelta(minutes=3))})
    result = asyncio.run(run_mtm_cycle(engine, mtm_source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    assert [r.symbol for r in result.symbol_results] == ["ETHUSDT"]
    assert result.symbol_results[0].outcome == "FRESH_EVIDENCE"


# --- no regression to single-symbol flows -----------------------------------

def test_run_mtm_cycle_with_a_single_open_symbol_matches_prior_single_symbol_behavior(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    _open(engine, "intent-1", "BTCUSDT", Decimal("100"))

    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("115"))})
    result = asyncio.run(run_mtm_cycle(engine, source, AccountKind.FUTURES, now=NOW + timedelta(minutes=5)))

    assert len(result.symbol_results) == 1
    assert result.symbol_results[0].outcome == "FRESH_EVIDENCE"
    # unrealized = (115-100)*1 = 15; equity = 2000 + 15 = 2015.
    assert result.unrealized_pnl == Decimal("15")
    assert result.equity == Decimal("2015")
