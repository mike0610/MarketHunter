from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from stage9.control import OrchestrationRegistry
from stage9.models import PipelineHealth

def health_snapshot(registry:OrchestrationRegistry,now:datetime)->dict:
 pipelines=[]
 overall="HEALTHY"
 for pid in sorted(registry.specs):
  s=registry.store.state(pid)
  if s.health is PipelineHealth.FAILED:overall="DEGRADED"
  pipelines.append({
   "pipeline_id":pid,"health":s.health.value,
   "last_started_at":s.last_started_at.isoformat() if s.last_started_at else None,
   "last_success_at":s.last_success_at.isoformat() if s.last_success_at else None,
   "last_failure_at":s.last_failure_at.isoformat() if s.last_failure_at else None,
   "next_eligible_at":s.next_eligible_at.isoformat(),
   "consecutive_failures":s.consecutive_failures,
   "running":s.active_run_id is not None,
   "last_error":s.last_error,
  })
 return {"as_of":now.isoformat(),"overall":overall,"pipelines":pipelines}
