"""
MarketHunter

tests/daily_levels/helpers.py

Shared fixtures for the DailyLevelsStrategy test package: deterministic
candle/snapshot builders and buffer helpers used across
test_baseline.py, test_level_quality.py, test_approach_context.py,
test_compression_breakouts.py, test_false_break_confirmation.py, and
test_bounce.py.

This is a read-only characterization suite: it locks in the CURRENT
behavior of DailyLevelsStrategy using synthetic daily candles (no
Binance/API/DB involved), before any Level Quality Foundation v1
changes touch the strategy itself. strategies/daily_levels.py is not
modified by this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models.candle import Candle
from models.market_snapshot import MarketSnapshot


RESISTANCE = 105.0
SUPPORT = 100.0

# breakout_buffer_percent / sweep_buffer_percent on DailyLevelsStrategy.
BUFFER_PERCENT = 0.15


def make_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    day_index: int,
) -> Candle:
    """
    Build a deterministic daily candle for a given day offset.
    """

    open_time = (
        datetime(2024, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=day_index)
    )

    return Candle(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        close_time=(
            open_time
            + timedelta(days=1)
            - timedelta(seconds=1)
        ),
        quote_volume=100000.0,
        trades=100,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=50000.0,
    )


def make_reference_candles(
    count: int,
    resistance: float,
    support: float,
    start_day_index: int,
) -> list[Candle]:
    """
    Build `count` uniform daily candles that pin resistance/support
    at exact known values, with a neutral midpoint close. The last
    candle in this list doubles as previous_candle in the strategy
    (candles[-3]), so its close must sit inside [support, resistance]
    for every setup's `previous_candle.close` condition to hold.
    """

    midpoint = (resistance + support) / 2

    return [
        make_candle(
            open_price=midpoint,
            high=resistance,
            low=support,
            close=midpoint,
            day_index=start_day_index + i,
        )
        for i in range(count)
    ]


def make_snapshot(
    candles: list[Candle],
    symbol: str = "BTCUSDT",
) -> MarketSnapshot:
    """
    Build a minimal MarketSnapshot. DailyLevelsStrategy only reads
    snapshot.symbol and snapshot.candles - the indicator fields below
    are unused by this strategy (it "intentionally avoids indicators"
    per its own docstring) and are set to inert placeholder values.
    """

    return MarketSnapshot(
        symbol=symbol,
        candles=candles,
        ema20=0.0,
        ema50=0.0,
        ema200=0.0,
        atr14=0.0,
        avg_volume20=0.0,
        highest20=0.0,
        lowest20=0.0,
    )


def build_candles(
    signal_candle: Candle,
    resistance: float = RESISTANCE,
    support: float = SUPPORT,
) -> list[Candle]:
    """
    Build a full 63-candle window matching what analyze() requires:
    - index 0: unused lead padding (only len(candles) matters here);
    - indices 1-60: the 60 reference candles that pin resistance/
      support (candles[-62:-2] once the list reaches length 63), the
      last of which is also previous_candle (candles[-3]);
    - index 61: the given signal_candle (candles[-2]);
    - index 62: unused trailing padding (candles[-1] is never read).
    """

    lead_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=0,
    )

    reference = make_reference_candles(
        count=60,
        resistance=resistance,
        support=support,
        start_day_index=1,
    )

    trailing_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=62,
    )

    return [lead_padding] + reference + [signal_candle, trailing_padding]


def build_candles_with_approach(
    signal_candle: Candle,
    approach_candles: list[Candle],
    resistance: float = RESISTANCE,
    support: float = SUPPORT,
) -> list[Candle]:
    """
    Build a full 63-candle window like build_candles(), but with the
    last 4 reference candles replaced by approach_candles - the ones
    _score_level_approach() reads. The remaining 56 reference candles
    are still the uniform filler that pins resistance/support, so
    approach_candles must keep every high <= resistance and every low
    >= support to avoid shifting the level itself. The last candle in
    approach_candles doubles as previous_candle (candles[-3]).
    """

    lead_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=0,
    )

    far_filler = make_reference_candles(
        count=56,
        resistance=resistance,
        support=support,
        start_day_index=1,
    )

    trailing_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=62,
    )

    return (
        [lead_padding]
        + far_filler
        + approach_candles
        + [signal_candle, trailing_padding]
    )


def above_buffer(level: float) -> float:
    """
    Smallest price that clears the 0.15% breakout/sweep buffer above
    `level` (mirrors DailyLevelsStrategy._above_level).
    """

    return level * (1 + BUFFER_PERCENT / 100)


def below_buffer(level: float) -> float:
    """
    Smallest price that clears the 0.15% breakout/sweep buffer below
    `level` (mirrors DailyLevelsStrategy._below_level).
    """

    return level * (1 - BUFFER_PERCENT / 100)
