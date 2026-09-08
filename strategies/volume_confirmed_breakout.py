"""MarketHunter - Volume Confirmed Breakout research strategy."""
from __future__ import annotations
from statistics import median
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class VolumeConfirmedBreakoutStrategy(BaseStrategy):
    """Range breakout requiring relative volume and trade-count participation."""
    name="VolumeConfirmedBreakout"
    minimum_candles=30
    lookback=20
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        trigger=cs[-1]; hist=cs[-(self.lookback+1):-1]
        high=max(c.high for c in hist); low=min(c.low for c in hist)
        med_vol=median(c.volume for c in hist); med_trades=median(c.trades for c in hist)
        if med_vol<=0 or med_trades<=0:return None
        vol_ratio=trigger.volume/med_vol; trade_ratio=trigger.trades/med_trades
        participation=vol_ratio>=1.5 and trade_ratio>=1.35
        if not participation or trigger.range<snapshot.atr14:return None
        if trigger.close>high and trigger.bullish:
            return self._build(snapshot,"LONG",high,trigger.close,trigger.low,vol_ratio,trade_ratio)
        if trigger.close<low and trigger.bearish:
            return self._build(snapshot,"SHORT",low,trigger.close,trigger.high,vol_ratio,trade_ratio)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,vol_ratio,trade_ratio):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,88.0+(3.0 if trend_ok else 0.0)+min(3.0,(vol_ratio-1.5)*2))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason("Price closed beyond the prior range with elevated relative volume.")
        s.add_reason("Trade-count participation confirms that the breakout was broadly active.")
        s.metadata.update({"pattern":"volume_confirmed_breakout","breakout_level":level,"volume_ratio":vol_ratio,"trade_count_ratio":trade_ratio,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
