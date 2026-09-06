from __future__ import annotations
import json,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from .models import ResearchObject,Stage

def _now()->str:return datetime.now(timezone.utc).isoformat()

class AutonomousResearchRepository:
    def __init__(self,db_path:Path):
        self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _connect(self):return sqlite3.connect(self.db_path)
    def _init(self):
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS research_loop_objects(
              object_id TEXT PRIMARY KEY, market TEXT NOT NULL, direction TEXT NOT NULL,
              hypothesis_id TEXT, data_handler TEXT, hypothesis_handler TEXT, validation_handler TEXT,
              product_owner_decision_required INTEGER NOT NULL DEFAULT 0,
              priority INTEGER NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
              attempt INTEGER NOT NULL DEFAULT 0, verdict TEXT, evidence_json TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_loop_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, object_id TEXT NOT NULL, event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_negative_knowledge(
              object_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_release_candidates(
              object_id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, evidence_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)
    def enqueue(self,obj:ResearchObject)->None:
        now=_now()
        with self._connect() as c:
            c.execute("""INSERT OR IGNORE INTO research_loop_objects
              (object_id,market,direction,hypothesis_id,data_handler,hypothesis_handler,validation_handler,
               product_owner_decision_required,priority,stage,status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?, ?,?)""",
              (obj.object_id,obj.market,obj.direction,obj.hypothesis_id,obj.data_handler,obj.hypothesis_handler,
               obj.validation_handler,int(obj.product_owner_decision_required),obj.priority,Stage.DATA_FEASIBILITY.value,
               "PENDING",now,now))
    def next_object(self):
        with self._connect() as c:
            c.row_factory=sqlite3.Row
            return c.execute("""SELECT * FROM research_loop_objects
              WHERE status IN ('PENDING','RUNNING') AND product_owner_decision_required=0
              ORDER BY priority, created_at, object_id LIMIT 1""").fetchone()
    def mark_running(self,object_id:str)->None:
        with self._connect() as c:
            c.execute("UPDATE research_loop_objects SET status='RUNNING',attempt=attempt+1,updated_at=? WHERE object_id=?",(_now(),object_id))
    def advance(self,object_id:str,stage:Stage,evidence:dict)->None:
        now=_now(); payload=json.dumps(evidence,sort_keys=True)
        with self._connect() as c:
            c.execute("UPDATE research_loop_objects SET stage=?,status='PENDING',evidence_json=?,updated_at=? WHERE object_id=?",(stage.value,payload,now,object_id))
            c.execute("INSERT INTO research_loop_events(object_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",(object_id,"ADVANCE:"+stage.value,payload,now))
    def terminal(self,object_id:str,verdict:str,evidence:dict,negative:dict|None=None,hypothesis_id:str|None=None)->None:
        now=_now(); payload=json.dumps(evidence,sort_keys=True)
        with self._connect() as c:
            c.execute("UPDATE research_loop_objects SET stage=?,status='TERMINAL',verdict=?,evidence_json=?,updated_at=? WHERE object_id=?",(Stage.TERMINAL.value,verdict,payload,now,object_id))
            c.execute("INSERT INTO research_loop_events(object_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",(object_id,"TERMINAL:"+verdict,payload,now))
            if negative is not None:
                c.execute("INSERT OR REPLACE INTO research_negative_knowledge(object_id,payload_json,created_at) VALUES(?,?,?)",(object_id,json.dumps(negative,sort_keys=True),now))
            if verdict=="PROMOTION-ELIGIBLE":
                if not hypothesis_id: raise ValueError("promotion eligible requires hypothesis_id")
                c.execute("INSERT OR REPLACE INTO research_release_candidates(object_id,hypothesis_id,evidence_json,created_at) VALUES(?,?,?,?)",(object_id,hypothesis_id,payload,now))
    def technical_failure(self,object_id:str,status:str,evidence:dict)->None:
        # Fail closed but keep the object resumable. Technical failure is never a strategy verdict.
        now=_now(); payload=json.dumps(evidence,sort_keys=True)
        with self._connect() as c:
            c.execute("UPDATE research_loop_objects SET status='PENDING',evidence_json=?,updated_at=? WHERE object_id=?",(payload,now,object_id))
            c.execute("INSERT INTO research_loop_events(object_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",(object_id,status,payload,now))
    def object(self,object_id:str):
        with self._connect() as c:
            c.row_factory=sqlite3.Row
            return c.execute("SELECT * FROM research_loop_objects WHERE object_id=?",(object_id,)).fetchone()
    def release_candidate(self,object_id:str):
        with self._connect() as c:
            c.row_factory=sqlite3.Row
            return c.execute("SELECT * FROM research_release_candidates WHERE object_id=?",(object_id,)).fetchone()
    def counts(self)->dict:
        with self._connect() as c:
            return dict(c.execute("SELECT status,count(*) FROM research_loop_objects GROUP BY status").fetchall())
