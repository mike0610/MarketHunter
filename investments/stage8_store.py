from __future__ import annotations
import sqlite3
from pathlib import Path
from investments.stage8_models import InvestmentCandidate,InvestmentRoutingResult

class Stage8InvestmentStore:
 def __init__(self,db_path:str|Path)->None:
  self.db_path=Path(db_path)
  with sqlite3.connect(self.db_path) as c:
   c.executescript("""
   CREATE TABLE IF NOT EXISTS stage8_investment_candidates(
    candidate_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,universe_id TEXT NOT NULL,setup_family TEXT NOT NULL,
    materiality_score TEXT NOT NULL,deterministic_rule_id TEXT,evidence_provider TEXT NOT NULL,
    evidence_observed_at TEXT NOT NULL,evidence_reference TEXT NOT NULL,market_price TEXT NOT NULL,
    fundamentals_reference TEXT,event_reference TEXT,evidence_fresh INTEGER NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS stage8_investment_routes(
    candidate_id TEXT PRIMARY KEY,route TEXT NOT NULL,reason TEXT NOT NULL,deterministic_rule_id TEXT,
    evidence_reference TEXT NOT NULL,observed_at TEXT NOT NULL);
   """)

 def record_candidate(self,x:InvestmentCandidate)->bool:
  with sqlite3.connect(self.db_path) as c:
   cur=c.execute("""INSERT OR IGNORE INTO stage8_investment_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (x.candidate_id,x.symbol,x.universe_id,x.setup_family,str(x.materiality_score),x.deterministic_rule_id,
     x.evidence.provider,x.evidence.observed_at.isoformat(),x.evidence.source_reference,str(x.evidence.market_price),
     x.evidence.fundamentals_reference,x.evidence.event_reference,1 if x.evidence.fresh else 0,x.state.value,x.reason))
   return cur.rowcount==1

 def record_route(self,x:InvestmentRoutingResult)->bool:
  with sqlite3.connect(self.db_path) as c:
   cur=c.execute("""INSERT OR IGNORE INTO stage8_investment_routes VALUES (?,?,?,?,?,?)""",
    (x.candidate_id,x.route.value,x.reason,x.deterministic_rule_id,x.evidence_reference,x.observed_at.isoformat()))
   return cur.rowcount==1
