"""
MarketHunter

research/manager.py

Responsibilities:
- Create virtual research trades from qualified signals.
- Classify trades as core or experimental research.
- Enforce research duplicate protection.
- Enforce open-trade limits.
- Never send real orders to Binance or any exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from models.signal import Signal
from research.models.trade import (
    CORE_RESEARCH_GROUP,
    EXPERIMENTAL_RESEARCH_GROUP,
    ResearchTrade,
)
from research.storage.repository import ResearchRepository


DEFAULT_MAX_OPEN_TRADES = 10
DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL = 1

SPOT_RESEARCH_EXPERIMENT_TAG = "spot_research"
LIQUIDITY_SWEEP_EXPERIMENT_TAG = "liquidity_sweep_v1"
DAILY_LEVELS_EXPERIMENT_TAG = "daily_levels_v1"


@dataclass(slots=True)
class ResearchTradeCreationResult:
    """
    Result of attempting to create a virtual research trade.
    """

    trade: ResearchTrade | None = None
    reason: str | None = None

    @property
    def created(
        self,
    ) -> bool:
        """
        Return True when a trade was created.
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

        if market == "spot" and direction == "SHORT":
            return ResearchTradeCreationResult(
                reason="spot_short_not_supported",
            )

        if direction == "SHORT":
            risk_geometry_valid = stop_loss > entry_price
        else:
            risk_geometry_valid = stop_loss < entry_price

        if not risk_geometry_valid:
            return ResearchTradeCreationResult(
                reason=(
                    "Research trade blocked by risk geometry: "
                    f"{direction} stop_loss ({stop_loss}) is not on the "
                    f"correct side of entry_price ({entry_price})."
                ),
            )

        if self.repository.has_open_direction_trade(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            direction=direction,
        ):
            return ResearchTradeCreationResult(
                reason=(
                    "Open trade already exists for "
                    f"{symbol} {market} {direction}."
                )
            )

        symbol_open_trades = (
            self.repository.count_open_trades_for_symbol(
                symbol=symbol,
                market=market,
            )
        )

        if symbol_open_trades >= (
            self.max_open_trades_per_symbol
        ):
            return ResearchTradeCreationResult(
                reason=(
                    f"Open trade limit for {symbol} {market} reached: "
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

        signal_id = signal.metadata.get(
            "signal_id",
        )

        research_group = self.research_group_for_signal(
            signal=signal,
        )

        experiment_tag = self.experiment_tag_for_signal(
            signal=signal,
        )

        signal.metadata["research_group"] = research_group
        signal.metadata["experiment_tag"] = experiment_tag

        trade = ResearchTrade(
            id=str(
                uuid4(),
            ),
            signal_id=(
                str(
                    signal_id,
                )
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
            reasons=list(
                signal.reasons,
            ),
            research_group=research_group,
            experiment_tag=experiment_tag,
        )

        self.repository.save(
            trade,
        )

        return ResearchTradeCreationResult(
            trade=trade,
        )

    @staticmethod
    def research_group_for_signal(
        signal: Signal,
    ) -> str:
        """
        Return research group for one signal.

        Core:
        - established Futures strategies.

        Experimental:
        - Spot research;
        - new LiquiditySweep / Stop Hunt strategy.
        """

        market = signal.market.strip().lower()
        strategy = signal.strategy.strip()

        if market == "spot":
            return EXPERIMENTAL_RESEARCH_GROUP

        if strategy in {
            "LiquiditySweep",
            "DailyLevels",
        }:
            return EXPERIMENTAL_RESEARCH_GROUP

        return CORE_RESEARCH_GROUP

    @staticmethod
    def experiment_tag_for_signal(
        signal: Signal,
    ) -> str | None:
        """
        Return experiment tag for one signal.
        """

        market = signal.market.strip().lower()
        strategy = signal.strategy.strip()

        if strategy == "DailyLevels":
            return DAILY_LEVELS_EXPERIMENT_TAG

        if strategy == "LiquiditySweep":
            return LIQUIDITY_SWEEP_EXPERIMENT_TAG

        if market == "spot":
            return SPOT_RESEARCH_EXPERIMENT_TAG

        return None
