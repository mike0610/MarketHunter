from datetime import datetime,timedelta,timezone
from decimal import Decimal
import tempfile
from pathlib import Path

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind,DecisionAction,MarketQuote
from investments.autonomous_loop import *
from investments.stage8_decision_bridge import Stage8InvestmentDecision,InvestmentDecisionSource
from investments.stage8_portfolio import portfolio_gate

NOW=datetime(2026,9,6,15,tzinfo=timezone.utc)

def research(decision,account=AccountKind.INVESTMENTS_GROWTH,revisit=None):
 return InvestmentResearchRecord("e2e-"+decision.value,"PROOF",account,decision,NOW,Decimal("0.85"),Decimal("0.90"),"proof:evidence:2026-09-06","fresh thesis","counter thesis",revisit)

def test_one_complete_buy_object_reaches_only_growth_paper_position():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);store=AutonomousInvestmentStore(root/"research.db");engine=Experiment1Engine(root/"paper.db")
  r=research(InvestmentResearchDecision.PARTIAL_BUY);assert store.record(r)
  d=Stage8InvestmentDecision("gil-e2e-investment-001",r.object_id,InvestmentDecisionSource.GIL,r.account,DecisionAction.BUY,r.symbol,r.decided_at,Decimal("10"),r.thesis,r.evidence_reference,"gil:gil-e2e-investment-001")
  gate=portfolio_gate(engine,d,execution_price=Decimal("100"),max_position_fraction=Decimal("0.25"))
  assert gate.approved and gate.intent is not None
  assert engine.submit_intent(gate.intent).value=="PENDING"
  fill=engine.execute_pending(gate.intent.intent_id,MarketQuote("PROOF",Decimal("100"),NOW+timedelta(minutes=1),"SIMULATED_EVIDENCE","proof:quote",Decimal("0"),Decimal("0")))
  assert fill.account is AccountKind.INVESTMENTS_GROWTH
  pos=engine.positions(AccountKind.INVESTMENTS_GROWTH);assert len(pos)==1 and pos[0].quantity==Decimal("10")
  assert engine.positions(AccountKind.INVESTMENTS_DEFENSIVE)==()
  assert engine.positions(AccountKind.INVESTMENTS_BALANCED)==()
  assert engine.account_state(AccountKind.INVESTMENTS_GROWTH).cash==Decimal("4000")
  assert len(store.rows())==1

def test_wait_hold_reject_produce_zero_order():
 with tempfile.TemporaryDirectory() as td:
  engine=Experiment1Engine(Path(td)/"paper.db")
  for decision,revisit in ((InvestmentResearchDecision.WAIT,"valuation changes"),(InvestmentResearchDecision.HOLD,None),(InvestmentResearchDecision.REJECT,None)):
   r=research(decision,revisit=revisit)
   action=admission_action(r)
   if action in (DecisionAction.WAIT,DecisionAction.HOLD):
    d=Stage8InvestmentDecision("d-"+decision.value,r.object_id,InvestmentDecisionSource.GIL,r.account,action,r.symbol,r.decided_at,Decimal("0"),r.thesis,r.evidence_reference,"gil:d")
    gate=portfolio_gate(engine,d,execution_price=Decimal("100"),max_position_fraction=Decimal("0.25"))
    assert not gate.approved and gate.intent is None
   else:
    assert action is None
  assert engine.pending_intent_ids()==()
  assert engine.positions(AccountKind.INVESTMENTS_GROWTH)==()
