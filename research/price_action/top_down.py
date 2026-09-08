"""Top-down assembly for indicator-free price-action context.

Timeframe roles:
- 1M / 1W: broad market regime
- 1D: structural phase / agreement or correction
- 1h: local execution map

This layer is observational only. It does not block or approve trades.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from research.price_action.context import (
    MarketRegime,
    PriceActionContext,
    PriceActionContextEngine,
)


@dataclass(frozen=True, slots=True)
class TopDownPriceActionContext:
    monthly: PriceActionContext
    weekly: PriceActionContext
    daily: PriceActionContext
    hourly: PriceActionContext
    broad_regime: MarketRegime
    broad_confidence: float
    daily_phase: str
    hourly_context: str
    alignment: str


class TopDownPriceActionEngine:
    """Assemble one coherent market picture from 1M -> 1W -> 1D -> 1h."""

    def __init__(
        self,
        context_engine: PriceActionContextEngine | None = None,
    ) -> None:
        self.context_engine = context_engine or PriceActionContextEngine()

    def analyze(
        self,
        *,
        monthly_candles: list[Candle],
        weekly_candles: list[Candle],
        daily_candles: list[Candle],
        hourly_candles: list[Candle],
    ) -> TopDownPriceActionContext:
        monthly = self.context_engine.analyze(monthly_candles)
        weekly = self.context_engine.analyze(weekly_candles)
        daily = self.context_engine.analyze(daily_candles)
        hourly = self.context_engine.analyze(hourly_candles)

        broad_regime, broad_confidence = self._broad_regime(
            monthly,
            weekly,
        )
        daily_phase = self._daily_phase(
            broad_regime,
            daily.regime,
        )
        hourly_context = self._hourly_context(
            broad_regime,
            hourly,
        )
        alignment = self._alignment(
            broad_regime,
            daily.regime,
            hourly.regime,
        )

        return TopDownPriceActionContext(
            monthly=monthly,
            weekly=weekly,
            daily=daily,
            hourly=hourly,
            broad_regime=broad_regime,
            broad_confidence=broad_confidence,
            daily_phase=daily_phase,
            hourly_context=hourly_context,
            alignment=alignment,
        )

    @staticmethod
    def _broad_regime(
        monthly: PriceActionContext,
        weekly: PriceActionContext,
    ) -> tuple[MarketRegime, float]:
        if (
            monthly.regime == weekly.regime
            and monthly.regime in {
                MarketRegime.BULLISH,
                MarketRegime.BEARISH,
                MarketRegime.RANGE,
            }
        ):
            confidence = (
                monthly.confidence + weekly.confidence
            ) / 2
            return monthly.regime, confidence

        if monthly.regime in {
            MarketRegime.BULLISH,
            MarketRegime.BEARISH,
        } and weekly.regime == MarketRegime.TRANSITION:
            return monthly.regime, monthly.confidence * 0.7

        if weekly.regime in {
            MarketRegime.BULLISH,
            MarketRegime.BEARISH,
        } and monthly.regime == MarketRegime.TRANSITION:
            return weekly.regime, weekly.confidence * 0.6

        if (
            monthly.regime == MarketRegime.RANGE
            and weekly.regime in {
                MarketRegime.BULLISH,
                MarketRegime.BEARISH,
            }
        ):
            return MarketRegime.TRANSITION, 0.5

        if (
            weekly.regime == MarketRegime.RANGE
            and monthly.regime in {
                MarketRegime.BULLISH,
                MarketRegime.BEARISH,
            }
        ):
            return MarketRegime.TRANSITION, 0.5

        return MarketRegime.TRANSITION, 0.4

    @staticmethod
    def _daily_phase(
        broad_regime: MarketRegime,
        daily_regime: MarketRegime,
    ) -> str:
        if broad_regime == MarketRegime.BULLISH:
            if daily_regime == MarketRegime.BULLISH:
                return "trend_continuation"
            if daily_regime == MarketRegime.BEARISH:
                return "countertrend_correction"
            if daily_regime == MarketRegime.RANGE:
                return "bullish_consolidation"
            return "bullish_transition"

        if broad_regime == MarketRegime.BEARISH:
            if daily_regime == MarketRegime.BEARISH:
                return "trend_continuation"
            if daily_regime == MarketRegime.BULLISH:
                return "countertrend_correction"
            if daily_regime == MarketRegime.RANGE:
                return "bearish_consolidation"
            return "bearish_transition"

        if broad_regime == MarketRegime.RANGE:
            return "range_structure"

        return "transition"

    @staticmethod
    def _hourly_context(
        broad_regime: MarketRegime,
        hourly: PriceActionContext,
    ) -> str:
        if broad_regime == MarketRegime.BULLISH:
            if hourly.regime == MarketRegime.BULLISH:
                return "with_broad_trend"
            if hourly.regime == MarketRegime.BEARISH:
                return "countertrend"
            return "local_neutral"

        if broad_regime == MarketRegime.BEARISH:
            if hourly.regime == MarketRegime.BEARISH:
                return "with_broad_trend"
            if hourly.regime == MarketRegime.BULLISH:
                return "countertrend"
            return "local_neutral"

        return "local_neutral"

    @staticmethod
    def _alignment(
        broad_regime: MarketRegime,
        daily_regime: MarketRegime,
        hourly_regime: MarketRegime,
    ) -> str:
        if broad_regime in {
            MarketRegime.BULLISH,
            MarketRegime.BEARISH,
        }:
            aligned = sum(
                regime == broad_regime
                for regime in (
                    daily_regime,
                    hourly_regime,
                )
            )

            if aligned == 2:
                return "full_alignment"
            if aligned == 1:
                return "partial_alignment"

            opposite = (
                MarketRegime.BEARISH
                if broad_regime == MarketRegime.BULLISH
                else MarketRegime.BULLISH
            )
            if (
                daily_regime == opposite
                and hourly_regime == opposite
            ):
                return "full_countertrend"

        return "mixed"
