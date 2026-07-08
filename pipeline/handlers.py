"""
MarketHunter

Module:
Signal Pipeline Handlers

Responsibilities:
- Calculate probability.
- Calculate risk parameters.
- Create virtual research trades.
- Limit research-trade creation per scan.
- Filter elite signals for presentation.
"""

from __future__ import annotations

from loguru import logger

from pipeline.context import SignalContext
from pipeline.handler import SignalHandler
from probability.probability_engine import ProbabilityEngine
from research.setup.support_resistance import SupportResistanceDetector
from research.manager import ResearchManager
from risk.risk_manager import RiskManager


class ProbabilityHandler(SignalHandler):
    """
    Calculate probability for every candidate signal.
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
        Add probability result to signal context and metadata.
        """

        result = self.engine.evaluate(
            snapshot=context.snapshot,
            direction=context.signal.direction,
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
    Calculate entry, Stop Loss, Take Profit and risk parameters.
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
    Create virtual trades for research-qualified signals.

    Research threshold remains lower than elite threshold. This captures
    useful empirical data without showing medium-quality signals as elite.
    """

    def __init__(
        self,
        manager: ResearchManager,
        minimum_probability: int = 40,
        notional: float = 100.0,
        maximum_new_trades_per_cycle: int = 5,
    ) -> None:
        if not 0 <= minimum_probability <= 100:
            raise ValueError(
                "Research probability must be between 0 and 100."
            )

        if notional <= 0:
            raise ValueError(
                "Virtual trade notional must be greater than zero."
            )

        if maximum_new_trades_per_cycle <= 0:
            raise ValueError(
                "Maximum new trades per cycle must be greater than zero."
            )

        self.manager = manager
        self.minimum_probability = minimum_probability
        self.notional = notional
        self.maximum_new_trades_per_cycle = (
            maximum_new_trades_per_cycle
        )
        self.target_rr = 3.0
        self.support_resistance = SupportResistanceDetector(
            lookback_candles=160,
            pivot_window=2,
            min_touches=1,
            max_zones=12,
        )
        self.created_trades_this_cycle = 0

    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Create one research trade when probability and limits allow it.
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

        snapshot = getattr(
            context,
            "snapshot",
            None,
        )
        candles = getattr(
            snapshot,
            "candles",
            None,
        )

        if candles:
            target_assessment = (
                self.support_resistance.assess_rr_target(
                    candles,
                    direction=context.signal.direction,
                    entry_price=context.risk.entry,
                    stop_loss=context.risk.stop_loss,
                    target_rr=self.target_rr,
                )
            )

            context.signal.metadata["target_rr"] = self.target_rr
            context.signal.metadata["target_clear"] = (
                target_assessment.target_clear
            )
            context.signal.metadata["target_summary"] = (
                target_assessment.summary
            )

            if not target_assessment.target_clear:
                self._skip(
                    context=context,
                    reason=(
                        "Research trade blocked by target quality: "
                        f"{target_assessment.summary}"
                    ),
                )
                return

        if probability < self.minimum_probability:
            self._skip(
                context=context,
                reason=(
                    f"Probability {probability}% is below research "
                    f"threshold {self.minimum_probability}%."
                ),
            )
            return

        if (
            self.created_trades_this_cycle
            >= self.maximum_new_trades_per_cycle
        ):
            self._skip(
                context=context,
                reason=(
                    "Research cycle limit reached: "
                    f"{self.created_trades_this_cycle}/"
                    f"{self.maximum_new_trades_per_cycle}."
                ),
            )
            return

        result = self.manager.create_from_signal(
            signal=context.signal,
            entry_price=context.risk.entry,
            stop_loss=context.risk.stop_loss,
            take_profit=context.risk.take_profit,
            probability=probability,
            notional=self.notional,
        )

        if not result.created:
            self._skip(
                context=context,
                reason=(
                    result.reason
                    or "Virtual trade was not created."
                ),
            )
            return

        trade = result.trade

        if trade is None:
            self._skip(
                context=context,
                reason="Virtual trade was not created.",
            )
            return

        self.created_trades_this_cycle += 1
        context.research_trade = trade

        context.signal.metadata["research_trade_id"] = (
            trade.id
        )

    @staticmethod
    def _skip(
        context: SignalContext,
        reason: str,
    ) -> None:
        """
        Store and log the reason a research trade was skipped.
        """

        context.metadata["research_skipped"] = reason

        context.signal.metadata["research_skipped"] = reason

        logger.debug(
            "{} {} research trade skipped: {}",
            context.signal.symbol,
            context.signal.strategy,
            reason,
        )


class EliteSignalHandler(SignalHandler):
    """
    Mark only high-probability signals as elite.
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
        Mark elite signals without rejecting valid research trades.
        """

        if context.probability is None:
            context.reject(
                "Elite signal requires probability result."
            )
            return

        probability = context.probability.probability

        if probability >= self.minimum_probability:
            context.metadata["elite_signal"] = True
            context.signal.metadata["elite_signal"] = True
            return

        elite_skipped = (
            f"Probability {probability}% is below elite "
            f"threshold {self.minimum_probability}%."
        )

        context.metadata["elite_signal"] = False
        context.metadata["elite_skipped"] = elite_skipped

        context.signal.metadata["elite_signal"] = False
        context.signal.metadata["elite_skipped"] = elite_skipped

        if context.research_trade is not None:
            return

        research_skipped = (
            context.metadata.get("research_skipped")
            or context.signal.metadata.get("research_skipped")
        )

        if research_skipped:
            context.reject(
                str(research_skipped)
            )
            return

        context.reject(
            elite_skipped
        )
