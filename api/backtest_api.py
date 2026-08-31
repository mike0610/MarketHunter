"""MarketHunter backtest API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backtesting.backtester import Backtester
from backtesting.repository import BacktestRepository


router = APIRouter(prefix="/backtest", tags=["Backtest"])
repository = BacktestRepository()


class BacktestRunRequest(BaseModel):
    initial_balance: float = Field(default=10_000.0, gt=0)
    profits: list[float] = Field(min_length=1, max_length=10_000)
    label: str = Field(default="Manual backtest", min_length=1, max_length=120)


def _public_result(record: dict) -> dict:
    return {**record, "result": dict(record["result"])}


@router.post("/run")
async def run_backtest(payload: BacktestRunRequest):
    """Build and persist a report from an explicit historical P&L series."""
    report = Backtester().build_report(
        initial_balance=payload.initial_balance,
        profits=payload.profits,
    )
    record = {
        "id": str(uuid4()),
        "label": payload.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": asdict(report),
    }
    repository.save(record)
    return _public_result(record)


@router.get("/results")
async def list_backtests(limit: int = Query(default=100, ge=1, le=500)):
    return [_public_result(item) for item in repository.list_recent(limit)]


@router.get("/results/{backtest_id}")
async def get_backtest(backtest_id: str):
    record = repository.get(backtest_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return _public_result(record)
