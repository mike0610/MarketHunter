from __future__ import annotations
import sqlite3,tempfile,unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from simulation.stage6_engine import build_exit_fill,evaluate_exit
from simulation.stage6_manager import Stage6PositionManager
from simulation.stage6_models import *
from simulation.stage6_store import Stage6PositionStore

T0=datetime(2026,9,5,12,tzinfo=timezone.utc)
def pos(direction="LONG"):
 return ManagedPosition("sim-position:p1","sim-order:o1","SPY",direction,Decimal("10"),Decimal("100"),Decimal("1"),T0,
  "decision-1","dedupe-1","strategy-1","1")
def policy(**kw):
 d=dict(strategy_id="strategy-1",strategy_version="1",stop_loss=Decimal("95"),take_profit=Decimal("110"),
        partial_take_profit=Decimal("105"),partial_fraction=Decimal("0.5"),structural_invalidation=Decimal("94"),expires_at=T0+timedelta(days=5))
 d.update(kw);return PositionExitPolicy(**d)
def bar(o="100",h="104",l="99",c="102",mins=30,fresh=True,ref="e1"):
 return PositionBarEvidence("SPY",Decimal(o),Decimal(h),Decimal(l),Decimal(c),T0+timedelta(minutes=mins),"YAHOO",ref,fresh)

class Stage6Tests(unittest.TestCase):
 def test_hold(self):
  self.assertEqual(evaluate_exit(pos(),policy(),bar()).verdict,ExitVerdict.HOLD)

 def test_stale_fails_closed(self):
  self.assertEqual(evaluate_exit(pos(),policy(),bar(fresh=False)).verdict,ExitVerdict.BLOCKED)

 def test_strategy_version_mismatch_blocks(self):
  self.assertEqual(evaluate_exit(pos(),policy(strategy_version="2"),bar()).verdict,ExitVerdict.BLOCKED)

 def test_gap_through_long_stop_uses_worse_open(self):
  x=evaluate_exit(pos(),policy(partial_take_profit=None,partial_fraction=None),bar(o="90",h="92",l="88",c="91"))
  self.assertEqual(x.reason,ExitReason.STOP_LOSS);self.assertEqual(x.raw_exit_price,Decimal("90"))

 def test_same_bar_stop_and_target_is_ambiguous(self):
  x=evaluate_exit(pos(),policy(),bar(h="111",l="94"))
  self.assertEqual(x.verdict,ExitVerdict.AMBIGUOUS)

 def test_structural_exit(self):
  x=evaluate_exit(pos(),policy(stop_loss=Decimal("90"),partial_take_profit=None,partial_fraction=None),bar(l="93"))
  self.assertEqual(x.reason,ExitReason.STRUCTURAL_INVALIDATION)

 def test_time_exit(self):
  x=evaluate_exit(pos(),policy(stop_loss=Decimal("90"),take_profit=Decimal("120"),partial_take_profit=None,partial_fraction=None,structural_invalidation=Decimal("89"),expires_at=T0+timedelta(minutes=10)),bar(mins=30))
  self.assertEqual(x.reason,ExitReason.TIME_EXIT);self.assertEqual(x.raw_exit_price,Decimal("102"))

 def test_exit_slippage_is_adverse(self):
  p=pos();e=bar(h="111",ref="tp");x=evaluate_exit(p,policy(partial_take_profit=None,partial_fraction=None),e)
  f=build_exit_fill(p,x,e,fee_bps=Decimal("5"),slippage_bps=Decimal("10"))
  self.assertLess(f.fill_price,Decimal("110"));self.assertGreater(f.fee_amount,0)

 def test_partial_restart_then_stop_closes_once_with_correct_pnl(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"s.db";p=pos();pol=policy()
   m1=Stage6PositionManager(Stage6PositionStore(db),fee_bps=Decimal("0"),slippage_bps=Decimal("0"))
   x1=m1.process(p,pol,bar(h="106",l="99",c="105",ref="partial"))
   self.assertEqual(x1.reason,ExitReason.PARTIAL_TAKE_PROFIT)
   rem,partial,status=Stage6PositionStore(db).restore(p)
   self.assertEqual(rem,Decimal("5.0"));self.assertTrue(partial);self.assertEqual(status,"OPEN")
   # restart manager/store, then adverse stop
   m2=Stage6PositionManager(Stage6PositionStore(db),fee_bps=Decimal("0"),slippage_bps=Decimal("0"))
   x2=m2.process(p,pol,bar(o="96",h="100",l="94",c="95",mins=60,ref="stop"))
   self.assertEqual(x2.reason,ExitReason.STOP_LOSS)
   ct=Stage6PositionStore(db).closed_trade(p.position_id)
   self.assertIsNotNone(ct);self.assertEqual(ct.quantity,Decimal("10.0"))
   self.assertEqual(ct.exit_price,Decimal("100.0"))
   self.assertEqual(ct.gross_pnl,Decimal("0.00"))
   self.assertEqual(ct.realized_pnl,Decimal("-1.00"))
   # same evidence after restart cannot close twice
   m3=Stage6PositionManager(Stage6PositionStore(db),fee_bps=Decimal("0"),slippage_bps=Decimal("0"))
   x3=m3.process(p,pol,bar(o="96",h="100",l="94",c="95",mins=60,ref="stop"))
   self.assertEqual(x3.detail,"already closed")
   with sqlite3.connect(db) as c:
    self.assertEqual(c.execute("select count(*) from stage6_exit_fills").fetchone()[0],2)
    self.assertEqual(c.execute("select count(*) from stage6_closed_trades").fetchone()[0],1)

 def test_partial_is_not_repeated(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"s.db";p=pos();pol=policy();m=Stage6PositionManager(Stage6PositionStore(db),fee_bps=Decimal("0"),slippage_bps=Decimal("0"))
   m.process(p,pol,bar(h="106",ref="partial1"))
   x=m.process(p,pol,bar(h="106",mins=60,ref="partial2"))
   self.assertEqual(x.verdict,ExitVerdict.HOLD)

 def test_short_gap_stop_uses_worse_open(self):
  p=pos("SHORT");pol=policy(stop_loss=Decimal("105"),take_profit=Decimal("90"),partial_take_profit=None,partial_fraction=None,structural_invalidation=Decimal("106"))
  x=evaluate_exit(p,pol,bar(o="110",h="112",l="108",c="109"))
  self.assertEqual(x.reason,ExitReason.STOP_LOSS);self.assertEqual(x.raw_exit_price,Decimal("110"))

if __name__=="__main__":unittest.main()
