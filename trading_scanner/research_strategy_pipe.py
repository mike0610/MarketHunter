"""
Pipe the already-implemented Research strategies into the Active Trading scanner.

No strategy rules are reimplemented here. This adapter only converts the
broker-independent daily MarketBar series into the existing MarketSnapshot
contract and records any signals emitted by the unchanged strategy classes in
the normal Trading Candidate Queue.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from experiment1.models import SessionState
from market_data.foundation import AsyncMarketDataProvider, MarketInstrument
from models.candle import Candle
from services.snapshot_builder import SnapshotBuilder
from strategies.breakout import BreakoutStrategy
from strategies.compression import CompressionStrategy
from strategies.liquidity_sweep import LiquiditySweepStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.premium_discount import PremiumDiscountStrategy
from trading_scanner.gates import (
    DEFAULT_LIQUIDITY_THRESHOLDS,
    LiquidityThresholds,
    evaluate_liquidity_gate,
)
from trading_scanner.models import (
    IbkrContract,
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)
from trading_scanner.store import TradingScannerStore


STRATEGY_PIPE = (
    (SetupFamily.PREMIUM_DISCOUNT, PremiumDiscountStrategy),
    (SetupFamily.BREAKOUT, BreakoutStrategy),
    (SetupFamily.ORDER_BLOCK, OrderBlockStrategy),
    (SetupFamily.COMPRESSION, CompressionStrategy),
    (SetupFamily.LIQUIDITY_SWEEP, LiquiditySweepStrategy),
)


def _scanner_id(instrument: MarketInstrument) -> int:
    raw = "|".join(
        (
            instrument.symbol,
            instrument.asset_class,
            instrument.currency,
            instrument.exchange or "",
        )
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _contract(instrument: MarketInstrument) -> IbkrContract:
    sec_type = {
        "CRYPTO_SPOT": "CRYPTO_SPOT",
        "CRYPTO_FUTURES": "CRYPTO_FUTURES",
        "US_STOCK_OR_ETF": "STK",
    }.get(instrument.asset_class, instrument.asset_class)
    return IbkrContract(
        conid=_scanner_id(instrument),
        symbol=instrument.symbol,
        sec_type=sec_type,
        exchange=instrument.exchange or "MARKET_DATA",
        currency=instrument.currency,
        primary_exchange=instrument.exchange,
        restricted=False,
    )


def _candles(series) -> list[Candle]:
    bars = list(series.bars)
    candles: list[Candle] = []
    for index, bar in enumerate(bars):
        close_time = bars[index + 1].timestamp if index + 1 < len(bars) else bar.timestamp
        candles.append(
            Candle(
                open_time=bar.timestamp,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
                close_time=close_time,
                quote_volume=float(bar.volume * bar.close),
                trades=0,
                taker_buy_base_volume=0.0,
                taker_buy_quote_volume=0.0,
            )
        )
    return candles


def _realized_range_pct(candles: list[Candle]) -> Decimal:
    tail = candles[-20:]
    close = Decimal(str(tail[-1].close))
    high = Decimal(str(max(c.high for c in tail)))
    low = Decimal(str(min(c.low for c in tail)))
    return Decimal("0") if close == 0 else ((high - low) / close) * Decimal("100")


async def run_research_strategy_pipe(
    provider: AsyncMarketDataProvider,
    store: TradingScannerStore,
    *,
    scan_cycle_id: str | None = None,
    now: datetime | None = None,
    history_limit: int = 500,
    liquidity_thresholds: LiquidityThresholds = DEFAULT_LIQUIDITY_THRESHOLDS,
) -> tuple[TradingCandidate, ...]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if history_limit < 200:
        raise ValueError("history_limit must be at least 200")

    cycle_id = scan_cycle_id or f"research-strategy-pipe:{moment.isoformat()}"
    snapshot_builder = SnapshotBuilder()
    recorded: list[TradingCandidate] = []

    for instrument in await provider.universe():
        contract = _contract(instrument)
        liquidity_evidence = await provider.liquidity(instrument)
        liquidity = LiquidityContext(
            average_daily_volume=liquidity_evidence.average_daily_volume,
            average_daily_dollar_volume=liquidity_evidence.average_daily_dollar_volume,
            last_price=liquidity_evidence.last_price,
        )
        gate = evaluate_liquidity_gate(
            contract,
            liquidity,
            SessionState.REGULAR,
            liquidity_thresholds,
            require_regular_session=False,
        )
        if not gate.eligible:
            continue

        series = await provider.history(instrument, timeframe="1d", limit=history_limit)
        candles = _candles(series)
        if len(candles) < 200:
            continue
        snapshot = snapshot_builder.build(instrument.symbol, candles)
        volatility = VolatilityContext(realized_range_pct=_realized_range_pct(candles))

        for family, strategy_type in STRATEGY_PIPE:
            signal = await strategy_type().analyze(snapshot)
            if signal is None:
                continue

            direction = str(signal.direction).strip().upper()
            if direction not in {"LONG", "SHORT"}:
                continue

            candidate = TradingCandidate(
                conid=contract.conid,
                symbol=contract.symbol,
                sec_type=contract.sec_type,
                exchange=contract.exchange,
                currency=contract.currency,
                setup_family=family,
                reason_stack=tuple(signal.reasons) or (f"{family.value} signal",),
                liquidity=liquidity,
                volatility=volatility,
                evidence_status="OK",
                eligible=True,
                discovered_at=moment,
                scan_cycle_id=cycle_id,
                dedupe_key=f"{contract.conid}:{family.value}:{cycle_id}",
                queue_state=QueueState.CANDIDATE,
                freshness_note=(
                    f"unchanged Research strategy over {series.provider} "
                    f"{series.timeframe} bars observed_at={series.observed_at.isoformat()}"
                ),
                signal_bar_high=Decimal(str(candles[-1].high)),
                signal_bar_low=Decimal(str(candles[-1].low)),
                signal_direction=direction,
                signal_score=Decimal(str(signal.score)),
            )
            recorded.append(store.record_candidate(candidate))

    return tuple(recorded)
