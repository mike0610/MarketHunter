"""MarketHunter - Taker Flow Absorption research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class TakerFlowAbsorptionStrategy(BaseStrategy):
    """Use Binance kline taker-buy volume to detect aggressive-flow/price divergence."""
    name="TakerFlowAbsorption"
    minimum_candles=25
    flow_window=3
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        w=cs[-self.flow_window:]
        total=sum(c.volume for c in w)
        if total<=0:return None
        taker_buy=sum(c.taker_buy_base_volume for c in w)
        buy_share=taker_buy/total
        first,last=w[0],w[-1]
        price_change=(last.close-first.open)/first.open if first.open else 0.0
        recent_low=min(c.low for c in cs[-20:-self.flow_window])
        recent_high=max(c.high for c in cs[-20:-self.flow_window])

        # Sellers dominate aggressively, but price refuses to extend lower and reclaims.
        if buy_share<=0.38 and min(c.low for c in w)<recent_low and last.close>recent_low and price_change>=-0.003 and last.bullish:
            return self._build(snapshot,"LONG",recent_low,last.close,min(c.low for c in w),buy_share,price_change)

        # Buyers dominate aggressively, but price refuses to extend higher and rejects.
        if buy_share>=0.62 and max(c.high for c in w)>recent_high and last.close<recent_high and price_change<=0.003 and last.bearish:
            return self._build(snapshot,"SHORT",recent_high,last.close,max(c.high for c in w),buy_share,price_change)
        return None

    def _build(self,snapshot,direction,level,entry,extreme,buy_share,price_change):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=90.0)
        s.add_reason("Aggressive taker flow diverged from price extension.")
        s.add_reason(f"{direction} absorption confirmed by reclaim/rejection of the recent range extreme.")
        s.metadata.update({"pattern":"taker_flow_absorption","taker_buy_share":buy_share,"window_price_change":price_change,"reference_level":level,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0})
        return s
