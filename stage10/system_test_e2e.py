from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from reports.stage7_repository import Stage7ClosedTradeReader
from risk_mm.models import RiskDecision,SizedExecutionPlan,TradingAccount
from simulation.foundation import MarketObservationEvidence,MarketObservationReference,SimulationCampaignReference
from simulation.runtime.orchestrator import SimulationRuntime
from simulation.stage5_bridge import *
from simulation.stage5_store import Stage5ExecutionStore
from simulation.stage6_manager import Stage6PositionManager
from simulation.stage6_models import ManagedPosition,PositionBarEvidence,PositionExitPolicy
from simulation.stage6_store import Stage6PositionStore
from stage10.test_only_provenance import Stage10TestOnlyProvenance
from strategy_engine.models import StrategyDecisionOutcome,StrategyDecisionRecord
from time_semantics.foundation import TemporalDisposition,TemporalFact,TemporalReference,TemporalRole
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext

T0=datetime(2026,9,5,12,tzinfo=timezone.utc);T1=T0+timedelta(minutes=1)

def _candidate():
 return TradingCandidate(1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("SYSTEM_TEST",),LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("100")),VolatilityContext(Decimal("2")),"TEST_ONLY",True,T0,"system-test-scan","system-test-dedupe",QueueState.CANDIDATE)

def _decision():
 return StrategyDecisionRecord("system-test-decision","system-test-dedupe","SPY",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,"SYSTEM_TEST","1",StrategyDecisionOutcome.LONG,T0,("TEST_ONLY",),"system-test-scan",T0,"TEST_ONLY",None)

def _plan():
 return SizedExecutionPlan("system-test-plan","system-test-decision",RiskDecision.APPROVED,TradingAccount.SPOT,"risk","1",T0,("TEST_ONLY",),Decimal("1"),Decimal("101"),Decimal("95"),Decimal("6"),Decimal("101"),Decimal("1"))

def _obs():
 tr=TemporalReference("market_observation","system-test-entry","1")
 ev=MarketObservationEvidence(MarketObservationReference("SYSTEM_TEST","TEST","SPY","1m","system-test-entry"),TemporalFact(tr,TemporalRole.EVENT_TIME,T1,TemporalDisposition.KNOWN),TemporalFact(tr,TemporalRole.OBSERVED_TIME,T1,TemporalDisposition.KNOWN),TemporalFact(tr,TemporalRole.RECORDED_TIME,T1,TemporalDisposition.KNOWN))
 return Stage5MarketObservation(ev,Decimal("101"),Decimal("10000"),"SYSTEM_TEST","system-test-entry")

def run(db_path:Path)->dict:
 c=_candidate();d=_decision();p=_plan()
 instruction=Stage5EntryInstruction(Stage5EntryMode.PRICE_AT_OR_ABOVE,Decimal("101"),Decimal("95"),T0+timedelta(hours=1))
 binding=build_order_binding(p,c,d,instruction);obs=_obs()
 store5=Stage5ExecutionStore(db_path);store5.record_order(binding)
 env=binding_to_envelope(binding,campaign=SimulationCampaignReference("stage10-system-test",1),recorded_at=T0)
 evaluator=Stage5MechanicsEvaluator({c.source_id:binding},{c.source_id:obs},Stage5MechanicsPolicy("stage5-mechanics","1",Decimal("5"),Decimal("10"),Decimal("0.01"),True))
 with SimulationRuntime(db_path,Stage5CandidateSource((env,)),Stage5ObservationSource({c.source_id:obs}),evaluator) as runtime:
  runtime.run_cycle();runtime.run_cycle()
 fill=evaluator.fill_details_for(c.source_id)
 if fill is None:raise RuntimeError("SYSTEM_TEST did not fill")
 store5.record_fill_and_position(binding,fill);store5.record_fill_and_position(binding,fill)
 position_id="sim-position:"+fill.fill_id.split(":",1)[-1]
 Stage10TestOnlyProvenance(db_path).mark_position(position_id)
 mp=ManagedPosition(position_id,binding.order_id,c.symbol,"LONG",fill.quantity,fill.fill_price,fill.fee_amount,fill.observed_at,d.decision_id,c.dedupe_key,"SYSTEM_TEST","1")
 policy=PositionExitPolicy("SYSTEM_TEST","1",Decimal("95"),None,None,None,None,T1+timedelta(minutes=1))
 exit_bar=PositionBarEvidence("SPY",Decimal("102"),Decimal("103"),Decimal("100"),Decimal("102"),T1+timedelta(minutes=2),"SYSTEM_TEST","system-test-exit",True)
 Stage6PositionManager(Stage6PositionStore(db_path),fee_bps=Decimal("5"),slippage_bps=Decimal("10")).process(mp,policy,exit_bar)
 # Restart/replay must not duplicate the close.
 Stage6PositionManager(Stage6PositionStore(db_path),fee_bps=Decimal("5"),slippage_bps=Decimal("10")).process(mp,policy,exit_bar)
 closed=Stage6PositionStore(db_path).closed_trade(position_id)
 if closed is None:raise RuntimeError("SYSTEM_TEST did not create ClosedTrade")
 report_rows=Stage7ClosedTradeReader(db_path).read_all()
 with sqlite3.connect(db_path) as con:
  counts={t:con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("stage5_sim_orders","stage5_sim_fills","stage5_sim_positions","stage6_closed_trades","stage10_test_only_provenance")}
 return {"status":"PASS","position_id":position_id,"realized_pnl":str(closed.realized_pnl),"exit_reason":closed.exit_reason.value,"counts":counts,"reports_visible_rows":len(report_rows),"test_only_excluded_from_reports":all(x.position_id!=position_id for x in report_rows)}

if __name__=="__main__":
 import argparse,json
 ap=argparse.ArgumentParser();ap.add_argument("--db",required=True);a=ap.parse_args()
 print(json.dumps(run(Path(a.db)),sort_keys=True))
