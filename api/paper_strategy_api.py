from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter

from stage10.paper_strategy_review import PaperStrategyReviewStore

router=APIRouter(prefix="/paper-strategies",tags=["paper-strategies"])
strategy_lab_router=APIRouter(prefix="/strategy-lab",tags=["strategy-lab"])

def _store()->PaperStrategyReviewStore:
    root=Path(os.getenv("PROMOTED_PAPER_STATE_DIR","data"))
    path=Path(os.getenv("PAPER_STRATEGY_REVIEW_DB_PATH",str(root/"paper_strategy_review.db")))
    return PaperStrategyReviewStore(path)

def _serialize(r):
    return {
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
    }

@router.get("/reviews")
def reviews():
    rows=_store().list_reviews()
    return {
      "simulation_only":True,
      "reviews":[_serialize(r) for r in rows],
    }

@strategy_lab_router.get("/statistics")
def strategy_lab_statistics():
    rows=[r for r in _store().list_reviews() if r["research_track"]=="SL"]
    reviews=[_serialize(r) for r in rows]
    return {
      "simulation_only":True,
      "research_track":"SL",
      "summary":{
        "strategies":len(reviews),
        "closed_trades":sum(r["closed_trades"] for r in rows),
        "r_covered_trades":sum(r["r_covered_trades"] for r in rows),
        "wins":sum(r["wins"] for r in rows),
        "losses":sum(r["losses"] for r in rows),
        "breakeven":sum(r["breakeven"] for r in rows),
        "net_pnl":str(sum((Decimal(r["net_pnl"]) for r in rows),Decimal("0"))),
        "fees_paid":str(sum((Decimal(r["fees_paid"]) for r in rows),Decimal("0"))),
        "last_evaluated_at":max((r["evaluated_at"] for r in rows),default=None),
      },
      "strategies":reviews,
    }
