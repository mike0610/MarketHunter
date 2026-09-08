"""MarketHunter - Failed Auction research strategy."""
from __future__ import annotations
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy

class FailedAuctionStrategy(BaseStrategy):
    """Detect failed acceptance beyond a prior range after multiple closes outside."""
    name="FailedAuction"
    minimum_candles=32
    lookback=24
    target_rr=3.0

    async def analyze(self,snapshot:MarketSnapshot)->Signal|None:
        cs=snapshot.candles
        if len(cs)<self.minimum_candles or snapshot.atr14<=0:return None
        auction1,auction2,return_bar=cs[-3],cs[-2],cs[-1]
        hist=cs[-(self.lookback+3):-3]
        if not hist:return None
        low=min(c.low for c in hist); high=max(c.high for c in hist)

        failed_down=(auction1.close<low and auction2.close<low and return_bar.close>low and return_bar.bullish)
        if failed_down:
            return self._build(snapshot,"LONG",low,return_bar.close,min(auction1.low,auction2.low,return_bar.low))

        failed_up=(auction1.close>high and auction2.close>high and return_bar.close<high and return_bar.bearish)
        if failed_up:
            return self._build(snapshot,"SHORT",high,return_bar.close,max(auction1.high,auction2.high,return_bar.high))

        return None

    def _build(self,snapshot,direction,level,entry,extreme):
        buffer=max(snapshot.atr14*.10,entry*.0005)
        stop=extreme-buffer if direction=="LONG" else extreme+buffer
        risk=entry-stop if direction=="LONG" else stop-entry
        if risk<=0:return None
        target=entry+3*risk if direction=="LONG" else entry-3*risk
        trend_ok=snapshot.ema20>snapshot.ema50 if direction=="LONG" else snapshot.ema20<snapshot.ema50
        score=min(95.0,87.0+(3.0 if trend_ok else 0.0))
        s=Signal(symbol=snapshot.symbol,market="",timeframe="",strategy=self.name,direction=direction,score=score)
        s.add_reason(f"{direction} failed auction: two closes beyond the prior range failed to gain acceptance.")
        s.add_reason("Price returned through the boundary with directional confirmation.")
        s.metadata.update({"pattern":"failed_auction","auction_boundary":level,"entry":entry,"stop_loss":stop,"take_profit":target,"rr":3.0,"trend_alignment":"with_trend" if trend_ok else "trend_unknown"})
        return s
