"""Yahoo/OOS runner for frozen PULLBACK LONG reclaim-entry hypothesis."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from research.pullback_validation import PullbackValidationSummary,validate_pullback_entries

UNIVERSE=("SPY","QQQ","AAPL","MSFT","NVDA"); HISTORY_BARS=1300; DEVELOPMENT_FRACTION=Decimal("0.70")

@dataclass(frozen=True,slots=True)
class SymbolResult:
 symbol:str; total_bars:int; split_index:int; development:PullbackValidationSummary; out_of_sample:PullbackValidationSummary

def _slice(series,start,end):
 return MarketSeries(instrument=series.instrument,timeframe=series.timeframe,bars=series.bars[start:end],provider=series.provider,source_reference=series.source_reference,observed_at=series.observed_at,available_at=series.available_at)

def _summary(obs):
 return PullbackValidationSummary(len(obs),sum(o.status=="FILLED" for o in obs),sum(o.status=="INVALIDATED_BEFORE_FILL" for o in obs),sum(o.status=="AMBIGUOUS_NO_FILL" for o in obs),sum(o.status=="CENSORED" for o in obs),sum(o.status=="FILLED" and o.fill_price is not None and o.fill_price>o.trigger_price for o in obs),tuple(obs))

def split_and_validate(series):
 if len(series.bars)<250: raise ValueError("insufficient history")
 split=int(Decimal(len(series.bars))*DEVELOPMENT_FRACTION)
 dev=validate_pullback_entries(_slice(series,0,split))
 start=max(0,split-50); raw=validate_pullback_entries(_slice(series,start,len(series.bars))); warmup=split-start
 kept=tuple(o for o in raw.observations if o.signal_index>=warmup)
 return SymbolResult(series.instrument.symbol,len(series.bars),split,dev,_summary(kept))

async def run():
 p=YahooChartDailyProvider(UNIVERSE); instruments=await p.universe(); out=[]
 for instrument in instruments: out.append(split_and_validate(await p.history(instrument,limit=HISTORY_BARS)))
 return tuple(out)

def main():
 rows=asyncio.run(run()); all_oos=[]
 for x in rows:
  o=x.out_of_sample; times=[z.bars_to_trigger for z in o.observations if z.bars_to_trigger is not None]
  all_oos.extend(o.observations)
  print(f"{x.symbol}: bars={x.total_bars} dev={x.development.signals}/{x.development.fills} oos signals={o.signals} fills={o.fills} invalidated={o.invalidated_before_fill} ambiguous={o.ambiguous_no_fill} censored={o.censored} gaps={o.gap_entries} trigger_bars_min/median/max={_dist(times)}")
 times=[z.bars_to_trigger for z in all_oos if z.bars_to_trigger is not None]
 print(f"OOS TOTAL: signals={len(all_oos)} fills={sum(z.status=='FILLED' for z in all_oos)} invalidated={sum(z.status=='INVALIDATED_BEFORE_FILL' for z in all_oos)} ambiguous={sum(z.status=='AMBIGUOUS_NO_FILL' for z in all_oos)} censored={sum(z.status=='CENSORED' for z in all_oos)} gaps={sum(z.status=='FILLED' and z.fill_price>z.trigger_price for z in all_oos if z.fill_price is not None)} trigger_bars_min/median/max={_dist(times)}")
def _dist(xs):
 if not xs:return "NA"
 s=sorted(xs);return f"{s[0]}/{s[len(s)//2]}/{s[-1]}"
if __name__=="__main__":main()
