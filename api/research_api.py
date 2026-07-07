"""
MarketHunter

Module:
Research API

Responsibilities:
- Provide virtual research trades for Dashboard.
- Provide details for one virtual trade.
- Provide aggregate research statistics.
- Provide persisted continuous worker status.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.statistics import ResearchStatistics
from research.storage.repository import (
    ResearchRepository,
    WorkerStatus,
)


DATABASE_PATH = "data/research.db"


router = APIRouter(
    prefix="/research",
    tags=["Research"],
)


class ResearchTradeResponse(BaseModel):
    """
    Serializable virtual trade representation for Dashboard.
    """

    id: str
    signal_id: str | None

    symbol: str
    market: str
    timeframe: str
    strategy: str
    direction: str

    entry_price: float
    stop_loss: float
    take_profit: float

    probability: int
    score: float
    notional: float

    reasons: list[str]

    status: str

    created_at: datetime
    opened_at: datetime | None
    closed_at: datetime | None

    close_reason: str | None

    profit_amount: float
    profit_percent: float
    rr: float

    max_profit_percent: float
    max_drawdown_percent: float

    active_candles: int
    max_active_candles: int
    last_processed_candle_at: datetime | None

    @classmethod
    def from_trade(
        cls,
        trade: ResearchTrade,
    ) -> "ResearchTradeResponse":
        """
        Convert ResearchTrade model into API response.
        """

        return cls(
            id=trade.id,
            signal_id=trade.signal_id,
            symbol=trade.symbol,
            market=trade.market,
            timeframe=trade.timeframe,
            strategy=trade.strategy,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            probability=trade.probability,
            score=trade.score,
            notional=trade.notional,
            reasons=list(trade.reasons),
            status=trade.status.value,
            created_at=trade.created_at,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            close_reason=trade.close_reason,
            profit_amount=trade.profit_amount,
            profit_percent=trade.profit_percent,
            rr=trade.rr,
            max_profit_percent=trade.max_profit_percent,
            max_drawdown_percent=trade.max_drawdown_percent,
            active_candles=trade.active_candles,
            max_active_candles=trade.max_active_candles,
            last_processed_candle_at=(
                trade.last_processed_candle_at
            ),
        )


class ResearchTradeListResponse(BaseModel):
    """
    Paginated list of virtual trades.
    """

    trades: list[ResearchTradeResponse]
    total: int
    offset: int
    limit: int


class ResearchStatisticsResponse(BaseModel):
    """
    Aggregate performance statistics for virtual trades.
    """

    total: int
    waiting_entry: int
    active: int
    completed: int

    wins: int
    losses: int
    breakeven: int

    win_rate: float
    total_profit: float
    average_profit: float
    average_rr: float
    profit_factor: float | None


class WorkerStatusResponse(BaseModel):
    """
    Persisted state of the continuous MarketHunter worker.
    """

    state: str
    cycle_number: int

    last_cycle_started_at: datetime | None
    last_cycle_finished_at: datetime | None
    next_cycle_at: datetime | None

    last_error: str | None
    updated_at: datetime | None

    @classmethod
    def from_status(
        cls,
        status: WorkerStatus,
    ) -> "WorkerStatusResponse":
        """
        Convert repository worker status into API response.
        """

        return cls(
            state=status.state,
            cycle_number=status.cycle_number,
            last_cycle_started_at=(
                status.last_cycle_started_at
            ),
            last_cycle_finished_at=(
                status.last_cycle_finished_at
            ),
            next_cycle_at=status.next_cycle_at,
            last_error=status.last_error,
            updated_at=status.updated_at,
        )

    @classmethod
    def not_started(
        cls,
    ) -> "WorkerStatusResponse":
        """
        Return a valid API response before first worker launch.
        """

        return cls(
            state="not_started",
            cycle_number=0,
            last_cycle_started_at=None,
            last_cycle_finished_at=None,
            next_cycle_at=None,
            last_error=None,
            updated_at=None,
        )


def get_repository() -> Iterator[ResearchRepository]:
    """
    Open one short-lived SQLite connection per API request.
    """

    repository = ResearchRepository(
        path=DATABASE_PATH,
    )

    try:
        yield repository
    finally:
        repository.close()


@router.get(
    "/worker-status",
    response_model=WorkerStatusResponse,
)
def get_worker_status(
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> WorkerStatusResponse:
    """
    Return current persisted state of the MarketHunter worker.
    """

    status = repository.get_worker_status()

    if status is None:
        return WorkerStatusResponse.not_started()

    return WorkerStatusResponse.from_status(
        status=status,
    )


@router.get(
    "/trades",
    response_model=ResearchTradeListResponse,
)
def list_research_trades(
    status: str | None = Query(
        default=None,
        description=(
            "Trade status: waiting_entry, active, "
            "closed, expired or candidate."
        ),
    ),
    symbol: str | None = Query(
        default=None,
        description="Optional Binance symbol filter.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> ResearchTradeListResponse:
    """
    Return virtual research trades for Dashboard.
    """

    normalized_status = _normalize_status(
        status=status,
    )

    normalized_symbol = (
        symbol.strip().upper()
        if symbol
        else None
    )

    trades = repository.list_all()

    if normalized_status is not None:
        trades = [
            trade
            for trade in trades
            if trade.status.value == normalized_status
        ]

    if normalized_symbol is not None:
        trades = [
            trade
            for trade in trades
            if trade.symbol.upper() == normalized_symbol
        ]

    total = len(trades)

    page = trades[
        offset:offset + limit
    ]

    return ResearchTradeListResponse(
        trades=[
            ResearchTradeResponse.from_trade(trade)
            for trade in page
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/statistics",
    response_model=ResearchStatisticsResponse,
)
def get_research_statistics(
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> ResearchStatisticsResponse:
    """
    Return aggregate research statistics.
    """

    statistics = ResearchStatistics().calculate(
        repository.list_all(),
    )

    return ResearchStatisticsResponse(
        total=int(statistics.get("total", 0)),
        waiting_entry=int(
            statistics.get("waiting_entry", 0)
        ),
        active=int(statistics.get("active", 0)),
        completed=int(
            statistics.get("completed", 0)
        ),
        wins=int(statistics.get("wins", 0)),
        losses=int(statistics.get("losses", 0)),
        breakeven=int(
            statistics.get("breakeven", 0)
        ),
        win_rate=float(
            statistics.get("win_rate", 0.0)
        ),
        total_profit=float(
            statistics.get("total_profit", 0.0)
        ),
        average_profit=float(
            statistics.get("average_profit", 0.0)
        ),
        average_rr=float(
            statistics.get("average_rr", 0.0)
        ),
        profit_factor=_safe_float(
            statistics.get("profit_factor")
        ),
    )


@router.get(
    "/trades/{trade_id}",
    response_model=ResearchTradeResponse,
)
def get_research_trade(
    trade_id: str,
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> ResearchTradeResponse:
    """
    Return full details for one virtual trade.
    """

    trade = repository.get_by_id(
        trade_id=trade_id,
    )

    if trade is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=(
                "Research trade was not found: "
                f"{trade_id}"
            ),
        )

    return ResearchTradeResponse.from_trade(
        trade,
    )


def _normalize_status(
    status: str | None,
) -> str | None:
    """
    Validate and normalize optional status query parameter.
    """

    if status is None:
        return None

    normalized = status.strip().lower()

    allowed_statuses = {
        item.value
        for item in TradeStatus
    }

    if normalized not in allowed_statuses:
        from fastapi import HTTPException

        allowed = ", ".join(
            sorted(allowed_statuses)
        )

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported trade status: {status}. "
                f"Allowed values: {allowed}."
            ),
        )

    return normalized


def _safe_float(
    value: object,
) -> float | None:
    """
    Convert finite numeric values for JSON responses.
    """

    if value is None:
        return None

    try:
        converted = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(converted):
        return None

    return converted