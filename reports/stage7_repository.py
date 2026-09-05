from __future__ import annotations
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from reports.stage7_analytics import ClosedTradeSample,TREND_UNKNOWN

class Stage7ClosedTradeReader:
 """Read-only reproducible analytics/provenance seam over Stage 2-6 durable tables."""
 def __init__(self,db_path:str|Path)->None:self.db_path=Path(db_path)

 def _tables(self,c)->set[str]:
  return {r[0] for r in c.execute("select name from sqlite_master where type='table'")}

 def read_all(self)->tuple[ClosedTradeSample,...]:
  if not self.db_path.exists():return ()
  with sqlite3.connect(self.db_path) as c:
   tables=self._tables(c)
   if "stage6_closed_trades" not in tables:return ()
   where_clause = ""
   if "stage10_test_only_provenance" in tables:
    where_clause = """ where not exists (
      select 1 from stage10_test_only_provenance t
      where t.position_id = stage6_closed_trades.position_id
    )"""
   rows=c.execute("""select closed_trade_id,position_id,symbol,direction,strategy_id,strategy_version,
      exit_reason,quantity,entry_price,exit_price,gross_pnl,entry_fees,exit_fees,realized_pnl,
      opened_at,closed_at,strategy_decision_id,candidate_dedupe_key
      from stage6_closed_trades""" + where_clause + """ order by closed_at,closed_trade_id""").fetchall()
   out=[]
   for r in rows:
    decision_id=r[16];candidate_key=r[17]
    setup_family="UNKNOWN"
    if "strategy_decisions" in tables:
     d=c.execute("select setup_family from strategy_decisions where decision_id=?",(decision_id,)).fetchone()
     if d:setup_family=d[0]
    risk_plan_id=order_id=entry_fill_id=None
    risk_amount=None
    if "stage5_sim_orders" in tables:
     o=c.execute("select order_id,risk_plan_id from stage5_sim_orders where strategy_decision_id=? order by order_id limit 1",(decision_id,)).fetchone()
     if o:order_id,risk_plan_id=o[0],o[1]
    if order_id and "stage5_sim_fills" in tables:
     f=c.execute("select fill_id from stage5_sim_fills where order_id=?",(order_id,)).fetchone()
     if f:entry_fill_id=f[0]
    if risk_plan_id and "risk_sized_plans" in tables:
     rp=c.execute("select risk_amount from risk_sized_plans where plan_id=?",(risk_plan_id,)).fetchone()
     if rp and rp[0] is not None:risk_amount=Decimal(rp[0])
    out.append(ClosedTradeSample(
      r[0],r[1],r[2],r[3],r[4],r[5],setup_family,TREND_UNKNOWN,r[6],Decimal(r[7]),Decimal(r[8]),
      Decimal(r[9]),Decimal(r[10]),Decimal(r[11]),Decimal(r[12]),Decimal(r[13]),
      datetime.fromisoformat(r[14]),datetime.fromisoformat(r[15]),risk_amount,candidate_key,decision_id,
      risk_plan_id,order_id,entry_fill_id))
  return tuple(out)

 def decision_outcomes(self)->dict[str,int]:
  if not self.db_path.exists():return {}
  with sqlite3.connect(self.db_path) as c:
   if "strategy_decisions" not in self._tables(c):return {}
   rows=c.execute("select outcome,count(*) from strategy_decisions group by outcome order by outcome").fetchall()
  return {r[0]:r[1] for r in rows}

 def candidate_states(self)->dict[str,int]:
  if not self.db_path.exists():return {}
  with sqlite3.connect(self.db_path) as c:
   if "trading_scanner_candidates" not in self._tables(c):return {}
   rows=c.execute("select queue_state,count(*) from trading_scanner_candidates group by queue_state order by queue_state").fetchall()
  return {r[0]:r[1] for r in rows}
