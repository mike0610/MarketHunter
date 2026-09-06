from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import sqlite3
from pathlib import Path

from investments.stage8_models import InvestmentCandidate,InvestmentRoute
from investments.stage8_router import route_investment_candidate
from investments.stage8_store import Stage8InvestmentStore

@dataclass(frozen=True,slots=True)
class InvestmentResearchQueueItem:
 candidate_id:str;symbol:str;queued_at:datetime;evidence_reference:str;priority:Decimal;status:str="PENDING"
 def __post_init__(self):
  if not self.queued_at.tzinfo:raise ValueError("queued_at must be timezone-aware")
  if not self.candidate_id or not self.symbol or not self.evidence_reference:raise ValueError("durable queue identity/evidence required")

class InvestmentResearchQueue:
 def __init__(self,path:str|Path):
  self.path=Path(path)
  with sqlite3.connect(self.path) as c:c.execute("""CREATE TABLE IF NOT EXISTS investment_research_queue(
   candidate_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,queued_at TEXT NOT NULL,evidence_reference TEXT NOT NULL,
   priority TEXT NOT NULL,status TEXT NOT NULL)""")
 def enqueue(self,x:InvestmentResearchQueueItem):
  with sqlite3.connect(self.path) as c:
   cur=c.execute("INSERT OR IGNORE INTO investment_research_queue VALUES(?,?,?,?,?,?)",(x.candidate_id,x.symbol,x.queued_at.isoformat(),x.evidence_reference,str(x.priority),x.status));return cur.rowcount==1
 def pending(self):
  with sqlite3.connect(self.path) as c:c.row_factory=sqlite3.Row;return tuple(dict(r) for r in c.execute("SELECT * FROM investment_research_queue WHERE status='PENDING' ORDER BY CAST(priority AS REAL) DESC,queued_at,candidate_id"))
 def mark(self,candidate_id,status):
  if status not in ("IN_RESEARCH","DECIDED","REJECTED","BLOCKED_EVIDENCE"):raise ValueError("invalid queue terminal/progress status")
  with sqlite3.connect(self.path) as c:c.execute("UPDATE investment_research_queue SET status=? WHERE candidate_id=?",(status,candidate_id))

def admit_candidate(candidate:InvestmentCandidate,*,materiality_floor:Decimal,stage8:Stage8InvestmentStore,queue:InvestmentResearchQueue):
 stage8.record_candidate(candidate)
 route=route_investment_candidate(candidate,materiality_floor=materiality_floor)
 stage8.record_route(route)
 if route.route is not InvestmentRoute.GIL_DEEP_ANALYSIS:return route,False
 item=InvestmentResearchQueueItem(candidate.candidate_id,candidate.symbol,route.observed_at,route.evidence_reference,candidate.materiality_score)
 return route,queue.enqueue(item)
