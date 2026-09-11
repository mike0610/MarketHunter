import asyncio
from types import SimpleNamespace

from models.breaker_block import BreakerBlock
from strategies.breaker import BreakerStrategy


class _BreakerStub:
    def __init__(
        self,
        *,
        bullish: BreakerBlock | None = None,
        bearish: BreakerBlock | None = None,
        inside_bullish: bool = False,
        inside_bearish: bool = False,
    ) -> None:
        self._bullish = bullish
        self._bearish = bearish
        self._inside_bullish = inside_bullish
        self._inside_bearish = inside_bearish

    def latest_bullish(self, snapshot):
        return self._bullish

    def latest_bearish(self, snapshot):
        return self._bearish

    def inside_bullish(self, snapshot):
        return self._inside_bullish

    def inside_bearish(self, snapshot):
        return self._inside_bearish


class _FalseFilter:
    def bullish(self, snapshot):
        return False

    def bearish(self, snapshot):
        return False


class _VolumeStub(_FalseFilter):
    def ratio(self, snapshot):
        return 1.0


def _block(*, bullish: bool) -> BreakerBlock:
    return BreakerBlock(
        bullish=bullish,
        low=100.0,
        high=110.0,
        created_index=1,
        break_index=2,
    )


def _strategy(*, breaker: _BreakerStub) -> BreakerStrategy:
    strategy = BreakerStrategy()
    strategy.breaker = breaker
    strategy.trend = _FalseFilter()
    strategy.volume = _VolumeStub()
    return strategy


def test_breaker_rejects_long_signal_when_price_is_outside_zone():
    strategy = _strategy(
        breaker=_BreakerStub(
            bullish=_block(bullish=True),
            inside_bullish=False,
        )
    )
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is None


def test_breaker_emits_long_signal_when_price_is_inside_zone():
    strategy = _strategy(
        breaker=_BreakerStub(
            bullish=_block(bullish=True),
            inside_bullish=True,
        )
    )
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is not None
    assert signal.direction == "LONG"
    assert signal.metadata["breaker_invalidation_price"] == 100.0
    assert signal.metadata["breaker_invalidation_rule"] == "close_below"
    assert "Price inside breaker" in signal.reasons


def test_breaker_rejects_short_signal_when_price_is_outside_zone():
    strategy = _strategy(
        breaker=_BreakerStub(
            bearish=_block(bullish=False),
            inside_bearish=False,
        )
    )
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is None


def test_breaker_emits_short_signal_when_price_is_inside_zone():
    strategy = _strategy(
        breaker=_BreakerStub(
            bearish=_block(bullish=False),
            inside_bearish=True,
        )
    )
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is not None
    assert signal.direction == "SHORT"
    assert signal.metadata["breaker_invalidation_price"] == 110.0
    assert signal.metadata["breaker_invalidation_rule"] == "close_above"
    assert "Bearish Breaker Block" in signal.reasons
    assert "Price inside breaker" in signal.reasons
