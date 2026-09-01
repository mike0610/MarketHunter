import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.engine import Experiment1Engine
from experiment1.market_data_providers import AssetClass, MultiAssetQuoteSource
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent
from experiment1.mtm import MtmCompleteness
from tools.experiment1_runtime.runtime import (
    _classify,
    build_quote_source,
    run_experiment1_cycle,
)


NOW = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, quotes: dict[str, MarketQuote]):
        self.quotes = quotes

    async def quote_for(self, intent):
        return self.quotes.get(intent.symbol)


def _quote(symbol, price, observed_at=None, ref="quote-1"):
    return MarketQuote(
        symbol=symbol,
        price=price,
        observed_at=observed_at or datetime.now(timezone.utc),
        source="test-feed",
        source_reference=ref,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


# --- classify / quote-source construction (no network I/O) ------------------

def test_classify_recognizes_only_usdt_suffixed_symbols_as_crypto():
    intent = OrderIntent(
        intent_id="i-1",
        created_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="BTCUSDT",
        quantity=Decimal("1"),
        reason="test",
    )
    assert _classify(intent) is AssetClass.CRYPTO

    stock_intent = OrderIntent(
        intent_id="i-2",
        created_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="AAPL",
        quantity=Decimal("1"),
        reason="test",
    )
    assert _classify(stock_intent) is None


def test_build_quote_source_only_registers_crypto():
    source = build_quote_source()
    assert isinstance(source, MultiAssetQuoteSource)
    assert set(source.providers.keys()) == {AssetClass.CRYPTO}


def test_build_quote_source_fails_closed_for_non_crypto_without_any_network_call(tmp_path):
    # AAPL is unclassifiable -> MultiAssetQuoteSource returns None before
    # ever consulting a provider, so this is safe to actually await.
    source = build_quote_source()
    intent = OrderIntent(
        intent_id="i-3",
        created_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="AAPL",
        quantity=Decimal("1"),
        reason="test",
    )
    quote = asyncio.run(source.quote_for(intent))
    assert quote is None


# --- orchestration: wires the four existing cycles correctly ----------------

def test_run_experiment1_cycle_fills_a_pending_crypto_intent_and_reprices_it(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(
        OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="scheduler test",
            leverage=Decimal("2"),
        )
    )
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"), observed_at=NOW + timedelta(minutes=1))})

    summary = asyncio.run(run_experiment1_cycle(engine, source))

    assert summary.market_fill_results[0].outcome == "PAPER_FILLED"
    assert engine.positions(AccountKind.FUTURES)[0].symbol == "BTCUSDT"
    futures_mtm = next(r for r in summary.mtm_results if r.account == AccountKind.FUTURES)
    assert futures_mtm.completeness is MtmCompleteness.FULLY_FRESH_EVIDENCE


def test_run_experiment1_cycle_gil_ingestion_step_is_a_safe_no_op(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    source = FakeSource({})

    summary = asyncio.run(run_experiment1_cycle(engine, source))

    # No real GIL-decision transport exists - an empty batch every cycle,
    # never a manufactured decision to "prove" the step ran.
    assert summary.gil_ingestion_results == ()


def test_run_experiment1_cycle_reprices_every_canonical_account(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    summary = asyncio.run(run_experiment1_cycle(engine, FakeSource({})))

    accounts = {r.account for r in summary.mtm_results}
    assert accounts == {
        AccountKind.INVESTMENTS_DEFENSIVE,
        AccountKind.INVESTMENTS_BALANCED,
        AccountKind.INVESTMENTS_GROWTH,
        AccountKind.SPOT,
        AccountKind.FUTURES,
    }


def test_run_experiment1_cycle_triggers_a_protective_exit_on_a_previously_filled_entry(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(
        OrderIntent(
            intent_id="entry-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="scheduler lifecycle test",
            leverage=Decimal("2"),
            stop_loss=Decimal("90"),
        )
    )
    # First cycle: fills the entry at 100.
    fill_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"), observed_at=NOW + timedelta(minutes=1))})
    first = asyncio.run(run_experiment1_cycle(engine, fill_source))
    assert first.market_fill_results[0].outcome == "PAPER_FILLED"
    assert len(engine.positions(AccountKind.FUTURES)) == 1

    # Second cycle: price has dropped through the stop-loss - the
    # already-FILLED entry (discovered via filled_intent_ids(), not
    # re-submitted) is re-checked and exited, with no new intent needed.
    exit_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("80"), observed_at=NOW + timedelta(minutes=5))})
    second = asyncio.run(run_experiment1_cycle(engine, exit_source))

    assert second.protective_exit_results[0].outcome == "STOP_LOSS"
    assert engine.positions(AccountKind.FUTURES) == ()
    assert len(engine.closed_trades(AccountKind.FUTURES)) == 1


def test_run_experiment1_cycle_is_idempotent_when_rerun_with_no_new_evidence(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    engine.submit_intent(
        OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="idempotency test",
            leverage=Decimal("2"),
        )
    )
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"), observed_at=NOW + timedelta(minutes=1))})

    asyncio.run(run_experiment1_cycle(engine, source))
    state_after_first = engine.account_state(AccountKind.FUTURES)

    # Rerunning with the same source and no new pending intents must not
    # duplicate the fill, the position, or any closed-trade row.
    asyncio.run(run_experiment1_cycle(engine, source))
    state_after_second = engine.account_state(AccountKind.FUTURES)

    assert state_after_first == state_after_second
    assert len(engine.positions(AccountKind.FUTURES)) == 1
    assert engine.closed_trades(AccountKind.FUTURES) == ()


def test_run_experiment1_cycle_is_restart_safe_across_a_fresh_engine_instance(tmp_path):
    db_path = tmp_path / "experiment1.db"
    first_engine = Experiment1Engine(db_path)
    first_engine.submit_intent(
        OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            reason="restart test",
            leverage=Decimal("2"),
        )
    )
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"), observed_at=NOW + timedelta(minutes=1))})
    asyncio.run(run_experiment1_cycle(first_engine, source))
    state_before_restart = first_engine.account_state(AccountKind.FUTURES)

    # A fresh Engine instance over the same db file - simulating a
    # service restart - must reproduce the identical state and not
    # duplicate anything on its own next cycle.
    second_engine = Experiment1Engine(db_path)
    asyncio.run(run_experiment1_cycle(second_engine, source))

    assert second_engine.account_state(AccountKind.FUTURES) == state_before_restart
    assert len(second_engine.positions(AccountKind.FUTURES)) == 1
