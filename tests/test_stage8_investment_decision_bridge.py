from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from experiment1.engine import Experiment1Engine
from experiment1.models import *
from investments.stage8_decision_bridge import *
from investments.stage8_market_guard import require_independent_execution_evidence
from investments.stage8_models import *
from investments.stage8_portfolio import portfolio_gate
NOW=datetime(2026,9,5,14,tzinfo=timezone.utc)
def candidate(rule=None):
 e=InvestmentEvidence("PROVIDER",NOW,"src:1",Decimal("100"),"fund:1",None,True)
 return InvestmentCandidate("c1","SPY","US","QUALITY",Decimal("90"),rule,e,InvestmentCandidateState.CANDIDATE,"ok")
def route(kind,rule=None):return InvestmentRoutingResult("c1",kind,"ok",rule,"src:1",NOW)
class Stage8BridgeTests(unittest.TestCase):
 def test_gil_route_without_actual_decision_fails_closed(self):
  with self.assertRaises(ValueError):require_gil_decision(route(InvestmentRoute.GIL_DEEP_ANALYSIS),None)
 def test_deterministic_route_requires_formal_rule(self):
  with self.assertRaises(ValueError):deterministic_decision(candidate(),route(InvestmentRoute.GIL_DEEP_ANALYSIS),account=AccountKind.INVESTMENTS_GROWTH,action=DecisionAction.BUY,quantity=Decimal("1"),thesis="x")
 def test_gil_cannot_cross_into_trading(self):
  g=GilDecision("g1",NOW,AccountKind.FUTURES,DecisionAction.LONG,"SPY","x",Decimal("1"),Decimal("1"))
  with self.assertRaises(ValueError):gil_decision(candidate(),route(InvestmentRoute.GIL_DEEP_ANALYSIS),g)
 def test_market_guard_accepts_only_execution_grade(self):
  good=MarketDataEvidence("SIP","SPY","SPY","XNYS","USD",Decimal("100"),PriceType.TRADE,NOW,NOW,SessionState.REGULAR,QuoteMode.REALTIME,"tick:1")
  self.assertIs(require_independent_execution_evidence(good,instrument="SPY",currency="USD",exchange="XNYS",now=NOW+timedelta(seconds=1),max_age_seconds=5),good)
  bad=MarketDataEvidence("SIP","SPY","SPY","XNYS","USD",Decimal("100"),PriceType.EOD_CLOSE,NOW,NOW,SessionState.CLOSED,QuoteMode.EOD,"eod:1")
  with self.assertRaises(ValueError):require_independent_execution_evidence(bad,instrument="SPY",currency="USD",exchange="XNYS",now=NOW+timedelta(seconds=1),max_age_seconds=5)
 def test_portfolio_gate_wait_does_not_create_intent(self):
  with tempfile.TemporaryDirectory() as td:
   e=Experiment1Engine(Path(td)/"x.db")
   d=Stage8InvestmentDecision("d","c",InvestmentDecisionSource.DETERMINISTIC_RULE,AccountKind.INVESTMENTS_GROWTH,DecisionAction.WAIT,"SPY",NOW,Decimal("0"),"wait","src","r1")
   r=portfolio_gate(e,d,execution_price=Decimal("100"),max_position_fraction=Decimal("0.25"))
   self.assertFalse(r.approved);self.assertIsNone(r.intent)
 def test_portfolio_gate_is_investment_only_and_caps_concentration(self):
  with tempfile.TemporaryDirectory() as td:
   e=Experiment1Engine(Path(td)/"x.db")
   d=Stage8InvestmentDecision("d","c",InvestmentDecisionSource.DETERMINISTIC_RULE,AccountKind.INVESTMENTS_GROWTH,DecisionAction.BUY,"SPY",NOW,Decimal("20"),"buy","src","r1")
   r=portfolio_gate(e,d,execution_price=Decimal("100"),max_position_fraction=Decimal("0.25"))
   self.assertFalse(r.approved);self.assertEqual(r.reason,"investment concentration limit")
 def test_approved_decision_maps_to_existing_engine_intent(self):
  with tempfile.TemporaryDirectory() as td:
   e=Experiment1Engine(Path(td)/"x.db")
   d=Stage8InvestmentDecision("d","c",InvestmentDecisionSource.DETERMINISTIC_RULE,AccountKind.INVESTMENTS_DEFENSIVE,DecisionAction.BUY,"SPY",NOW,Decimal("5"),"buy","src","r1")
   r=portfolio_gate(e,d,execution_price=Decimal("100"),max_position_fraction=Decimal("0.25"))
   self.assertTrue(r.approved);self.assertEqual(r.intent.account,AccountKind.INVESTMENTS_DEFENSIVE);self.assertEqual(r.intent.action,DecisionAction.BUY)
if __name__=="__main__":unittest.main()
