import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent
from experiment1.runtime import run_market_cycle


class FakeSource:
    def __init__(self, quote):
        self.quote = quote

    async def quote_for(self, intent):
        return self.quote


def _intent(now):
    return OrderIntent(
        intent_id="runtime-1",
        created_at=now,
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        quantity=Decimal("0.01"),
        reason="runtime test",
    )


def test_market_cycle_waits_without_quote(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    engine.submit_intent(_intent(now))

    result = asyncio.run(run_market_cycle(engine, FakeSource(None)))

    assert result[0].outcome == "WAITING_EVIDENCE"
    assert engine.pending_intent_ids() == ("runtime-1",)


def test_market_cycle_paper_fills_from_quote(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    engine.submit_intent(_intent(now))
    quote = MarketQuote(
        symbol="BTCUSDT",
        price=Decimal("60000"),
        observed_at=now + timedelta(minutes=1),
        source="test-feed",
        source_reference="runtime-quote",
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )

    result = asyncio.run(run_market_cycle(engine, FakeSource(quote)))

    assert result[0].outcome == "PAPER_FILLED"
    assert engine.pending_intent_ids() == ()
    assert engine.positions(AccountKind.SPOT)[0].quantity == Decimal("0.01")
