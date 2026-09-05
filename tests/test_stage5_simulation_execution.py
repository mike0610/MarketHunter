from __future__ import annotations
import sqlite3,tempfile,unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from risk_mm.models import RiskDecision,SizedExecutionPlan,TradingAccount
from simulation.foundation import MarketObservationEvidence,MarketObservationReference,SimulationCampaignReference,SimulationEventType
from simulation.runtime.contracts import RuntimeOperationalStatus,RuntimeSourceState
from simulation.runtime.orchestrator import SimulationRuntime
from simulation.stage5_bridge import *
from simulation.stage5_store import Stage5ExecutionStore
from strategy_engine.models import StrategyDecisionOutcome,StrategyDecisionRecord
from time_semantics.foundation import TemporalDisposition,TemporalFact,TemporalReference,TemporalRole
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext

T0=datetime(2026,9,5,12,tzinfo=timezone.utc); T1=T0+timedelta(minutes=1)

def candidate():
 return TradingCandidate(1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("setup",),
  LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("500")),VolatilityContext(Decimal("2")),
  "OK",True,T0,"scan-1","dedupe-1",QueueState.CANDIDATE)

def decision(outcome=StrategyDecisionOutcome.LONG):
 return StrategyDecisionRecord("decision-1","dedupe-1","SPY",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,
  "strategy-1","1",outcome,T0,("valid",),"scan-1",T0,"OK",None)

def plan(decision_state=RiskDecision.APPROVED,quantity=Decimal("10")):
 return SizedExecutionPlan("plan-1","decision-1",decision_state,TradingAccount.SPOT,"risk","1",T0,("ok",),
  quantity,Decimal("500"),Decimal("490"),Decimal("50"),Decimal("5000"),Decimal("1"))

def observation(price="501",volume="10000",when=T1,ref="obs-1"):
 tr=TemporalReference("market_observation",ref,"1")
 ev=MarketObservationEvidence(MarketObservationReference("yahoo","NASDAQ","SPY","1m",ref),
  TemporalFact(tr,TemporalRole.EVENT_TIME,when,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.OBSERVED_TIME,when,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.RECORDED_TIME,when,TemporalDisposition.KNOWN))
 return Stage5MarketObservation(ev,Decimal(price),None if volume is None else Decimal(volume),"YAHOO",ref)

def binding(instruction=None,p=None):
 return build_order_binding(p or plan(),candidate(),decision(),instruction or Stage5EntryInstruction(Stage5EntryMode.MARKET,None,Decimal("490"),None))

def runtime_parts(b,obs,policy=None):
 env=binding_to_envelope(b,campaign=SimulationCampaignReference("stage5",1),recorded_at=T0)
 key=env.snapshot.candidate.source_id
 pol=policy or Stage5MechanicsPolicy("stage5-mechanics","1",Decimal("5"),Decimal("10"),Decimal("0.01"),True)
 evaluator=Stage5MechanicsEvaluator({key:b},{key:obs},pol)
 return env,evaluator

class Stage5BridgeTests(unittest.TestCase):
 def test_rejected_plan_cannot_create_order(self):
  with self.assertRaises(ValueError): binding(p=plan(RiskDecision.REJECTED,None))

 def test_trigger_unmet_stays_waiting(self):
  b=binding(Stage5EntryInstruction(Stage5EntryMode.PRICE_AT_OR_ABOVE,Decimal("510"),Decimal("490"),None))
  obs=observation("505");env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:
    out=r.run_cycle()[0]
    self.assertEqual(out.status,RuntimeOperationalStatus.PROGRESSED)
    self.assertIsNone(e.fill_details_for(env.snapshot.candidate.source_id))
    out2=r.run_cycle()[0]
    self.assertEqual(out2.status,RuntimeOperationalStatus.NO_CHANGE)

 def test_invalidation_before_fill_censors(self):
  b=binding(Stage5EntryInstruction(Stage5EntryMode.PRICE_AT_OR_ABOVE,Decimal("510"),Decimal("490"),None))
  obs=observation("489");env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:
    r.run_cycle()
    self.assertEqual(e.terminal_reason_for(env.snapshot.candidate.source_id),"INVALIDATED_BEFORE_FILL")

 def test_expiry_before_fill_censors(self):
  b=binding(Stage5EntryInstruction(Stage5EntryMode.PRICE_AT_OR_ABOVE,Decimal("510"),Decimal("490"),T0+timedelta(seconds=30)))
  obs=observation("505");env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:r.run_cycle()
  self.assertEqual(e.terminal_reason_for(env.snapshot.candidate.source_id),"EXPIRED_BEFORE_FILL")

 def test_stale_source_fails_closed(self):
  b=binding();obs=observation();env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({},state=RuntimeSourceState.STALE),e) as r:
    self.assertEqual(r.run_cycle()[0].status,RuntimeOperationalStatus.SOURCE_STALE)
  self.assertIsNone(e.fill_details_for(env.snapshot.candidate.source_id))

 def test_observation_not_forward_fails_closed(self):
  b=binding();obs=observation(when=T0);env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:
    self.assertEqual(r.run_cycle()[0].status,RuntimeOperationalStatus.AWAITING_EVIDENCE)
  self.assertIsNone(e.fill_details_for(env.snapshot.candidate.source_id))

 def test_missing_liquidity_never_fills(self):
  b=binding();obs=observation(volume=None);env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:r.run_cycle()
  self.assertIsNone(e.fill_details_for(env.snapshot.candidate.source_id))
  self.assertEqual(e.terminal_reason_for(env.snapshot.candidate.source_id),"INSUFFICIENT_LIQUIDITY_EVIDENCE")

 def test_partial_fill_fee_slippage_are_explicit(self):
  b=binding(p=plan(quantity=Decimal("10")));obs=observation("500",volume="500");env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   with SimulationRuntime(Path(td)/"x.db",Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:r.run_cycle()
  f=e.fill_details_for(env.snapshot.candidate.source_id)
  self.assertIsNotNone(f);self.assertEqual(f.quantity,Decimal("5"));self.assertTrue(f.partial)
  self.assertEqual(f.fill_price,Decimal("500.5"));self.assertEqual(f.slippage_amount,Decimal("2.5"))
  self.assertEqual(f.fee_amount,Decimal("1.25125"))

 def test_duplicate_cycle_does_not_duplicate_fill_or_position(self):
  b=binding();obs=observation();env,e=runtime_parts(b,obs)
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/"x.db";store=Stage5ExecutionStore(db);store.record_order(b);store.record_order(b)
   with SimulationRuntime(db,Stage5CandidateSource((env,)),Stage5ObservationSource({env.snapshot.candidate.source_id:obs}),e) as r:
    r.run_cycle();r.run_cycle()
   f=e.fill_details_for(env.snapshot.candidate.source_id);store.record_fill_and_position(b,f);store.record_fill_and_position(b,f)
   with sqlite3.connect(db) as c:
    self.assertEqual(c.execute("select count(*) from stage5_sim_orders").fetchone()[0],1)
    self.assertEqual(c.execute("select count(*) from stage5_sim_fills").fetchone()[0],1)
    self.assertEqual(c.execute("select count(*) from stage5_sim_positions").fetchone()[0],1)

 def test_no_broker_execution_surface(self):
  import simulation.stage5_bridge as mod
  names=" ".join(dir(mod)).lower()
  for forbidden in ("ibkr","submit_order","broker_order","executionfill"):
   self.assertNotIn(forbidden,names)

if __name__=="__main__": unittest.main()
