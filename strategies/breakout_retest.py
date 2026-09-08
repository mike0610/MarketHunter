"""MarketHunter - Breakout Retest research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class BreakoutRetestStrategy(BaseStrategy):
    """Continuation only after a prior range breakout is retested and held."""
    name = "BreakoutRetest"
    minimum_candles = 25
    lookback = 20
    target_rr = 3.0
    maximum_score = 95.0

    async def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        candles=snapshot.candles
        if len(candles)<self.minimum_candles or snapshot.atr14<=0:return None
        breakout=candles[-2]; retest=candles[-1]
        history=candles[-(self.lookback+2):-2]
        if not history:return None
        resistance=max(c.high for c in history); support=min(c.low for c in history)
        if breakout.close>resistance and retest.low<=resistance and retest.close>resistance and retest.bullish:
            return self._build(snapshot,"LONG",resistance,retest.close,retest.low)
        if breakout.close<support and retest.high>=support and retest.close<support and retest.bearish:
            return self._build(snapshot,"SHORT",support,retest.close,retest.high)
        return None

    def _build(self,snapshot,direction,level,entry,extreme):
        buffer=max(snapshot.atr14*0.10,entry*0.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+self.target_rr*risk if direction=="LONG" else entry-self.target_rr*risk
        trend_ok=(snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50)
        score=min(self.maximum_score,84.0+(5.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason(f"{direction} breakout was followed by a successful retest of the broken range level.")
        s.add_reason("Retest candle closed back on the continuation side of the level.")
        s.metadata.update({"pattern":"breakout_retest","breakout_level":level,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":self.target_rr,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
