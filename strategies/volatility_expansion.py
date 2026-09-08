"""MarketHunter - Volatility Expansion research strategy."""
from __future__ import annotations
from statistics import median
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class VolatilityExpansionStrategy(BaseStrategy):
    """Trade directional expansion only after a measurable quiet regime."""
    name="VolatilityExpansion"
    minimum_candles=35
    quiet_window=12
    baseline_window=20
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        trigger=cs[-1]; quiet=cs[-(self.quiet_window+1):-1]; baseline=cs[-(self.baseline_window+self.quiet_window+1):-(self.quiet_window+1)]
        if len(quiet)<self.quiet_window or len(baseline)<self.baseline_window:return None
        q=median([x.range for x in quiet]); b=median([x.range for x in baseline])
        if b<=0 or q/b>0.65:return None
        qhigh=max(x.high for x in quiet); qlow=min(x.low for x in quiet)
        expansion=trigger.range>=max(snapshot.atr14*1.25,q*1.75)
        if not expansion:return None
        if trigger.close>qhigh and trigger.bullish:return self._build(snapshot,"LONG",qhigh,trigger.close,trigger.low,q/b,trigger.range/snapshot.atr14)
        if trigger.close<qlow and trigger.bearish:return self._build(snapshot,"SHORT",qlow,trigger.close,trigger.high,q/b,trigger.range/snapshot.atr14)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,quiet_ratio,expansion_ratio):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,84.0+(4.0 if trend_ok else 0.0)+min(5.0,max(0.0,(expansion_ratio-1.25)*4)))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason("Measured quiet regime preceded directional volatility expansion.")
        s.add_reason(f"{direction} trigger closed outside the quiet range.")
        s.metadata.update({"pattern":"volatility_expansion","quiet_boundary":level,"quiet_range_ratio":quiet_ratio,"trigger_atr_ratio":expansion_ratio,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
