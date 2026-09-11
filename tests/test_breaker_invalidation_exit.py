from datetime import datetime, timezone

from models.candle import Candle
from models.signal import Signal
from research.manager import ResearchManager
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.monitor import TradeMonitor


class _RepositoryStub:
    def __init__(self) -> None:
        self.saved = []

    def has_open_direction_trade(self, **kwargs):
        return False

    def count_open_trades_for_symbol(self, **kwargs):
        return 0

    def count_open_trades(self):
        return 0

    def save(self, trade):
        self.saved.append(trade)


def _candle(*, close: float, low: float, high: float) -> Candle:
    opened = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 10, 10, 59, tzinfo=timezone.utc)
    return Candle(
        open_time=opened,
        open=105.0,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        close_time=closed,
        quote_volume=1.0,
        trades=1,
        taker_buy_base_volume=0.5,
        taker_buy_quote_volume=0.5,
    )


def _active_breaker_trade(*, direction: str = "LONG") -> ResearchTrade:
    is_long = direction == "LONG"
    return ResearchTrade(
        id=f"breaker-{direction.lower()}",
        signal_id=None,
        symbol="TESTUSDT",
        market="futures",
        timeframe="1h",
        strategy="Breaker",
        direction=direction,
        entry_price=105.0,
        stop_loss=90.0 if is_long else 120.0,
        take_profit=130.0 if is_long else 80.0,
        probability=60,
        score=90.0,
        mtf_context={
            "breaker_zone_low": 100.0,
            "breaker_zone_high": 110.0,
            "breaker_invalidation_price": 100.0 if is_long else 110.0,
            "breaker_invalidation_rule": (
                "close_below" if is_long else "close_above"
            ),
        },
        status=TradeStatus.ACTIVE,
        opened_at=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc),
    )


def test_manager_preserves_breaker_invalidation_context():
    repository = _RepositoryStub()
    manager = ResearchManager(repository)
    signal = Signal(
        symbol="TESTUSDT",
        market="futures",
        timeframe="1h",
        strategy="Breaker",
        direction="LONG",
        score=90.0,
        metadata={
            "breaker_zone_low": 100.0,
            "breaker_zone_high": 110.0,
            "breaker_invalidation_price": 100.0,
            "breaker_invalidation_rule": "close_below",
        },
    )

    result = manager.create_from_signal(
        signal=signal,
        entry_price=105.0,
        stop_loss=90.0,
        take_profit=130.0,
        probability=60,
    )

    assert result.created
    assert result.trade is not None
    assert result.trade.mtf_context["breaker_invalidation_price"] == 100.0
    assert result.trade.mtf_context["breaker_invalidation_rule"] == "close_below"


def test_breaker_long_exits_on_confirmed_zone_invalidation_before_fail_safe_stop():
    repository = _RepositoryStub()
    monitor = TradeMonitor(repository)
    trade = _active_breaker_trade(direction="LONG")

    result = monitor.update_with_candle(
        trade,
        _candle(close=98.0, low=95.0, high=108.0),
    )

    assert result.status == TradeStatus.CLOSED
    assert result.close_reason == "BREAKER_INVALIDATED"
    assert result.profit_percent == ((98.0 - 105.0) / 105.0) * 100


def test_breaker_long_wick_below_zone_does_not_invalidate_without_close_below():
    repository = _RepositoryStub()
    monitor = TradeMonitor(repository)
    trade = _active_breaker_trade(direction="LONG")

    result = monitor.update_with_candle(
        trade,
        _candle(close=102.0, low=95.0, high=108.0),
    )

    assert result.status == TradeStatus.ACTIVE
    assert result.close_reason is None


def test_breaker_short_exits_when_candle_closes_above_bearish_zone():
    repository = _RepositoryStub()
    monitor = TradeMonitor(repository)
    trade = _active_breaker_trade(direction="SHORT")

    result = monitor.update_with_candle(
        trade,
        _candle(close=112.0, low=102.0, high=115.0),
    )

    assert result.status == TradeStatus.CLOSED
    assert result.close_reason == "BREAKER_INVALIDATED"
    assert result.profit_percent == ((105.0 - 112.0) / 105.0) * 100


def test_breaker_short_wick_above_zone_does_not_invalidate_without_close_above():
    repository = _RepositoryStub()
    monitor = TradeMonitor(repository)
    trade = _active_breaker_trade(direction="SHORT")

    result = monitor.update_with_candle(
        trade,
        _candle(close=108.0, low=102.0, high=115.0),
    )

    assert result.status == TradeStatus.ACTIVE
    assert result.close_reason is None
