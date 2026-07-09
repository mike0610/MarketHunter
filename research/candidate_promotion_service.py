"""
MarketHunter

Module:
Candidate Promotion Service

Responsibilities:
- Re-check candidate/watchlist trades.
- Promote candidate -> waiting_entry when setup becomes valid again.
- Keep bad candidates out of active monitoring until target/reaction improve.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.candle import Candle
from research.models.trade import ResearchTrade
from research.setup.reaction_quality import ReactionQualityDetector
from research.setup.support_resistance import SupportResistanceDetector
from research.storage.repository import ResearchRepository
from services.snapshot_builder import SnapshotBuilder


CandleLoader = Callable[
    [ResearchTrade],
    Awaitable[list[Candle]],
]


@dataclass(slots=True)
class CandidatePromotionResult:
    candidates: int = 0
    checked: int = 0
    promoted: int = 0
    blocked: int = 0
    skipped_without_candles: int = 0
    errors: list[str] = field(default_factory=list)


class CandidatePromotionService:
    """
    Promotes candidate trades only when current market conditions improve.
    """

    def __init__(
        self,
        *,
        repository: ResearchRepository,
        target_rr: float = 3.0,
        support_resistance: SupportResistanceDetector | None = None,
        reaction_quality: ReactionQualityDetector | None = None,
        snapshot_builder: SnapshotBuilder | None = None,
        max_promotions_per_cycle: int = 3,
    ) -> None:
        if target_rr <= 0:
            raise ValueError(
                "Target RR must be positive."
            )

        if max_promotions_per_cycle < 1:
            raise ValueError(
                "Max promotions per cycle must be at least 1."
            )

        self.repository = repository
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
        self.reaction_quality = (
            reaction_quality
            or ReactionQualityDetector()
        )
        self.snapshot_builder = (
            snapshot_builder
            or SnapshotBuilder()
        )
        self.max_promotions_per_cycle = max_promotions_per_cycle

    async def run_once(
        self,
        *,
        candle_loader: CandleLoader,
        now: datetime | None = None,
    ) -> CandidatePromotionResult:
        run_time = now or datetime.now(
            timezone.utc,
        )

        result = CandidatePromotionResult()

        candidates = self.repository.list_candidates()
        result.candidates = len(candidates)

        for trade in candidates:
            if result.promoted >= self.max_promotions_per_cycle:
                break

            try:
                candles = await candle_loader(trade)

                completed_candles = self._completed_candles(
                    candles=candles,
                    now=run_time,
                )

                if not completed_candles:
                    result.skipped_without_candles += 1
                    continue

                result.checked += 1

                if not self._candidate_still_actionable(
                    trade=trade,
                    candles=completed_candles,
                    result=result,
                ):
                    continue

                snapshot = self.snapshot_builder.build(
                    trade.symbol,
                    completed_candles,
                )

                reaction = self.reaction_quality.assess(
                    snapshot=snapshot,
                    direction=trade.direction,
                )

                if not reaction.confirmed:
                    self._block_candidate(
                        trade=trade,
                        reason=(
                            "CANDIDATE_PROMOTION_BLOCKED: "
                            f"{reaction.summary}"
                        ),
                        processed_at=completed_candles[-1].close_time,
                    )
                    result.blocked += 1
                    continue

                parabolic_reason = self._parabolic_extension_reason(
                    snapshot=snapshot,
                    direction=trade.direction,
                )

                if parabolic_reason is not None:
                    self._block_candidate(
                        trade=trade,
                        reason=(
                            "CANDIDATE_PROMOTION_BLOCKED: "
                            f"{parabolic_reason}"
                        ),
                        processed_at=completed_candles[-1].close_time,
                    )
                    result.blocked += 1
                    continue

                trade.promote_to_waiting_entry(
                    reason=(
                        "CANDIDATE_PROMOTED: target clear and "
                        f"{reaction.summary}"
                    ),
                    processed_at=completed_candles[-1].close_time,
                )

                self.repository.save(trade)
                result.promoted += 1

            except Exception as exc:
                result.errors.append(
                    f"{trade.symbol} {trade.direction} "
                    f"{trade.strategy}: {type(exc).__name__}: {exc}"
                )

        return result

    def _candidate_still_actionable(
        self,
        *,
        trade: ResearchTrade,
        candles: list[Candle],
        result: CandidatePromotionResult,
    ) -> bool:
        assessment = self.support_resistance.assess_rr_target(
            candles,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            target_rr=self.target_rr,
        )

        if assessment.target_clear:
            return True

        self._block_candidate(
            trade=trade,
            reason=(
                "CANDIDATE_PROMOTION_BLOCKED: "
                f"{assessment.summary}"
            ),
            processed_at=candles[-1].close_time,
        )

        result.blocked += 1

        return False

    def _block_candidate(
        self,
        *,
        trade: ResearchTrade,
        reason: str,
        processed_at: datetime,
    ) -> None:
        trade.close_reason = reason
        trade.last_processed_candle_at = processed_at
        self.repository.save(trade)

    @staticmethod
    def _completed_candles(
        *,
        candles: list[Candle],
        now: datetime,
    ) -> list[Candle]:
        now_utc = CandidatePromotionService._utc_time(now)

        return sorted(
            [
                candle
                for candle in candles
                if CandidatePromotionService._utc_time(
                    candle.close_time,
                )
                <= now_utc
            ],
            key=lambda candle: CandidatePromotionService._utc_time(
                candle.close_time,
            ),
        )

    @staticmethod
    def _parabolic_extension_reason(
        *,
        snapshot,
        direction: str,
    ) -> str | None:
        candles = getattr(
            snapshot,
            "candles",
            None,
        )

        if not candles or len(candles) < 30:
            return None

        atr = float(
            getattr(
                snapshot,
                "atr14",
                0.0,
            )
            or 0.0
        )

        ema20 = float(
            getattr(
                snapshot,
                "ema20",
                0.0,
            )
            or 0.0
        )

        if atr <= 0 or ema20 <= 0:
            return None

        normalized_direction = direction.strip().upper()
        close = candles[-1].close
        lookback_close = candles[-21].close

        if lookback_close <= 0:
            return None

        recent = candles[-5:]

        if normalized_direction == "SHORT":
            recent_move_percent = (
                (lookback_close - close)
                / lookback_close
                * 100
            )
            ema_distance_percent = (
                (ema20 - close)
                / ema20
                * 100
            )
            ema_distance_atr = (
                (ema20 - close)
                / atr
            )
            recent_high = max(
                candle.high
                for candle in recent
            )
            has_pullback = recent_high >= (
                ema20 - (atr * 0.25)
            )

        else:
            normalized_direction = "LONG"
            recent_move_percent = (
                (close - lookback_close)
                / lookback_close
                * 100
            )
            ema_distance_percent = (
                (close - ema20)
                / ema20
                * 100
            )
            ema_distance_atr = (
                (close - ema20)
                / atr
            )
            recent_low = min(
                candle.low
                for candle in recent
            )
            has_pullback = recent_low <= (
                ema20 + (atr * 0.25)
            )

        if recent_move_percent < 12.0:
            return None

        if ema_distance_percent < 5.0:
            return None

        if ema_distance_atr < 1.8:
            return None

        if has_pullback:
            return None

        return (
            f"{normalized_direction} is extended after a "
            f"{recent_move_percent:.2f}% move over 20 candles, "
            f"{ema_distance_percent:.2f}% / "
            f"{ema_distance_atr:.2f} ATR away from EMA20, "
            "without a pullback/retest."
        )

    @staticmethod
    def _utc_time(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc,
            )

        return value.astimezone(
            timezone.utc,
        )
