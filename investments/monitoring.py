from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import sqlite3
from pathlib import Path
from experiment1.models import AccountKind
from investments.stage8_boundary import assert_investment_account

class ThesisStatus(str,Enum):
 INTACT="INTACT";STRENGTHENED="STRENGTHENED";WEAKENED="WEAKENED";BROKEN="BROKEN";UNKNOWN="UNKNOWN"

@dataclass(frozen=True,slots=True)
class InvestmentMonitorSnapshot:
 monitor_id:str;decision_id:str;account:AccountKind;symbol:str;observed_at:datetime
 evidence_reference:str;mark_price:Decimal;cost_basis:Decimal;quantity:Decimal
 benchmark_symbol:str|None;benchmark_return:Decimal|None;thesis_status:ThesisStatus
 thesis_note:str;revisit_triggered:bool

 def __post_init__(self):
  assert_investment_account(self.account)
  if not self.observed_at.tzinfo:raise ValueError("observed_at must be timezone-aware")
  if self.mark_price<=0 or self.cost_basis<=0 or self.quantity<=0:raise ValueError("position monitoring requires positive price/cost/quantity")
  if not self.evidence_reference or not self.thesis_note:raise ValueError("monitoring evidence and thesis note required")

 @property
 def unrealized_pnl(self):return (self.mark_price-self.cost_basis)*self.quantity
 @property
 def absolute_return(self):return self.mark_price/self.cost_basis-Decimal("1")
 @property
 def benchmark_relative_return(self):return None if self.benchmark_return is None else self.absolute_return-self.benchmark_return

class InvestmentMonitoringStore:
 def __init__(self,path:str|Path):
  self.path=Path(path)
  with sqlite3.connect(self.path) as c:c.execute("""CREATE TABLE IF NOT EXISTS investment_monitor_snapshots(
   monitor_id TEXT PRIMARY KEY,decision_id TEXT NOT NULL,account TEXT NOT NULL,symbol TEXT NOT NULL,observed_at TEXT NOT NULL,
   evidence_reference TEXT NOT NULL,mark_price TEXT NOT NULL,cost_basis TEXT NOT NULL,quantity TEXT NOT NULL,
   benchmark_symbol TEXT,benchmark_return TEXT,thesis_status TEXT NOT NULL,thesis_note TEXT NOT NULL,revisit_triggered INTEGER NOT NULL,
   unrealized_pnl TEXT NOT NULL,absolute_return TEXT NOT NULL,benchmark_relative_return TEXT)""")
 def record(self,x:InvestmentMonitorSnapshot):
  with sqlite3.connect(self.path) as c:
   cur=c.execute("INSERT OR IGNORE INTO investment_monitor_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (x.monitor_id,x.decision_id,x.account.value,x.symbol,x.observed_at.isoformat(),x.evidence_reference,str(x.mark_price),str(x.cost_basis),str(x.quantity),x.benchmark_symbol,None if x.benchmark_return is None else str(x.benchmark_return),x.thesis_status.value,x.thesis_note,1 if x.revisit_triggered else 0,str(x.unrealized_pnl),str(x.absolute_return),None if x.benchmark_relative_return is None else str(x.benchmark_relative_return)))
   return cur.rowcount==1
 def rows(self):
  with sqlite3.connect(self.path) as c:c.row_factory=sqlite3.Row;return tuple(dict(r) for r in c.execute("SELECT * FROM investment_monitor_snapshots ORDER BY observed_at,monitor_id"))
