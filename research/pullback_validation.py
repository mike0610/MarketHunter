"""Bounded historical entry validation for PULLBACK LONG reclaim trigger."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from market_data.foundation import MarketBar,MarketSeries

@dataclass(frozen=True,slots=True)
class PullbackObservation:
 symbol:str; signal_index:int; signal_time:object; trigger_price:Decimal; invalidation_price:Decimal
 status:str; fill_price:Decimal|None; fill_index:int|None; bars_to_trigger:int|None

@dataclass(frozen=True,slots=True)
class PullbackValidationSummary:
 signals:int; fills:int; invalidated_before_fill:int; ambiguous_no_fill:int; censored:int; gap_entries:int
 observations:tuple[PullbackObservation,...]

def _sma(bars:tuple[MarketBar,...],end:int,length:int)->Decimal:
 w=bars[end-length+1:end+1]; return sum((b.close for b in w),Decimal("0"))/Decimal(length)

def find_pullback_signals(series:MarketSeries)->tuple[tuple[int,Decimal],...]:
 bars=series.bars; found=[]
 for i in range(49,len(bars)):
  sma20=_sma(bars,i,20); sma50=_sma(bars,i,50)
  if sma20<=sma50: continue
  if abs(bars[i].close-sma20)/sma20*Decimal("100")<=Decimal("2"):
   found.append((i,sma50))
 return tuple(found)

def evaluate_entry(series:MarketSeries,signal_index:int,invalidation_price:Decimal,expiry_bars:int|None=None)->PullbackObservation:
 bars=series.bars; signal=bars[signal_index]; trigger=signal.high
 end=len(bars) if expiry_bars is None else min(len(bars),signal_index+expiry_bars+1)
 for i in range(signal_index+1,end):
  bar=bars[i]; crossed=bar.high>=trigger; invalid_close=bar.close<invalidation_price
  if crossed and invalid_close:
   return PullbackObservation(series.instrument.symbol,signal_index,signal.timestamp,trigger,invalidation_price,"AMBIGUOUS_NO_FILL",None,None,None)
  if invalid_close:
   return PullbackObservation(series.instrument.symbol,signal_index,signal.timestamp,trigger,invalidation_price,"INVALIDATED_BEFORE_FILL",None,None,None)
  if crossed:
   raw_fill=max(trigger,bar.open)
   return PullbackObservation(series.instrument.symbol,signal_index,signal.timestamp,trigger,invalidation_price,"FILLED",raw_fill,i,i-signal_index)
 status="EXPIRED" if expiry_bars is not None and signal_index+expiry_bars<len(bars) else "CENSORED"
 return PullbackObservation(series.instrument.symbol,signal_index,signal.timestamp,trigger,invalidation_price,status,None,None,None)

def validate_pullback_entries(series:MarketSeries,expiry_bars:int|None=None)->PullbackValidationSummary:
 obs=tuple(evaluate_entry(series,i,level,expiry_bars) for i,level in find_pullback_signals(series))
 return PullbackValidationSummary(len(obs),sum(o.status=="FILLED" for o in obs),sum(o.status=="INVALIDATED_BEFORE_FILL" for o in obs),sum(o.status=="AMBIGUOUS_NO_FILL" for o in obs),sum(o.status=="CENSORED" for o in obs),sum(o.status=="FILLED" and o.fill_price is not None and o.fill_price>o.trigger_price for o in obs),obs)
