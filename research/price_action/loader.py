"""Research-only data delivery for top-down price-action context.

Loads real Binance OHLCV candles for 1M / 1w / 1d / 1h, then hands them
unchanged to TopDownPriceActionEngine. No production scanner wiring here.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.market_symbol import MarketSymbol
from research.price_action.top_down import (
    TopDownPriceActionContext,
    TopDownPriceActionEngine,
)
from services.market_data import MarketDataService


@dataclass(frozen=True, slots=True)
class TopDownCandleLimits:
    monthly: int = 120
    weekly: int = 260
    daily: int = 365
    hourly: int = 500


class TopDownPriceActionLoader:
    """Fetch the four timeframe histories required by the research engine."""

    def __init__(
        self,
        market_data: MarketDataService,
        *,
        engine: TopDownPriceActionEngine | None = None,
        limits: TopDownCandleLimits | None = None,
    ) -> None:
        self.market_data = market_data
        self.engine = engine or TopDownPriceActionEngine()
        self.limits = limits or TopDownCandleLimits()

    async def analyze_symbol(
        self,
        symbol: MarketSymbol,
    ) -> TopDownPriceActionContext:
        monthly = await self.market_data.load_candles(
            symbol=symbol,
            interval="1M",
            limit=self.limits.monthly,
        )
        weekly = await self.market_data.load_candles(
            symbol=symbol,
            interval="1w",
            limit=self.limits.weekly,
        )
        daily = await self.market_data.load_candles(
            symbol=symbol,
            interval="1d",
            limit=self.limits.daily,
        )
        hourly = await self.market_data.load_candles(
            symbol=symbol,
            interval="1h",
            limit=self.limits.hourly,
        )

        return self.engine.analyze(
            monthly_candles=monthly,
            weekly_candles=weekly,
            daily_candles=daily,
            hourly_candles=hourly,
        )
