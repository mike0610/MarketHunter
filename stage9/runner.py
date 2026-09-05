from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from stage9.control import NotDue,OrchestrationRegistry,OverlapBlocked

@dataclass(frozen=True,slots=True)
class CycleResult:
 pipeline_id:str
 run_id:str
 outcome:str
 detail:str|None=None

def run_controlled_cycle(registry:OrchestrationRegistry,pipeline_id:str,run_id:str,now:datetime,cycle:Callable[[],None])->CycleResult:
 try:registry.begin(pipeline_id,run_id,now)
 except NotDue:return CycleResult(pipeline_id,run_id,"SKIPPED_NOT_DUE")
 except OverlapBlocked:return CycleResult(pipeline_id,run_id,"SKIPPED_OVERLAP")
 try:
  cycle()
 except Exception as exc:
  registry.fail(pipeline_id,run_id,now,type(exc).__name__+": "+str(exc))
  return CycleResult(pipeline_id,run_id,"FAILED",str(exc))
 registry.succeed(pipeline_id,run_id,now)
 return CycleResult(pipeline_id,run_id,"SUCCEEDED")
