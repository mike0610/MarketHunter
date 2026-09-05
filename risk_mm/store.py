from __future__ import annotations
import json, sqlite3
from pathlib import Path
from risk_mm.models import SizedExecutionPlan


class RiskPlanStore:
    def __init__(self, db_path):
        self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS risk_sized_plans(
                plan_id TEXT PRIMARY KEY, trading_decision_id TEXT NOT NULL UNIQUE,
                decision TEXT NOT NULL, account TEXT NOT NULL, policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL, evaluated_at TEXT NOT NULL, reasons_json TEXT NOT NULL,
                quantity TEXT, reference_price TEXT, stop_price TEXT, risk_amount TEXT,
                notional TEXT, leverage TEXT)""")

    def record(self,p:SizedExecutionPlan):
        vals=(p.plan_id,p.trading_decision_id,p.decision.value,p.account.value,p.policy_id,p.policy_version,
              p.evaluated_at.isoformat(),json.dumps(p.reasons),*[None if x is None else str(x) for x in
              (p.quantity,p.reference_price,p.stop_price,p.risk_amount,p.notional,p.leverage)])
        with sqlite3.connect(self.db_path) as c:
            row=c.execute("select * from risk_sized_plans where trading_decision_id=?",(p.trading_decision_id,)).fetchone()
            if row:
                if row[0] == p.plan_id: return p
                raise ValueError("duplicate trading decision")
            c.execute("insert into risk_sized_plans values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
        return p
