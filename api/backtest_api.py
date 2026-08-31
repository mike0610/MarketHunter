"""MarketHunter backtest API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backtesting.backtester import Backtester


router = APIRouter(prefix="/backtest", tags=["Backtest"])


class BacktestRunRequest(BaseModel):
    initial_balance: float = Field(default=10_000.0, gt=0)
    profits: list[float] = Field(min_length=1, max_length=10_000)
    label: str = Field(default="Manual backtest", min_length=1, max_length=120)


_results: list[dict] = []
_results_lock = Lock()


def _public_result(record: dict) -> dict:
    return {**record, "result": dict(record["result"])}


@router.post("/run")
async def run_backtest(payload: BacktestRunRequest):
    """Build a real report from an explicit historical P&L series."""
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
    with _results_lock:
        _results.insert(0, record)
        del _results[100:]
    return _public_result(record)


@router.get("/results")
async def list_backtests():
    with _results_lock:
        return [_public_result(item) for item in _results]


@router.get("/results/{backtest_id}")
async def get_backtest(backtest_id: str):
    with _results_lock:
        record = next((item for item in _results if item["id"] == backtest_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return _public_result(record)
