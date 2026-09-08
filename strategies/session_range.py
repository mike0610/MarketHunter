"""MarketHunter - Session Range Expansion research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class SessionRangeStrategy(BaseStrategy):
    """1h-only UTC session-range expansion after the Asia window is complete."""
    name="SessionRange"
    target_rr=3.0
    minimum_candles=30
    asia_start_hour=0
    asia_end_hour=8

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        trigger=cs[-1]
        # Strategy is wired only into the 1h scanner. Use same UTC calendar day.
        day=trigger.open_time.date()
        asia=[c for c in cs if c.open_time.date()==day and self.asia_start_hour<=c.open_time.hour<self.asia_end_hour]
        if len(asia)<6:return None
        high=max(c.high for c in asia); low=min(c.low for c in asia)
        if trigger.open_time.hour<self.asia_end_hour:return None
        range_size=high-low
        if range_size<=0:return None
        # Avoid trading pathological oversized session ranges.
        if range_size>snapshot.atr14*4:return None
        if trigger.close>high and trigger.bullish and trigger.range>=snapshot.atr14*.8:
            return self._build(snapshot,"LONG",high,trigger.close,trigger.low,range_size)
        if trigger.close<low and trigger.bearish and trigger.range>=snapshot.atr14*.8:
            return self._build(snapshot,"SHORT",low,trigger.close,trigger.high,range_size)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,session_range):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,85.0+(4.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason("UTC Asia session range completed before the trigger.")
        s.add_reason(f"{direction} close expanded beyond the completed session boundary.")
        s.metadata.update({"pattern":"session_range_expansion","session":"asia_00_08_utc","session_boundary":level,"session_range":session_range,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
