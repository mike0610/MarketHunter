from __future__ import annotations
import asyncio,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.models import AccountKind,MarketQuote
from experiment1.runtime import run_market_cycle
from experiment1.trading_decision import drain_trading_decision_inbox
from research.autonomous_loop.models import ResearchObject
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),4*24*3600)

class QuoteSource:
 def __init__(self,price):self.price=Decimal(price);self.n=0
 async def quote_for(self,intent):
  self.n+=1
  return MarketQuote(intent.symbol,self.price,datetime.now(timezone.utc),"TEST","quote-"+str(self.n),Decimal("4"),Decimal("6"))

def promote(repo):
 repo.enqueue(ResearchObject("P","SPY","LONG","H-P"))
 ev={"paper_contract":{
  "strategy_id":"PROMOTED-TEST","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND",
  "direction":"LONG","account":"SPOT","requested_leverage":"1","cluster_key":"US_EQ",
  "entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":259200,"take_profit_r":"3"
 }}
 repo.terminal("P","PROMOTION-ELIGIBLE",ev,hypothesis_id="H-P")
 return datetime.fromisoformat(repo.release_candidate("P")["created_at"])

def candidate(when):
 return TradingCandidate(1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,
  ("promoted setup",),LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("500")),
  VolatilityContext(Decimal("2")),"OK",True,when,"scan-forward","1:BREAKOUT_OR_PULLBACK_IN_TREND:scan-forward",QueueState.CANDIDATE,
  invalidation_reference="close below structural stop (490)",signal_bar_high=Decimal("505"),signal_bar_low=Decimal("495"))

def test_promotion_dispatches_once_then_existing_paper_engine_fills_and_closes():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)
  research=AutonomousResearchRepository(root/"research.db");promoted=promote(research)
  scanner=TradingScannerStore(root/"scanner.db");scanner.record_candidate(candidate(promoted+timedelta(seconds=1)))
  engine=Experiment1Engine(root/"experiment1.db");dispatch=PromotedPaperDispatchStore(root/"dispatch.db")
  kwargs=dict(research_repo=research,scanner_store=scanner,engine=engine,dispatch_store=dispatch,
   strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
   open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),risk_policy=POLICY)
  first=dispatch_promoted_candidates(**kwargs)
  second=dispatch_promoted_candidates(**kwargs)
  assert [x.status for x in first]==["QUEUED"]
  assert second==()
  decision_id=first[0].decision_id
  inbox=engine.trading_decision_inbox_status(decision_id)
  assert inbox is not None
  q=QuoteSource("506")
  ing=asyncio.run(drain_trading_decision_inbox(engine,q))
  assert ing[0].outcome=="PENDING"
  fills=asyncio.run(run_market_cycle(engine,q))
  assert fills[0].outcome=="PAPER_FILLED"
  intent_id=ing[0].intent_id
  entry=engine.get_intent(intent_id)
  assert entry.stop_loss==Decimal("490")
  assert entry.take_profit==Decimal("550")
  # Risk sizing is based on trigger 505 rather than candidate close 500:
  assert entry.quantity==Decimal("20")/Decimal("15")
  q.price=Decimal("551")
  life=asyncio.run(run_protective_exit_cycle(engine,q,(intent_id,)))
  assert life[0].outcome=="TAKE_PROFIT"
  closed=engine.closed_trades(AccountKind.SPOT)
  assert len(closed)==1 and closed[0].realized_pnl>0
