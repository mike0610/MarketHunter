"""Yahoo/OOS comparison for frozen PULLBACK LONG 3-trading-bar expiry hypothesis."""
from __future__ import annotations
import asyncio
from decimal import Decimal
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from research.pullback_validation import validate_pullback_entries
UNIVERSE=("SPY","QQQ","AAPL","MSFT","NVDA");HISTORY_BARS=1300;DEVELOPMENT_FRACTION=Decimal("0.70");EXPIRY_BARS=3
def sl(series,start,end):
 return MarketSeries(instrument=series.instrument,timeframe=series.timeframe,bars=series.bars[start:end],provider=series.provider,source_reference=series.source_reference,observed_at=series.observed_at,available_at=series.available_at)
def oos(series,expiry):
 split=int(Decimal(len(series.bars))*DEVELOPMENT_FRACTION);start=max(0,split-50);raw=validate_pullback_entries(sl(series,start,len(series.bars)),expiry);warmup=split-start
 return tuple(o for o in raw.observations if o.signal_index>=warmup)
def stats(obs):
 return {"signals":len(obs),"fills":sum(o.status=="FILLED" for o in obs),"expired":sum(o.status=="EXPIRED" for o in obs),"invalidated":sum(o.status=="INVALIDATED_BEFORE_FILL" for o in obs),"ambiguous":sum(o.status=="AMBIGUOUS_NO_FILL" for o in obs),"censored":sum(o.status=="CENSORED" for o in obs),"gaps":sum(o.status=="FILLED" and o.fill_price is not None and o.fill_price>o.trigger_price for o in obs)}
async def run():
 p=YahooChartDailyProvider(UNIVERSE);out=[]
 for ins in await p.universe():
  series=await p.history(ins,limit=HISTORY_BARS);out.append((ins.symbol,oos(series,None),oos(series,EXPIRY_BARS)))
 return out
def main():
 rows=asyncio.run(run());ua=[];ea=[]
 for sym,u,e in rows:
  ua+=list(u);ea+=list(e);su=stats(u);se=stats(e)
  print(f"{sym}: uncapped={su} expiry3={se} fill_retention={se['fills']/su['fills'] if su['fills'] else 0:.4f}")
 su=stats(ua);se=stats(ea)
 print(f"OOS TOTAL UNCAPPED: {su}")
 print(f"OOS TOTAL EXPIRY3: {se}")
 print(f"FILL RETENTION: {se['fills']/su['fills'] if su['fills'] else 0:.4f}")
if __name__=="__main__":main()
