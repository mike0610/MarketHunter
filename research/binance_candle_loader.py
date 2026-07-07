"""
MarketHunter

Module:
Binance Trade Candle Loader

Responsibilities:
- Load historical candles for virtual research trades.
- Convert stored trade information into MarketSymbol.
- Provide an async callback compatible with ResearchMonitorService.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from models.market_symbol import MarketSymbol
from research.models.trade import ResearchTrade
from services.market_data import MarketDataService


@dataclass(slots=True)
class BinanceTradeCandleLoader:
    """
    Loads candles from Binance for one ResearchTrade.
    """

    market_data: MarketDataService
    limit: int = 120

    def __post_init__(self) -> None:
        if self.limit < 2:
            raise ValueError(
                "Candle limit must be at least 2."
            )

    async def __call__(
        self,
        trade: ResearchTrade,
    ) -> list[Candle]:
        """
        Load candles using the virtual trade symbol and timeframe.
        """

        market = trade.market.strip().lower()

        if market not in {
            "spot",
            "futures",
        }:
            raise ValueError(
                f"Unsupported trade market: {trade.market}."
            )

        timeframe = trade.timeframe.strip()

        if not timeframe:
            raise ValueError(
                "Trade timeframe cannot be empty."
            )

        symbol = MarketSymbol(
            symbol=trade.symbol,
            base_asset=self._base_asset(
                trade.symbol,
            ),
            quote_asset="USDT",
            market=market,
        )

        return await self.market_data.load_candles(
            symbol=symbol,
            interval=timeframe,
            limit=self.limit,
        )

    @staticmethod
    def _base_asset(
        symbol: str,
    ) -> str:
        """
        Derive base asset for the temporary MarketSymbol object.
        """

        quote_asset = "USDT"

        if symbol.endswith(quote_asset):
            return symbol.removesuffix(
                quote_asset,
            )

        return symbol