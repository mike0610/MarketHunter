from __future__ import annotations
from dataclasses import replace
from decimal import Decimal
from simulation.stage6_engine import build_exit_fill,evaluate_exit
from simulation.stage6_models import *
from simulation.stage6_store import Stage6PositionStore

class Stage6PositionManager:
 def __init__(self,store:Stage6PositionStore,*,fee_bps:Decimal,slippage_bps:Decimal)->None:
  self.store=store;self.fee_bps=fee_bps;self.slippage_bps=slippage_bps

 def process(self,p:ManagedPosition,policy:PositionExitPolicy,evidence:PositionBarEvidence)->ExitEvaluation:
  remaining,partial_done,status=self.store.restore(p)
  if status=="CLOSED":return ExitEvaluation(ExitVerdict.HOLD,None,None,Decimal("0"),"already closed")
  current=replace(p,quantity=remaining)
  result=evaluate_exit(current,policy,evidence,partial_already_done=partial_done)
  if result.verdict is not ExitVerdict.EXIT:return result
  fill=build_exit_fill(current,result,evidence,fee_bps=self.fee_bps,slippage_bps=self.slippage_bps)
  self.store.apply_exit(current,fill)
  return result
