"""
MarketHunter

Module:
Research Manager

Responsibilities:
- Create virtual trades from candidate signals.
- Enforce global and per-symbol open-trade limits.
- Prevent duplicate same-direction research positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from models.signal import Signal
from research.models.trade import ResearchTrade
from research.storage.repository import ResearchRepository


DEFAULT_MAX_OPEN_TRADES = 80
DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL = 1


@dataclass(frozen=True, slots=True)
class ResearchTradeCreationResult:
    """
    Result of an attempted virtual trade creation.
    """

    trade: ResearchTrade | None = None
    reason: str | None = None

    @property
    def created(self) -> bool:
        """
        Return True when a virtual trade was stored.
        """

        return self.trade is not None


class ResearchManager:
    """
    Creates and persists virtual trades.

    This module never sends real orders to Binance or any exchange.
    """

    def __init__(
        self,
        repository: ResearchRepository,
        max_open_trades: int = DEFAULT_MAX_OPEN_TRADES,
        max_open_trades_per_symbol: int = (
            DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL
        ),
    ) -> None:
        if max_open_trades <= 0:
            raise ValueError(
                "Maximum open trade count must be greater than zero."
            )

        if max_open_trades_per_symbol <= 0:
            raise ValueError(
                "Maximum open trades per symbol must be greater than zero."
            )

        self.repository = repository
        self.max_open_trades = max_open_trades
        self.max_open_trades_per_symbol = (
            max_open_trades_per_symbol
        )

    def create_from_signal(
        self,
        signal: Signal,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        probability: int,
        notional: float = 100.0,
    ) -> ResearchTradeCreationResult:
        """
        Create a virtual trade when all research limits allow it.
        """

        if notional <= 0:
            raise ValueError(
                "Virtual trade notional must be greater than zero."
            )

        symbol = signal.symbol.strip().upper()
        market = signal.market.strip().lower()
        timeframe = signal.timeframe.strip()
        direction = signal.direction.strip().upper()

        if not symbol:
            raise ValueError(
                "Signal symbol cannot be empty."
            )

        if not market:
            raise ValueError(
                "Signal market cannot be empty."
            )

        if not timeframe:
            raise ValueError(
                "Signal timeframe cannot be empty."
            )

        if direction not in {
            "LONG",
            "SHORT",
        }:
            raise ValueError(
                f"Unsupported signal direction: {direction}."
            )

        if self.repository.has_open_direction_trade(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
        ):
            return ResearchTradeCreationResult(
                reason=(
                    "Open trade already exists for "
                    f"{symbol} {timeframe} {direction}."
                )
            )

        symbol_open_trades = (
            self.repository.count_open_trades_for_symbol(
                symbol=symbol,
            )
        )

        if symbol_open_trades >= (
            self.max_open_trades_per_symbol
        ):
            return ResearchTradeCreationResult(
                reason=(
                    f"Open trade limit for {symbol} reached: "
                    f"{symbol_open_trades}/"
                    f"{self.max_open_trades_per_symbol}."
                )
            )

        all_open_trades = self.repository.count_open_trades()

        if all_open_trades >= self.max_open_trades:
            return ResearchTradeCreationResult(
                reason=(
                    "Global open virtual trade limit reached: "
                    f"{all_open_trades}/{self.max_open_trades}."
                )
            )

        signal_id = signal.metadata.get("signal_id")

        trade = ResearchTrade(
            id=str(uuid4()),
            signal_id=(
                str(signal_id)
                if signal_id is not None
                else None
            ),
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            strategy=signal.strategy,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            probability=probability,
            score=signal.score,
            notional=notional,
            reasons=list(signal.reasons),
        )

        self.repository.save(trade)

        return ResearchTradeCreationResult(
            trade=trade,
        )