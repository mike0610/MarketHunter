"""
MarketHunter

Module:
Research API

Responsibilities:
- Provide virtual research trades for Dashboard.
- Provide details for one virtual trade.
- Provide aggregate research statistics.
- Provide persisted continuous worker status.
- Provide scan runs and signal journal records.
- Provide trade setup analysis with RR targets and S/R zones.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator, Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from indicators.divergence_detector import (
    DivergenceSignal,
    RSIDivergenceDetector,
)
from models.market_symbol import MarketSymbol
from research.models.trade import (
    CORE_RESEARCH_GROUP,
    EXPERIMENTAL_RESEARCH_GROUP,
    ResearchTrade,
)
from research.models.trade_status import TradeStatus
from research.setup.support_resistance import (
    SupportResistanceDetector,
    SupportResistanceZone,
    calculate_rr_target,
    normalize_direction,
)
from research.statistics import ResearchStatistics
from research.storage.repository import (
    ResearchRepository,
    WorkerStatus,
)
from research.storage.scan_journal_repository import (
    ScanJournalRepository,
    ScanRun,
    SignalRecord,
)
from services.market_data import MarketDataService


DATABASE_PATH = "data/research.db"
SETUP_CANDLE_LIMIT = 240
SETUP_TARGET_RR = 3.0
SETUP_DIVERGENCE_FRESH_BARS = 40


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

    research_group: str
    experiment_tag: str | None
    is_experimental: bool

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
            research_group=trade.research_group,
            experiment_tag=trade.experiment_tag,
            is_experimental=trade.is_experimental,
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


class ScanRunResponse(BaseModel):
    """
    Serializable scan run.
    """

    id: str
    started_at: datetime
    finished_at: datetime | None
    status: str

    timeframe: str
    candle_limit: int
    symbol_limit: int
    min_quote_volume_usdt: float

    research_minimum_probability: int
    elite_minimum_probability: int

    symbols_scanned: int
    candidate_signals: int
    research_trades_created: int
    elite_signals_found: int

    error: str | None

    @classmethod
    def from_scan_run(
        cls,
        scan_run: ScanRun,
    ) -> "ScanRunResponse":
        """
        Convert ScanRun into API response.
        """

        return cls(
            id=scan_run.id,
            started_at=scan_run.started_at,
            finished_at=scan_run.finished_at,
            status=scan_run.status,
            timeframe=scan_run.timeframe,
            candle_limit=scan_run.candle_limit,
            symbol_limit=scan_run.symbol_limit,
            min_quote_volume_usdt=(
                scan_run.min_quote_volume_usdt
            ),
            research_minimum_probability=(
                scan_run.research_minimum_probability
            ),
            elite_minimum_probability=(
                scan_run.elite_minimum_probability
            ),
            symbols_scanned=scan_run.symbols_scanned,
            candidate_signals=scan_run.candidate_signals,
            research_trades_created=(
                scan_run.research_trades_created
            ),
            elite_signals_found=scan_run.elite_signals_found,
            error=scan_run.error,
        )


class LatestScanRunResponse(BaseModel):
    """
    Latest scan response.
    """

    scan_run: ScanRunResponse | None


class ScanRunListResponse(BaseModel):
    """
    Scan run list response.
    """

    scan_runs: list[ScanRunResponse]
    total: int
    offset: int
    limit: int


class SignalRecordResponse(BaseModel):
    """
    Serializable scan signal record.
    """

    id: str
    scan_run_id: str

    symbol: str
    market: str
    timeframe: str
    strategy: str
    direction: str

    score: float
    probability: int | None
    confidence: str | None

    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None

    status: str
    rejected_reason: str | None

    research_trade_id: str | None
    research_skipped: str | None
    is_elite: bool

    reasons: list[str]
    probability_reasons: list[str]
    metadata: dict

    created_at: datetime

    @classmethod
    def from_signal_record(
        cls,
        record: SignalRecord,
    ) -> "SignalRecordResponse":
        """
        Convert SignalRecord into API response.
        """

        return cls(
            id=record.id,
            scan_run_id=record.scan_run_id,
            symbol=record.symbol,
            market=record.market,
            timeframe=record.timeframe,
            strategy=record.strategy,
            direction=record.direction,
            score=record.score,
            probability=record.probability,
            confidence=record.confidence,
            entry_price=record.entry_price,
            stop_loss=record.stop_loss,
            take_profit=record.take_profit,
            risk_reward=record.risk_reward,
            status=record.status,
            rejected_reason=record.rejected_reason,
            research_trade_id=record.research_trade_id,
            research_skipped=record.research_skipped,
            is_elite=record.is_elite,
            reasons=list(record.reasons),
            probability_reasons=list(
                record.probability_reasons
            ),
            metadata=dict(record.metadata),
            created_at=record.created_at,
        )


class SignalRecordListResponse(BaseModel):
    """
    Signal record list response.
    """

    signals: list[SignalRecordResponse]
    total: int
    offset: int
    limit: int


class SetupTargetResponse(BaseModel):
    """
    RR target price.
    """

    rr: float
    price: float


class SupportResistanceZoneResponse(BaseModel):
    """
    Serializable support / resistance zone.
    """

    zone_type: str

    lower: float
    upper: float
    center: float

    touches: int
    strength: float

    last_touched_at: datetime | None

    distance_to_entry_percent: float | None
    distance_to_target_percent: float | None

    @classmethod
    def from_zone(
        cls,
        zone: SupportResistanceZone,
    ) -> "SupportResistanceZoneResponse":
        """
        Convert zone into API response.
        """

        return cls(
            zone_type=zone.zone_type,
            lower=zone.lower,
            upper=zone.upper,
            center=zone.center,
            touches=zone.touches,
            strength=zone.strength,
            last_touched_at=zone.last_touched_at,
            distance_to_entry_percent=(
                zone.distance_to_entry_percent
            ),
            distance_to_target_percent=(
                zone.distance_to_target_percent
            ),
        )


class SetupDivergenceResponse(BaseModel):
    """
    Serializable RSI divergence confirmation.
    """

    kind: str
    direction: str
    oscillator: str

    first_index: int
    second_index: int
    bars_between: int

    price_first: float
    price_second: float

    oscillator_first: float
    oscillator_second: float

    strength: float

    @classmethod
    def from_signal(
        cls,
        signal: DivergenceSignal,
    ) -> "SetupDivergenceResponse":
        """
        Convert divergence signal into API response.
        """

        return cls(
            kind=signal.kind,
            direction=signal.direction,
            oscillator=signal.oscillator,
            first_index=signal.first_index,
            second_index=signal.second_index,
            bars_between=signal.bars_between,
            price_first=signal.price_first,
            price_second=signal.price_second,
            oscillator_first=signal.oscillator_first,
            oscillator_second=signal.oscillator_second,
            strength=signal.strength,
        )


class TradeSetupResponse(BaseModel):
    """
    Trade setup analysis for chart visualization.
    """

    trade_id: str

    symbol: str
    market: str
    timeframe: str
    direction: str

    entry_price: float
    stop_loss: float
    current_take_profit: float

    rr_targets: list[SetupTargetResponse]

    assessed_rr: float
    assessed_target_price: float
    assessed_target_clear: bool
    summary: str

    zones: list[SupportResistanceZoneResponse]
    blocking_zones: list[SupportResistanceZoneResponse]

    divergences: list[SetupDivergenceResponse]
    latest_bullish_divergence: SetupDivergenceResponse | None
    latest_bearish_divergence: SetupDivergenceResponse | None

    trade_direction_divergence: SetupDivergenceResponse | None
    opposite_direction_divergence: SetupDivergenceResponse | None
    trade_direction_divergence_confirmed: bool
    divergence_fresh_window_bars: int


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


def get_scan_journal() -> Iterator[ScanJournalRepository]:
    """
    Open one short-lived scan journal connection per API request.
    """

    journal = ScanJournalRepository(
        path=DATABASE_PATH,
    )

    try:
        yield journal
    finally:
        journal.close()


async def get_market_data() -> AsyncIterator[MarketDataService]:
    """
    Open one short-lived market data client per API request.
    """

    market_data = MarketDataService()

    try:
        yield market_data
    finally:
        await market_data.close()


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
    "/latest-scan",
    response_model=LatestScanRunResponse,
)
def get_latest_scan(
    journal: ScanJournalRepository = Depends(
        get_scan_journal,
    ),
) -> LatestScanRunResponse:
    """
    Return latest scan run.
    """

    scan_run = journal.get_latest_scan_run()

    if scan_run is None:
        return LatestScanRunResponse(
            scan_run=None,
        )

    return LatestScanRunResponse(
        scan_run=ScanRunResponse.from_scan_run(
            scan_run,
        ),
    )


@router.get(
    "/scan-runs",
    response_model=ScanRunListResponse,
)
def list_scan_runs(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    journal: ScanJournalRepository = Depends(
        get_scan_journal,
    ),
) -> ScanRunListResponse:
    """
    Return recent scan runs.
    """

    scan_runs = journal.list_scan_runs(
        limit=limit,
        offset=offset,
    )

    return ScanRunListResponse(
        scan_runs=[
            ScanRunResponse.from_scan_run(scan_run)
            for scan_run in scan_runs
        ],
        total=len(scan_runs),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/scan-runs/{scan_run_id}/signals",
    response_model=SignalRecordListResponse,
)
def list_scan_signals(
    scan_run_id: str,
    status: str | None = Query(
        default=None,
        description="Signal status: rejected, research or elite.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    journal: ScanJournalRepository = Depends(
        get_scan_journal,
    ),
) -> SignalRecordListResponse:
    """
    Return signal records for one scan run.
    """

    normalized_status = _normalize_signal_status(
        status,
    )

    signals = journal.list_signal_records(
        scan_run_id=scan_run_id,
        status=normalized_status,
        limit=limit,
        offset=offset,
    )

    total = journal.count_signal_records(
        scan_run_id=scan_run_id,
        status=normalized_status,
    )

    return SignalRecordListResponse(
        signals=[
            SignalRecordResponse.from_signal_record(signal)
            for signal in signals
        ],
        total=total,
        offset=offset,
        limit=limit,
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
    research_group: str | None = Query(
        default=None,
        description="Optional research group filter: core or experimental.",
    ),
    experiment_tag: str | None = Query(
        default=None,
        description="Optional experiment tag filter, for example spot_research.",
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

    normalized_research_group = _normalize_research_group(
        research_group,
    )

    normalized_experiment_tag = (
        experiment_tag.strip().lower()
        if experiment_tag
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

    if normalized_research_group is not None:
        trades = [
            trade
            for trade in trades
            if trade.research_group == normalized_research_group
        ]

    if normalized_experiment_tag is not None:
        trades = [
            trade
            for trade in trades
            if trade.experiment_tag == normalized_experiment_tag
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
    "/statistics/setup-reasons",
)
def get_research_setup_reason_statistics(
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> dict[str, object]:
    """
    Return research performance grouped by setup and block reason.
    """

    trades = repository.list_all()

    statistics = ResearchStatistics().calculate_setup_reasons(
        trades,
    )

    statistics["signal_block_reasons"] = (
        repository.get_signal_block_reason_statistics(
            limit=1000,
        )
    )

    return statistics


@router.get(
    "/statistics/conflicts",
)
def get_research_direction_conflict_statistics(
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> dict[str, object]:
    """
    Return direction-conflict analytics from scan journal.
    """

    return repository.get_direction_conflict_statistics(
        limit=2000,
    )


@router.get(
    "/statistics/target-blocks",
)
def get_research_target_block_statistics(
    repository: ResearchRepository = Depends(
        get_repository,
    ),
) -> dict[str, object]:
    """
    Return target-block analytics from scan journal.
    """

    return repository.get_target_block_statistics(
        limit=2000,
    )


@router.get(
    "/trades/{trade_id}/setup",
    response_model=TradeSetupResponse,
)
async def get_research_trade_setup(
    trade_id: str,
    repository: ResearchRepository = Depends(
        get_repository,
    ),
    market_data: MarketDataService = Depends(
        get_market_data,
    ),
) -> TradeSetupResponse:
    """
    Return RR targets and support/resistance zones for one trade.
    """

    trade = repository.get_by_id(
        trade_id=trade_id,
    )

    if trade is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Research trade was not found: "
                f"{trade_id}"
            ),
        )

    try:
        direction = normalize_direction(
            trade.direction,
        )

        setup_stop_loss = trade.stop_loss

        if direction == "LONG" and setup_stop_loss >= trade.entry_price:
            inferred_risk = (
                trade.take_profit
                - trade.entry_price
            ) / 2.0

            if inferred_risk <= 0:
                raise ValueError(
                    "LONG setup risk cannot be inferred from take_profit."
                )

            setup_stop_loss = trade.entry_price - inferred_risk

        elif direction == "SHORT" and setup_stop_loss <= trade.entry_price:
            inferred_risk = (
                trade.entry_price
                - trade.take_profit
            ) / 2.0

            if inferred_risk <= 0:
                raise ValueError(
                    "SHORT setup risk cannot be inferred from take_profit."
                )

            setup_stop_loss = trade.entry_price + inferred_risk

        rr_targets = [
            SetupTargetResponse(
                rr=rr,
                price=calculate_rr_target(
                    direction=direction,
                    entry_price=trade.entry_price,
                    stop_loss=setup_stop_loss,
                    risk_reward=rr,
                ),
            )
            for rr in [
                1.0,
                2.0,
                3.0,
            ]
        ]

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    symbol = _build_market_symbol(
        symbol=trade.symbol,
        market=trade.market,
    )

    try:
        candles = await market_data.load_candles(
            symbol=symbol,
            interval=trade.timeframe,
            limit=SETUP_CANDLE_LIMIT,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Failed to load market candles for setup "
                f"analysis: {type(exc).__name__}: {exc}"
            ),
        ) from exc

    if len(candles) < 20:
        raise HTTPException(
            status_code=502,
            detail=(
                "Not enough candles for setup analysis. "
                f"Loaded: {len(candles)}."
            ),
        )

    detector = SupportResistanceDetector(
        lookback_candles=160,
        pivot_window=2,
        min_touches=1,
        max_zones=12,
    )

    try:
        assessment = detector.assess_rr_target(
            candles,
            direction=direction,
            entry_price=trade.entry_price,
            stop_loss=setup_stop_loss,
            target_rr=SETUP_TARGET_RR,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    divergence_detector = RSIDivergenceDetector(
        rsi_period=14,
        pivot_window=2,
        min_bars_between=3,
        max_bars_between=80,
        min_rsi_delta=2.0,
    )

    divergences = divergence_detector.detect(
        candles,
    )

    latest_bullish_divergence = next(
        (
            signal
            for signal in reversed(divergences)
            if signal.direction == "LONG"
        ),
        None,
    )

    latest_bearish_divergence = next(
        (
            signal
            for signal in reversed(divergences)
            if signal.direction == "SHORT"
        ),
        None,
    )

    if direction == "LONG":
        trade_direction_divergence = latest_bullish_divergence
        opposite_direction_divergence = latest_bearish_divergence
    else:
        trade_direction_divergence = latest_bearish_divergence
        opposite_direction_divergence = latest_bullish_divergence

    latest_candle_index = len(candles) - 1

    trade_direction_divergence_confirmed = (
        trade_direction_divergence is not None
        and (
            latest_candle_index
            - trade_direction_divergence.second_index
        )
        <= SETUP_DIVERGENCE_FRESH_BARS
    )

    return TradeSetupResponse(
        trade_id=trade.id,
        symbol=trade.symbol,
        market=trade.market,
        timeframe=trade.timeframe,
        direction=trade.direction,
        entry_price=trade.entry_price,
        stop_loss=trade.stop_loss,
        current_take_profit=trade.take_profit,
        rr_targets=rr_targets,
        assessed_rr=assessment.target_rr,
        assessed_target_price=assessment.target_price,
        assessed_target_clear=assessment.target_clear,
        summary=assessment.summary,
        zones=[
            SupportResistanceZoneResponse.from_zone(zone)
            for zone in assessment.zones
        ],
        blocking_zones=[
            SupportResistanceZoneResponse.from_zone(zone)
            for zone in assessment.blocking_zones
        ],
        divergences=[
            SetupDivergenceResponse.from_signal(signal)
            for signal in divergences
        ],
        latest_bullish_divergence=(
            None
            if latest_bullish_divergence is None
            else SetupDivergenceResponse.from_signal(
                latest_bullish_divergence,
            )
        ),
        latest_bearish_divergence=(
            None
            if latest_bearish_divergence is None
            else SetupDivergenceResponse.from_signal(
                latest_bearish_divergence,
            )
        ),
        trade_direction_divergence=(
            None
            if trade_direction_divergence is None
            else SetupDivergenceResponse.from_signal(
                trade_direction_divergence,
            )
        ),
        opposite_direction_divergence=(
            None
            if opposite_direction_divergence is None
            else SetupDivergenceResponse.from_signal(
                opposite_direction_divergence,
            )
        ),
        trade_direction_divergence_confirmed=(
            trade_direction_divergence_confirmed
        ),
        divergence_fresh_window_bars=(
            SETUP_DIVERGENCE_FRESH_BARS
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


def _build_market_symbol(
    *,
    symbol: str,
    market: str,
) -> MarketSymbol:
    """
    Build MarketSymbol from stored trade symbol.

    Examples:
    - BTCUSDT -> base BTC, quote USDT
    - 1000PEPEUSDT -> base 1000PEPE, quote USDT
    """

    normalized_symbol = symbol.strip().upper()
    normalized_market = market.strip().lower()

    known_quote_assets = [
        "FDUSD",
        "USDT",
        "USDC",
        "BUSD",
        "TUSD",
        "BTC",
        "ETH",
        "BNB",
        "EUR",
        "TRY",
        "BRL",
    ]

    for quote_asset in known_quote_assets:
        if not normalized_symbol.endswith(quote_asset):
            continue

        base_asset = normalized_symbol[
            : -len(quote_asset)
        ]

        if not base_asset:
            continue

        return MarketSymbol(
            symbol=normalized_symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            market=normalized_market,
        )

    return MarketSymbol(
        symbol=normalized_symbol,
        base_asset=normalized_symbol,
        quote_asset="",
        market=normalized_market,
    )


def _normalize_status(
    status: str | None,
) -> str | None:
    """
    Validate and normalize optional trade status query parameter.
    """

    if status is None:
        return None

    normalized = status.strip().lower()

    allowed_statuses = {
        item.value
        for item in TradeStatus
    }

    if normalized not in allowed_statuses:
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


def _normalize_research_group(
    research_group: str | None,
) -> str | None:
    """
    Validate and normalize optional research group query parameter.
    """

    if research_group is None:
        return None

    normalized = research_group.strip().lower()

    allowed_groups = {
        CORE_RESEARCH_GROUP,
        EXPERIMENTAL_RESEARCH_GROUP,
    }

    if normalized not in allowed_groups:
        allowed = ", ".join(
            sorted(allowed_groups)
        )

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported research group: {research_group}. "
                f"Allowed values: {allowed}."
            ),
        )

    return normalized


def _normalize_signal_status(
    status: str | None,
) -> str | None:
    """
    Validate and normalize optional signal status query parameter.
    """

    if status is None:
        return None

    normalized = status.strip().lower()

    allowed_statuses = {
        "rejected",
        "research",
        "elite",
    }

    if normalized not in allowed_statuses:
        allowed = ", ".join(
            sorted(allowed_statuses)
        )

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported signal status: {status}. "
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