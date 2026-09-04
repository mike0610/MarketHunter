from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class MarketDataError(RuntimeError):
    pass


class MarketDataUnavailable(MarketDataError):
    pass


class MarketDataStale(MarketDataError):
    pass


@dataclass(frozen=True, slots=True)
class MarketInstrument:
    symbol: str
    asset_class: str
    currency: str
    exchange: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-blank")
        if not self.asset_class.strip():
            raise ValueError("asset_class must be non-blank")
        if not self.currency.strip():
            raise ValueError("currency must be non-blank")


@dataclass(frozen=True, slots=True)
class MarketBar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")


@dataclass(frozen=True, slots=True)
class MarketSeries:
    instrument: MarketInstrument
    timeframe: str
    bars: tuple[MarketBar, ...]
    provider: str
    source_reference: str
    observed_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        if not self.timeframe.strip():
            raise ValueError("timeframe must be non-blank")
        if not self.provider.strip():
            raise ValueError("provider must be non-blank")
        if not self.source_reference.strip():
            raise ValueError("source_reference must be non-blank")
        if self.observed_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("observed_at/available_at must be timezone-aware")
        if not self.bars:
            raise ValueError("bars must be non-empty")


@dataclass(frozen=True, slots=True)
class LiquidityEvidence:
    instrument: MarketInstrument
    average_daily_volume: Decimal
    average_daily_dollar_volume: Decimal
    last_price: Decimal
    provider: str
    observed_at: datetime
    source_reference: str

    def __post_init__(self) -> None:
        if self.average_daily_volume < 0 or self.average_daily_dollar_volume < 0:
            raise ValueError("liquidity values must be non-negative")
        if self.last_price <= 0:
            raise ValueError("last_price must be positive")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")


class AsyncMarketDataProvider(Protocol):
    async def universe(self) -> tuple[MarketInstrument, ...]: ...
    async def history(
        self,
        instrument: MarketInstrument,
        *,
        timeframe: str = "1d",
        limit: int = 120,
    ) -> MarketSeries: ...
    async def liquidity(self, instrument: MarketInstrument) -> LiquidityEvidence: ...
