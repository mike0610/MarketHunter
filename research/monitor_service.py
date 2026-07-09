"""
MarketHunter

Module:
Research Monitor Service

Responsibilities:
- Load all open virtual trades.
- Process only completed market candles.
- Process only candles closed after virtual trade creation.
- Delegate lifecycle updates to TradeMonitor.
- Return a transparent monitoring summary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.monitor import TradeMonitor
from research.setup.support_resistance import SupportResistanceDetector
from research.setup.risk_geometry import RiskGeometryDetector
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
    revalidated_to_candidate: int = 0
    errors: list[str] = field(
        default_factory=list,
    )


class ResearchMonitorService:
    """
    Monitors all waiting-entry and active virtual trades.

    On the first run, only candles closed after trade creation are used.
    This prevents a new trade from replaying historical price action.
    """

    def __init__(
        self,
        repository: ResearchRepository,
        monitor: TradeMonitor | None = None,
        target_rr: float = 3.0,
        support_resistance: SupportResistanceDetector | None = None,
        risk_geometry: RiskGeometryDetector | None = None,
    ) -> None:
        self.repository = repository
        self.monitor = monitor or TradeMonitor(
            repository=repository,
        )
        self.target_rr = target_rr
        self.support_resistance = (
            support_resistance
            or SupportResistanceDetector(
                lookback_candles=160,
                pivot_window=2,
                min_touches=1,
                max_zones=12,
            )
        )
        self.risk_geometry = (
            risk_geometry
            or RiskGeometryDetector()
        )

    async def run_once(
        self,
        candle_loader: CandleLoader,
        now: datetime | None = None,
    ) -> MonitorRunResult:
        """
        Process all open virtual trades once.
        """

        run_time = now or datetime.now(
            timezone.utc,
        )

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

                if (
                    trade.status == TradeStatus.WAITING_ENTRY
                    and not self._waiting_entry_still_valid(
                        trade=trade,
                        candles=completed_candles,
                    )
                ):
                    result.revalidated_to_candidate += 1
                    continue

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
                    f"{trade.symbol} "
                    f"{trade.strategy}: {exc}"
                )

        return result

    def _waiting_entry_still_valid(
        self,
        *,
        trade: ResearchTrade,
        candles: list[Candle],
    ) -> bool:
        if not candles:
            return True

        risk_geometry = self.risk_geometry.assess_values(
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
        )

        if not risk_geometry.valid:
            reason = (
                "WAITING_ENTRY_REVALIDATION_FAILED: "
                f"{risk_geometry.summary}"
            )

            trade.move_to_candidate(
                reason=reason,
                processed_at=candles[-1].close_time,
            )

            self.repository.save(trade)

            return False

        assessment = self.support_resistance.assess_rr_target(
            candles,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            target_rr=self.target_rr,
        )

        if assessment.target_clear:
            return True

        reason = (
            "WAITING_ENTRY_REVALIDATION_FAILED: "
            f"{assessment.summary}"
        )

        trade.move_to_candidate(
            reason=reason,
            processed_at=candles[-1].close_time,
        )

        self.repository.save(trade)

        return False

    def _completed_candles(
        self,
        candles: list[Candle],
        now: datetime,
    ) -> list[Candle]:
        """
        Return completed candles ordered by close time.
        """

        now_utc = self._utc_time(now)

        return sorted(
            [
                candle
                for candle in candles
                if self._utc_time(candle.close_time)
                <= now_utc
            ],
            key=lambda candle: self._utc_time(
                candle.close_time
            ),
        )

    def _new_candles(
        self,
        trade: ResearchTrade,
        candles: list[Candle],
    ) -> list[Candle]:
        """
        Return unprocessed candles valid for this trade.

        A first monitor cycle may replay multiple candles only when they
        closed after the virtual trade was created.
        """

        if not candles:
            return []

        if trade.last_processed_candle_at is None:
            created_at = self._utc_time(
                trade.created_at,
            )

            return [
                candle
                for candle in candles
                if self._utc_time(candle.close_time)
                > created_at
            ]

        last_time = self._utc_time(
            trade.last_processed_candle_at,
        )

        return [
            candle
            for candle in candles
            if self._utc_time(candle.close_time)
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
        Add lifecycle changes to the monitoring summary.
        """

        if (
            previous_status
            == TradeStatus.WAITING_ENTRY
            and current_status
            == TradeStatus.ACTIVE
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
    def _utc_time(
        value: datetime,
    ) -> datetime:
        """
        Convert naive or aware time into timezone-aware UTC time.
        """

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )