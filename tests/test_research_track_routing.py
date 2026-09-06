from __future__ import annotations
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from research.autonomous_loop.models import ResearchObject,ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

POLICY=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),345600)

def promote(repo,oid,track,account="SPOT"):
    repo.enqueue(ResearchObject(oid,oid,"LONG",f"H-{oid}",research_track=track))
    repo.terminal(oid,"PROMOTION-ELIGIBLE",{"paper_contract":{
        "strategy_id":f"S-{oid}","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND",
        "direction":"LONG","account":account,"requested_leverage":"1","cluster_key":"TEST",
        "entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":86400,"take_profit_r":"2"
    }},hypothesis_id=f"H-{oid}")
    return repo.release_candidate(oid)

def candidate(symbol,sec_type,when,key,stop,high,low):
    return TradingCandidate(
        1,symbol,sec_type,"BINANCE" if sec_type.startswith("CRYPTO") else "SMART","USDT" if sec_type.startswith("CRYPTO") else "USD",
        SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("setup",),
        LiquidityContext(Decimal("1000000"),Decimal("100000000"),Decimal(str((high+low)/2))),
        VolatilityContext(Decimal("2")),"OK",True,when,"scan",key,QueueState.CANDIDATE,
        invalidation_reference=f"structural stop ({stop})",signal_bar_high=Decimal(str(high)),signal_bar_low=Decimal(str(low))
    )

def ctx(root):
    return dict(
        engine=Experiment1Engine(root/"experiment1.db"),
        dispatch_store=PromotedPaperDispatchStore(root/"dispatch.db"),
        strategy_store=StrategyDecisionStore(root/"strategy.db"),
        risk_store=RiskPlanStore(root/"risk.db"),
        open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),
        risk_policy=POLICY,
    )

def test_release_candidate_persists_explicit_research_track():
    with tempfile.TemporaryDirectory() as td:
        repo=AutonomousResearchRepository(Path(td)/"research.db")
        row=promote(repo,"SL1",ResearchTrack.SL)
        assert row["research_track"]=="SL"

def test_gil_never_dispatches_crypto_candidate():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);repo=AutonomousResearchRepository(root/"research.db")
        row=promote(repo,"G1",ResearchTrack.GIL);when=__import__("datetime").datetime.fromisoformat(row["created_at"])+timedelta(seconds=1)
        store=TradingScannerStore(root/"scanner.db")
        store.record_candidate(candidate("BTCUSDT","CRYPTO_SPOT",when,"crypto","59000","61000","60000"))
        out=dispatch_promoted_candidates(research_repo=repo,scanner_store=store,research_track=ResearchTrack.GIL,**ctx(root))
        assert out==()

def test_sl_never_dispatches_stock_candidate():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);repo=AutonomousResearchRepository(root/"research.db")
        row=promote(repo,"SL1",ResearchTrack.SL);when=__import__("datetime").datetime.fromisoformat(row["created_at"])+timedelta(seconds=1)
        store=TradingScannerStore(root/"scanner.db")
        store.record_candidate(candidate("SPY","STK",when,"stock","490","505","495"))
        out=dispatch_promoted_candidates(research_repo=repo,scanner_store=store,research_track=ResearchTrack.SL,**ctx(root))
        assert out==()

def test_sl_spot_promotion_accepts_only_crypto_spot():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);repo=AutonomousResearchRepository(root/"research.db")
        row=promote(repo,"SL1",ResearchTrack.SL,"SPOT");when=__import__("datetime").datetime.fromisoformat(row["created_at"])+timedelta(seconds=1)
        store=TradingScannerStore(root/"scanner.db")
        store.record_candidate(candidate("BTCUSDT","CRYPTO_FUTURES",when,"fut","59000","61000","60000"))
        store.record_candidate(candidate("ETHUSDT","CRYPTO_SPOT",when,"spot","2900","3100","3000"))
        out=dispatch_promoted_candidates(research_repo=repo,scanner_store=store,research_track=ResearchTrack.SL,**ctx(root))
        assert len(out)==1 and out[0].candidate_dedupe_key=="spot" and out[0].status=="QUEUED"

def test_sl_futures_promotion_accepts_only_crypto_futures():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);repo=AutonomousResearchRepository(root/"research.db")
        row=promote(repo,"SL1",ResearchTrack.SL,"FUTURES");when=__import__("datetime").datetime.fromisoformat(row["created_at"])+timedelta(seconds=1)
        store=TradingScannerStore(root/"scanner.db")
        store.record_candidate(candidate("BTCUSDT","CRYPTO_SPOT",when,"spot","59000","61000","60000"))
        store.record_candidate(candidate("ETHUSDT","CRYPTO_FUTURES",when,"fut","2900","3100","3000"))
        out=dispatch_promoted_candidates(research_repo=repo,scanner_store=store,research_track=ResearchTrack.SL,**ctx(root))
        assert len(out)==1 and out[0].candidate_dedupe_key=="fut" and out[0].status=="QUEUED"
