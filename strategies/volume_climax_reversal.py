"""MarketHunter - Volume Climax Reversal research strategy."""
from __future__ import annotations
from statistics import median
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class VolumeClimaxReversalStrategy(BaseStrategy):
    """Fade a volume/range climax only after rejection and next-bar confirmation."""
    name="VolumeClimaxReversal"
    minimum_candles=30
    lookback=20
    target_rr=2.5

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        climax,confirm=cs[-2],cs[-1]; hist=cs[-(self.lookback+2):-2]
        vols=[c.volume for c in hist]; ranges=[c.range for c in hist]
        med_vol=median(vols); med_range=median(ranges)
        if med_vol<=0 or med_range<=0:return None
        if climax.volume<med_vol*2.0 or climax.range<max(med_range*1.5,snapshot.atr14*1.2):return None
        body=max(climax.body,1e-12)
        upper_ratio=climax.upper_wick/body; lower_ratio=climax.lower_wick/body
        recent_low=min(c.low for c in hist); recent_high=max(c.high for c in hist)
        if climax.low<recent_low and lower_ratio>=1.25 and confirm.bullish and confirm.close>climax.open:
            return self._build(snapshot,"LONG",confirm.close,climax.low,climax.volume/med_vol,climax.range/med_range)
        if climax.high>recent_high and upper_ratio>=1.25 and confirm.bearish and confirm.close<climax.open:
            return self._build(snapshot,"SHORT",confirm.close,climax.high,climax.volume/med_vol,climax.range/med_range)
        return None

    def _build(self,snapshot,direction,entry,extreme,volume_ratio,range_ratio):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+self.target_rr*risk if direction=="LONG" else entry-self.target_rr*risk
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=90.0)
        s.add_reason("Volume and candle range reached a local climax at a range extreme.")
        s.add_reason("Long rejection wick plus a separate confirmation candle supports reversal.")
        s.metadata.update({"pattern":"volume_climax_reversal","volume_ratio":volume_ratio,"range_ratio":range_ratio,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":self.target_rr})
        return s
