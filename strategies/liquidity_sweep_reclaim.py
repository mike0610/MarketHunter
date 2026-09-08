"""MarketHunter - Liquidity Sweep Reclaim research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class LiquiditySweepReclaimStrategy(BaseStrategy):
    """Two-step stop-hunt strategy: sweep/reclaim first, continuation confirmation next."""
    name="LiquiditySweepReclaim"
    minimum_candles=25
    lookback=20
    target_rr=3.0
    maximum_score=95.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        sweep,confirm=cs[-2],cs[-1]
        history=cs[-(self.lookback+2):-2]
        if not history:return None
        low=min(c.low for c in history); high=max(c.high for c in history)
        bullish_sweep=sweep.low<low and sweep.close>low
        bullish_confirm=confirm.close>sweep.high and confirm.bullish
        if bullish_sweep and bullish_confirm:
            return self._build(snapshot,"LONG",low,confirm.close,sweep.low,sweep,confirm)
        bearish_sweep=sweep.high>high and sweep.close<high
        bearish_confirm=confirm.close<sweep.low and confirm.bearish
        if bearish_sweep and bearish_confirm:
            return self._build(snapshot,"SHORT",high,confirm.close,sweep.high,sweep,confirm)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,sweep,confirm):
        buffer=max(snapshot.atr14*0.10,entry*0.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+self.target_rr*risk if direction=="LONG" else entry-self.target_rr*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(self.maximum_score,86.0+(4.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason(f"{direction} liquidity sweep reclaimed the prior range boundary.")
        s.add_reason("A separate confirmation candle closed beyond the sweep candle in the reversal direction.")
        s.metadata.update({"pattern":"liquidity_sweep_reclaim","liquidity_level":level,"sweep_extreme":extreme,"confirmation_close":confirm.close,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":self.target_rr,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
