"""MarketHunter - Volume Confirmed Breakout research strategy."""
from __future__ import annotations

from statistics import median

from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class VolumeConfirmedBreakoutStrategy(BaseStrategy):
    """Range breakout requiring participation and clean continuation geometry."""

    name = "VolumeConfirmedBreakout"
    minimum_candles = 30
    lookback = 20
    target_rr = 3.0

    min_volume_ratio = 1.5
    min_trade_ratio = 1.35
    min_body_fraction = 0.55
    max_opposing_wick_fraction = 0.25
    max_extension_atr = 0.75

    async def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        cs = snapshot.candles
        if len(cs) < self.minimum_candles or snapshot.atr14 <= 0:
            return None

        trigger = cs[-1]
        hist = cs[-(self.lookback + 1) : -1]
        high = max(c.high for c in hist)
        low = min(c.low for c in hist)
        med_vol = median(c.volume for c in hist)
        med_trades = median(c.trades for c in hist)
        if med_vol <= 0 or med_trades <= 0 or trigger.range <= 0:
            return None

        vol_ratio = trigger.volume / med_vol
        trade_ratio = trigger.trades / med_trades
        participation = (
            vol_ratio >= self.min_volume_ratio
            and trade_ratio >= self.min_trade_ratio
        )
        if not participation or trigger.range < snapshot.atr14:
            return None

        if trigger.close > high and trigger.bullish:
            return self._candidate(
                snapshot, trigger, "LONG", high, vol_ratio, trade_ratio
            )

        if trigger.close < low and trigger.bearish:
            return self._candidate(
                snapshot, trigger, "SHORT", low, vol_ratio, trade_ratio
            )

        return None

    def _candidate(
        self,
        snapshot,
        trigger,
        direction,
        level,
        vol_ratio,
        trade_ratio,
    ):
        trend_ok = (
            snapshot.ema20 > snapshot.ema50
            if direction == "LONG"
            else snapshot.ema20 < snapshot.ema50
        )
        if not trend_ok:
            return None

        body_fraction = trigger.body / trigger.range
        opposing_wick = (
            trigger.upper_wick if direction == "LONG" else trigger.lower_wick
        )
        opposing_wick_fraction = opposing_wick / trigger.range
        extension_atr = abs(trigger.close - level) / snapshot.atr14

        # A volume spike alone is not continuation evidence. Reject weak
        # closes, rejection wicks and already-overextended breakout closes.
        if body_fraction < self.min_body_fraction:
            return None
        if opposing_wick_fraction > self.max_opposing_wick_fraction:
            return None
        if extension_atr > self.max_extension_atr:
            return None

        extreme = trigger.low if direction == "LONG" else trigger.high
        return self._build(
            snapshot,
            direction,
            level,
            trigger.close,
            extreme,
            vol_ratio,
            trade_ratio,
            body_fraction,
            opposing_wick_fraction,
            extension_atr,
        )

    def _build(
        self,
        snapshot,
        direction,
        level,
        entry,
        extreme,
        vol_ratio,
        trade_ratio,
        body_fraction,
        opposing_wick_fraction,
        extension_atr,
    ):
        buffer = max(snapshot.atr14 * 0.10, entry * 0.0005)
        stop = extreme - buffer if direction == "LONG" else extreme + buffer
        risk = entry - stop if direction == "LONG" else stop - entry
        if risk <= 0:
            return None

        target = entry + 3 * risk if direction == "LONG" else entry - 3 * risk
        score = min(95.0, 91.0 + min(4.0, (vol_ratio - 1.5) * 2))
        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="",
            strategy=self.name,
            direction=direction,
            score=score,
        )
        signal.add_reason(
            "Price closed beyond the prior range with elevated relative volume."
        )
        signal.add_reason(
            "Trade-count participation confirms that the breakout was broadly active."
        )
        signal.add_reason(
            "Breakout is trend-aligned and passes close-quality/extension guards."
        )
        signal.metadata.update(
            {
                "pattern": "volume_confirmed_breakout",
                "breakout_level": level,
                "volume_ratio": vol_ratio,
                "trade_count_ratio": trade_ratio,
                "entry": entry,
                "stop_loss": stop,
                "take_profit": target,
                "rr": 3.0,
                "trend_alignment": "with_trend",
                "body_fraction": body_fraction,
                "opposing_wick_fraction": opposing_wick_fraction,
                "breakout_extension_atr": extension_atr,
            }
        )
        return signal
