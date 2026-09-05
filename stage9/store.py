from __future__ import annotations
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from stage9.models import PipelineHealth,PipelineSpec,PipelineState

class OrchestrationStore:
 def __init__(self,path:str|Path):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(self.path) as c:c.executescript("""
  CREATE TABLE IF NOT EXISTS orchestration_pipeline_state(
   pipeline_id TEXT PRIMARY KEY,health TEXT NOT NULL,last_started_at TEXT,last_success_at TEXT,last_failure_at TEXT,
   next_eligible_at TEXT NOT NULL,consecutive_failures INTEGER NOT NULL,active_run_id TEXT,last_error TEXT);
  CREATE TABLE IF NOT EXISTS orchestration_audit(
   id INTEGER PRIMARY KEY AUTOINCREMENT,pipeline_id TEXT NOT NULL,run_id TEXT,event TEXT NOT NULL,at TEXT NOT NULL,detail TEXT);
  """)
 def register(self,spec:PipelineSpec,now:datetime):
  with sqlite3.connect(self.path) as c:c.execute("""INSERT OR IGNORE INTO orchestration_pipeline_state VALUES(?,?,?,?,?,?,?,?,?)""",
   (spec.pipeline_id,PipelineHealth.IDLE.value,None,None,None,now.isoformat(),0,None,None))
 def state(self,pipeline_id:str)->PipelineState:
  with sqlite3.connect(self.path) as c:r=c.execute("SELECT * FROM orchestration_pipeline_state WHERE pipeline_id=?",(pipeline_id,)).fetchone()
  if not r:raise KeyError(pipeline_id)
  dt=lambda x:datetime.fromisoformat(x) if x else None
  return PipelineState(r[0],PipelineHealth(r[1]),dt(r[2]),dt(r[3]),dt(r[4]),dt(r[5]),r[6],r[7],r[8])
 def audit(self,pipeline_id,run_id,event,at,detail=None):
  with sqlite3.connect(self.path) as c:c.execute("INSERT INTO orchestration_audit(pipeline_id,run_id,event,at,detail) VALUES(?,?,?,?,?)",(pipeline_id,run_id,event,at.isoformat(),detail))
