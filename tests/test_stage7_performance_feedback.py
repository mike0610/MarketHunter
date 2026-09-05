from __future__ import annotations
import sqlite3,tempfile,unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from reports.stage7_analytics import ClosedTradeSample,TREND_UNKNOWN,group_by,summarize
from reports.stage7_repository import Stage7ClosedTradeReader
from reports.stage7_service import build_stage7_report

T0=datetime(2026,9,1,tzinfo=timezone.utc)
def sample(pnl,*,strategy="s1",version="1",direction="LONG",reason="TAKE_PROFIT",symbol="SPY",setup="BREAKOUT",risk="5",hours=24,closed_id="ct"):
 p=Decimal(str(pnl))
 return ClosedTradeSample(closed_id,"p-"+closed_id,symbol,direction,strategy,version,setup,TREND_UNKNOWN,reason,Decimal("1"),
  Decimal("100"),Decimal("101"),p+Decimal("1"),Decimal("0.5"),Decimal("0.5"),p,T0,T0+timedelta(hours=hours),
  None if risk is None else Decimal(risk),"cand-"+closed_id,"dec-"+closed_id,"risk-"+closed_id,"ord-"+closed_id,"fill-"+closed_id)

class Stage7AnalyticsTests(unittest.TestCase):
 def test_empty_sample_is_explicit_and_safe(self):
  s=summarize(())
  self.assertEqual(s.trades,0);self.assertEqual(s.win_rate,Decimal("0"));self.assertEqual(s.max_drawdown,Decimal("0"))
  self.assertIsNone(s.profit_factor);self.assertIsNone(s.average_r_multiple);self.assertIsNone(s.average_holding_seconds)

 def test_summary_costs_drawdown_r_and_holding_time(self):
  xs=(sample("9",risk="3",hours=24,closed_id="1"),sample("-6",risk="3",hours=48,closed_id="2"),sample("0",risk=None,hours=72,closed_id="3"))
  s=summarize(xs)
  self.assertEqual((s.wins,s.losses,s.breakeven),(1,1,1));self.assertEqual(s.win_rate,Decimal("50"))
  self.assertEqual(s.net_pnl,Decimal("3"));self.assertEqual(s.profit_factor,Decimal("1.5"));self.assertEqual(s.expectancy,Decimal("1"))
  self.assertEqual(s.max_drawdown,Decimal("6"));self.assertEqual(s.average_r_multiple,Decimal("0.5"))
  self.assertEqual(s.average_holding_seconds,Decimal("172800.0"))

 def test_grouping_keeps_version_setup_direction_and_trend_separate(self):
  xs=(sample("5",version="1",setup="A",direction="LONG",closed_id="1"),sample("-2",version="2",setup="B",direction="SHORT",closed_id="2"))
  self.assertEqual(set(group_by(xs,"strategy_version")),{"1","2"})
  self.assertEqual(set(group_by(xs,"setup_family")),{"A","B"})
  self.assertEqual(set(group_by(xs,"direction")),{"LONG","SHORT"})
  self.assertEqual(set(group_by(xs,"trend_alignment")),{TREND_UNKNOWN})

 def test_reader_provenance_and_no_legacy_contamination(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db"
   with sqlite3.connect(db) as c:
    c.executescript("""CREATE TABLE stage6_closed_trades(
closed_trade_id TEXT PRIMARY KEY,position_id TEXT UNIQUE,symbol TEXT,direction TEXT,entry_price TEXT,exit_price TEXT,quantity TEXT,gross_pnl TEXT,entry_fees TEXT,exit_fees TEXT,realized_pnl TEXT,opened_at TEXT,closed_at TEXT,exit_reason TEXT,strategy_id TEXT,strategy_version TEXT,strategy_decision_id TEXT,candidate_dedupe_key TEXT);
CREATE TABLE strategy_decisions(decision_id TEXT PRIMARY KEY,setup_family TEXT,outcome TEXT);
CREATE TABLE stage5_sim_orders(order_id TEXT PRIMARY KEY,risk_plan_id TEXT,strategy_decision_id TEXT,candidate_dedupe_key TEXT);
CREATE TABLE stage5_sim_fills(fill_id TEXT PRIMARY KEY,order_id TEXT);
CREATE TABLE risk_sized_plans(plan_id TEXT PRIMARY KEY,risk_amount TEXT);
CREATE TABLE research_trades(id TEXT,realized_pnl TEXT);""")
    c.execute("insert into stage6_closed_trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("ct1","p1","SPY","LONG","100","110","2","20","1","1","18",T0.isoformat(),(T0+timedelta(days=1)).isoformat(),"TAKE_PROFIT","s1","1","d1","c1"))
    c.execute("insert into strategy_decisions values ('d1','BREAKOUT','LONG')")
    c.execute("insert into stage5_sim_orders values ('o1','r1','d1','c1')")
    c.execute("insert into stage5_sim_fills values ('f1','o1')")
    c.execute("insert into risk_sized_plans values ('r1','10')")
    c.execute("insert into research_trades values ('legacy','999999')")
   row=Stage7ClosedTradeReader(db).read_all()[0]
   self.assertEqual(row.realized_pnl,Decimal("18"));self.assertEqual(row.setup_family,"BREAKOUT")
   self.assertEqual(row.initial_risk_amount,Decimal("10"));self.assertEqual(row.r_multiple,Decimal("1.8"))
   self.assertEqual((row.risk_plan_id,row.order_id,row.entry_fill_id),("r1","o1","f1"));self.assertEqual(row.trend_alignment,TREND_UNKNOWN)

 def test_rejected_no_trade_and_candidate_states_are_separate(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db"
   with sqlite3.connect(db) as c:
    c.executescript("""CREATE TABLE strategy_decisions(decision_id TEXT,outcome TEXT);
CREATE TABLE trading_scanner_candidates(id TEXT,queue_state TEXT);""")
    c.executemany("insert into strategy_decisions values (?,?)",[("d1","LONG"),("d2","NO_TRADE"),("d3","NO_TRADE")])
    c.executemany("insert into trading_scanner_candidates values (?,?)",[("c1","CANDIDATE"),("c2","REJECTED")])
   r=Stage7ClosedTradeReader(db)
   self.assertEqual(r.decision_outcomes(),{"LONG":1,"NO_TRADE":2})
   self.assertEqual(r.candidate_states(),{"CANDIDATE":1,"REJECTED":1})

 def test_report_is_reproducible_advisory_and_does_not_infer_trend(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db"
   a=build_stage7_report(db);b=build_stage7_report(db)
   self.assertEqual(a,b);self.assertEqual(a["sample_size"],0)
   self.assertIn("analytics only",a["automation_note"]);self.assertIn(TREND_UNKNOWN,a["trend_alignment_note"])
   self.assertNotIn("action",a);self.assertNotIn("tuning",a)

 def test_unsupported_group_field_fails_closed(self):
  with self.assertRaises(ValueError):group_by((sample("1"),),"secret_dimension")

if __name__=="__main__":unittest.main()
