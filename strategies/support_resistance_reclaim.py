"""MarketHunter - Support/Resistance Reclaim research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class SupportResistanceReclaimStrategy(BaseStrategy):
    """Failed displacement through a range boundary followed by reclaim and hold."""
    name="SupportResistanceReclaim"
    minimum_candles=30
    lookback=24
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        displacement,reclaim,hold=cs[-3],cs[-2],cs[-1]
        hist=cs[-(self.lookback+3):-3]
        if not hist:return None
        support=min(c.low for c in hist); resistance=max(c.high for c in hist)
        if displacement.close<support and reclaim.close>support and hold.low>=support and hold.close>reclaim.close and hold.bullish:
            return self._build(snapshot,"LONG",support,hold.close,min(displacement.low,reclaim.low))
        if displacement.close>resistance and reclaim.close<resistance and hold.high<=resistance and hold.close<reclaim.close and hold.bearish:
            return self._build(snapshot,"SHORT",resistance,hold.close,max(displacement.high,reclaim.high))
        return None

    def _build(self,snapshot,direction,level,entry,extreme):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,85.0+(4.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason(f"{direction} range-boundary reclaim held after failed displacement.")
        s.add_reason("A separate hold candle confirmed acceptance back through the reclaimed level.")
        s.metadata.update({"pattern":"support_resistance_reclaim","reclaim_level":level,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
