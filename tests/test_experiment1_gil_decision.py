import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.gil_decision import (
    decision_from_json,
    decision_id_from,
    decision_to_json,
    drain_gil_decision_inbox,
    ingest_gil_decision,
    intent_id_for,
    run_gil_ingestion_cycle,
    to_order_intent,
)
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    GilDecision,
    IntentStatus,
    MarketQuote,
    SizingIntent,
    SizingMode,
    TriggerType,
)
from experiment1.mtm import MtmCompleteness, run_mtm_cycle
from experiment1.runtime import run_market_cycle


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
        observed_at=observed_at or NOW + timedelta(minutes=1),
        source="test-feed",
        source_reference=ref,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


def _decision(**overrides) -> GilDecision:
    data = dict(
        decision_id="gil-001",
        decided_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="BTCUSDT",
        thesis="breakout confirmed above resistance",
        quantity=Decimal("1"),
        leverage=Decimal("2"),
    )
    data.update(overrides)
    return GilDecision(**data)


@pytest.fixture
def engine(tmp_path: Path) -> Experiment1Engine:
    return Experiment1Engine(tmp_path / "experiment1.db")


# --- deterministic mapping / provenance binding -----------------------------

def test_to_order_intent_maps_every_gil_owned_field_verbatim():
    decision = _decision(stop_loss=Decimal("90"), take_profit=Decimal("120"))
    intent = to_order_intent(decision)

    assert intent.account == decision.account
    assert intent.action == decision.action
    assert intent.symbol == decision.symbol
    assert intent.quantity == decision.quantity
    assert intent.leverage == decision.leverage
    assert intent.stop_loss == decision.stop_loss
    assert intent.take_profit == decision.take_profit
    assert intent.created_at == decision.decided_at
    assert decision.decision_id in intent.reason
    assert decision.thesis in intent.reason


def test_intent_id_and_decision_id_round_trip():
    intent_id = intent_id_for("gil-042")
    assert decision_id_from(intent_id) == "gil-042"
    # An intent never derived from a GIL decision is not misattributed.
    assert decision_id_from("intent-1") is None


def test_intent_id_for_rejects_blank_decision_id():
    with pytest.raises(ValueError):
        intent_id_for("   ")


# --- valid BUY/LONG path -----------------------------------------------------

def test_ingest_gil_long_decision_submits_a_pending_intent(engine):
    decision = _decision()
    status = ingest_gil_decision(engine, decision)

    assert status is IntentStatus.PENDING
    intent_id = intent_id_for(decision.decision_id)
    assert engine.pending_intent_ids() == (intent_id,)
    stored = engine.get_intent(intent_id)
    assert stored.symbol == "BTCUSDT"
    assert stored.leverage == Decimal("2")


def test_ingest_gil_buy_decision_on_spot_submits_pending(engine):
    decision = _decision(
        decision_id="gil-spot-1",
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        leverage=Decimal("1"),
    )
    status = ingest_gil_decision(engine, decision)
    assert status is IntentStatus.PENDING


# --- WAIT/HOLD no-order path -------------------------------------------------

def test_ingest_gil_wait_decision_never_creates_an_executable_order(engine):
    decision = _decision(
        decision_id="gil-wait-1", action=DecisionAction.WAIT, quantity=Decimal("0")
    )
    status = ingest_gil_decision(engine, decision)

    assert status is IntentStatus.NO_ACTION
    assert engine.pending_intent_ids() == ()
    intent_id = intent_id_for(decision.decision_id)
    with pytest.raises(Experiment1Error):
        engine.execute_pending(intent_id, _quote("BTCUSDT", Decimal("100")))


def test_ingest_gil_hold_decision_never_creates_an_executable_order(engine):
    decision = _decision(
        decision_id="gil-hold-1", action=DecisionAction.HOLD, quantity=Decimal("0")
    )
    status = ingest_gil_decision(engine, decision)

    assert status is IntentStatus.NO_ACTION
    assert engine.pending_intent_ids() == ()


# --- blocked risk path -------------------------------------------------------

def test_ingest_gil_decision_blocked_by_existing_leverage_cap_is_persisted_and_raises(engine):
    decision = _decision(decision_id="gil-over-lev", leverage=Decimal("10"))

    with pytest.raises(Experiment1Error) as excinfo:
        ingest_gil_decision(engine, decision)
    assert "3x" in str(excinfo.value)

    intent_id = intent_id_for(decision.decision_id)
    assert intent_id in engine.blocked_intent_ids()
    assert "3x" in engine.intent_status_reason(intent_id)
    # No fill, no position - a rejected GIL decision never trades.
    assert engine.positions(AccountKind.FUTURES) == ()


def test_run_gil_ingestion_cycle_reports_blocked_without_raising(engine):
    decision = _decision(decision_id="gil-over-lev-2", leverage=Decimal("10"))

    results = run_gil_ingestion_cycle(engine, [decision])

    assert len(results) == 1
    assert results[0].outcome == "BLOCKED"
    assert "3x" in results[0].detail
    assert results[0].intent_id in engine.blocked_intent_ids()


def test_run_gil_ingestion_cycle_processes_remaining_decisions_after_one_is_blocked(engine):
    blocked = _decision(decision_id="gil-bad", leverage=Decimal("10"))
    good = _decision(decision_id="gil-good", symbol="ETHUSDT")

    results = run_gil_ingestion_cycle(engine, [blocked, good])

    outcomes = {r.decision_id: r.outcome for r in results}
    assert outcomes == {"gil-bad": "BLOCKED", "gil-good": "PENDING"}


# --- duplicate / replay idempotency ------------------------------------------

def test_ingest_gil_decision_duplicate_resubmission_is_idempotent(engine):
    decision = _decision()

    first = ingest_gil_decision(engine, decision)
    second = ingest_gil_decision(engine, decision)

    assert first == second == IntentStatus.PENDING
    assert len(engine.pending_intent_ids()) == 1


def test_ingest_gil_blocked_decision_duplicate_resubmission_is_idempotent(engine):
    decision = _decision(decision_id="gil-dup-blocked", leverage=Decimal("10"))

    with pytest.raises(Experiment1Error):
        ingest_gil_decision(engine, decision)
    # Resubmitting the identical decision returns the recorded status
    # instead of re-validating or re-raising a fresh rejection.
    status = ingest_gil_decision(engine, decision)

    assert status is IntentStatus.BLOCKED
    assert len(engine.blocked_intent_ids()) == 1


# --- restart preserves the binding -------------------------------------------

def test_gil_decision_binding_survives_a_process_restart(tmp_path):
    db_path = tmp_path / "experiment1.db"
    first_engine = Experiment1Engine(db_path)
    decision = _decision()
    ingest_gil_decision(first_engine, decision)

    second_engine = Experiment1Engine(db_path)
    intent_id = intent_id_for(decision.decision_id)
    assert second_engine.pending_intent_ids() == (intent_id,)
    assert decision_id_from(intent_id) == decision.decision_id

    # Replaying the same decision through the restarted engine instance
    # is still idempotent - no duplicate intent.
    status = ingest_gil_decision(second_engine, decision)
    assert status is IntentStatus.PENDING
    assert len(second_engine.pending_intent_ids()) == 1


# --- full lifecycle integration: no parallel execution path -----------------

def test_gil_decision_flows_through_the_existing_paper_lifecycle_end_to_end(engine):
    decision = _decision(
        decision_id="gil-lifecycle-1",
        stop_loss=Decimal("90"),
    )
    status = ingest_gil_decision(engine, decision)
    assert status is IntentStatus.PENDING

    # Fresh evidence + paper fill, via the existing, unmodified runtime cycle.
    fill_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"))})
    cycle_results = asyncio.run(run_market_cycle(engine, fill_source))
    assert cycle_results[0].outcome == "PAPER_FILLED"

    positions = engine.positions(AccountKind.FUTURES)
    assert len(positions) == 1
    assert positions[0].symbol == "BTCUSDT"

    # Monitoring/SL, via the existing, unmodified protective-exit cycle.
    exit_source = FakeSource(
        {"BTCUSDT": _quote("BTCUSDT", Decimal("85"), observed_at=NOW + timedelta(minutes=2), ref="exit")}
    )
    intent_id = intent_id_for(decision.decision_id)
    lifecycle_results = asyncio.run(run_protective_exit_cycle(engine, exit_source, (intent_id,)))
    assert lifecycle_results[0].outcome == "STOP_LOSS"

    # Exit/closed result/statistics, via the existing, unmodified closed-trades view.
    trades = engine.closed_trades(AccountKind.FUTURES)
    assert len(trades) == 1
    assert trades[0].symbol == "BTCUSDT"
    assert engine.positions(AccountKind.FUTURES) == ()


# --- independent ledgers and MTM completeness preserved (PR #76) ------------

def test_gil_originated_positions_preserve_independent_ledgers_and_mtm_completeness(engine):
    futures_decision = _decision(decision_id="gil-futures-1")
    spot_decision = _decision(
        decision_id="gil-spot-2",
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="ETHUSDT",
        leverage=Decimal("1"),
    )
    ingest_gil_decision(engine, futures_decision)
    ingest_gil_decision(engine, spot_decision)

    fill_source = FakeSource(
        {
            "BTCUSDT": _quote("BTCUSDT", Decimal("100"), ref="futures-fill"),
            "ETHUSDT": _quote("ETHUSDT", Decimal("50"), ref="spot-fill"),
        }
    )
    asyncio.run(run_market_cycle(engine, fill_source))

    # FUTURES gets a fresh mark this cycle - fully evidenced. SPOT gets
    # none - falls back to cost basis, and must be reported as such.
    mtm_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("110"), observed_at=NOW + timedelta(minutes=5))})
    futures_mtm = asyncio.run(run_mtm_cycle(engine, mtm_source, AccountKind.FUTURES, now=NOW + timedelta(minutes=6)))
    spot_mtm = asyncio.run(run_mtm_cycle(engine, mtm_source, AccountKind.SPOT, now=NOW + timedelta(minutes=6)))

    assert futures_mtm.completeness is MtmCompleteness.FULLY_FRESH_EVIDENCE
    assert spot_mtm.completeness is MtmCompleteness.PARTIAL_EVIDENCE_FALLBACK
    # Each account's positions are its own - no cross-contamination.
    assert [p.symbol for p in engine.positions(AccountKind.FUTURES)] == ["BTCUSDT"]
    assert [p.symbol for p in engine.positions(AccountKind.SPOT)] == ["ETHUSDT"]


# --- decision_to_json / decision_from_json round trip ------------------------

def test_decision_to_json_round_trips_every_field():
    decision = _decision(stop_loss=Decimal("90"), take_profit=Decimal("120"), execution_condition="daily close > 105")
    restored = decision_from_json(decision_to_json(decision))
    assert restored == decision


def test_decision_to_json_round_trips_a_decision_with_no_optional_fields():
    decision = _decision(decision_id="gil-minimal", stop_loss=None, take_profit=None, execution_condition=None)
    restored = decision_from_json(decision_to_json(decision))
    assert restored == decision


def test_decision_to_json_is_deterministic_for_the_same_decision():
    decision = _decision()
    assert decision_to_json(decision) == decision_to_json(decision)


# --- drain_gil_decision_inbox: the durable-inbox processing cycle -----------

def _seed(engine, decision: GilDecision) -> None:
    engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))


def test_drain_processes_a_valid_long_decision_to_pending(engine):
    decision = _decision()
    _seed(engine, decision)

    results = asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    assert len(results) == 1
    assert results[0].outcome == "PENDING"
    intent_id = intent_id_for(decision.decision_id)
    assert engine.pending_intent_ids() == (intent_id,)
    record = engine.gil_decision_inbox_status(decision.decision_id)
    assert record.status.value == "PROCESSED"
    assert record.outcome == "PENDING"
    assert record.intent_id == intent_id


def test_drain_processes_a_wait_decision_to_no_action_never_executable(engine):
    decision = _decision(decision_id="gil-wait", action=DecisionAction.WAIT, quantity=Decimal("0"))
    _seed(engine, decision)

    results = asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    assert results[0].outcome == "NO_ACTION"
    assert engine.pending_intent_ids() == ()
    with pytest.raises(Experiment1Error):
        engine.execute_pending(intent_id_for(decision.decision_id), _quote("BTCUSDT", Decimal("100")))


def test_drain_marks_a_conditional_decision_waiting_evidence_without_submitting_an_intent(engine):
    decision = _decision(decision_id="gil-conditional", execution_condition="only if daily close confirms above 105")
    _seed(engine, decision)

    results = asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    assert results[0].outcome == "WAITING_EVIDENCE"
    assert "no evaluator" in results[0].detail.lower()
    # Never submitted - not pending, not blocked, no intent exists at all.
    assert engine.pending_intent_ids() == ()
    assert engine.blocked_intent_ids() == ()
    with pytest.raises(Experiment1Error):
        engine.get_intent(intent_id_for(decision.decision_id))

    record = engine.gil_decision_inbox_status(decision.decision_id)
    assert record.outcome == "WAITING_EVIDENCE"
    assert record.status.value == "PROCESSED"


def test_drain_marks_a_risk_blocked_decision_blocked_with_reason(engine):
    decision = _decision(decision_id="gil-over-leverage", leverage=Decimal("10"))
    _seed(engine, decision)

    results = asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    assert results[0].outcome == "BLOCKED"
    assert "3x" in results[0].detail
    record = engine.gil_decision_inbox_status(decision.decision_id)
    assert record.outcome == "BLOCKED"
    assert "3x" in record.outcome_reason
    intent_id = intent_id_for(decision.decision_id)
    assert intent_id in engine.blocked_intent_ids()
    assert engine.positions(AccountKind.FUTURES) == ()


def test_drain_never_reprocesses_an_already_processed_decision(engine):
    decision = _decision()
    _seed(engine, decision)
    asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    # No new envelope arrived - a second drain cycle must find nothing
    # PENDING_DRAIN and must not resubmit/duplicate anything.
    results = asyncio.run(drain_gil_decision_inbox(engine, FakeSource({})))

    assert results == ()
    assert len(engine.pending_intent_ids()) == 1


def test_drain_is_restart_safe_across_a_fresh_engine_instance(tmp_path):
    db_path = tmp_path / "experiment1.db"
    first_engine = Experiment1Engine(db_path)
    decision = _decision()
    _seed(first_engine, decision)
    asyncio.run(drain_gil_decision_inbox(first_engine, FakeSource({})))

    second_engine = Experiment1Engine(db_path)
    record = second_engine.gil_decision_inbox_status(decision.decision_id)
    assert record.status.value == "PROCESSED"
    assert record.outcome == "PENDING"

    # Nothing left to drain, and re-seeding the identical decision is
    # still idempotent on the restarted instance.
    assert asyncio.run(drain_gil_decision_inbox(second_engine, FakeSource({}))) == ()
    second_engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))
    assert len(second_engine.pending_intent_ids()) == 1


# --- structured ExecutionTrigger / SizingIntent model validation ------------

def test_gil_decision_requires_exactly_one_of_quantity_or_sizing():
    with pytest.raises(ValueError):
        _decision(sizing=SizingIntent(mode=SizingMode.EXACT_QUANTITY, exact_quantity=Decimal("1")))
    with pytest.raises(ValueError):
        _decision(quantity=None)


def test_risk_budget_from_stop_sizing_requires_stop_loss_on_the_decision():
    with pytest.raises(ValueError):
        _decision(
            decision_id="gil-missing-stop",
            quantity=None,
            stop_loss=None,
            sizing=SizingIntent(mode=SizingMode.RISK_BUDGET_FROM_STOP, risk_budget_amount=Decimal("10")),
        )


def test_execution_trigger_immediate_rejects_a_price():
    with pytest.raises(ValueError):
        ExecutionTrigger(trigger_type=TriggerType.IMMEDIATE, trigger_price=Decimal("100"))


def test_execution_trigger_at_or_above_requires_a_positive_trigger_price():
    with pytest.raises(ValueError):
        ExecutionTrigger(trigger_type=TriggerType.PRICE_AT_OR_ABOVE)


def test_execution_trigger_price_in_range_requires_low_less_than_high():
    with pytest.raises(ValueError):
        ExecutionTrigger(
            trigger_type=TriggerType.PRICE_IN_RANGE,
            trigger_price_low=Decimal("120"),
            trigger_price_high=Decimal("115"),
        )


def test_sizing_intent_rejects_a_mismatched_field():
    with pytest.raises(ValueError):
        SizingIntent(mode=SizingMode.EXACT_QUANTITY, max_notional=Decimal("500"))


# --- drain: structured trigger + sizing evaluation --------------------------

class _ExplodingSource:
    """A quote source that fails the test if it is ever consulted."""

    async def quote_for(self, intent):
        raise AssertionError("quote_source should never be called for an immediate, exact-quantity decision")


def test_immediate_exact_quantity_decision_never_fetches_a_quote(engine):
    # The dispatch's own required scenario: "immediate exact-quantity
    # BUY/LONG -> existing canonical path unchanged" - proven
    # structurally, not just behaviorally: no evidence is ever fetched.
    decision = _decision()
    _seed(engine, decision)

    results = asyncio.run(drain_gil_decision_inbox(engine, _ExplodingSource()))

    assert results[0].outcome == "PENDING"


def test_threshold_unmet_produces_waiting_evidence_and_no_executable_intent(engine):
    decision = _decision(
        decision_id="gil-threshold",
        trigger=ExecutionTrigger(trigger_type=TriggerType.PRICE_AT_OR_ABOVE, trigger_price=Decimal("65000")),
    )
    _seed(engine, decision)
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("60000"))})

    results = asyncio.run(drain_gil_decision_inbox(engine, source))

    assert results[0].outcome == "WAITING_EVIDENCE"
    assert "not yet satisfied" in results[0].detail
    assert engine.pending_intent_ids() == ()
    assert engine.blocked_intent_ids() == ()
    with pytest.raises(Experiment1Error):
        engine.get_intent(intent_id_for("gil-threshold"))


def test_missing_quote_produces_waiting_evidence_and_stays_watchable(engine):
    decision = _decision(
        decision_id="gil-missing-quote",
        trigger=ExecutionTrigger(trigger_type=TriggerType.PRICE_AT_OR_ABOVE, trigger_price=Decimal("65000")),
    )
    _seed(engine, decision)
    empty_source = FakeSource({})  # no quote at all for BTCUSDT

    results = asyncio.run(drain_gil_decision_inbox(engine, empty_source))

    assert results[0].outcome == "WAITING_EVIDENCE"
    assert "no fresh quote" in results[0].detail
    record = engine.gil_decision_inbox_status("gil-missing-quote")
    assert record.status.value == "PENDING_DRAIN"  # still watchable, not terminal
    assert engine.pending_intent_ids() == ()


def test_price_range_and_max_notional_decision_remains_watchable_then_submits_exactly_once(engine):
    # The dispatch's own canonical example: a CROX-style buy-zone plus a
    # max-notional tranche.
    decision = _decision(
        decision_id="gil-buy-zone",
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        leverage=Decimal("1"),
        quantity=None,
        trigger=ExecutionTrigger(
            trigger_type=TriggerType.PRICE_IN_RANGE,
            trigger_price_low=Decimal("115"),
            trigger_price_high=Decimal("120"),
        ),
        sizing=SizingIntent(mode=SizingMode.MAX_NOTIONAL, max_notional=Decimal("500")),
    )
    _seed(engine, decision)

    # Cycle 1: price outside the range - stays watchable, no intent yet.
    outside_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("108"))})
    first = asyncio.run(drain_gil_decision_inbox(engine, outside_source))
    assert first[0].outcome == "WAITING_EVIDENCE"
    assert engine.gil_decision_inbox_status("gil-buy-zone").status.value == "PENDING_DRAIN"
    assert engine.pending_intent_ids() == ()

    # Cycle 2: price inside the range - derives quantity from evidence,
    # submits exactly once.
    inside_source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("117"))})
    second = asyncio.run(drain_gil_decision_inbox(engine, inside_source))
    assert second[0].outcome == "PENDING"
    intent = engine.get_intent(intent_id_for("gil-buy-zone"))
    assert intent.quantity == Decimal("500") / Decimal("117")
    assert engine.gil_decision_inbox_status("gil-buy-zone").status.value == "PROCESSED"

    # Cycle 3: already resolved - must not resubmit or duplicate.
    third = asyncio.run(drain_gil_decision_inbox(engine, inside_source))
    assert third == ()
    assert len(engine.pending_intent_ids()) == 1


def test_risk_budget_from_stop_sizing_derives_quantity_from_evidence_and_stop_distance(engine):
    # The dispatch's own canonical example: BTC Futures sized from a
    # max planned loss and the decision's own stop distance.
    decision = _decision(
        decision_id="gil-risk-budget",
        stop_loss=Decimal("95"),
        quantity=None,
        sizing=SizingIntent(mode=SizingMode.RISK_BUDGET_FROM_STOP, risk_budget_amount=Decimal("10")),
    )
    _seed(engine, decision)
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"))})

    results = asyncio.run(drain_gil_decision_inbox(engine, source))

    assert results[0].outcome == "PENDING"
    intent = engine.get_intent(intent_id_for("gil-risk-budget"))
    # distance = |100 - 95| = 5; quantity = risk_budget(10) / distance(5) = 2.
    assert intent.quantity == Decimal("2")


def test_risk_budget_from_stop_with_zero_distance_stays_watchable_never_guessed(engine):
    decision = _decision(
        decision_id="gil-zero-distance",
        stop_loss=Decimal("100"),
        quantity=None,
        sizing=SizingIntent(mode=SizingMode.RISK_BUDGET_FROM_STOP, risk_budget_amount=Decimal("10")),
    )
    _seed(engine, decision)
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"))})  # price == stop_loss

    results = asyncio.run(drain_gil_decision_inbox(engine, source))

    assert results[0].outcome == "WAITING_EVIDENCE"
    assert "zero stop distance" in results[0].detail
    assert engine.gil_decision_inbox_status("gil-zero-distance").status.value == "PENDING_DRAIN"
    assert engine.pending_intent_ids() == ()


def test_trigger_and_sizing_decision_replay_restart_remains_idempotent(tmp_path):
    db_path = tmp_path / "experiment1.db"
    first_engine = Experiment1Engine(db_path)
    decision = _decision(
        decision_id="gil-replay-restart",
        quantity=None,
        trigger=ExecutionTrigger(trigger_type=TriggerType.PRICE_AT_OR_ABOVE, trigger_price=Decimal("100")),
        sizing=SizingIntent(mode=SizingMode.MAX_NOTIONAL, max_notional=Decimal("300")),
    )
    _seed(first_engine, decision)
    source = FakeSource({"BTCUSDT": _quote("BTCUSDT", Decimal("100"))})
    asyncio.run(drain_gil_decision_inbox(first_engine, source))
    state_before_restart = first_engine.account_state(AccountKind.FUTURES)

    # Restart: a fresh Engine instance over the same db file.
    second_engine = Experiment1Engine(db_path)
    assert second_engine.account_state(AccountKind.FUTURES) == state_before_restart
    assert len(second_engine.positions(AccountKind.FUTURES)) == 0  # PENDING, not yet filled

    # Replay: resubmitting the identical decision again is a no-op.
    second_engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))
    assert asyncio.run(drain_gil_decision_inbox(second_engine, source)) == ()
    assert len(second_engine.pending_intent_ids()) == 1
