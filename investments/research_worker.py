from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import sqlite3
from pathlib import Path

from investments.research_queue import InvestmentResearchQueue

@dataclass(frozen=True,slots=True)
class ClaimedInvestmentResearch:
 candidate_id:str
 symbol:str
 evidence_reference:str
 priority:str
 claimed_at:datetime

class InvestmentResearchWorker:
 """Durably claims exactly one pending research object per cycle.

 This worker deliberately does not fabricate deep-research conclusions.
 It is the machine seam for an external GIL research agent to consume.
 """
 def __init__(self,queue:InvestmentResearchQueue):
  self.queue=queue

 def claim_next(self,*,now:datetime|None=None)->ClaimedInvestmentResearch|None:
  moment=now or datetime.now(timezone.utc)
  if moment.tzinfo is None:raise ValueError("now must be timezone-aware")
  with sqlite3.connect(self.queue.path) as c:
   c.row_factory=sqlite3.Row
   c.execute("BEGIN IMMEDIATE")
   row=c.execute("""SELECT * FROM investment_research_queue
                    WHERE status='PENDING'
                    ORDER BY CAST(priority AS REAL) DESC,queued_at,candidate_id
                    LIMIT 1""").fetchone()
   if row is None:
    c.commit();return None
   cur=c.execute("UPDATE investment_research_queue SET status='IN_RESEARCH' WHERE candidate_id=? AND status='PENDING'",(row["candidate_id"],))
   if cur.rowcount!=1:
    c.rollback();return None
   c.commit()
   return ClaimedInvestmentResearch(row["candidate_id"],row["symbol"],row["evidence_reference"],row["priority"],moment)

 def complete(self,candidate_id:str,status:str)->None:
  self.queue.mark(candidate_id,status)
