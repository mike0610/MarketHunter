"""
MarketHunter

Module:
Signal Pipeline Handlers

Responsibilities:
- Calculate probability.
- Calculate risk parameters.
- Create virtual research trades.
- Filter elite signals for presentation.
"""

from __future__ import annotations

from pipeline.context import SignalContext
from pipeline.handler import SignalHandler
from probability.probability_engine import ProbabilityEngine
from research.manager import ResearchManager
from risk.risk_manager import RiskManager


class ProbabilityHandler(SignalHandler):
    """
    Calculates probability for every candidate signal.

    This handler does not reject signals. Rejection is performed later
    by EliteSignalHandler, while ResearchTradeHandler may still record
    medium-probability candidates for empirical statistics.
    """

    def __init__(
        self,
        engine: ProbabilityEngine,
    ) -> None:
        self.engine = engine

    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Add probability result to the signal context and metadata.
        """

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
            list(result.reasons)
        )


class RiskHandler(SignalHandler):
    """
    Calculates entry, stop loss, take profit and position parameters.
    """

    def __init__(
        self,
        manager: RiskManager,
        account_size: float,
        risk_percent: float = 1.0,
        rr: float = 2.0,
    ) -> None:
        if account_size <= 0:
            raise ValueError(
                "Account size must be greater than zero."
            )

        if risk_percent <= 0:
            raise ValueError(
                "Risk percent must be greater than zero."
            )

        if rr <= 0:
            raise ValueError(
                "Risk reward ratio must be greater than zero."
            )

        self.manager = manager
        self.account_size = account_size
        self.risk_percent = risk_percent
        self.rr = rr

    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Calculate risk parameters for LONG or SHORT signal.
        """

        direction = context.signal.direction.upper()

        try:
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

        except (
            ArithmeticError,
            ValueError,
            ZeroDivisionError,
        ) as exc:
            context.reject(
                f"Risk calculation failed: {exc}"
            )
            return

        context.risk = result

        context.signal.metadata["risk"] = {
            "entry": result.entry,
            "stop_loss": result.stop_loss,
            "take_profit": result.take_profit,
            "risk_reward": result.risk_reward,
            "position_size": result.position_size,
            "risk_amount": result.risk_amount,
        }


class ResearchTradeHandler(SignalHandler):
    """
    Creates virtual trades for signals accepted into the research sample.

    Research threshold is intentionally lower than elite threshold.
    This allows MarketHunter to collect outcome statistics while still
    showing only high-confidence signals to the user.
    """

    def __init__(
        self,
        manager: ResearchManager,
        minimum_probability: int = 40,
        notional: float = 100.0,
    ) -> None:
        if not 0 <= minimum_probability <= 100:
            raise ValueError(
                "Research probability must be between 0 and 100."
            )

        if notional <= 0:
            raise ValueError(
                "Virtual trade notional must be greater than zero."
            )

        self.manager = manager
        self.minimum_probability = minimum_probability
        self.notional = notional

    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Create one virtual trade when signal meets research threshold.
        """

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

        probability = context.probability.probability

        if probability < self.minimum_probability:
            context.metadata["research_skipped"] = (
                f"Probability {probability}% is below research "
                f"threshold {self.minimum_probability}%."
            )
            return

        trade = self.manager.create_from_signal(
            signal=context.signal,
            entry_price=context.risk.entry,
            stop_loss=context.risk.stop_loss,
            take_profit=context.risk.take_profit,
            probability=probability,
            notional=self.notional,
        )

        if trade is None:
            context.metadata["research_skipped"] = (
                "Duplicate open virtual trade."
            )
            return

        context.research_trade = trade

        context.signal.metadata["research_trade_id"] = (
            trade.id
        )


class EliteSignalHandler(SignalHandler):
    """
    Leaves only high-probability signals in Scanner output.

    It runs after ResearchTradeHandler, so medium-probability signals
    can still be stored as virtual research trades.
    """

    def __init__(
        self,
        minimum_probability: int = 80,
    ) -> None:
        if not 0 <= minimum_probability <= 100:
            raise ValueError(
                "Elite probability must be between 0 and 100."
            )

        self.minimum_probability = minimum_probability

    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Reject a signal from elite output when its probability is low.
        """

        if context.probability is None:
            context.reject(
                "Elite signal requires probability result."
            )
            return

        probability = context.probability.probability

        if probability < self.minimum_probability:
            context.reject(
                f"Probability {probability}% is below elite "
                f"threshold {self.minimum_probability}%."
            )
            return

        context.metadata["elite_signal"] = True