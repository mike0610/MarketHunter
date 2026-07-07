"""
MarketHunter

Module:
Candle Model

Responsibilities:
- Represent one OHLCV candle.
- Normalize Binance timestamps to UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class Candle:
    """
    Represents one OHLCV candle.
    """

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    quote_volume: float
    trades: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float

    @classmethod
    def from_binance(
        cls,
        data: list,
    ) -> "Candle":
        """
        Create UTC-aware Candle from Binance kline data.
        """

        return cls(
            open_time=datetime.fromtimestamp(
                data[0] / 1000,
                tz=timezone.utc,
            ),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            close_time=datetime.fromtimestamp(
                data[6] / 1000,
                tz=timezone.utc,
            ),
            quote_volume=float(data[7]),
            trades=int(data[8]),
            taker_buy_base_volume=float(data[9]),
            taker_buy_quote_volume=float(data[10]),
        )

    @property
    def body(self) -> float:
        """
        Candle body size.
        """

        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        """
        High-low range.
        """

        return self.high - self.low

    @property
    def bullish(self) -> bool:
        """
        Return True for a green candle.
        """

        return self.close > self.open

    @property
    def bearish(self) -> bool:
        """
        Return True for a red candle.
        """

        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        """
        Upper candle wick size.
        """

        return self.high - max(
            self.open,
            self.close,
        )

    @property
    def lower_wick(self) -> float:
        """
        Lower candle wick size.
        """

        return min(
            self.open,
            self.close,
        ) - self.low