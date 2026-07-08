"""
MarketHunter

indicators/divergence_detector.py

Detects regular and hidden RSI divergences.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from indicators.rsi import rsi


@dataclass(frozen=True, slots=True)
class DivergenceSignal:
    kind: str
    direction: str
    oscillator: str
    first_index: int
    second_index: int
    bars_between: int
    price_first: float
    price_second: float
    oscillator_first: float
    oscillator_second: float
    strength: float


class DivergenceDetector:
    """
    Detect regular and hidden oscillator divergences.
    """

    def __init__(
        self,
        pivot_window: int = 2,
        min_bars_between: int = 3,
        max_bars_between: int = 80,
        min_oscillator_delta: float = 2.0,
    ) -> None:
        self.pivot_window = pivot_window
        self.min_bars_between = min_bars_between
        self.max_bars_between = max_bars_between
        self.min_oscillator_delta = min_oscillator_delta

    def detect(
        self,
        candles: Sequence[Any],
        oscillator_values: Sequence[float | None],
        oscillator_name: str = "RSI",
    ) -> list[DivergenceSignal]:
        if len(candles) != len(oscillator_values):
            raise ValueError(
                "Candles and oscillator values must have the same length."
            )

        signals: list[DivergenceSignal] = []

        signals.extend(
            self._detect_bullish(
                candles,
                oscillator_values,
                oscillator_name,
            )
        )

        signals.extend(
            self._detect_bearish(
                candles,
                oscillator_values,
                oscillator_name,
            )
        )

        return sorted(
            signals,
            key=lambda item: item.second_index,
        )

    def latest_bullish(
        self,
        candles: Sequence[Any],
        oscillator_values: Sequence[float | None],
        oscillator_name: str = "RSI",
    ) -> DivergenceSignal | None:
        signals = [
            signal
            for signal in self.detect(
                candles,
                oscillator_values,
                oscillator_name,
            )
            if signal.direction == "LONG"
        ]

        return signals[-1] if signals else None

    def latest_bearish(
        self,
        candles: Sequence[Any],
        oscillator_values: Sequence[float | None],
        oscillator_name: str = "RSI",
    ) -> DivergenceSignal | None:
        signals = [
            signal
            for signal in self.detect(
                candles,
                oscillator_values,
                oscillator_name,
            )
            if signal.direction == "SHORT"
        ]

        return signals[-1] if signals else None

    def _detect_bullish(
        self,
        candles: Sequence[Any],
        oscillator_values: Sequence[float | None],
        oscillator_name: str,
    ) -> list[DivergenceSignal]:
        signals: list[DivergenceSignal] = []
        pivots = self._pivot_lows(candles)

        for first_index, second_index in self._pairs(pivots):
            first_osc = oscillator_values[first_index]
            second_osc = oscillator_values[second_index]

            if first_osc is None or second_osc is None:
                continue

            first_low = self._low(candles[first_index])
            second_low = self._low(candles[second_index])

            first_value = float(first_osc)
            second_value = float(second_osc)

            oscillator_delta = second_value - first_value

            if (
                second_low < first_low
                and oscillator_delta >= self.min_oscillator_delta
            ):
                signals.append(
                    self._build_signal(
                        kind="regular_bullish",
                        direction="LONG",
                        oscillator=oscillator_name,
                        first_index=first_index,
                        second_index=second_index,
                        price_first=first_low,
                        price_second=second_low,
                        oscillator_first=first_value,
                        oscillator_second=second_value,
                    )
                )

            if (
                second_low > first_low
                and -oscillator_delta >= self.min_oscillator_delta
            ):
                signals.append(
                    self._build_signal(
                        kind="hidden_bullish",
                        direction="LONG",
                        oscillator=oscillator_name,
                        first_index=first_index,
                        second_index=second_index,
                        price_first=first_low,
                        price_second=second_low,
                        oscillator_first=first_value,
                        oscillator_second=second_value,
                    )
                )

        return signals

    def _detect_bearish(
        self,
        candles: Sequence[Any],
        oscillator_values: Sequence[float | None],
        oscillator_name: str,
    ) -> list[DivergenceSignal]:
        signals: list[DivergenceSignal] = []
        pivots = self._pivot_highs(candles)

        for first_index, second_index in self._pairs(pivots):
            first_osc = oscillator_values[first_index]
            second_osc = oscillator_values[second_index]

            if first_osc is None or second_osc is None:
                continue

            first_high = self._high(candles[first_index])
            second_high = self._high(candles[second_index])

            first_value = float(first_osc)
            second_value = float(second_osc)

            oscillator_delta = second_value - first_value

            if (
                second_high > first_high
                and -oscillator_delta >= self.min_oscillator_delta
            ):
                signals.append(
                    self._build_signal(
                        kind="regular_bearish",
                        direction="SHORT",
                        oscillator=oscillator_name,
                        first_index=first_index,
                        second_index=second_index,
                        price_first=first_high,
                        price_second=second_high,
                        oscillator_first=first_value,
                        oscillator_second=second_value,
                    )
                )

            if (
                second_high < first_high
                and oscillator_delta >= self.min_oscillator_delta
            ):
                signals.append(
                    self._build_signal(
                        kind="hidden_bearish",
                        direction="SHORT",
                        oscillator=oscillator_name,
                        first_index=first_index,
                        second_index=second_index,
                        price_first=first_high,
                        price_second=second_high,
                        oscillator_first=first_value,
                        oscillator_second=second_value,
                    )
                )

        return signals

    def _pairs(
        self,
        pivots: Sequence[int],
    ) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []

        for index in range(1, len(pivots)):
            first_index = pivots[index - 1]
            second_index = pivots[index]
            bars_between = second_index - first_index

            if (
                bars_between >= self.min_bars_between
                and bars_between <= self.max_bars_between
            ):
                pairs.append(
                    (
                        first_index,
                        second_index,
                    )
                )

        return pairs

    def _pivot_lows(
        self,
        candles: Sequence[Any],
    ) -> list[int]:
        pivots: list[int] = []

        for index in range(
            self.pivot_window,
            len(candles) - self.pivot_window,
        ):
            center = self._low(candles[index])

            surrounding = [
                self._low(candles[item])
                for item in range(
                    index - self.pivot_window,
                    index + self.pivot_window + 1,
                )
                if item != index
            ]

            if all(center < value for value in surrounding):
                pivots.append(index)

        return pivots

    def _pivot_highs(
        self,
        candles: Sequence[Any],
    ) -> list[int]:
        pivots: list[int] = []

        for index in range(
            self.pivot_window,
            len(candles) - self.pivot_window,
        ):
            center = self._high(candles[index])

            surrounding = [
                self._high(candles[item])
                for item in range(
                    index - self.pivot_window,
                    index + self.pivot_window + 1,
                )
                if item != index
            ]

            if all(center > value for value in surrounding):
                pivots.append(index)

        return pivots

    def _build_signal(
        self,
        kind: str,
        direction: str,
        oscillator: str,
        first_index: int,
        second_index: int,
        price_first: float,
        price_second: float,
        oscillator_first: float,
        oscillator_second: float,
    ) -> DivergenceSignal:
        price_move_percent = 0.0

        if price_first != 0:
            price_move_percent = abs(
                (price_second - price_first)
                / price_first
                * 100.0
            )

        oscillator_move = abs(
            oscillator_second - oscillator_first
        )

        strength = round(
            oscillator_move + price_move_percent,
            4,
        )

        return DivergenceSignal(
            kind=kind,
            direction=direction,
            oscillator=oscillator,
            first_index=first_index,
            second_index=second_index,
            bars_between=second_index - first_index,
            price_first=price_first,
            price_second=price_second,
            oscillator_first=oscillator_first,
            oscillator_second=oscillator_second,
            strength=strength,
        )

    @staticmethod
    def _high(
        candle: Any,
    ) -> float:
        return float(candle.high)

    @staticmethod
    def _low(
        candle: Any,
    ) -> float:
        return float(candle.low)


class RSIDivergenceDetector:
    """
    Convenience wrapper for RSI divergences.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        pivot_window: int = 2,
        min_bars_between: int = 3,
        max_bars_between: int = 80,
        min_rsi_delta: float = 2.0,
    ) -> None:
        self.rsi_period = rsi_period
        self.detector = DivergenceDetector(
            pivot_window=pivot_window,
            min_bars_between=min_bars_between,
            max_bars_between=max_bars_between,
            min_oscillator_delta=min_rsi_delta,
        )

    def detect(
        self,
        candles: Sequence[Any],
    ) -> list[DivergenceSignal]:
        values = rsi(
            candles=candles,
            period=self.rsi_period,
        )

        return self.detector.detect(
            candles=candles,
            oscillator_values=values,
            oscillator_name="RSI",
        )

    def latest_bullish(
        self,
        candles: Sequence[Any],
    ) -> DivergenceSignal | None:
        values = rsi(
            candles=candles,
            period=self.rsi_period,
        )

        return self.detector.latest_bullish(
            candles=candles,
            oscillator_values=values,
            oscillator_name="RSI",
        )

    def latest_bearish(
        self,
        candles: Sequence[Any],
    ) -> DivergenceSignal | None:
        values = rsi(
            candles=candles,
            period=self.rsi_period,
        )

        return self.detector.latest_bearish(
            candles=candles,
            oscillator_values=values,
            oscillator_name="RSI",
        )
