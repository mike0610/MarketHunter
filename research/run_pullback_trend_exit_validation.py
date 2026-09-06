"""GIL-bounded PULLBACK LONG structural-stop + SMA20-close exit validation."""
from __future__ import annotations
import asyncio,json
from dataclasses import asdict,dataclass
from math import isfinite
from backtesting.trade_simulator import ExecutionAssumptions
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from research.pullback_validation import validate_pullback_entries

UNIVERSE=("SPY","QQQ","AAPL","MSFT","NVDA");HISTORY_BARS=1300;DEV=0.70;WARMUP=50;EXPIRY=3
@dataclass(frozen=True,slots=True)
class Trade:
 symbol:str;signal_time:str;entry:float;stop:float;exit_reason:str;holding_bars:int;pnl_1unit:float;fees_1unit:float;net_r:float;gap_stop:bool
def sl(s,a,b):
 return MarketSeries(instrument=s.instrument,timeframe=s.timeframe,bars=s.bars[a:b],provider=s.provider,source_reference=s.source_reference,observed_at=s.observed_at,available_at=s.available_at)
def sma20(bars,i):
 return float(sum(x.close for x in bars[i-19:i+1])/20)
def trades(series):
 summary=validate_pullback_entries(series,EXPIRY);bars=series.bars;a=ExecutionAssumptions();out=[]
 for o in summary.observations:
  if o.status!="FILLED":continue
  entry=float(o.fill_price);stop=float(o.invalidation_price);risk=entry-stop
  if risk<=0:continue
  raw=None;ix=None;reason=None;gap=False
  for i in range(o.fill_index+1,len(bars)):
   bar=bars[i]
   if float(bar.low)<=stop:
    raw=min(stop,float(bar.open));ix=i;reason="structural_stop";gap=float(bar.open)<stop;break
   if float(bar.close)<=sma20(bars,i):
    raw=float(bar.close);ix=i;reason="sma20_close";break
  if raw is None:raw=float(bars[-1].close);ix=len(bars)-1;reason="window_close"
  sr=a.slippage_bps_per_side/10000;fr=a.fee_bps_per_side/10000
  ef=entry*(1+sr);xf=raw*(1-sr);fees=(ef+xf)*fr;pnl=xf-ef-fees;r=pnl/risk
  if not isfinite(r):raise ValueError("non-finite R")
  out.append(Trade(o.symbol,str(o.signal_time),entry,stop,reason,ix-o.fill_index,pnl,fees,r,gap))
 return tuple(out)
def summary(ts):
 resolved=[t for t in ts if t.exit_reason!="window_close"];pos=sum(t.net_r for t in resolved if t.net_r>0);neg=sum(t.net_r for t in resolved if t.net_r<0)
 eq=peak=0.;dd=0.
 for t in sorted(ts,key=lambda x:x.signal_time):eq+=t.net_r;peak=max(peak,eq);dd=min(dd,eq-peak)
 hs=sorted(t.holding_bars for t in ts)
 return {"trades":len(ts),"wins":sum(t.net_r>0 for t in resolved),"losses":sum(t.net_r<=0 for t in resolved),"unresolved":len(ts)-len(resolved),"win_rate":sum(t.net_r>0 for t in resolved)/len(resolved) if resolved else None,"average_net_r":sum(t.net_r for t in ts)/len(ts) if ts else None,"profit_factor_r":pos/abs(neg) if neg<0 else None,"net_pnl_1unit":sum(t.pnl_1unit for t in ts),"max_cumulative_r_drawdown":dd,"median_holding_bars":hs[len(hs)//2] if hs else None,"structural_stop_exits":sum(t.exit_reason=="structural_stop" for t in ts),"sma20_exits":sum(t.exit_reason=="sma20_close" for t in ts),"gap_stops":sum(t.gap_stop for t in ts)}
async def run():
 p=YahooChartDailyProvider(UNIVERSE);rows=[];all_oos=[]
 for ins in await p.universe():
  s=await p.history(ins,limit=HISTORY_BARS);split=int(len(s.bars)*DEV);start=max(0,split-WARMUP)
  dev=trades(sl(s,0,split));o=trades(sl(s,start,len(s.bars)))
  # warmup slice can generate pre-OOS signals; filter by signal timestamp against split timestamp
  boundary=s.bars[split].timestamp;o=tuple(t for t in o if t.signal_time>=str(boundary));all_oos+=list(o)
  rows.append({"symbol":ins.symbol,"development":summary(dev),"oos":summary(o)})
 return {"hypothesis":"PULLBACK_LONG_SMA50_STOP_SMA20_CLOSE_EXIT","entry_expiry_bars":3,"symbols":rows,"oos_total":summary(tuple(all_oos)),"notes":{"stop":"signal-time SMA50 fixed","exit":"first completed daily close <= SMA20 after fill","costs":"ExecutionAssumptions defaults","broker":"ZERO","ibkr":"ZERO","live_money":"ZERO"}}
if __name__=="__main__":print(json.dumps(asyncio.run(run()),sort_keys=True))
