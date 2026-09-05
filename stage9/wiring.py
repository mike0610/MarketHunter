from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from stage9.control import OrchestrationRegistry
from stage9.policy import DEFAULT_PIPELINES
from stage9.runner import CycleResult,run_controlled_cycle
from stage9.store import OrchestrationStore

def build_registry(db_path:str|Path,now:datetime|None=None)->OrchestrationRegistry:
 r=OrchestrationRegistry(OrchestrationStore(db_path),list(DEFAULT_PIPELINES));r.register_all(now or datetime.now(timezone.utc));return r

def run_pipeline(registry:OrchestrationRegistry,pipeline_id:str,cycle,now:datetime|None=None)->CycleResult:
 t=now or datetime.now(timezone.utc)
 return run_controlled_cycle(registry,pipeline_id,str(uuid4()),t,cycle)
