"""MarketHunter - Statistical Mean Reversion research strategy."""
from __future__ import annotations
from statistics import mean,pstdev
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class StatisticalMeanReversionStrategy(BaseStrategy):
    """Fade statistically extreme closes only after a reversal candle confirms."""
    name="StatisticalMeanReversion"
    minimum_candles=35
    lookback=30
    z_threshold=2.0
    target_rr=2.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        trigger=cs[-1]; hist=cs[-(self.lookback+1):-1]
        closes=[c.close for c in hist]; mu=mean(closes); sd=pstdev(closes)
        if sd<=0:return None
        prior=cs[-2]; z=(prior.close-mu)/sd
        # Avoid fading a strongly ordered EMA regime; this is a range/weak-trend hypothesis.
        ema_spread=abs(snapshot.ema20-snapshot.ema50)/snapshot.atr14
        if ema_spread>1.5:return None
        if z<=-self.z_threshold and trigger.bullish and trigger.close>prior.high:
            return self._build(snapshot,"LONG",mu,trigger.close,min(prior.low,trigger.low),z,ema_spread)
        if z>=self.z_threshold and trigger.bearish and trigger.close<prior.low:
            return self._build(snapshot,"SHORT",mu,trigger.close,max(prior.high,trigger.high),z,ema_spread)
        return None

    def _build(self,snapshot,direction,mu,entry,extreme,z,ema_spread):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        rr_target=entry+self.target_rr*risk if direction=="LONG" else entry-self.target_rr*risk
        # Mean is informative but never force a target through the entry.
        target=min(rr_target,mu) if direction=="LONG" and mu>entry else max(rr_target,mu) if direction=="SHORT" and mu<entry else rr_target
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=88.0)
        s.add_reason(f"Prior close reached a statistical extreme (z={z:.2f}).")
        s.add_reason("A separate reversal candle confirmed mean-reversion intent.")
        s.metadata.update({"pattern":"statistical_mean_reversion","zscore":z,"mean_close":mu,"ema_spread_atr":ema_spread,"entry":entry,"stop_loss":stop,"take_profit":target,"rr_cap":self.target_rr})
        return s
