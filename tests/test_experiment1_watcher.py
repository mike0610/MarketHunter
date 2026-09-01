from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent
from experiment1.watcher import Experiment1Watcher


def _intent(now):
    return OrderIntent(
        intent_id="watch-1",
        created_at=now,
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        quantity=Decimal("0.01"),
        reason="Experiment 1 test decision",
    )


def test_watcher_leaves_intent_pending_without_market_evidence(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    engine.submit_intent(_intent(now))

    result = Experiment1Watcher(engine, lambda symbol: None).run_once()

    assert result[0].outcome == "WAITING_EVIDENCE"
    assert engine.pending_intent_ids() == ("watch-1",)


def test_watcher_paper_fills_only_from_supplied_evidence(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    engine.submit_intent(_intent(now))
    quote = MarketQuote(
        symbol="BTCUSDT",
        price=Decimal("60000"),
        observed_at=now + timedelta(minutes=1),
        source="test-feed",
        source_reference="quote-1",
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )

    result = Experiment1Watcher(engine, lambda symbol: quote).run_once()

    assert result[0].outcome == "PAPER_FILLED"
    assert result[0].fill.reference_price == Decimal("60000")
    assert engine.pending_intent_ids() == ()
    assert engine.positions(AccountKind.SPOT)[0].quantity == Decimal("0.01")
