"""
MarketHunter

Module:
Research Monitor Service

Responsibilities:
- Load all open virtual trades.
- Process only completed and new market candles.
- Delegate lifecycle changes to TradeMonitor.
- Return a transparent monitoring summary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.monitor import TradeMonitor
from research.storage.repository import ResearchRepository


CandleLoader = Callable[
    [ResearchTrade],
    Awaitable[list[Candle]],
]


@dataclass(slots=True)
class MonitorRunResult:
    """
    Summary of one monitoring cycle.
    """

    open_trades: int = 0
    monitored_trades: int = 0
    activated: int = 0
    closed_tp: int = 0
    closed_sl: int = 0
    expired: int = 0
    skipped_without_candles: int = 0
    errors: list[str] = field(default_factory=list)


class ResearchMonitorService:
    """
    Monitors all open virtual trades.

    On the first monitoring cycle for a trade, only the latest completed
    candle is processed. This prevents accidental replay of historical
    candles that existed before the virtual trade was created.
    """

    def __init__(
        self,
        repository: ResearchRepository,
        monitor: TradeMonitor | None = None,
    ) -> None:
        self.repository = repository
        self.monitor = monitor or TradeMonitor(
            repository=repository,
        )

    async def run_once(
        self,
        candle_loader: CandleLoader,
        now: datetime | None = None,
    ) -> MonitorRunResult:
        """
        Process all waiting-entry and active virtual trades once.
        """

        run_time = now or datetime.now()

        result = MonitorRunResult()

        trades = self.repository.list_open()

        result.open_trades = len(trades)

        for trade in trades:
            try:
                candles = await candle_loader(trade)

                completed_candles = self._completed_candles(
                    candles=candles,
                    now=run_time,
                )

                new_candles = self._new_candles(
                    trade=trade,
                    candles=completed_candles,
                )

                if not new_candles:
                    result.skipped_without_candles += 1
                    continue

                result.monitored_trades += 1

                for candle in new_candles:
                    previous_status = trade.status

                    self.monitor.update_with_candle(
                        trade=trade,
                        candle=candle,
                    )

                    self._count_transition(
                        result=result,
                        previous_status=previous_status,
                        current_status=trade.status,
                        close_reason=trade.close_reason,
                    )

                    if not trade.is_open:
                        break

            except Exception as exc:
                result.errors.append(
                    f"{trade.symbol} {trade.strategy}: {exc}"
                )

        return result

    def _completed_candles(
        self,
        candles: list[Candle],
        now: datetime,
    ) -> list[Candle]:
        """
        Keep candles that are already closed and sort them by close time.
        """

        return sorted(
            [
                candle
                for candle in candles
                if self._naive_time(candle.close_time)
                <= self._naive_time(now)
            ],
            key=lambda candle: self._naive_time(
                candle.close_time
            ),
        )

    def _new_candles(
        self,
        trade: ResearchTrade,
        candles: list[Candle],
    ) -> list[Candle]:
        """
        Return candles that were not processed for this trade yet.

        A newly created trade receives only the latest completed candle.
        Later cycles receive every candle newer than the saved timestamp.
        """

        if not candles:
            return []

        if trade.last_processed_candle_at is None:
            return candles[-1:]

        last_time = self._naive_time(
            trade.last_processed_candle_at
        )

        return [
            candle
            for candle in candles
            if self._naive_time(candle.close_time)
            > last_time
        ]

    def _count_transition(
        self,
        result: MonitorRunResult,
        previous_status: TradeStatus,
        current_status: TradeStatus,
        close_reason: str | None,
    ) -> None:
        """
        Add lifecycle changes to the run summary.
        """

        if (
            previous_status == TradeStatus.WAITING_ENTRY
            and current_status == TradeStatus.ACTIVE
        ):
            result.activated += 1

        if current_status == TradeStatus.CLOSED:
            if close_reason == "TP":
                result.closed_tp += 1

            elif close_reason == "SL":
                result.closed_sl += 1

        elif current_status == TradeStatus.EXPIRED:
            result.expired += 1

    @staticmethod
    def _naive_time(
        value: datetime,
    ) -> datetime:
        """
        Normalize aware and naive datetimes for safe comparison.
        """

        return value.replace(tzinfo=None)