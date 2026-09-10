from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from research.statistics import ResearchStatistics
from research.storage.repository import ResearchRepository
from stage10.paper_strategy_review import PaperStrategyReviewStore

router = APIRouter(prefix="/paper-strategies", tags=["paper-strategies"])
strategy_lab_router = APIRouter(prefix="/strategy-lab", tags=["strategy-lab"])


def _store() -> PaperStrategyReviewStore:
    root = Path(os.getenv("PROMOTED_PAPER_STATE_DIR", "data"))
    path = Path(
        os.getenv(
            "PAPER_STRATEGY_REVIEW_DB_PATH",
            str(root / "paper_strategy_review.db"),
        )
    )
    return PaperStrategyReviewStore(path)


def _research_store() -> ResearchRepository:
    return ResearchRepository(
        Path(os.getenv("RESEARCH_DB_PATH", "data/research.db"))
    )


def _serialize(r):
    return {
        "object_id": r["object_id"],
        "research_track": r["research_track"],
        "strategy_id": r["strategy_id"],
        "strategy_version": r["strategy_version"],
        "hypothesis_id": r["hypothesis_id"],
        "closed_trades": r["closed_trades"],
        "r_covered_trades": r["r_covered_trades"],
        "wins": r["wins"],
        "losses": r["losses"],
        "breakeven": r["breakeven"],
        "average_net_r": r["average_net_r"],
        "profit_factor_r": r["profit_factor_r"],
        "max_cumulative_r_drawdown": r["max_cumulative_r_drawdown"],
        "net_pnl": r["net_pnl"],
        "fees_paid": r["fees_paid"],
        "status": r["status"],
        "reason": r["reason"],
        "evaluated_at": r["evaluated_at"],
    }


def _report_snapshot() -> dict:
    trades = _research_store().list_all()
    statistics = ResearchStatistics()
    grouped = statistics.calculate_setup_reasons(trades)
    return {
        "summary": statistics.calculate(trades),
        "strategies": grouped["by_strategy"],
        "by_setup_reason": grouped["by_setup_reason"],
        "by_close_reason": grouped["by_close_reason"],
        "by_status": grouped["by_status"],
        "by_outcome": grouped["by_outcome"],
        "by_outcome_group": grouped["by_outcome_group"],
    }


@router.get("/reviews")
def reviews():
    rows = _store().list_reviews()
    return {
        "simulation_only": True,
        "reviews": [_serialize(r) for r in rows],
    }


@strategy_lab_router.get("/statistics")
def strategy_lab_statistics():
    snapshot = _report_snapshot()
    return {
        "read_only": True,
        "simulation_only": True,
        "research_track": "SL",
        "source": "reports",
        "source_routes": [
            "/research/statistics",
            "/research/statistics/setup-reasons",
        ],
        **snapshot,
    }
