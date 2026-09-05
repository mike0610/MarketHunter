from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta
from stage9.models import PipelineHealth,PipelineSpec
from stage9.store import OrchestrationStore

class OverlapBlocked(Exception):pass
class NotDue(Exception):pass

class OrchestrationRegistry:
 def __init__(self,store:OrchestrationStore,specs:list[PipelineSpec]):
  self.store=store;self.specs={s.pipeline_id:s for s in specs}
 def register_all(self,now:datetime):
  for s in self.specs.values():self.store.register(s,now)
 def begin(self,pipeline_id:str,run_id:str,now:datetime):
  spec=self.specs[pipeline_id]
  with sqlite3.connect(self.store.path) as c:
   c.execute("BEGIN IMMEDIATE")
   r=c.execute("SELECT health,next_eligible_at,active_run_id FROM orchestration_pipeline_state WHERE pipeline_id=?",(pipeline_id,)).fetchone()
   if not r:raise KeyError(pipeline_id)
   if r[2] is not None:raise OverlapBlocked(pipeline_id)
   if now<datetime.fromisoformat(r[1]):raise NotDue(pipeline_id)
   c.execute("UPDATE orchestration_pipeline_state SET health=?,last_started_at=?,active_run_id=? WHERE pipeline_id=?",(PipelineHealth.RUNNING.value,now.isoformat(),run_id,pipeline_id))
   c.execute("INSERT INTO orchestration_audit(pipeline_id,run_id,event,at) VALUES(?,?,?,?)",(pipeline_id,run_id,"STARTED",now.isoformat()))
 def succeed(self,pipeline_id:str,run_id:str,now:datetime):
  spec=self.specs[pipeline_id]
  with sqlite3.connect(self.store.path) as c:
   cur=c.execute("""UPDATE orchestration_pipeline_state SET health=?,last_success_at=?,next_eligible_at=?,consecutive_failures=0,active_run_id=NULL,last_error=NULL WHERE pipeline_id=? AND active_run_id=?""",
    (PipelineHealth.HEALTHY.value,now.isoformat(),(now+spec.cadence).isoformat(),pipeline_id,run_id))
   if cur.rowcount!=1:raise OverlapBlocked("run ownership lost")
   c.execute("INSERT INTO orchestration_audit(pipeline_id,run_id,event,at) VALUES(?,?,?,?)",(pipeline_id,run_id,"SUCCEEDED",now.isoformat()))
 def fail(self,pipeline_id:str,run_id:str,now:datetime,error:str):
  spec=self.specs[pipeline_id]
  with sqlite3.connect(self.store.path) as c:
   r=c.execute("SELECT consecutive_failures FROM orchestration_pipeline_state WHERE pipeline_id=? AND active_run_id=?",(pipeline_id,run_id)).fetchone()
   if not r:raise OverlapBlocked("run ownership lost")
   n=r[0]+1;delay=min(spec.cadence*(2**(n-1)),spec.max_backoff)
   c.execute("""UPDATE orchestration_pipeline_state SET health=?,last_failure_at=?,next_eligible_at=?,consecutive_failures=?,active_run_id=NULL,last_error=? WHERE pipeline_id=?""",
    (PipelineHealth.FAILED.value,now.isoformat(),(now+delay).isoformat(),n,error,pipeline_id))
   c.execute("INSERT INTO orchestration_audit(pipeline_id,run_id,event,at,detail) VALUES(?,?,?,?,?)",(pipeline_id,run_id,"FAILED",now.isoformat(),error))
