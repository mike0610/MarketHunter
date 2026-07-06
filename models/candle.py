"""
MarketHunter

models/candle.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    def from_binance(cls, data: list) -> "Candle":
        """
        Create Candle from Binance kline.
        """

        return cls(
            open_time=datetime.fromtimestamp(data[0] / 1000),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            close_time=datetime.fromtimestamp(data[6] / 1000),
            quote_volume=float(data[7]),
            trades=int(data[8]),
            taker_buy_base_volume=float(data[9]),
            taker_buy_quote_volume=float(data[10]),
        )

    @property
    def body(self) -> float:
        """Candle body size."""

        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        """High-Low range."""

        return self.high - self.low

    @property
    def bullish(self) -> bool:
        """Green candle."""

        return self.close > self.open

    @property
    def bearish(self) -> bool:
        """Red candle."""

        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low