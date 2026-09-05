from __future__ import annotations
import sqlite3,tempfile,unittest
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from experiment1.models import AccountKind,DecisionAction
from investments.stage8_boundary import assert_investment_account,assert_investment_action
from investments.stage8_models import *
from investments.stage8_router import route_investment_candidate
from investments.stage8_store import Stage8InvestmentStore

NOW=datetime(2026,9,5,tzinfo=timezone.utc)
def cand(*,score="80",rule=None,fresh=True,state=InvestmentCandidateState.CANDIDATE):
 e=InvestmentEvidence("REAL_PROVIDER",NOW,"market:ABC:20260905",Decimal("100"),"fund:ABC:q2",None,fresh)
 return InvestmentCandidate("ic-1","ABC","INVESTMENT-US","QUALITY_VALUE",Decimal(score),rule,e,state,"screen")

class Stage8Tests(unittest.TestCase):
 def test_material_deterministic_rule_routes_deterministically(self):
  x=route_investment_candidate(cand(rule="INV-RULE-1"),materiality_floor=Decimal("50"))
  self.assertEqual(x.route,InvestmentRoute.DETERMINISTIC)

 def test_material_without_formal_rule_routes_to_gil(self):
  x=route_investment_candidate(cand(),materiality_floor=Decimal("50"))
  self.assertEqual(x.route,InvestmentRoute.GIL_DEEP_ANALYSIS)

 def test_low_materiality_rejects(self):
  self.assertEqual(route_investment_candidate(cand(score="10"),materiality_floor=Decimal("50")).route,InvestmentRoute.REJECT)

 def test_stale_evidence_fails_closed_even_with_rule(self):
  self.assertEqual(route_investment_candidate(cand(rule="R",fresh=False),materiality_floor=Decimal("50")).route,InvestmentRoute.REJECT)

 def test_trading_accounts_cannot_enter_investment_flow(self):
  for a in (AccountKind.SPOT,AccountKind.FUTURES):
   with self.assertRaises(ValueError):assert_investment_account(a)
  for a in (AccountKind.INVESTMENTS_DEFENSIVE,AccountKind.INVESTMENTS_BALANCED,AccountKind.INVESTMENTS_GROWTH):
   assert_investment_account(a)

 def test_investment_actions_exclude_long_short_semantics(self):
  for a in (DecisionAction.BUY,DecisionAction.SELL,DecisionAction.WAIT,DecisionAction.HOLD):assert_investment_action(a)

 def test_candidate_and_route_are_durable_and_idempotent(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"i.db";s=Stage8InvestmentStore(db);c=cand();r=route_investment_candidate(c,materiality_floor=Decimal("50"))
   self.assertTrue(s.record_candidate(c));self.assertFalse(s.record_candidate(c))
   self.assertTrue(s.record_route(r));self.assertFalse(s.record_route(r))
   with sqlite3.connect(db) as con:
    self.assertEqual(con.execute("select count(*) from stage8_investment_candidates").fetchone()[0],1)
    self.assertEqual(con.execute("select count(*) from stage8_investment_routes").fetchone()[0],1)

if __name__=="__main__":unittest.main()
