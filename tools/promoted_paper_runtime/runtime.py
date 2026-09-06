from __future__ import annotations
import argparse,json,os
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from research.autonomous_loop.models import ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.store import TradingScannerStore

def _p(name,default):return Path(os.getenv(name,default))
def run_once():
    track=ResearchTrack(os.getenv("PROMOTED_PAPER_RESEARCH_TRACK","GIL"))
    risk=RiskPolicy(
      os.getenv("PROMOTED_PAPER_RISK_POLICY_ID","MH-RISK"),
      os.getenv("PROMOTED_PAPER_RISK_POLICY_VERSION","1"),
      Decimal(os.getenv("PROMOTED_PAPER_RISK_PER_TRADE_PCT","1")),
      Decimal(os.getenv("PROMOTED_PAPER_MAX_AGGREGATE_RISK_PCT","3")),
      Decimal(os.getenv("PROMOTED_PAPER_MAX_CLUSTER_RISK_PCT","2")),
      Decimal(os.getenv("PROMOTED_PAPER_FUTURES_MAX_LEVERAGE","3")),
      int(os.getenv("PROMOTED_PAPER_MAX_DECISION_AGE_SECONDS",str(4*24*3600))),
    )
    root=_p("PROMOTED_PAPER_STATE_DIR","data")
    return dispatch_promoted_candidates(
      research_repo=AutonomousResearchRepository(_p("AUTONOMOUS_RESEARCH_DB_PATH",str(root/"autonomous_research.db"))),
      scanner_store=TradingScannerStore(_p("TRADING_SCANNER_DB_PATH",str(root/"trading_scanner.db"))),
      engine=Experiment1Engine(_p("EXPERIMENT1_DB_PATH",str(root/"experiment1.db"))),
      dispatch_store=PromotedPaperDispatchStore(_p("PROMOTED_PAPER_DISPATCH_DB_PATH",str(root/"promoted_paper_dispatch.db"))),
      strategy_store=StrategyDecisionStore(_p("PROMOTED_PAPER_STRATEGY_DB_PATH",str(root/"promoted_paper_strategy.db"))),
      risk_store=RiskPlanStore(_p("PROMOTED_PAPER_RISK_DB_PATH",str(root/"promoted_paper_risk.db"))),
      open_risk_ledger=OpenRiskLedger(_p("PROMOTED_PAPER_OPEN_RISK_DB_PATH",str(root/"promoted_paper_open_risk.db"))),
      risk_policy=risk,
      research_track=track,
    )
def main(argv=None):
    argparse.ArgumentParser(prog="promoted-paper-runtime").parse_args(argv)
    print(json.dumps([x.__dict__ for x in run_once()],sort_keys=True))
if __name__=="__main__":main()
