"""MarketHunter backtest API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backtesting.backtester import Backtester
from backtesting.repository import BacktestRepository
from backtesting.strategy_replay import ReplayAssumptions, StrategyReplayEngine
from models.market_symbol import MarketSymbol
from services.market_data import MarketDataService
from strategies.breakout import BreakoutStrategy


router = APIRouter(prefix="/backtest", tags=["Backtest"])
repository = BacktestRepository()


class BacktestRunRequest(BaseModel):
    initial_balance: float = Field(default=10_000.0, gt=0)
    profits: list[float] = Field(min_length=1, max_length=10_000)
    label: str = Field(default="Manual backtest", min_length=1, max_length=120)


class StrategyBacktestRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=30)
    market: str = Field(default="futures", pattern="^(spot|futures)$")
    timeframe: str = Field(default="1h", min_length=1, max_length=10)
    candle_limit: int = Field(default=500, ge=220, le=1000)
    initial_balance: float = Field(default=10_000.0, gt=0)
    fee_bps_per_side: float = Field(default=4.0, ge=0, le=100)
    slippage_bps_per_side: float = Field(default=2.0, ge=0, le=100)
    ambiguous_candle_policy: str = Field(
        default="stop_first",
        pattern="^(stop_first|target_first)$",
    )
    allow_overlapping_positions: bool = False


def _public_result(record: dict) -> dict:
    return {**record, "result": dict(record["result"])}


def _save_report(label: str, report, assumptions: dict | None = None) -> dict:
    result = asdict(report)
    if assumptions is not None:
        result["assumptions"] = assumptions
    record = {
        "id": str(uuid4()),
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    repository.save(record)
    return _public_result(record)


@router.post("/run")
async def run_backtest(payload: BacktestRunRequest):
    """Build and persist a report from an explicit historical P&L series."""
    report = Backtester().build_report(
        initial_balance=payload.initial_balance,
        profits=payload.profits,
    )
    return _save_report(payload.label, report)


@router.post("/run/strategy")
async def run_strategy_backtest(payload: StrategyBacktestRequest):
    """Replay the existing Breakout strategy over public Binance candles."""
    symbol_name = payload.symbol.strip().upper()
    base_asset = symbol_name.removesuffix("USDT") or symbol_name
    market_symbol = MarketSymbol(
        symbol=symbol_name,
        base_asset=base_asset,
        quote_asset="USDT",
        market=payload.market,
    )

    candles = await MarketDataService().load_candles(
        symbol=market_symbol,
        interval=payload.timeframe,
        limit=payload.candle_limit,
    )
    assumptions = ReplayAssumptions(
        fee_bps_per_side=payload.fee_bps_per_side,
        slippage_bps_per_side=payload.slippage_bps_per_side,
        ambiguous_candle_policy=payload.ambiguous_candle_policy,
        allow_overlapping_positions=payload.allow_overlapping_positions,
    )
    profits = await StrategyReplayEngine(assumptions).run(
        strategy=BreakoutStrategy(),
        symbol=symbol_name,
        market=payload.market,
        candles=candles,
    )
    if not profits:
        raise HTTPException(
            status_code=422,
            detail="Breakout produced no executable signals in the selected window.",
        )

    report = Backtester().build_report(
        initial_balance=payload.initial_balance,
        profits=profits,
    )
    label = (
        f"Breakout {symbol_name} {payload.market} {payload.timeframe} "
        f"({payload.candle_limit} candles)"
    )
    return _save_report(label, report, assumptions=asdict(assumptions))


@router.get("/results")
async def list_backtests(limit: int = Query(default=100, ge=1, le=500)):
    return [_public_result(item) for item in repository.list_recent(limit)]


@router.get("/results/{backtest_id}")
async def get_backtest(backtest_id: str):
    record = repository.get(backtest_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return _public_result(record)
