"""Repeated price reactions and structural line detection.

Pure OHLC price-action research. The detector looks for repeated touches followed
by meaningful rebounds, then asks whether those reaction points can be explained
by one horizontal or gently sloped structural line.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from research.price_action.context import SwingPoint


@dataclass(frozen=True, slots=True)
class ReactionPoint:
    index: int
    price: float
    side: str
    rebound_percent: float


@dataclass(frozen=True, slots=True)
class StructuralLine:
    side: str
    kind: str
    slope_per_bar: float
    intercept: float
    touches: int
    first_index: int
    last_index: int
    max_deviation_percent: float
    average_rebound_percent: float


class StructuralLineDetector:
    """Detect repeated support/resistance reactions that align to one line."""

    def __init__(
        self,
        *,
        reaction_window: int = 6,
        minimum_rebound_percent: float = 1.0,
        minimum_touches: int = 3,
        maximum_line_deviation_percent: float = 0.8,
        minimum_touch_spacing: int = 3,
        horizontal_slope_percent_per_bar: float = 0.02,
    ) -> None:
        self.reaction_window = reaction_window
        self.minimum_rebound_percent = minimum_rebound_percent
        self.minimum_touches = minimum_touches
        self.maximum_line_deviation_percent = maximum_line_deviation_percent
        self.minimum_touch_spacing = minimum_touch_spacing
        self.horizontal_slope_percent_per_bar = (
            horizontal_slope_percent_per_bar
        )

    def detect(
        self,
        candles: list[Candle],
        *,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> list[StructuralLine]:
        reactions = [
            *self._reaction_points(
                candles,
                swing_lows,
                side="support",
            ),
            *self._reaction_points(
                candles,
                swing_highs,
                side="resistance",
            ),
        ]

        lines: list[StructuralLine] = []

        for side in ("support", "resistance"):
            side_points = [
                point for point in reactions
                if point.side == side
            ]
            lines.extend(
                self._fit_lines(side_points, side=side)
            )

        lines.sort(
            key=lambda line: (
                -line.touches,
                -line.average_rebound_percent,
                line.max_deviation_percent,
            )
        )
        return lines

    def _reaction_points(
        self,
        candles: list[Candle],
        swings: list[SwingPoint],
        *,
        side: str,
    ) -> list[ReactionPoint]:
        points: list[ReactionPoint] = []

        for swing in swings:
            future = candles[
                swing.index + 1:
                swing.index + 1 + self.reaction_window
            ]
            if not future or swing.price <= 0:
                continue

            if side == "support":
                best = max(candle.high for candle in future)
                rebound = (best - swing.price) / swing.price * 100
            else:
                best = min(candle.low for candle in future)
                rebound = (swing.price - best) / swing.price * 100

            if rebound < self.minimum_rebound_percent:
                continue

            points.append(
                ReactionPoint(
                    index=swing.index,
                    price=swing.price,
                    side=side,
                    rebound_percent=rebound,
                )
            )

        return points

    def _fit_lines(
        self,
        points: list[ReactionPoint],
        *,
        side: str,
    ) -> list[StructuralLine]:
        if len(points) < self.minimum_touches:
            return []

        candidates: list[StructuralLine] = []
        seen: set[tuple[int, int, int]] = set()

        for start in range(len(points) - 1):
            for end in range(start + 1, len(points)):
                a = points[start]
                b = points[end]

                if b.index - a.index < self.minimum_touch_spacing:
                    continue

                slope = (b.price - a.price) / (b.index - a.index)
                intercept = a.price - slope * a.index

                matched = [
                    point
                    for point in points
                    if self._distance_percent(
                        point.price,
                        intercept + slope * point.index,
                    )
                    <= self.maximum_line_deviation_percent
                ]

                matched = self._dedupe_nearby_touches(matched)

                if len(matched) < self.minimum_touches:
                    continue

                first = matched[0]
                last = matched[-1]
                key = (
                    first.index,
                    last.index,
                    len(matched),
                )
                if key in seen:
                    continue
                seen.add(key)

                deviations = [
                    self._distance_percent(
                        point.price,
                        intercept + slope * point.index,
                    )
                    for point in matched
                ]

                reference_price = sum(
                    point.price for point in matched
                ) / len(matched)
                slope_percent = (
                    slope / reference_price * 100
                    if reference_price > 0
                    else 0.0
                )

                if abs(slope_percent) <= self.horizontal_slope_percent_per_bar:
                    kind = "horizontal"
                elif slope > 0:
                    kind = "ascending"
                else:
                    kind = "descending"

                candidates.append(
                    StructuralLine(
                        side=side,
                        kind=kind,
                        slope_per_bar=slope,
                        intercept=intercept,
                        touches=len(matched),
                        first_index=first.index,
                        last_index=last.index,
                        max_deviation_percent=max(deviations),
                        average_rebound_percent=sum(
                            point.rebound_percent
                            for point in matched
                        ) / len(matched),
                    )
                )

        return self._remove_dominated(candidates)

    def _dedupe_nearby_touches(
        self,
        points: list[ReactionPoint],
    ) -> list[ReactionPoint]:
        ordered = sorted(points, key=lambda point: point.index)
        kept: list[ReactionPoint] = []

        for point in ordered:
            if (
                kept
                and point.index - kept[-1].index < self.minimum_touch_spacing
            ):
                if point.rebound_percent > kept[-1].rebound_percent:
                    kept[-1] = point
                continue
            kept.append(point)

        return kept

    @staticmethod
    def _distance_percent(
        actual: float,
        expected: float,
    ) -> float:
        if expected == 0:
            return float("inf")
        return abs(actual - expected) / abs(expected) * 100

    @staticmethod
    def _remove_dominated(
        lines: list[StructuralLine],
    ) -> list[StructuralLine]:
        ranked = sorted(
            lines,
            key=lambda line: (
                -line.touches,
                line.max_deviation_percent,
                -line.average_rebound_percent,
            ),
        )
        kept: list[StructuralLine] = []

        for candidate in ranked:
            duplicate = any(
                line.side == candidate.side
                and line.kind == candidate.kind
                and abs(line.first_index - candidate.first_index) <= 2
                and abs(line.last_index - candidate.last_index) <= 2
                for line in kept
            )
            if not duplicate:
                kept.append(candidate)

        return kept
