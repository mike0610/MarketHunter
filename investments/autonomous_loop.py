from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import sqlite3
from pathlib import Path

from experiment1.models import AccountKind,DecisionAction
from investments.stage8_boundary import assert_investment_account

class InvestmentResearchDecision(str,Enum):
 BUY="BUY";PARTIAL_BUY="PARTIAL_BUY";WAIT="WAIT";HOLD="HOLD";REJECT="REJECT"

@dataclass(frozen=True,slots=True)
class InvestmentResearchRecord:
 object_id:str;symbol:str;account:AccountKind;decision:InvestmentResearchDecision
 decided_at:datetime;investment_attractiveness:Decimal;executability:Decimal
 evidence_reference:str;thesis:str;counter_thesis:str;revisit_condition:str|None=None

 def __post_init__(self):
  assert_investment_account(self.account)
  if not self.object_id or not self.symbol or not self.evidence_reference:raise ValueError("durable investment research identity/evidence required")
  if not self.decided_at.tzinfo:raise ValueError("decided_at must be timezone-aware")
  if self.decision is InvestmentResearchDecision.WAIT and not self.revisit_condition:raise ValueError("WAIT requires explicit revisit condition")

class AutonomousInvestmentStore:
 def __init__(self,path:str|Path):
  self.path=Path(path)
  with sqlite3.connect(self.path) as c:c.executescript("""
  CREATE TABLE IF NOT EXISTS investment_research_decisions(
   object_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,account TEXT NOT NULL,decision TEXT NOT NULL,
   decided_at TEXT NOT NULL,investment_attractiveness TEXT NOT NULL,executability TEXT NOT NULL,
   evidence_reference TEXT NOT NULL,thesis TEXT NOT NULL,counter_thesis TEXT NOT NULL,revisit_condition TEXT);
  """)
 def record(self,x:InvestmentResearchRecord)->bool:
  with sqlite3.connect(self.path) as c:
   cur=c.execute("INSERT OR IGNORE INTO investment_research_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    (x.object_id,x.symbol,x.account.value,x.decision.value,x.decided_at.isoformat(),str(x.investment_attractiveness),str(x.executability),x.evidence_reference,x.thesis,x.counter_thesis,x.revisit_condition))
   return cur.rowcount==1
 def rows(self):
  with sqlite3.connect(self.path) as c:
   c.row_factory=sqlite3.Row;return tuple(dict(r) for r in c.execute("SELECT * FROM investment_research_decisions ORDER BY decided_at,object_id"))

def admission_action(x:InvestmentResearchRecord)->DecisionAction|None:
 if x.decision in (InvestmentResearchDecision.BUY,InvestmentResearchDecision.PARTIAL_BUY):return DecisionAction.BUY
 if x.decision is InvestmentResearchDecision.HOLD:return DecisionAction.HOLD
 if x.decision is InvestmentResearchDecision.WAIT:return DecisionAction.WAIT
 return None
