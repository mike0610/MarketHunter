import asyncio
from types import SimpleNamespace

from models.breaker_block import BreakerBlock
from strategies.breaker import BreakerStrategy


class _BreakerStub:
    def __init__(self, block: BreakerBlock, inside: bool) -> None:
        self._block = block
        self._inside = inside

    def latest_bullish(self, snapshot):
        return self._block

    def inside(self, snapshot):
        return self._inside


class _FalseFilter:
    def bullish(self, snapshot):
        return False


class _VolumeStub(_FalseFilter):
    def ratio(self, snapshot):
        return 1.0


def _strategy(*, inside: bool) -> BreakerStrategy:
    strategy = BreakerStrategy()
    strategy.breaker = _BreakerStub(
        BreakerBlock(
            bullish=True,
            low=100.0,
            high=110.0,
            created_index=1,
            break_index=2,
        ),
        inside=inside,
    )
    strategy.trend = _FalseFilter()
    strategy.volume = _VolumeStub()
    return strategy


def test_breaker_rejects_long_signal_when_price_is_outside_zone():
    strategy = _strategy(inside=False)
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is None


def test_breaker_emits_long_signal_when_price_is_inside_zone():
    strategy = _strategy(inside=True)
    snapshot = SimpleNamespace(symbol="TESTUSDT")

    signal = asyncio.run(strategy.analyze(snapshot))

    assert signal is not None
    assert signal.direction == "LONG"
    assert "Price inside breaker" in signal.reasons
