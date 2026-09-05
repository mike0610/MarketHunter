from __future__ import annotations
import sqlite3,tempfile,unittest
from decimal import Decimal
from pathlib import Path

from reports.stage7_analytics import ClosedTradeSample,group_by,summarize
from reports.stage7_repository import Stage7ClosedTradeReader
from reports.stage7_service import build_stage7_report

def sample(pnl,*,strategy="s1",version="1",direction="LONG",reason="TAKE_PROFIT",symbol="SPY"):
 p=Decimal(str(pnl))
 return ClosedTradeSample(symbol,direction,strategy,version,reason,Decimal("1"),Decimal("100"),Decimal("101"),
  p+Decimal("1"),Decimal("0.5"),Decimal("0.5"),p)

class Stage7AnalyticsTests(unittest.TestCase):
 def test_empty_sample_is_explicit_and_safe(self):
  s=summarize(())
  self.assertEqual(s.trades,0);self.assertEqual(s.win_rate,Decimal("0"))
  self.assertIsNone(s.profit_factor);self.assertEqual(s.expectancy,Decimal("0"))

 def test_summary_uses_realized_pnl_after_costs(self):
  s=summarize((sample("9"),sample("-6"),sample("0")))
  self.assertEqual((s.wins,s.losses,s.breakeven),(1,1,1))
  self.assertEqual(s.win_rate,Decimal("50"))
  self.assertEqual(s.gross_profit,Decimal("9"));self.assertEqual(s.gross_loss,Decimal("6"))
  self.assertEqual(s.net_pnl,Decimal("3"));self.assertEqual(s.profit_factor,Decimal("1.5"))
  self.assertEqual(s.expectancy,Decimal("1"));self.assertEqual(s.payoff_ratio,Decimal("1.5"))

 def test_grouping_keeps_strategy_versions_separate(self):
  xs=(sample("5",version="1"),sample("-2",version="2"))
  g=group_by(xs,"strategy_version")
  self.assertEqual(set(g),{"1","2"});self.assertEqual(g["1"].net_pnl,Decimal("5"));self.assertEqual(g["2"].net_pnl,Decimal("-2"))

 def test_reader_reads_only_stage6_closed_trades(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db"
   with sqlite3.connect(db) as c:
    c.executescript("""CREATE TABLE stage6_closed_trades(
closed_trade_id TEXT PRIMARY KEY,position_id TEXT UNIQUE,symbol TEXT,direction TEXT,entry_price TEXT,exit_price TEXT,quantity TEXT,gross_pnl TEXT,entry_fees TEXT,exit_fees TEXT,realized_pnl TEXT,opened_at TEXT,closed_at TEXT,exit_reason TEXT,strategy_id TEXT,strategy_version TEXT,strategy_decision_id TEXT,candidate_dedupe_key TEXT);
CREATE TABLE research_trades(id TEXT, realized_pnl TEXT);""")
    c.execute("insert into stage6_closed_trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
     ("ct1","p1","SPY","LONG","100","110","2","20","1","1","18","2026-09-01T00:00:00+00:00","2026-09-02T00:00:00+00:00","TAKE_PROFIT","s1","1","d1","c1"))
    c.execute("insert into research_trades values ('legacy','999999')")
   rows=Stage7ClosedTradeReader(db).read_all()
   self.assertEqual(len(rows),1);self.assertEqual(rows[0].realized_pnl,Decimal("18"))

 def test_report_is_advisory_and_exposes_sample_size(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db"
   report=build_stage7_report(db)
   self.assertEqual(report["sample_size"],0)
   self.assertIn("analytics only",report["automation_note"])
   self.assertNotIn("action",report);self.assertNotIn("decision",report)

 def test_unsupported_group_field_fails_closed(self):
  with self.assertRaises(ValueError):group_by((sample("1"),),"secret_dimension")

if __name__=="__main__":unittest.main()
