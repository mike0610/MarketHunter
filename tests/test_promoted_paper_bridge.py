from __future__ import annotations
import tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import pytest

from experiment1.models import AccountKind,AccountState
from research.autonomous_loop.models import ResearchObject
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskDecision,RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_bridge import PaperAdmissionError,build_promoted_paper_binding,load_paper_admission
from strategies.runtime_release_manifest import STRATEGY_RELEASE_MANIFEST
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext

POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"))

def state():
 return AccountState(AccountKind.SPOT,Decimal("2000"),Decimal("2000"),Decimal("0"),Decimal("0"),Decimal("2000"),Decimal("2000"),Decimal("0"),Decimal("0"),Decimal("2000"))

def candidate(when,*,stop=True):
 return TradingCandidate(
  1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("PULLBACK frozen",),
  LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("500")),
  VolatilityContext(Decimal("2")),"OK",True,when,"scan-1","1:BREAKOUT_OR_PULLBACK_IN_TREND:scan-1",QueueState.CANDIDATE,
  invalidation_reference="close below structural stop (490)" if stop else None,
  signal_bar_high=Decimal("505"),signal_bar_low=Decimal("495"),
 )

def promotion(repo,*,contract=True):
 repo.enqueue(ResearchObject("P","SPY","LONG","H-P"))
 ev={"oos":{"avg_r":"0.2","pf":"1.3"}}
 if contract:
  ev["paper_contract"]={
   "strategy_id":"TEST-PROMOTED","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND",
   "direction":"LONG","account":"SPOT","requested_leverage":"1","cluster_key":"US_EQ",
   "entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":259200,
  }
 repo.terminal("P","PROMOTION-ELIGIBLE",ev,hypothesis_id="H-P")
 return load_paper_admission(repo,"P")

def test_promoted_forward_candidate_reaches_risk_and_stage5_conditional_binding():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);repo=AutonomousResearchRepository(root/"research.db");adm=promotion(repo)
  c=candidate(adm.promoted_at+timedelta(seconds=1))
  out=build_promoted_paper_binding(repo=repo,object_id="P",candidate=c,
   strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
   account_state=state(),open_risk_ledger=OpenRiskLedger(root/"open.db"),risk_policy=POLICY)
  assert out.risk.risk_plan.decision is RiskDecision.APPROVED
  assert out.binding is not None
  assert out.binding.instruction.mode.value=="PRICE_AT_OR_ABOVE"
  assert out.binding.instruction.trigger_price==Decimal("505")
  assert out.binding.strategy_decision.strategy_id=="TEST-PROMOTED"
  assert out.binding.strategy_decision.strategy_version=="1"
  assert STRATEGY_RELEASE_MANIFEST.declarations==()

def test_candidate_from_before_promotion_is_rejected_fail_closed():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);repo=AutonomousResearchRepository(root/"research.db");adm=promotion(repo)
  with pytest.raises(PaperAdmissionError,match="forward candidates only"):
   build_promoted_paper_binding(repo=repo,object_id="P",candidate=candidate(adm.promoted_at-timedelta(seconds=1)),
    strategy_store=StrategyDecisionStore(root/"s.db"),risk_store=RiskPlanStore(root/"r.db"),account_state=state(),
    open_risk_ledger=OpenRiskLedger(root/"o.db"),risk_policy=POLICY)

def test_promotion_without_runtime_contract_does_not_trade():
 with tempfile.TemporaryDirectory() as td:
  repo=AutonomousResearchRepository(Path(td)/"r.db")
  repo.enqueue(ResearchObject("P","SPY","LONG","H-P"))
  repo.terminal("P","PROMOTION-ELIGIBLE",{"oos":{"avg_r":"0.2"}},hypothesis_id="H-P")
  with pytest.raises(PaperAdmissionError,match="no runtime-compatible paper_contract"):
   load_paper_admission(repo,"P")

def test_risk_rejection_never_creates_stage5_order():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);repo=AutonomousResearchRepository(root/"research.db");adm=promotion(repo)
  out=build_promoted_paper_binding(repo=repo,object_id="P",candidate=candidate(adm.promoted_at+timedelta(seconds=1),stop=False),
   strategy_store=StrategyDecisionStore(root/"s.db"),risk_store=RiskPlanStore(root/"r.db"),account_state=state(),
   open_risk_ledger=OpenRiskLedger(root/"o.db"),risk_policy=POLICY)
  assert out.risk.risk_plan.decision is RiskDecision.REJECTED
  assert out.binding is None
