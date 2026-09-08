"""MarketHunter - Taker Flow Continuation research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class TakerFlowContinuationStrategy(BaseStrategy):
    """Trade accepted range expansion when aggressive taker flow confirms price direction."""
    name="TakerFlowContinuation"
    minimum_candles=25
    flow_window=3
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        w=cs[-self.flow_window:]; hist=cs[-20:-self.flow_window]
        if not hist:return None
        total=sum(c.volume for c in w)
        if total<=0:return None
        buy_share=sum(c.taker_buy_base_volume for c in w)/total
        high=max(c.high for c in hist); low=min(c.low for c in hist)
        first,last=w[0],w[-1]
        move=(last.close-first.open)/first.open if first.open else 0.0
        # Require both aggressive flow and price acceptance outside the prior range.
        if buy_share>=0.62 and last.close>high and move>=0.006 and last.bullish:
            return self._build(snapshot,"LONG",high,last.close,min(c.low for c in w),buy_share,move)
        if buy_share<=0.38 and last.close<low and move<=-0.006 and last.bearish:
            return self._build(snapshot,"SHORT",low,last.close,max(c.high for c in w),buy_share,move)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,buy_share,move):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,88.0+(4.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason("Aggressive taker flow and price expansion agree.")
        s.add_reason(f"{direction} close accepted beyond the prior range.")
        s.metadata.update({"pattern":"taker_flow_continuation","taker_buy_share":buy_share,"window_price_change":move,"acceptance_level":level,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
