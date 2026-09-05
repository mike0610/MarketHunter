from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

@dataclass(frozen=True,slots=True)
class ClosedTradeSample:
 symbol:str
 direction:str
 strategy_id:str
 strategy_version:str
 exit_reason:str
 quantity:Decimal
 entry_price:Decimal
 exit_price:Decimal
 gross_pnl:Decimal
 entry_fees:Decimal
 exit_fees:Decimal
 realized_pnl:Decimal

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
 expectancy=avg
 return PerformanceSummary(len(samples),len(wins),len(losses),len(breakeven),win_rate,gross_profit,gross_loss,net,pf,avg,expectancy,avg_win,avg_loss,payoff)

def group_by(samples:tuple[ClosedTradeSample,...],field:str)->dict[str,PerformanceSummary]:
 allowed={"strategy_id","strategy_version","direction","exit_reason","symbol"}
 if field not in allowed:raise ValueError("unsupported group field")
 buckets:dict[str,list[ClosedTradeSample]]={}
 for s in samples:buckets.setdefault(str(getattr(s,field)),[]).append(s)
 return {k:summarize(tuple(v)) for k,v in sorted(buckets.items())}
