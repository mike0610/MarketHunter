"""MarketHunter - Momentum Acceleration research strategy."""
from __future__ import annotations
from statistics import median
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class MomentumAccelerationStrategy(BaseStrategy):
    """Trade accelerating directional returns with expanding participation."""
    name="MomentumAcceleration"
    minimum_candles=30
    window=4
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        w=cs[-self.window:]; hist=cs[-24:-self.window]
        if len(hist)<20:return None
        med_range=median(c.range for c in hist); med_vol=median(c.volume for c in hist)
        if med_range<=0 or med_vol<=0:return None
        rets=[(c.close-c.open)/c.open if c.open else 0.0 for c in w]
        ranges=[c.range for c in w]
        vols=[c.volume for c in w]
        long_accel=all(r>0 for r in rets) and rets[-1]>rets[-2]>rets[-3] and ranges[-1]>ranges[-2] and vols[-1]>=med_vol*1.25
        short_accel=all(r<0 for r in rets) and abs(rets[-1])>abs(rets[-2])>abs(rets[-3]) and ranges[-1]>ranges[-2] and vols[-1]>=med_vol*1.25
        if long_accel and snapshot.ema20>snapshot.ema50>snapshot.ema200 and w[-1].range>=med_range*1.25:
            return self._build(snapshot,"LONG",w[-1].close,min(c.low for c in w),rets,vols[-1]/med_vol)
        if short_accel and snapshot.ema20<snapshot.ema50<snapshot.ema200 and w[-1].range>=med_range*1.25:
            return self._build(snapshot,"SHORT",w[-1].close,max(c.high for c in w),rets,vols[-1]/med_vol)
        return None

    def _build(self,snapshot,direction,entry,extreme,returns,volume_ratio):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=91.0)
        s.add_reason("Directional candle returns accelerated across the recent window.")
        s.add_reason("Range expansion, relative volume and full EMA alignment confirm momentum.")
        s.metadata.update({"pattern":"momentum_acceleration","recent_returns":returns,"volume_ratio":volume_ratio,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend"})
        return s
