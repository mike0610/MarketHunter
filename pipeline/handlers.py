"""
MarketHunter

Default handlers for signal processing pipeline.
"""

from __future__ import annotations

from probability.probability_engine import ProbabilityEngine
from research.manager import ResearchManager
from risk.risk_manager import RiskManager

from pipeline.context import SignalContext
from pipeline.handler import SignalHandler


class ProbabilityHandler(SignalHandler):
    """
    Calculates probability and rejects weak signals.
    """

    def __init__(
        self,
        engine: ProbabilityEngine,
        minimum_probability: int = 80,
    ) -> None:

        if not 0 <= minimum_probability <= 100:
            raise ValueError(
                "Minimum probability must be between 0 and 100."
            )

        self.engine = engine
        self.minimum_probability = minimum_probability

    async def handle(
        self,
        context: SignalContext,
    ) -> None:

        result = self.engine.evaluate(
            context.snapshot,
        )

        context.probability = result

        context.signal.metadata["probability"] = (
            result.probability
        )

        context.signal.metadata["confidence"] = (
            result.confidence
        )

        context.signal.metadata["probability_reasons"] = (
            result.reasons
        )

        if result.probability < self.minimum_probability:

            context.reject(
                "Probability "
                f"{result.probability}% is below "
                f"{self.minimum_probability}%."
            )


class RiskHandler(SignalHandler):
    """
    Calculates entry, stop loss, take profit and virtual position data.
    """

    def __init__(
        self,
        manager: RiskManager,
        account_size: float,
        risk_percent: float = 1.0,
        rr: float = 2.0,
    ) -> None:

        self.manager = manager
        self.account_size = account_size
        self.risk_percent = risk_percent
        self.rr = rr

    async def handle(
        self,
        context: SignalContext,
    ) -> None:

        direction = context.signal.direction.upper()

        if direction == "LONG":

            result = self.manager.long(
                snapshot=context.snapshot,
                account=self.account_size,
                risk_percent=self.risk_percent,
                rr=self.rr,
            )

        elif direction == "SHORT":

            result = self.manager.short(
                snapshot=context.snapshot,
                account=self.account_size,
                risk_percent=self.risk_percent,
                rr=self.rr,
            )

        else:

            context.reject(
                f"Unsupported direction: {direction}."
            )

            return

        context.risk = result

        context.signal.metadata["risk"] = {
            "entry": result.entry,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "risk_reward": result.risk_reward,
            "position_size": result.position_size,
        }


class ResearchTradeHandler(SignalHandler):
    """
    Creates a virtual trade for an approved signal.
    """

    def __init__(
        self,
        manager: ResearchManager,
        notional: float = 100.0,
    ) -> None:

        if notional <= 0:
            raise ValueError(
                "Virtual trade notional must be greater than zero."
            )

        self.manager = manager
        self.notional = notional

    async def handle(
        self,
        context: SignalContext,
    ) -> None:

        if context.probability is None:

            context.reject(
                "Research trade requires probability result."
            )

            return

        if context.risk is None:

            context.reject(
                "Research trade requires risk result."
            )

            return

        trade = self.manager.create_from_signal(
            signal=context.signal,
            entry_price=context.risk.entry,
            stop_loss=context.risk.stop_loss,
            take_profit=context.risk.take_profit,
            probability=context.probability.probability,
            notional=self.notional,
        )

        if trade is None:

            context.metadata["research_skipped"] = (
                "Duplicate open virtual trade."
            )

            return

        context.research_trade = trade