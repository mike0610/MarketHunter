from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

TREND_UNKNOWN="trend-unknown"

@dataclass(frozen=True,slots=True)
class ClosedTradeSample:
 closed_trade_id:str
 position_id:str
 symbol:str
 direction:str
 strategy_id:str
 strategy_version:str
 setup_family:str
 trend_alignment:str
 exit_reason:str
 quantity:Decimal
 entry_price:Decimal
 exit_price:Decimal
 gross_pnl:Decimal
 entry_fees:Decimal
 exit_fees:Decimal
 realized_pnl:Decimal
 opened_at:datetime
 closed_at:datetime
 initial_risk_amount:Decimal|None
 candidate_dedupe_key:str
 strategy_decision_id:str
 risk_plan_id:str|None
 order_id:str|None
 entry_fill_id:str|None

 @property
 def holding_seconds(self)->Decimal:
  return Decimal(str((self.closed_at-self.opened_at).total_seconds()))

 @property
 def r_multiple(self)->Decimal|None:
  if self.initial_risk_amount is None or self.initial_risk_amount<=0:return None
  return self.realized_pnl/self.initial_risk_amount

@dataclass(frozen=True,slots=True)
class PerformanceSummary:
 trades:int
 wins:int
 losses:int
 breakeven:int
 win_rate:Decimal
 gross_profit:Decimal
 gross_loss:Decimal
 net_pnl:Decimal
 profit_factor:Decimal|None
 average_pnl:Decimal
 expectancy:Decimal
 average_win:Decimal|None
 average_loss:Decimal|None
 payoff_ratio:Decimal|None
 max_drawdown:Decimal
 average_r_multiple:Decimal|None
 average_holding_seconds:Decimal|None

def _max_drawdown(samples:tuple[ClosedTradeSample,...])->Decimal:
 equity=Decimal("0");peak=Decimal("0");max_dd=Decimal("0")
 for x in sorted(samples,key=lambda s:(s.closed_at,s.closed_trade_id)):
  equity+=x.realized_pnl
  if equity>peak:peak=equity
  dd=peak-equity
  if dd>max_dd:max_dd=dd
 return max_dd

def summarize(samples:tuple[ClosedTradeSample,...])->PerformanceSummary:
 wins=[x for x in samples if x.realized_pnl>0]
 losses=[x for x in samples if x.realized_pnl<0]
 breakeven=[x for x in samples if x.realized_pnl==0]
 decisive=len(wins)+len(losses)
 gross_profit=sum((x.realized_pnl for x in wins),Decimal("0"))
 gross_loss=abs(sum((x.realized_pnl for x in losses),Decimal("0")))
 net=sum((x.realized_pnl for x in samples),Decimal("0"))
 avg=(net/Decimal(len(samples))) if samples else Decimal("0")
 win_rate=(Decimal(len(wins))/Decimal(decisive)*Decimal("100")) if decisive else Decimal("0")
 avg_win=(gross_profit/Decimal(len(wins))) if wins else None
 avg_loss=(gross_loss/Decimal(len(losses))) if losses else None
 pf=(gross_profit/gross_loss) if gross_loss>0 else None
 payoff=(avg_win/avg_loss) if avg_win is not None and avg_loss not in (None,Decimal("0")) else None
 rs=[x.r_multiple for x in samples if x.r_multiple is not None]
 avg_r=(sum(rs,Decimal("0"))/Decimal(len(rs))) if rs else None
 avg_hold=(sum((x.holding_seconds for x in samples),Decimal("0"))/Decimal(len(samples))) if samples else None
 return PerformanceSummary(len(samples),len(wins),len(losses),len(breakeven),win_rate,gross_profit,gross_loss,net,pf,avg,avg,avg_win,avg_loss,payoff,_max_drawdown(samples),avg_r,avg_hold)

def group_by(samples:tuple[ClosedTradeSample,...],field:str)->dict[str,PerformanceSummary]:
 allowed={"strategy_id","strategy_version","setup_family","direction","trend_alignment","exit_reason","symbol"}
 if field not in allowed:raise ValueError("unsupported group field")
 buckets:dict[str,list[ClosedTradeSample]]={}
 for s in samples:buckets.setdefault(str(getattr(s,field)),[]).append(s)
 return {k:summarize(tuple(v)) for k,v in sorted(buckets.items())}
