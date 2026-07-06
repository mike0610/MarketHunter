"""
MarketHunter

models/market_symbol.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MarketSymbol:
    """
    Trading symbol description.
    """

    symbol: str
    base_asset: str
    quote_asset: str
    market: str  # spot | futures

    @property
    def is_spot(self) -> bool:
        return self.market == "spot"

    @property
    def is_futures(self) -> bool:
        return self.market == "futures"

    def __str__(self) -> str:
        return self.symbol