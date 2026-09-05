from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from risk_mm.models import SizedExecutionPlan,TradingAccount

@dataclass(frozen=True,slots=True)
class OpenRiskExposure:
    position_id:str
    plan_id:str
    account:TradingAccount
    symbol:str
    cluster_key:str
    original_quantity:Decimal
    open_quantity:Decimal
    original_risk_amount:Decimal
    open_risk_amount:Decimal

class OpenRiskLedger:
    """Durable risk-at-stop exposure. Never derives risk from P&L or current price."""
    def __init__(self,db_path:str|Path)->None:
        self.db_path=Path(db_path);self.db_path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS open_risk_exposure(
              position_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL UNIQUE,account TEXT NOT NULL,
              symbol TEXT NOT NULL,cluster_key TEXT NOT NULL,original_quantity TEXT NOT NULL,
              open_quantity TEXT NOT NULL,original_risk_amount TEXT NOT NULL,open_risk_amount TEXT NOT NULL)""")

    def record_open(self,*,position_id:str,plan:SizedExecutionPlan,symbol:str,cluster_key:str,filled_quantity:Decimal)->None:
        if plan.decision.value!="APPROVED" or plan.risk_amount is None or plan.quantity is None:
            raise ValueError("only an APPROVED sized plan with risk and quantity may create exposure")
        if filled_quantity<=0 or filled_quantity>plan.quantity: raise ValueError("invalid filled quantity")
        risk=plan.risk_amount*(filled_quantity/plan.quantity)
        vals=(position_id,plan.plan_id,plan.account.value,symbol,cluster_key,str(filled_quantity),str(filled_quantity),str(risk),str(risk))
        with sqlite3.connect(self.db_path) as c:
            row=c.execute("select * from open_risk_exposure where plan_id=?",(plan.plan_id,)).fetchone()
            if row is None:c.execute("insert into open_risk_exposure values (?,?,?,?,?,?,?,?,?)",vals)
            elif tuple(row)!=vals: raise ValueError("plan_id already has different exposure")

    def reduce(self,position_id:str,closed_quantity:Decimal)->OpenRiskExposure:
        if closed_quantity<=0: raise ValueError("closed_quantity must be positive")
        with sqlite3.connect(self.db_path) as c:
            c.row_factory=sqlite3.Row;r=c.execute("select * from open_risk_exposure where position_id=?",(position_id,)).fetchone()
            if r is None: raise ValueError("unknown position exposure")
            oq=Decimal(r["open_quantity"])
            if closed_quantity>oq: raise ValueError("cannot reduce beyond open quantity")
            nr=oq-closed_quantity
            risk=Decimal(r["original_risk_amount"])*(nr/Decimal(r["original_quantity"])) if nr else Decimal("0")
            c.execute("update open_risk_exposure set open_quantity=?,open_risk_amount=? where position_id=?",(str(nr),str(risk),position_id))
        return self.get(position_id)

    def get(self,position_id:str)->OpenRiskExposure:
        with sqlite3.connect(self.db_path) as c:
            c.row_factory=sqlite3.Row;r=c.execute("select * from open_risk_exposure where position_id=?",(position_id,)).fetchone()
            if r is None: raise ValueError("unknown position exposure")
            return OpenRiskExposure(r["position_id"],r["plan_id"],TradingAccount(r["account"]),r["symbol"],r["cluster_key"],Decimal(r["original_quantity"]),Decimal(r["open_quantity"]),Decimal(r["original_risk_amount"]),Decimal(r["open_risk_amount"]))

    def aggregate(self,account:TradingAccount,cluster_key:str)->tuple[Decimal,Decimal]:
        with sqlite3.connect(self.db_path) as c:
            rows=c.execute("select cluster_key,open_risk_amount from open_risk_exposure where account=?",(account.value,)).fetchall()
        total=sum((Decimal(r[1]) for r in rows),Decimal("0"))
        cluster=sum((Decimal(r[1]) for r in rows if r[0]==cluster_key),Decimal("0"))
        return total,cluster
