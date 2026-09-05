from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from reports.stage7_repository import Stage7ClosedTradeReader
from risk_mm.engine import evaluate_risk
from risk_mm.models import PortfolioRiskState,RiskDecision,RiskInput,RiskPolicy,TradingAccount
from simulation.foundation import MarketObservationEvidence,MarketObservationReference,SimulationCampaignReference
from simulation.runtime.orchestrator import SimulationRuntime
from simulation.stage5_bridge import (
 Stage5CandidateSource,Stage5EntryInstruction,Stage5EntryMode,Stage5MarketObservation,
 Stage5MechanicsEvaluator,Stage5MechanicsPolicy,Stage5ObservationSource,
 binding_to_envelope,build_order_binding,
)
from simulation.stage5_store import Stage5ExecutionStore
from simulation.stage6_manager import Stage6PositionManager
from simulation.stage6_models import ManagedPosition,PositionBarEvidence,PositionExitPolicy
from simulation.stage6_store import Stage6PositionStore
from stage10.test_only_provenance import Stage10TestOnlyProvenance
from strategy_engine.models import StrategyDecisionOutcome,StrategyDecisionRecord
from time_semantics.foundation import TemporalDisposition,TemporalFact,TemporalReference,TemporalRole
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext

T0=datetime(2026,9,5,12,tzinfo=timezone.utc);T1=T0+timedelta(minutes=1)
TEST_RISK_POLICY=RiskPolicy("SYSTEM_TEST_RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),3600)

def _suffix(account:TradingAccount)->str:
 return account.value.lower()

def _symbol(account:TradingAccount)->str:
 return "SPY" if account is TradingAccount.SPOT else "BTCUSDT"

def _candidate(account:TradingAccount):
 s=_suffix(account);symbol=_symbol(account)
 return TradingCandidate(1,symbol,"STK" if account is TradingAccount.SPOT else "CRYPTO","TEST","USD",
  SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("SYSTEM_TEST",),
  LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("100")),
  VolatilityContext(Decimal("2")),"TEST_ONLY",True,T0,f"system-test-scan-{s}",f"system-test-dedupe-{s}",QueueState.CANDIDATE)

def _decision(account:TradingAccount):
 s=_suffix(account);symbol=_symbol(account)
 return StrategyDecisionRecord(f"system-test-decision-{s}",f"system-test-dedupe-{s}",symbol,
  SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,"SYSTEM_TEST","1",StrategyDecisionOutcome.LONG,T0,
  ("TEST_ONLY",),f"system-test-scan-{s}",T0,"TEST_ONLY",None)

def _risk_plan(account:TradingAccount):
 s=_suffix(account);leverage=Decimal("1") if account is TradingAccount.SPOT else Decimal("3")
 item=RiskInput(f"system-test-decision-{s}",_symbol(account),"LONG",T0,"OK",Decimal("100"),Decimal("95"),f"SYSTEM_TEST:{s}")
 state=PortfolioRiskState(account,Decimal("2000"),Decimal("2000"),Decimal("0"),Decimal("0"),f"SYSTEM_TEST:{s}",leverage)
 plan=evaluate_risk(item,state,TEST_RISK_POLICY,evaluated_at=T0)
 if plan.decision is not RiskDecision.APPROVED:
  raise RuntimeError(f"SYSTEM_TEST Risk/MM rejected: {plan.reasons}")
 return plan

def _obs(account:TradingAccount):
 s=_suffix(account)
 tr=TemporalReference("market_observation",f"system-test-entry-{s}","1")
 ev=MarketObservationEvidence(
  MarketObservationReference("SYSTEM_TEST","TEST",_symbol(account),"1m",f"system-test-entry-{s}"),
  TemporalFact(tr,TemporalRole.EVENT_TIME,T1,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.OBSERVED_TIME,T1,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.RECORDED_TIME,T1,TemporalDisposition.KNOWN))
 return Stage5MarketObservation(ev,Decimal("101"),Decimal("10000"),"SYSTEM_TEST",f"system-test-entry-{s}")

def run(db_path:Path,account:TradingAccount=TradingAccount.SPOT)->dict:
 c=_candidate(account);d=_decision(account);p=_risk_plan(account);s=_suffix(account)
 instruction=Stage5EntryInstruction(Stage5EntryMode.PRICE_AT_OR_ABOVE,Decimal("101"),Decimal("95"),T0+timedelta(hours=1))
 binding=build_order_binding(p,c,d,instruction);obs=_obs(account)
 store5=Stage5ExecutionStore(db_path);store5.record_order(binding)
 env=binding_to_envelope(binding,campaign=SimulationCampaignReference(f"stage10-system-test-{s}",1),recorded_at=T0)
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
 exit_bar=PositionBarEvidence(c.symbol,Decimal("102"),Decimal("103"),Decimal("100"),Decimal("102"),T1+timedelta(minutes=2),"SYSTEM_TEST",f"system-test-exit-{s}",True)
 Stage6PositionManager(Stage6PositionStore(db_path),fee_bps=Decimal("5"),slippage_bps=Decimal("10")).process(mp,policy,exit_bar)
 Stage6PositionManager(Stage6PositionStore(db_path),fee_bps=Decimal("5"),slippage_bps=Decimal("10")).process(mp,policy,exit_bar)
 closed=Stage6PositionStore(db_path).closed_trade(position_id)
 if closed is None:raise RuntimeError("SYSTEM_TEST did not create ClosedTrade")
 report_rows=Stage7ClosedTradeReader(db_path).read_all()
 with sqlite3.connect(db_path) as con:
  counts={t:con.execute(f"select count(*) from {t}").fetchone()[0] for t in ("stage5_sim_orders","stage5_sim_fills","stage5_sim_positions","stage6_closed_trades","stage10_test_only_provenance")}
 return {
  "status":"PASS","account":account.value,"leverage":str(p.leverage),"risk_decision":p.decision.value,
  "risk_amount":str(p.risk_amount),"quantity":str(p.quantity),"position_id":position_id,
  "realized_pnl":str(closed.realized_pnl),"exit_reason":closed.exit_reason.value,"counts":counts,
  "reports_visible_rows":len(report_rows),"test_only_excluded_from_reports":all(x.position_id!=position_id for x in report_rows)
 }

if __name__=="__main__":
 import argparse,json
 ap=argparse.ArgumentParser();ap.add_argument("--db",required=True);ap.add_argument("--account",choices=("SPOT","FUTURES"),default="SPOT")
 a=ap.parse_args();print(json.dumps(run(Path(a.db),TradingAccount(a.account)),sort_keys=True))
