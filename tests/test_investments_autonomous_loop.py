from datetime import datetime,timezone
from decimal import Decimal
import tempfile
from pathlib import Path
import pytest
from experiment1.models import AccountKind,DecisionAction
from investments.autonomous_loop import *

NOW=datetime(2026,9,6,15,tzinfo=timezone.utc)
def rec(decision,account=AccountKind.INVESTMENTS_GROWTH,revisit=None):
 return InvestmentResearchRecord("obj-"+decision.value,"VWCE",account,decision,NOW,Decimal("0.8"),Decimal("0.7"),"evidence:2026-09-06","thesis","counter",revisit)

def test_three_ledgers_are_valid_and_trading_is_not():
 for a in (AccountKind.INVESTMENTS_DEFENSIVE,AccountKind.INVESTMENTS_BALANCED,AccountKind.INVESTMENTS_GROWTH):
  assert rec(InvestmentResearchDecision.HOLD,a).account is a
 with pytest.raises(ValueError):rec(InvestmentResearchDecision.HOLD,AccountKind.SPOT)

def test_wait_requires_revisit_and_zero_order_semantics():
 with pytest.raises(ValueError):rec(InvestmentResearchDecision.WAIT)
 x=rec(InvestmentResearchDecision.WAIT,revisit="fresh valuation or executability change")
 assert admission_action(x) is DecisionAction.WAIT
 assert admission_action(rec(InvestmentResearchDecision.REJECT)) is None

def test_candidate_like_research_cannot_infer_buy():
 assert admission_action(rec(InvestmentResearchDecision.HOLD)) is DecisionAction.HOLD
 assert admission_action(rec(InvestmentResearchDecision.PARTIAL_BUY)) is DecisionAction.BUY

def test_decision_state_is_durable_and_idempotent():
 with tempfile.TemporaryDirectory() as td:
  s=AutonomousInvestmentStore(Path(td)/"i.db");x=rec(InvestmentResearchDecision.WAIT,revisit="new evidence")
  assert s.record(x);assert not s.record(x);assert s.rows()[0]["decision"]=="WAIT"
