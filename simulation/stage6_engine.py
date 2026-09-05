from __future__ import annotations
from decimal import Decimal
from hashlib import sha256
from simulation.stage6_models import *

def evaluate_exit(p:ManagedPosition,policy:PositionExitPolicy,e:PositionBarEvidence,*,partial_already_done=False)->ExitEvaluation:
 if not e.fresh:return ExitEvaluation(ExitVerdict.BLOCKED,None,None,Decimal("0"),"stale evidence")
 if e.symbol!=p.symbol:return ExitEvaluation(ExitVerdict.BLOCKED,None,None,Decimal("0"),"symbol mismatch")
 if policy.strategy_id!=p.strategy_id or policy.strategy_version!=p.strategy_version:return ExitEvaluation(ExitVerdict.BLOCKED,None,None,Decimal("0"),"strategy version mismatch")
 long=p.direction=="LONG"
 stop=policy.stop_loss is not None and (e.low<=policy.stop_loss if long else e.high>=policy.stop_loss)
 target=policy.take_profit is not None and (e.high>=policy.take_profit if long else e.low<=policy.take_profit)
 partial=(not partial_already_done and policy.partial_take_profit is not None and (e.high>=policy.partial_take_profit if long else e.low<=policy.partial_take_profit))
 structural=policy.structural_invalidation is not None and (e.low<=policy.structural_invalidation if long else e.high>=policy.structural_invalidation)
 if stop and (target or partial):return ExitEvaluation(ExitVerdict.AMBIGUOUS,None,None,Decimal("0"),"same bar contains adverse and favorable exit levels; order unknowable")
 # Gap rule: an adverse gap exits at open, never at a magically better stop.
 if stop:
  raw=min(e.open,policy.stop_loss) if long else max(e.open,policy.stop_loss)
  return ExitEvaluation(ExitVerdict.EXIT,ExitReason.STOP_LOSS,raw,p.quantity,"stop")
 if structural:
  raw=min(e.open,policy.structural_invalidation) if long else max(e.open,policy.structural_invalidation)
  return ExitEvaluation(ExitVerdict.EXIT,ExitReason.STRUCTURAL_INVALIDATION,raw,p.quantity,"structural invalidation")
 if target:return ExitEvaluation(ExitVerdict.EXIT,ExitReason.TAKE_PROFIT,policy.take_profit,p.quantity,"take profit")
 if partial:
  q=p.quantity*policy.partial_fraction
  return ExitEvaluation(ExitVerdict.EXIT,ExitReason.PARTIAL_TAKE_PROFIT,policy.partial_take_profit,q,"partial take profit")
 if policy.expires_at is not None and e.observed_at>=policy.expires_at:
  return ExitEvaluation(ExitVerdict.EXIT,ExitReason.TIME_EXIT,e.close,p.quantity,"time exit")
 return ExitEvaluation(ExitVerdict.HOLD,None,None,Decimal("0"),"no exit condition")

def build_exit_fill(p:ManagedPosition,x:ExitEvaluation,e:PositionBarEvidence,*,fee_bps:Decimal,slippage_bps:Decimal)->SimulatedExitFill:
 if x.verdict is not ExitVerdict.EXIT or x.reason is None or x.raw_exit_price is None:raise ValueError("EXIT evaluation required")
 if fee_bps<0 or slippage_bps<0:raise ValueError("cost bps must be non-negative")
 # Closing LONG sells lower; closing SHORT buys higher.
 sign=Decimal("-1") if p.direction=="LONG" else Decimal("1")
 slip=x.raw_exit_price*slippage_bps/Decimal("10000")*sign;price=x.raw_exit_price+slip
 fee=price*x.quantity*fee_bps/Decimal("10000")
 fid="sim-exit:"+sha256(f"{p.position_id}|{x.reason.value}|{e.source_reference}|{x.quantity}".encode()).hexdigest()
 return SimulatedExitFill(fid,p.position_id,x.reason,x.quantity,x.raw_exit_price,price,fee,abs(slip)*x.quantity,e.observed_at,e.provider,e.source_reference)

def realized_pnl(p:ManagedPosition,f:SimulatedExitFill,allocated_entry_fees:Decimal)->Decimal:
 gross=(f.fill_price-p.average_price)*f.quantity if p.direction=="LONG" else (p.average_price-f.fill_price)*f.quantity
 return gross-allocated_entry_fees-f.fee_amount
