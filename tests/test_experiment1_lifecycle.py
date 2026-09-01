from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent


class StaticQuoteSource:
    def __init__(self, quote):
        self.quote = quote

    async def quote_for(self, intent):
        return self.quote


def _quote(symbol: str, price: str, now):
    return MarketQuote(
        symbol=symbol,
        price=Decimal(price),
        observed_at=now + timedelta(minutes=2),
        source="test-feed",
        source_reference=f"quote:{symbol}:{price}",
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    )


def _open_spot(engine, now):
    entry = OrderIntent(
        intent_id="spot-entry",
        created_at=now,
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        quantity=Decimal("0.01"),
        reason="entry",
        stop_loss=Decimal("59000"),
        take_profit=Decimal("62000"),
    )
    engine.submit_intent(entry)
    engine.execute_pending("spot-entry", _quote("BTCUSDT", "60000", now))
    return entry


@pytest.mark.anyio
async def test_spot_take_profit_closes_position(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    _open_spot(engine, now)

    result = await run_protective_exit_cycle(
        engine,
        StaticQuoteSource(_quote("BTCUSDT", "62000", now)),
        ("spot-entry",),
    )

    assert result[0].outcome == "TAKE_PROFIT"
    assert engine.positions(AccountKind.SPOT) == ()


@pytest.mark.anyio
async def test_no_trigger_keeps_position_active(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    _open_spot(engine, now)

    result = await run_protective_exit_cycle(
        engine,
        StaticQuoteSource(_quote("BTCUSDT", "60500", now)),
        ("spot-entry",),
    )

    assert result[0].outcome == "ACTIVE"
    assert engine.positions(AccountKind.SPOT)[0].quantity == Decimal("0.01")


@pytest.mark.anyio
async def test_futures_short_stop_loss_closes_position(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    entry = OrderIntent(
        intent_id="short-entry",
        created_at=now,
        account=AccountKind.FUTURES,
        action=DecisionAction.SHORT,
        symbol="ETHUSDT",
        quantity=Decimal("1"),
        reason="short",
        leverage=Decimal("2"),
        stop_loss=Decimal("3100"),
        take_profit=Decimal("2800"),
    )
    engine.submit_intent(entry)
    engine.execute_pending("short-entry", _quote("ETHUSDT", "3000", now))

    result = await run_protective_exit_cycle(
        engine,
        StaticQuoteSource(_quote("ETHUSDT", "3100", now)),
        ("short-entry",),
    )

    assert result[0].outcome == "STOP_LOSS"
    assert engine.positions(AccountKind.FUTURES) == ()
