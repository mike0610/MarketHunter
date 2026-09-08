"""Top-down price-action market context.

Pure OHLC structure analysis. No EMA/RSI/MACD or other technical indicators.
This module describes what price did; it does not grant trading permission.
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
    kind: str


@dataclass(frozen=True, slots=True)
class PriceZone:
    lower: float
    upper: float
    touches: int
    side: str


@dataclass(frozen=True, slots=True)
class StructureEvent:
    index: int
    kind: str
    direction: str
    level: float
    close: float


@dataclass(frozen=True, slots=True)
class ZoneBehavior:
    side: str
    lower: float
    upper: float
    state: str
    direction: str
    last_index: int | None
    compression: bool


@dataclass(frozen=True, slots=True)
class PriceActionContext:
    regime: MarketRegime
    confidence: float
    swing_highs: tuple[SwingPoint, ...]
    swing_lows: tuple[SwingPoint, ...]
    support_zones: tuple[PriceZone, ...]
    resistance_zones: tuple[PriceZone, ...]
    structure_sequence: tuple[str, ...]
    structure_events: tuple[StructureEvent, ...]
    zone_behaviors: tuple[ZoneBehavior, ...]


class PriceActionContextEngine:
    """Human-style market structure from candle history only."""

    def __init__(
        self,
        *,
        pivot_left: int = 2,
        pivot_right: int = 2,
        zone_tolerance_percent: float = 0.6,
        min_zone_touches: int = 2,
        behavior_lookback: int = 12,
    ) -> None:
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.zone_tolerance_percent = zone_tolerance_percent
        self.min_zone_touches = min_zone_touches
        self.behavior_lookback = behavior_lookback

    def analyze(self, candles: list[Candle]) -> PriceActionContext:
        if len(candles) < 12:
            raise ValueError("At least 12 candles are required.")

        highs, lows = self._swings(candles)
        sequence = self._structure_sequence(highs, lows)
        events = self._structure_events(candles, highs, lows)
        regime, confidence = self._regime(highs, lows, sequence)

        all_supports = self._zones(lows, side="support")
        all_resistances = self._zones(highs, side="resistance")
        last_close = candles[-1].close

        supports = tuple(
            zone for zone in all_supports
            if zone.upper < last_close
        )
        resistances = tuple(
            zone for zone in all_resistances
            if zone.lower > last_close
        )

        behaviors = self._zone_behaviors(
            candles,
            [*all_supports, *all_resistances],
        )

        return PriceActionContext(
            regime=regime,
            confidence=confidence,
            swing_highs=tuple(highs),
            swing_lows=tuple(lows),
            support_zones=supports,
            resistance_zones=resistances,
            structure_sequence=tuple(sequence),
            structure_events=tuple(events),
            zone_behaviors=tuple(behaviors),
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
            window = candles[i - left:i + right + 1]

            if c.high == max(x.high for x in window):
                if sum(1 for x in window if x.high == c.high) == 1:
                    highs.append(SwingPoint(i, c.high, "high"))

            if c.low == min(x.low for x in window):
                if sum(1 for x in window if x.low == c.low) == 1:
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
    def _structure_events(
        candles: list[Candle],
        highs: list[SwingPoint],
        lows: list[SwingPoint],
    ) -> list[StructureEvent]:
        events: list[StructureEvent] = []
        levels = sorted(
            [(s.index, s.price, "high") for s in highs]
            + [(s.index, s.price, "low") for s in lows]
        )

        for swing_index, level, side in levels:
            broken = False

            for i in range(swing_index + 1, len(candles)):
                close = candles[i].close
                crossed = (
                    close > level
                    if side == "high"
                    else close < level
                )

                if not broken and crossed:
                    events.append(
                        StructureEvent(
                            index=i,
                            kind="break_of_structure",
                            direction=(
                                "bullish"
                                if side == "high"
                                else "bearish"
                            ),
                            level=level,
                            close=close,
                        )
                    )
                    broken = True
                    continue

                if broken:
                    reclaimed = (
                        close < level
                        if side == "high"
                        else close > level
                    )
                    if reclaimed:
                        events.append(
                            StructureEvent(
                                index=i,
                                kind="reclaim",
                                direction=(
                                    "bearish"
                                    if side == "high"
                                    else "bullish"
                                ),
                                level=level,
                                close=close,
                            )
                        )
                        break

        events.sort(key=lambda event: event.index)
        return events

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

        zones = [
            PriceZone(
                lower=min(cluster),
                upper=max(cluster),
                touches=len(cluster),
                side=side,
            )
            for cluster in clusters
            if len(cluster) >= self.min_zone_touches
        ]

        zones.sort(
            key=lambda zone: (
                zone.lower,
                zone.upper,
            )
        )
        return zones

    def _zone_behaviors(
        self,
        candles: list[Candle],
        zones: list[PriceZone],
    ) -> list[ZoneBehavior]:
        start = max(0, len(candles) - self.behavior_lookback)
        window = candles[start:]
        behaviors: list[ZoneBehavior] = []

        for zone in zones:
            state = "untested"
            direction = "neutral"
            last_index: int | None = None

            breakout_index: int | None = None
            breakout_direction: str | None = None

            for local_index, candle in enumerate(window):
                index = start + local_index
                touches = (
                    candle.high >= zone.lower
                    and candle.low <= zone.upper
                )

                if zone.side == "resistance":
                    if candle.close > zone.upper:
                        breakout_index = index
                        breakout_direction = "bullish"
                        state = "breakout"
                        direction = "bullish"
                        last_index = index
                        continue

                    if (
                        breakout_index is not None
                        and touches
                        and index > breakout_index
                    ):
                        if candle.close >= zone.upper:
                            state = "retest_hold"
                            direction = "bullish"
                        else:
                            state = "retest_fail"
                            direction = "bearish"
                        last_index = index
                        continue

                    if touches and candle.close < zone.lower:
                        state = "rejection"
                        direction = "bearish"
                        last_index = index

                else:
                    if candle.close < zone.lower:
                        breakout_index = index
                        breakout_direction = "bearish"
                        state = "breakout"
                        direction = "bearish"
                        last_index = index
                        continue

                    if (
                        breakout_index is not None
                        and touches
                        and index > breakout_index
                    ):
                        if candle.close <= zone.lower:
                            state = "retest_hold"
                            direction = "bearish"
                        else:
                            state = "retest_fail"
                            direction = "bullish"
                        last_index = index
                        continue

                    if touches and candle.close > zone.upper:
                        state = "rejection"
                        direction = "bullish"
                        last_index = index

            compression = self._is_compressing_toward_zone(
                window,
                zone,
            )

            if breakout_direction is not None and state == "breakout":
                direction = breakout_direction

            behaviors.append(
                ZoneBehavior(
                    side=zone.side,
                    lower=zone.lower,
                    upper=zone.upper,
                    state=state,
                    direction=direction,
                    last_index=last_index,
                    compression=compression,
                )
            )

        return behaviors

    @staticmethod
    def _is_compressing_toward_zone(
        candles: list[Candle],
        zone: PriceZone,
    ) -> bool:
        recent = candles[-4:]
        if len(recent) < 4:
            return False

        ranges = [c.range for c in recent]
        if not (
            ranges[-1] <= ranges[-2] <= ranges[-3]
        ):
            return False

        center = (zone.lower + zone.upper) / 2
        distances = [
            abs(c.close - center)
            for c in recent
        ]

        return (
            distances[-1]
            < distances[-2]
            < distances[-3]
        )
