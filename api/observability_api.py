from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import AccountKind
from research.statistics import ResearchStatistics
from research.storage.repository import ResearchRepository
from stage10.paper_strategy_review import PaperStrategyReviewStore
from trading_scanner.models import QueueState
from trading_scanner.store import TradingScannerStore


router = APIRouter(prefix="/observability", tags=["observability"])


def _authorize(x_markethunter_read_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("MARKETHUNTER_READ_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="read-only observability API is not configured")
    if x_markethunter_read_key != expected:
        raise HTTPException(status_code=401, detail="invalid read-only API key")


def _research() -> ResearchRepository:
    return ResearchRepository(Path(os.getenv("RESEARCH_DB_PATH", "data/research.db")))


def _scanner() -> TradingScannerStore:
    return TradingScannerStore(Path(os.getenv("TRADING_SCANNER_DB_PATH", "data/trading_scanner.db")))


def _paper_reviews() -> PaperStrategyReviewStore:
    root = Path(os.getenv("PROMOTED_PAPER_STATE_DIR", "data"))
    path = Path(os.getenv("PAPER_STRATEGY_REVIEW_DB_PATH", str(root / "paper_strategy_review.db")))
    return PaperStrategyReviewStore(path)


def _experiment() -> Experiment1Engine:
    return Experiment1Engine(Path(os.getenv("EXPERIMENT1_DB_PATH", "data/experiment1.db")))


@router.get("/snapshot", dependencies=[Depends(_authorize)])
def snapshot() -> dict:
    repo = _research()
    trades = repo.list_all()
    stats = ResearchStatistics()
    setup = stats.calculate_setup_reasons(trades)

    candidates = _scanner().list_candidates()
    queue_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    reject_counts: dict[str, int] = {}
    for candidate in candidates:
        queue_counts[candidate.queue_state.value] = queue_counts.get(candidate.queue_state.value, 0) + 1
        family_counts[candidate.setup_family.value] = family_counts.get(candidate.setup_family.value, 0) + 1
        if candidate.reject_reason:
            reject_counts[candidate.reject_reason] = reject_counts.get(candidate.reject_reason, 0) + 1

    reviews = _paper_reviews().list_reviews()
    paper_strategies = [
        {
            "object_id": row["object_id"],
            "strategy_id": row["strategy_id"],
            "strategy_version": row["strategy_version"],
            "hypothesis_id": row["hypothesis_id"],
            "closed_trades": row["closed_trades"],
            "wins": row["wins"],
            "losses": row["losses"],
            "average_net_r": row["average_net_r"],
            "profit_factor_r": row["profit_factor_r"],
            "max_cumulative_r_drawdown": row["max_cumulative_r_drawdown"],
            "net_pnl": row["net_pnl"],
            "status": row["status"],
            "reason": row["reason"],
            "evaluated_at": row["evaluated_at"],
        }
        for row in reviews
    ]

    accounts = []
    engine = _experiment()
    for account in AccountKind:
        try:
            state = engine.account_state(account)
        except Experiment1Error:
            continue
        accounts.append(
            {
                "account": account.value,
                "cash": str(state.cash),
                "equity": str(state.last_equity),
                "realized_pnl": str(state.realized_pnl),
                "fees_paid": str(state.fees_paid),
                "max_drawdown": str(state.max_drawdown),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "quantity": str(p.quantity),
                        "average_price": str(p.average_price),
                        "leverage": str(p.leverage),
                        "notional": str(p.notional),
                    }
                    for p in engine.positions(account)
                ],
            }
        )

    return {
        "read_only": True,
        "simulation_only": True,
        "research": {
            "statistics": stats.calculate(trades),
            "by_strategy": setup["by_strategy"],
            "by_setup_reason": setup["by_setup_reason"],
            "by_status": setup["by_status"],
            "by_outcome": setup["by_outcome"],
            "by_outcome_group": setup["by_outcome_group"],
        },
        "trading_scanner": {
            "total_candidates": len(candidates),
            "by_queue_state": queue_counts,
            "by_setup_family": family_counts,
            "rejection_reasons": reject_counts,
        },
        "paper_strategies": paper_strategies,
        "experiment1": {"accounts": accounts},
    }
