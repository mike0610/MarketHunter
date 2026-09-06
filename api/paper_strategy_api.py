from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from stage10.paper_strategy_review import PaperStrategyReviewStore

router=APIRouter(prefix="/paper-strategies",tags=["paper-strategies"])

def _store()->PaperStrategyReviewStore:
    root=Path(os.getenv("PROMOTED_PAPER_STATE_DIR","data"))
    path=Path(os.getenv("PAPER_STRATEGY_REVIEW_DB_PATH",str(root/"paper_strategy_review.db")))
    return PaperStrategyReviewStore(path)

@router.get("/reviews")
def reviews():
    rows=_store().list_reviews()
    return {
      "simulation_only":True,
      "reviews":[{
        "object_id":r["object_id"],
        "research_track":r["research_track"],
        "strategy_id":r["strategy_id"],
        "strategy_version":r["strategy_version"],
        "hypothesis_id":r["hypothesis_id"],
        "closed_trades":r["closed_trades"],
        "r_covered_trades":r["r_covered_trades"],
        "wins":r["wins"],
        "losses":r["losses"],
        "breakeven":r["breakeven"],
        "average_net_r":r["average_net_r"],
        "profit_factor_r":r["profit_factor_r"],
        "max_cumulative_r_drawdown":r["max_cumulative_r_drawdown"],
        "net_pnl":r["net_pnl"],
        "fees_paid":r["fees_paid"],
        "status":r["status"],
        "reason":r["reason"],
        "evaluated_at":r["evaluated_at"],
      } for r in rows],
    }
