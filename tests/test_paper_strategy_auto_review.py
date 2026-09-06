from __future__ import annotations
import sqlite3,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from research.autonomous_loop.models import ResearchObject,ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.paper_strategy_review import (
    AttributedPaperTrade,PaperReviewPolicy,PaperReviewStatus,PaperStrategyReview,
    PaperStrategyReviewStore,collect_attributed_trades,evaluate_reviews,run_review_cycle,
)
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

NOW=datetime(2026,9,6,6,tzinfo=timezone.utc)
POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),345600)

def trade(i,r):
    risk=Decimal("10");net=Decimal(str(r))*risk
    return AttributedPaperTrade("O","SL","S","1","H",f"d{i}",f"i{i}","SPOT","BTCUSDT",
        NOW+timedelta(minutes=i),NOW+timedelta(minutes=i+1),net,Decimal("0"),net,risk,Decimal(str(r)))

def test_review_stays_active_before_minimum_sample():
    reviews=evaluate_reviews(tuple(trade(i,1) for i in range(3)),PaperReviewPolicy(4),now=NOW)
    assert reviews[0].status is PaperReviewStatus.PAPER_ACTIVE

def test_positive_r_evidence_keeps_strategy_after_minimum_sample():
    rs=(1,-0.5,1.5,-0.25)
    review=evaluate_reviews(tuple(trade(i,r) for i,r in enumerate(rs)),PaperReviewPolicy(4),now=NOW)[0]
    assert review.status is PaperReviewStatus.KEEP
    assert review.average_net_r>0 and review.profit_factor_r>1

def test_negative_r_evidence_pauses_new_entries_after_minimum_sample():
    rs=(-1,0.25,-0.8,0.1)
    review=evaluate_reviews(tuple(trade(i,r) for i,r in enumerate(rs)),PaperReviewPolicy(4),now=NOW)[0]
    assert review.status is PaperReviewStatus.PAUSE
    assert review.average_net_r<0 and review.profit_factor_r<1

def test_missing_risk_attribution_requires_review_not_fake_r():
    items=list(trade(i,1) for i in range(3))
    x=items[-1]
    items[-1]=AttributedPaperTrade(x.object_id,x.research_track,x.strategy_id,x.strategy_version,x.hypothesis_id,
        x.decision_id,x.intent_id,x.account,x.symbol,x.opened_at,x.closed_at,x.realized_pnl,x.fees_paid,x.net_pnl,None,None)
    review=evaluate_reviews(tuple(items),PaperReviewPolicy(3),now=NOW)[0]
    assert review.status is PaperReviewStatus.REVIEW_REQUIRED
    assert review.r_covered_trades==2

def test_attribution_joins_dispatch_decision_to_authoritative_fill_leg():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);exp=root/"experiment.db";dispatch=root/"dispatch.db"
        Experiment1Engine(exp)
        ds=PromotedPaperDispatchStore(dispatch)
        ds.record(object_id="O",dedupe="C",decision_id="D",strategy_id="S",version="1",hypothesis_id="H",
                  research_track="SL",strategy_decision_id="SD",risk_plan_id="RP",risk_amount=Decimal("10"))
        entry="trading-decision:D"
        with sqlite3.connect(exp) as c:
            c.execute("""insert into experiment1_trading_decision_inbox
              (decision_id,received_at,raw_payload,status,outcome,outcome_reason,intent_id,processed_at)
              values(?,?,?,?,?,?,?,?)""",("D",NOW.isoformat(),"{}","PROCESSED","PENDING",None,entry,NOW.isoformat()))
            c.execute("""insert into experiment1_fills
              (intent_id,account,action,symbol,quantity,reference_price,fill_price,fee,leverage,observed_at,source,source_reference,realized_pnl_delta)
              values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(entry,"SPOT","BUY","BTCUSDT","1","100","100","1","1",NOW.isoformat(),"TEST","e","0"))
            c.execute("""insert into experiment1_fills
              (intent_id,account,action,symbol,quantity,reference_price,fill_price,fee,leverage,observed_at,source,source_reference,realized_pnl_delta)
              values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(entry+":protective:TAKE_PROFIT","SPOT","SELL","BTCUSDT","1","120","120","1","1",(NOW+timedelta(hours=1)).isoformat(),"TEST","x","20"))
        rows=collect_attributed_trades(dispatch,exp)
        assert len(rows)==1
        assert rows[0].net_pnl==Decimal("18")
        assert rows[0].net_r==Decimal("1.8")
        assert rows[0].research_track=="SL"

def _promote_and_candidate(root):
    repo=AutonomousResearchRepository(root/"research.db")
    repo.enqueue(ResearchObject("O","BTCUSDT","LONG","H",research_track=ResearchTrack.SL))
    repo.terminal("O","PROMOTION-ELIGIBLE",{"paper_contract":{
        "strategy_id":"S","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND",
        "direction":"LONG","account":"SPOT","requested_leverage":"1","cluster_key":"CRYPTO",
        "entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":86400,"take_profit_r":"2"
    }},hypothesis_id="H")
    promoted=datetime.fromisoformat(repo.release_candidate("O")["created_at"])
    scanner=TradingScannerStore(root/"scanner.db")
    scanner.record_candidate(TradingCandidate(
        1,"BTCUSDT","CRYPTO_SPOT","BINANCE","USDT",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("setup",),
        LiquidityContext(Decimal("1000000"),Decimal("1000000000"),Decimal("100")),
        VolatilityContext(Decimal("2")),"OK",True,promoted+timedelta(seconds=1),"scan","cand",QueueState.CANDIDATE,
        invalidation_reference="structural stop (95)",signal_bar_high=Decimal("101"),signal_bar_low=Decimal("96")))
    return repo,scanner

def test_paused_review_blocks_new_dispatch_without_touching_existing_positions():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);repo,scanner=_promote_and_candidate(root)
        reviews=PaperStrategyReviewStore(root/"review.db")
        reviews.upsert(PaperStrategyReview("O","SL","S","1","H",30,30,5,25,0,Decimal("-0.2"),Decimal("0.5"),
            Decimal("-8"),Decimal("-60"),Decimal("2"),PaperReviewStatus.PAUSE,"negative evidence",NOW))
        engine=Experiment1Engine(root/"experiment.db")
        out=dispatch_promoted_candidates(
            research_repo=repo,scanner_store=scanner,engine=engine,
            dispatch_store=PromotedPaperDispatchStore(root/"dispatch.db"),
            strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
            open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),risk_policy=POLICY,
            research_track=ResearchTrack.SL,review_store=reviews)
        assert len(out)==1 and out[0].status=="PAUSED"
        assert engine.trading_decision_inbox_status("promoted-paper:O:cand") is None
