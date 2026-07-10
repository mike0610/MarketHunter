"""
MarketHunter

Module:
Liquidity Sweep / Stop Hunt Strategy

Responsibilities:
- Detect bullish liquidity sweep below local swing low.
- Detect bearish liquidity sweep above local swing high.
- Produce directional LONG/SHORT signal with clear entry, stop loss and RR 1:3 target.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


@dataclass(slots=True)
class _SweepCandidate:
    direction: str
    score: float
    swing_level: float
    swing_source: str
    sweep_extreme: float
    entry: float
    stop_loss: float
    take_profit: float
    risk: float
    reward: float
    rr: float
    wick_ratio: float
    volume_ratio: float
    reasons: list[str]


class LiquiditySweepStrategy(BaseStrategy):
    """
    Liquidity Sweep / Stop Hunt strategy.

    LONG idea:
    - price sweeps below local swing low;
    - candle closes back above that swing low;
    - lower rejection wick confirms failed breakdown / stop hunt.

    SHORT idea:
    - price sweeps above local swing high;
    - candle closes back below that swing high;
    - upper rejection wick confirms failed breakout / stop hunt.
    """

    name = "LiquiditySweep"

    minimum_candles = 12

    pivot_left = 2
    pivot_right = 2
    pivot_lookback = 30

    target_rr = 3.0

    minimum_wick_to_range = 0.30
    minimum_wick_to_body = 1.00

    atr_stop_buffer = 0.10
    price_stop_buffer = 0.0005

    maximum_score = 95.0

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        """
        Analyze prepared market snapshot.
        """

        candles = snapshot.candles

        if len(candles) < self.minimum_candles:
            return None

        last_candle = candles[-1]

        if last_candle.range <= 0:
            return None

        long_candidate = self._build_long_candidate(snapshot)
        short_candidate = self._build_short_candidate(snapshot)

        candidates = [
            candidate
            for candidate in (long_candidate, short_candidate)
            if candidate is not None
        ]

        if not candidates:
            return None

        best_candidate = max(
            candidates,
            key=lambda candidate: (
                candidate.score,
                candidate.wick_ratio,
                candidate.volume_ratio,
            ),
        )

        signal = Signal(
            symbol=snapshot.symbol,
            market=self._market(snapshot),
            timeframe=self._timeframe(snapshot),
            strategy=self.name,
            direction=best_candidate.direction,
            score=best_candidate.score,
        )

        for reason in best_candidate.reasons:
            signal.add_reason(reason)

        signal.metadata.update(
            {
                "pattern": "liquidity_sweep_stop_hunt",
                "direction": best_candidate.direction,
                "swing_level": best_candidate.swing_level,
                "swing_source": best_candidate.swing_source,
                "reclaim_level": best_candidate.swing_level,
                "sweep_extreme": best_candidate.sweep_extreme,
                "entry": best_candidate.entry,
                "stop_loss": best_candidate.stop_loss,
                "take_profit": best_candidate.take_profit,
                "risk": best_candidate.risk,
                "reward": best_candidate.reward,
                "rr": best_candidate.rr,
                "wick_ratio": best_candidate.wick_ratio,
                "volume_ratio": best_candidate.volume_ratio,
                "atr14": snapshot.atr14,
            }
        )

        return signal

    def _build_long_candidate(
        self,
        snapshot: MarketSnapshot,
    ) -> _SweepCandidate | None:
        """
        Build LONG candidate after sweep below local swing low.
        """

        candles = snapshot.candles
        last_candle = candles[-1]

        swing = self._recent_swing_low(candles)

        if swing is None:
            return None

        swing_level, swing_source = swing

        swept_low = last_candle.low < swing_level
        reclaimed = last_candle.close > swing_level
        rejected = self._has_lower_rejection(last_candle)

        if not swept_low or not reclaimed or not rejected:
            return None

        entry = last_candle.close
        stop_loss = last_candle.low - self._stop_buffer(snapshot, entry)

        risk = entry - stop_loss

        if risk <= 0:
            return None

        reward = risk * self.target_rr
        take_profit = entry + reward

        wick_ratio = self._safe_ratio(
            last_candle.lower_wick,
            last_candle.range,
        )
        volume_ratio = self._volume_ratio(snapshot, last_candle)

        score = 80.0

        if swing_source == "pivot_low":
            score += 4.0

        if last_candle.bullish:
            score += 4.0

        if wick_ratio >= 0.45:
            score += 4.0

        if volume_ratio >= 1.20:
            score += 4.0

        if snapshot.ema20 > snapshot.ema50:
            score += 2.0

        if last_candle.close > snapshot.ema20:
            score += 2.0

        score = min(score, self.maximum_score)

        reasons = [
            "Liquidity sweep LONG: price swept local swing low and reclaimed it.",
            (
                "Stop hunt below liquidity: "
                f"sweep low={last_candle.low:.8g}, "
                f"reclaim level={swing_level:.8g}, "
                f"close={last_candle.close:.8g}."
            ),
            (
                "Lower rejection wick confirms failed breakdown: "
                f"wick ratio={wick_ratio:.2%}."
            ),
            (
                "Trade geometry prepared: "
                f"entry={entry:.8g}, "
                f"SL={stop_loss:.8g}, "
                f"TP={take_profit:.8g}, "
                f"RR={self.target_rr:.2f}."
            ),
        ]

        if volume_ratio >= 1.20:
            reasons.append(
                f"Volume expansion supports sweep: volume ratio={volume_ratio:.2f}."
            )

        if last_candle.close > snapshot.ema20:
            reasons.append("Close reclaimed above EMA20 after liquidity sweep.")

        return _SweepCandidate(
            direction="LONG",
            score=score,
            swing_level=swing_level,
            swing_source=swing_source,
            sweep_extreme=last_candle.low,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk=risk,
            reward=reward,
            rr=self.target_rr,
            wick_ratio=wick_ratio,
            volume_ratio=volume_ratio,
            reasons=reasons,
        )

    def _build_short_candidate(
        self,
        snapshot: MarketSnapshot,
    ) -> _SweepCandidate | None:
        """
        Build SHORT candidate after sweep above local swing high.
        """

        candles = snapshot.candles
        last_candle = candles[-1]

        swing = self._recent_swing_high(candles)

        if swing is None:
            return None

        swing_level, swing_source = swing

        swept_high = last_candle.high > swing_level
        reclaimed = last_candle.close < swing_level
        rejected = self._has_upper_rejection(last_candle)

        if not swept_high or not reclaimed or not rejected:
            return None

        entry = last_candle.close
        stop_loss = last_candle.high + self._stop_buffer(snapshot, entry)

        risk = stop_loss - entry

        if risk <= 0:
            return None

        reward = risk * self.target_rr
        take_profit = entry - reward

        wick_ratio = self._safe_ratio(
            last_candle.upper_wick,
            last_candle.range,
        )
        volume_ratio = self._volume_ratio(snapshot, last_candle)

        score = 80.0

        if swing_source == "pivot_high":
            score += 4.0

        if last_candle.bearish:
            score += 4.0

        if wick_ratio >= 0.45:
            score += 4.0

        if volume_ratio >= 1.20:
            score += 4.0

        if snapshot.ema20 < snapshot.ema50:
            score += 2.0

        if last_candle.close < snapshot.ema20:
            score += 2.0

        score = min(score, self.maximum_score)

        reasons = [
            "Liquidity sweep SHORT: price swept local swing high and reclaimed below it.",
            (
                "Stop hunt above liquidity: "
                f"sweep high={last_candle.high:.8g}, "
                f"reclaim level={swing_level:.8g}, "
                f"close={last_candle.close:.8g}."
            ),
            (
                "Upper rejection wick confirms failed breakout: "
                f"wick ratio={wick_ratio:.2%}."
            ),
            (
                "Trade geometry prepared: "
                f"entry={entry:.8g}, "
                f"SL={stop_loss:.8g}, "
                f"TP={take_profit:.8g}, "
                f"RR={self.target_rr:.2f}."
            ),
        ]

        if volume_ratio >= 1.20:
            reasons.append(
                f"Volume expansion supports sweep: volume ratio={volume_ratio:.2f}."
            )

        if last_candle.close < snapshot.ema20:
            reasons.append("Close rejected below EMA20 after liquidity sweep.")

        return _SweepCandidate(
            direction="SHORT",
            score=score,
            swing_level=swing_level,
            swing_source=swing_source,
            sweep_extreme=last_candle.high,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk=risk,
            reward=reward,
            rr=self.target_rr,
            wick_ratio=wick_ratio,
            volume_ratio=volume_ratio,
            reasons=reasons,
        )

    def _recent_swing_low(
        self,
        candles: list[Candle],
    ) -> tuple[float, str] | None:
        """
        Find recent pivot swing low.

        Fallback:
        - if no strict pivot exists, use recent range low before current candle.
        """

        pivot = self._recent_pivot_low(candles)

        if pivot is not None:
            return pivot, "pivot_low"

        previous_candles = candles[:-1]
        window = previous_candles[-self.pivot_lookback :]

        if not window:
            return None

        return min(candle.low for candle in window), "range_low"

    def _recent_swing_high(
        self,
        candles: list[Candle],
    ) -> tuple[float, str] | None:
        """
        Find recent pivot swing high.

        Fallback:
        - if no strict pivot exists, use recent range high before current candle.
        """

        pivot = self._recent_pivot_high(candles)

        if pivot is not None:
            return pivot, "pivot_high"

        previous_candles = candles[:-1]
        window = previous_candles[-self.pivot_lookback :]

        if not window:
            return None

        return max(candle.high for candle in window), "range_high"

    def _recent_pivot_low(
        self,
        candles: list[Candle],
    ) -> float | None:
        """
        Find latest local swing low before current candle.
        """

        last_allowed_index = len(candles) - 2 - self.pivot_right
        first_allowed_index = max(
            self.pivot_left,
            last_allowed_index - self.pivot_lookback,
        )

        if last_allowed_index < first_allowed_index:
            return None

        for index in range(last_allowed_index, first_allowed_index - 1, -1):
            current_low = candles[index].low

            left_lows = [
                candles[index - offset].low
                for offset in range(1, self.pivot_left + 1)
            ]
            right_lows = [
                candles[index + offset].low
                for offset in range(1, self.pivot_right + 1)
            ]

            if current_low <= min(left_lows) and current_low <= min(right_lows):
                return current_low

        return None

    def _recent_pivot_high(
        self,
        candles: list[Candle],
    ) -> float | None:
        """
        Find latest local swing high before current candle.
        """

        last_allowed_index = len(candles) - 2 - self.pivot_right
        first_allowed_index = max(
            self.pivot_left,
            last_allowed_index - self.pivot_lookback,
        )

        if last_allowed_index < first_allowed_index:
            return None

        for index in range(last_allowed_index, first_allowed_index - 1, -1):
            current_high = candles[index].high

            left_highs = [
                candles[index - offset].high
                for offset in range(1, self.pivot_left + 1)
            ]
            right_highs = [
                candles[index + offset].high
                for offset in range(1, self.pivot_right + 1)
            ]

            if current_high >= max(left_highs) and current_high >= max(right_highs):
                return current_high

        return None

    def _has_lower_rejection(
        self,
        candle: Candle,
    ) -> bool:
        """
        Check lower rejection wick quality.
        """

        return (
            candle.lower_wick >= candle.range * self.minimum_wick_to_range
            and candle.lower_wick >= candle.body * self.minimum_wick_to_body
        )

    def _has_upper_rejection(
        self,
        candle: Candle,
    ) -> bool:
        """
        Check upper rejection wick quality.
        """

        return (
            candle.upper_wick >= candle.range * self.minimum_wick_to_range
            and candle.upper_wick >= candle.body * self.minimum_wick_to_body
        )

    def _stop_buffer(
        self,
        snapshot: MarketSnapshot,
        price: float,
    ) -> float:
        """
        Stop buffer below/above sweep extreme.
        """

        atr_buffer = snapshot.atr14 * self.atr_stop_buffer
        price_buffer = price * self.price_stop_buffer

        return max(
            atr_buffer,
            price_buffer,
        )

    def _volume_ratio(
        self,
        snapshot: MarketSnapshot,
        candle: Candle,
    ) -> float:
        """
        Last candle volume relative to average volume.
        """

        if snapshot.avg_volume20 <= 0:
            return 1.0

        return candle.volume / snapshot.avg_volume20

    def _safe_ratio(
        self,
        numerator: float,
        denominator: float,
    ) -> float:
        """
        Safe division helper.
        """

        if denominator <= 0:
            return 0.0

        return numerator / denominator

    def _market(
        self,
        snapshot: MarketSnapshot,
    ) -> str:
        """
        Preserve future snapshot.market compatibility.

        Current MarketSnapshot does not expose market.
        """

        return str(
            getattr(
                snapshot,
                "market",
                "crypto",
            )
        )

    def _timeframe(
        self,
        snapshot: MarketSnapshot,
    ) -> str:
        """
        Preserve future snapshot.timeframe compatibility.

        Current MarketSnapshot does not expose timeframe.
        """

        return str(
            getattr(
                snapshot,
                "timeframe",
                "15m",
            )
        )