from __future__ import annotations
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from risk_mm.engine import evaluate_risk
from risk_mm.models import PortfolioRiskState,RiskDecision,RiskInput,RiskPolicy,TradingAccount
from strategies.registry_foundation import StrategyUsability,StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext

NOW=datetime(2026,9,5,12,tzinfo=timezone.utc)
USABLE=StrategyVersionAssessment(StrategyUsability.USABLE,())
POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"))

def candidate(ref):
 return TradingCandidate(1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("BREAKOUT confirmed",),
  LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("500")),VolatilityContext(Decimal("1.2")),
  "OK",True,NOW,"cycle-1","1:BREAKOUT:cycle-1",QueueState.CANDIDATE,invalidation_reference=ref)

def state():
 return PortfolioRiskState(TradingAccount.SPOT,Decimal("2000"),Decimal("2000"),Decimal("0"),Decimal("0"),"US_MEGA_TECH",Decimal("1"))

class Stage10StructuralStopContractTests(unittest.TestCase):
 def test_evidence_backed_stop_can_feed_existing_risk_engine(self):
  d=validate_candidate(candidate("close back below the breakout level (490)"),strategy_assessment=USABLE,decided_at=NOW)
  p=evaluate_risk(RiskInput(d.decision_id,d.symbol,d.outcome.value,d.decided_at,d.candidate_evidence_status,d.reference_price,d.structural_stop_price,"US_MEGA_TECH"),state(),POLICY,evaluated_at=NOW)
  self.assertEqual(p.decision,RiskDecision.APPROVED)

 def test_missing_stop_is_rejected_by_existing_risk_engine(self):
  d=validate_candidate(candidate(None),strategy_assessment=USABLE,decided_at=NOW)
  p=evaluate_risk(RiskInput(d.decision_id,d.symbol,d.outcome.value,d.decided_at,d.candidate_evidence_status,d.reference_price,d.structural_stop_price,"US_MEGA_TECH"),state(),POLICY,evaluated_at=NOW)
  self.assertEqual(p.decision,RiskDecision.REJECTED)
  self.assertIn("INVALID_OR_MISSING_STOP",p.reasons)

if __name__=="__main__":unittest.main()
