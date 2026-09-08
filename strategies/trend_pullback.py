"""MarketHunter - Trend Pullback research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class TrendPullbackStrategy(BaseStrategy):
    """Continuation after a controlled pullback into EMA20 in an established trend."""
    name = "TrendPullback"
    minimum_candles = 50
    minimum_score = 80.0
    maximum_score = 95.0

    async def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        if len(snapshot.candles) < self.minimum_candles or snapshot.atr14 <= 0:
            return None
        c = snapshot.candles[-1]
        p = snapshot.candles[-2]
        long_trend = snapshot.ema20 > snapshot.ema50 > snapshot.ema200
        short_trend = snapshot.ema20 < snapshot.ema50 < snapshot.ema200
        if long_trend:
            touched = c.low <= snapshot.ema20 or p.low <= snapshot.ema20
            reclaimed = c.close > snapshot.ema20 and c.close > c.open
            if touched and reclaimed:
                return self._signal(snapshot, "LONG", c.close, min(c.low,p.low), True)
        if short_trend:
            touched = c.high >= snapshot.ema20 or p.high >= snapshot.ema20
            reclaimed = c.close < snapshot.ema20 and c.close < c.open
            if touched and reclaimed:
                return self._signal(snapshot, "SHORT", c.close, max(c.high,p.high), True)
        return None

    def _signal(self, snapshot: MarketSnapshot, direction: str, entry: float, structural: float, confirmed: bool) -> Signal | None:
        buffer = max(snapshot.atr14 * 0.10, entry * 0.0005)
        stop = structural - buffer if direction == "LONG" else structural + buffer
        risk = entry-stop if direction == "LONG" else stop-entry
        if risk <= 0:
            return None
        target = entry + 3*risk if direction == "LONG" else entry - 3*risk
        separation = abs(snapshot.ema20-snapshot.ema50)/snapshot.atr14
        score = min(self.maximum_score, 80.0 + min(8.0,separation*4.0) + (4.0 if confirmed else 0.0))
        if score < self.minimum_score:
            return None
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason(f"{direction} trend continuation: EMA20/EMA50/EMA200 aligned.")
        s.add_reason("Controlled pullback touched EMA20 and closed back with trend.")
        s.metadata.update({"pattern":"trend_pullback","entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend","ema20":snapshot.ema20,"ema50":snapshot.ema50,"ema200":snapshot.ema200})
        return s
