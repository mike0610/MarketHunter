from __future__ import annotations

import sqlite3
from pathlib import Path

from simulation.stage5_bridge import Stage5FillDetails, Stage5OrderBinding


class Stage5ExecutionStore:
    """Durable simulation details supplementing the canonical Simulation event log."""

    def __init__(self,db_path:str|Path)->None:
        self.db_path=Path(db_path);self.db_path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.db_path) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS stage5_sim_orders(
              order_id TEXT PRIMARY KEY,risk_plan_id TEXT NOT NULL UNIQUE,
              strategy_decision_id TEXT NOT NULL,candidate_dedupe_key TEXT NOT NULL,
              symbol TEXT NOT NULL,direction TEXT NOT NULL,requested_quantity TEXT NOT NULL,
              entry_mode TEXT NOT NULL,trigger_price TEXT,invalidation_price TEXT,expires_at TEXT);
            CREATE TABLE IF NOT EXISTS stage5_sim_fills(
              fill_id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE,quantity TEXT NOT NULL,
              market_price TEXT NOT NULL,fill_price TEXT NOT NULL,fee_amount TEXT NOT NULL,
              slippage_amount TEXT NOT NULL,observed_at TEXT NOT NULL,provider TEXT NOT NULL,
              source_reference TEXT NOT NULL,partial INTEGER NOT NULL,unfilled_quantity TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stage5_sim_positions(
              position_id TEXT PRIMARY KEY,fill_id TEXT NOT NULL UNIQUE,order_id TEXT NOT NULL UNIQUE,
              symbol TEXT NOT NULL,direction TEXT NOT NULL,quantity TEXT NOT NULL,
              average_price TEXT NOT NULL,fees_paid TEXT NOT NULL,opened_at TEXT NOT NULL,status TEXT NOT NULL);
            """)

    def record_order(self,b:Stage5OrderBinding)->None:
        p=b.plan;i=b.instruction
        values=(b.order_id,p.plan_id,b.strategy_decision.decision_id,b.candidate.dedupe_key,
                b.candidate.symbol,b.strategy_decision.outcome.value,str(p.quantity),i.mode.value,
                None if i.trigger_price is None else str(i.trigger_price),
                None if i.invalidation_price is None else str(i.invalidation_price),
                None if i.expires_at is None else i.expires_at.isoformat())
        with sqlite3.connect(self.db_path) as c:
            row=c.execute("select * from stage5_sim_orders where order_id=?",(b.order_id,)).fetchone()
            if row is None:c.execute("insert into stage5_sim_orders values (?,?,?,?,?,?,?,?,?,?,?)",values)

    def record_fill_and_position(self,b:Stage5OrderBinding,f:Stage5FillDetails)->None:
        pos_id="sim-position:"+f.fill_id.split(":",1)[-1]
        with sqlite3.connect(self.db_path) as c:
            row=c.execute("select fill_id from stage5_sim_fills where order_id=?",(b.order_id,)).fetchone()
            if row is None:
                c.execute("insert into stage5_sim_fills values (?,?,?,?,?,?,?,?,?,?,?,?)",(
                    f.fill_id,f.order_id,str(f.quantity),str(f.market_price),str(f.fill_price),
                    str(f.fee_amount),str(f.slippage_amount),f.observed_at.isoformat(),f.provider,
                    f.source_reference,1 if f.partial else 0,str(f.unfilled_quantity)))
            prow=c.execute("select position_id from stage5_sim_positions where order_id=?",(b.order_id,)).fetchone()
            if prow is None:
                c.execute("insert into stage5_sim_positions values (?,?,?,?,?,?,?,?,?,?)",(
                    pos_id,f.fill_id,b.order_id,b.candidate.symbol,b.strategy_decision.outcome.value,
                    str(f.quantity),str(f.fill_price),str(f.fee_amount),f.observed_at.isoformat(),"OPEN"))
