from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timedelta
from enum import Enum

class PipelineHealth(str,Enum):
 IDLE="IDLE";RUNNING="RUNNING";HEALTHY="HEALTHY";DEGRADED="DEGRADED";FAILED="FAILED"

@dataclass(frozen=True,slots=True)
class PipelineSpec:
 pipeline_id:str
 cadence:timedelta
 max_backoff:timedelta
 def __post_init__(self):
  if self.cadence.total_seconds()<=0:raise ValueError("cadence must be positive")
  if self.max_backoff<self.cadence:raise ValueError("max_backoff must be >= cadence")

@dataclass(frozen=True,slots=True)
class PipelineState:
 pipeline_id:str
 health:PipelineHealth
 last_started_at:datetime|None
 last_success_at:datetime|None
 last_failure_at:datetime|None
 next_eligible_at:datetime
 consecutive_failures:int
 active_run_id:str|None
 last_error:str|None
