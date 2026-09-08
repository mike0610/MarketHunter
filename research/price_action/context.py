"""Top-down price-action market context.

Pure OHLC structure analysis. No EMA/RSI/MACD or other technical indicators.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from models.candle import Candle


class MarketRegime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"
    TRANSITION = "transition"


@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" | "low"


@dataclass(frozen=True, slots=True)
class PriceZone:
    lower: float
    upper: float
    touches: int
    side: str  # "support" | "resistance"


@dataclass(frozen=True, slots=True)
class PriceActionContext:
    regime: MarketRegime
    confidence: float
    swing_highs: tuple[SwingPoint, ...]
    swing_lows: tuple[SwingPoint, ...]
    support_zones: tuple[PriceZone, ...]
    resistance_zones: tuple[PriceZone, ...]
    structure_sequence: tuple[str, ...]


class PriceActionContextEngine:
    """Human-style market structure from candle history only."""

    def __init__(
        self,
        *,
        pivot_left: int = 2,
        pivot_right: int = 2,
        zone_tolerance_percent: float = 0.6,
        min_zone_touches: int = 2,
    ) -> None:
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.zone_tolerance_percent = zone_tolerance_percent
        self.min_zone_touches = min_zone_touches

    def analyze(self, candles: list[Candle]) -> PriceActionContext:
        if len(candles) < 12:
            raise ValueError("At least 12 candles are required.")

        highs, lows = self._swings(candles)
        sequence = self._structure_sequence(highs, lows)
        regime, confidence = self._regime(highs, lows, sequence)

        last_close = candles[-1].close
        supports = self._zones(
            lows,
            side="support",
            current_price=last_close,
        )
        resistances = self._zones(
            highs,
            side="resistance",
            current_price=last_close,
        )

        return PriceActionContext(
            regime=regime,
            confidence=confidence,
            swing_highs=tuple(highs),
            swing_lows=tuple(lows),
            support_zones=tuple(supports),
            resistance_zones=tuple(resistances),
            structure_sequence=tuple(sequence),
        )

    def _swings(
        self,
        candles: list[Candle],
    ) -> tuple[list[SwingPoint], list[SwingPoint]]:
        highs: list[SwingPoint] = []
        lows: list[SwingPoint] = []

        left = self.pivot_left
        right = self.pivot_right

        for i in range(left, len(candles) - right):
            c = candles[i]
            high_window = candles[i - left:i + right + 1]
            low_window = high_window

            if c.high == max(x.high for x in high_window):
                if sum(1 for x in high_window if x.high == c.high) == 1:
                    highs.append(SwingPoint(i, c.high, "high"))

            if c.low == min(x.low for x in low_window):
                if sum(1 for x in low_window if x.low == c.low) == 1:
                    lows.append(SwingPoint(i, c.low, "low"))

        return highs, lows

    @staticmethod
    def _structure_sequence(
        highs: list[SwingPoint],
        lows: list[SwingPoint],
    ) -> list[str]:
        labels: list[tuple[int, str]] = []

        for a, b in zip(highs, highs[1:]):
            labels.append((b.index, "HH" if b.price > a.price else "LH"))

        for a, b in zip(lows, lows[1:]):
            labels.append((b.index, "HL" if b.price > a.price else "LL"))

        labels.sort(key=lambda item: item[0])
        return [label for _, label in labels]

    @staticmethod
    def _regime(
        highs: list[SwingPoint],
        lows: list[SwingPoint],
        sequence: list[str],
    ) -> tuple[MarketRegime, float]:
        recent = sequence[-6:]
        bullish_votes = recent.count("HH") + recent.count("HL")
        bearish_votes = recent.count("LH") + recent.count("LL")

        latest_high_up = (
            len(highs) >= 2 and highs[-1].price > highs[-2].price
        )
        latest_low_up = (
            len(lows) >= 2 and lows[-1].price > lows[-2].price
        )
        latest_high_down = (
            len(highs) >= 2 and highs[-1].price < highs[-2].price
        )
        latest_low_down = (
            len(lows) >= 2 and lows[-1].price < lows[-2].price
        )

        if latest_high_up and latest_low_up and bullish_votes > bearish_votes:
            confidence = bullish_votes / max(1, len(recent))
            return MarketRegime.BULLISH, confidence

        if latest_high_down and latest_low_down and bearish_votes > bullish_votes:
            confidence = bearish_votes / max(1, len(recent))
            return MarketRegime.BEARISH, confidence

        if abs(bullish_votes - bearish_votes) <= 1 and len(recent) >= 4:
            return MarketRegime.RANGE, 1.0 - (
                abs(bullish_votes - bearish_votes) / len(recent)
            )

        return MarketRegime.TRANSITION, 0.5

    def _zones(
        self,
        swings: list[SwingPoint],
        *,
        side: str,
        current_price: float,
    ) -> list[PriceZone]:
        if not swings:
            return []

        clusters: list[list[float]] = []

        for swing in swings:
            placed = False
            for cluster in clusters:
                center = sum(cluster) / len(cluster)
                tolerance = center * self.zone_tolerance_percent / 100
                if abs(swing.price - center) <= tolerance:
                    cluster.append(swing.price)
                    placed = True
                    break
            if not placed:
                clusters.append([swing.price])

        zones: list[PriceZone] = []
        for cluster in clusters:
            if len(cluster) < self.min_zone_touches:
                continue

            lower = min(cluster)
            upper = max(cluster)

            if side == "support" and upper >= current_price:
                continue
            if side == "resistance" and lower <= current_price:
                continue

            zones.append(
                PriceZone(
                    lower=lower,
                    upper=upper,
                    touches=len(cluster),
                    side=side,
                )
            )

        zones.sort(
            key=lambda zone: (
                abs(((zone.lower + zone.upper) / 2) - current_price),
                -zone.touches,
            )
        )
        return zones
