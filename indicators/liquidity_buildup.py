"""
MarketHunter

Module:
Liquidity Buildup Sweep Detector

Detects:
- Equal lows -> sweep below -> close back above -> LONG confirmation
- Equal highs -> sweep above -> close back below -> SHORT confirmation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.candle import Candle


BuildupKind = Literal[
    "sell_side_liquidity_sweep",
    "buy_side_liquidity_sweep",
]


@dataclass(slots=True)
class LiquidityBuildupSweepSignal:
    kind: BuildupKind
    direction: str
    level: float
    first_index: int
    second_index: int
    swept_index: int
    touches: int
    tolerance_percent: float


class LiquidityBuildupSweepDetector:
    """
    Finds equal-high/equal-low liquidity buildup before a sweep.

    LONG:
    equal lows exist below price, last candle sweeps below that level,
    then closes back above it.

    SHORT:
    equal highs exist above price, last candle sweeps above that level,
    then closes back below it.
    """

    def __init__(
        self,
        *,
        lookback_candles: int = 80,
        tolerance_percent: float = 0.25,
        min_touches: int = 2,
        min_bars_between: int = 3,
        pivot_window: int = 1,
    ) -> None:
        if lookback_candles < 10:
            raise ValueError(
                "Liquidity buildup lookback must be at least 10 candles."
            )

        if tolerance_percent <= 0:
            raise ValueError(
                "Liquidity buildup tolerance must be positive."
            )

        if min_touches < 2:
            raise ValueError(
                "Liquidity buildup needs at least two touches."
            )

        if min_bars_between < 1:
            raise ValueError(
                "Minimum bars between touches must be positive."
            )

        if pivot_window < 1:
            raise ValueError(
                "Pivot window must be positive."
            )

        self.lookback_candles = lookback_candles
        self.tolerance_percent = tolerance_percent
        self.min_touches = min_touches
        self.min_bars_between = min_bars_between
        self.pivot_window = pivot_window

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        return self.latest_bullish(candles) is not None

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        return self.latest_bearish(candles) is not None

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> LiquidityBuildupSweepSignal | None:
        """
        Equal lows -> sell-side sweep -> bullish reclaim.
        """

        return self._latest(
            candles=candles,
            side="low",
        )

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> LiquidityBuildupSweepSignal | None:
        """
        Equal highs -> buy-side sweep -> bearish reclaim.
        """

        return self._latest(
            candles=candles,
            side="high",
        )

    def _latest(
        self,
        *,
        candles: list[Candle],
        side: Literal["low", "high"],
    ) -> LiquidityBuildupSweepSignal | None:
        if len(candles) < (
            self.min_touches
            + self.pivot_window
            + 2
        ):
            return None

        last = candles[-1]
        points = self._turning_points(
            candles=candles,
            side=side,
        )

        if len(points) < self.min_touches:
            return None

        candidates: list[LiquidityBuildupSweepSignal] = []

        for anchor_index, anchor_level in points:
            tolerance = self._tolerance(anchor_level)

            cluster = [
                (index, level)
                for index, level in points
                if abs(level - anchor_level) <= tolerance
            ]

            if len(cluster) < self.min_touches:
                continue

            cluster = sorted(
                cluster,
                key=lambda item: item[0],
            )

            first_index = cluster[0][0]
            second_index = cluster[-1][0]

            if (
                second_index - first_index
                < self.min_bars_between
            ):
                continue

            level = sum(
                level
                for _, level in cluster
            ) / len(cluster)

            if side == "low":
                if not (
                    last.low < level
                    and last.close > level
                ):
                    continue

                candidates.append(
                    LiquidityBuildupSweepSignal(
                        kind="sell_side_liquidity_sweep",
                        direction="LONG",
                        level=level,
                        first_index=first_index,
                        second_index=second_index,
                        swept_index=len(candles) - 1,
                        touches=len(cluster),
                        tolerance_percent=self.tolerance_percent,
                    )
                )

            else:
                if not (
                    last.high > level
                    and last.close < level
                ):
                    continue

                candidates.append(
                    LiquidityBuildupSweepSignal(
                        kind="buy_side_liquidity_sweep",
                        direction="SHORT",
                        level=level,
                        first_index=first_index,
                        second_index=second_index,
                        swept_index=len(candles) - 1,
                        touches=len(cluster),
                        tolerance_percent=self.tolerance_percent,
                    )
                )

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda signal: (
                signal.second_index,
                signal.touches,
            ),
        )

    def _turning_points(
        self,
        *,
        candles: list[Candle],
        side: Literal["low", "high"],
    ) -> list[tuple[int, float]]:
        """
        Return all pre-sweep highs/lows in the lookback window.

        Liquidity buildup is about repeated equal levels before the sweep.
        A touch immediately before the sweep may not be a classical pivot
        because the sweep candle itself breaks that level, so strict pivot
        filtering would miss valid equal highs/lows.
        """

        sweep_index = len(candles) - 1
        start_index = max(
            0,
            sweep_index - self.lookback_candles,
        )

        points: list[tuple[int, float]] = []

        for index in range(
            start_index,
            sweep_index,
        ):
            candle = candles[index]

            if side == "low":
                points.append(
                    (
                        index,
                        candle.low,
                    )
                )

            else:
                points.append(
                    (
                        index,
                        candle.high,
                    )
                )

        return points

    def _tolerance(
        self,
        level: float,
    ) -> float:
        return abs(level) * (
            self.tolerance_percent
            / 100.0
        )
