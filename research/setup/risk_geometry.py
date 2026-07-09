"""
MarketHunter

Module:
Risk Geometry Filter

Blocks setups with invalid entry/stop geometry:
- stop too far from entry
- stop too many ATRs away
- FVG entry too far from its setup zone
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RiskGeometryAssessment:
    direction: str
    valid: bool
    summary: str
    reasons: list[str]
    entry_price: float
    stop_loss: float
    stop_distance: float
    stop_distance_percent: float
    stop_distance_atr: float | None
    entry_zone_relation: str
    entry_zone_distance_percent: float | None


class RiskGeometryDetector:
    """
    Validates that planned entry and stop-loss are realistic.
    """

    def __init__(
        self,
        *,
        max_stop_distance_percent: float = 10.0,
        max_stop_distance_atr: float = 6.0,
        max_entry_zone_distance_percent: float = 0.25,
    ) -> None:
        if max_stop_distance_percent <= 0:
            raise ValueError(
                "Max stop distance percent must be positive."
            )

        if max_stop_distance_atr <= 0:
            raise ValueError(
                "Max stop distance ATR must be positive."
            )

        if max_entry_zone_distance_percent < 0:
            raise ValueError(
                "Max entry zone distance percent cannot be negative."
            )

        self.max_stop_distance_percent = max_stop_distance_percent
        self.max_stop_distance_atr = max_stop_distance_atr
        self.max_entry_zone_distance_percent = (
            max_entry_zone_distance_percent
        )

    def assess(
        self,
        *,
        snapshot: object | None,
        direction: str,
        entry_price: float,
        stop_loss: float,
        strategy: str | None = None,
        signal_metadata: dict[str, Any] | None = None,
    ) -> RiskGeometryAssessment:
        atr14 = None

        if snapshot is not None:
            raw_atr = getattr(
                snapshot,
                "atr14",
                None,
            )

            if raw_atr is not None:
                atr14 = float(raw_atr)

        return self.assess_values(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            atr14=atr14,
            strategy=strategy,
            signal_metadata=signal_metadata,
        )

    def assess_values(
        self,
        *,
        direction: str,
        entry_price: float,
        stop_loss: float,
        atr14: float | None = None,
        strategy: str | None = None,
        signal_metadata: dict[str, Any] | None = None,
    ) -> RiskGeometryAssessment:
        normalized_direction = direction.strip().upper()
        reasons: list[str] = []

        if entry_price <= 0:
            return self._invalid(
                direction=normalized_direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                stop_distance=0.0,
                stop_distance_percent=0.0,
                stop_distance_atr=None,
                entry_zone_relation="unavailable",
                entry_zone_distance_percent=None,
                reason="entry price must be greater than zero",
            )

        if stop_loss <= 0:
            return self._invalid(
                direction=normalized_direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                stop_distance=0.0,
                stop_distance_percent=0.0,
                stop_distance_atr=None,
                entry_zone_relation="unavailable",
                entry_zone_distance_percent=None,
                reason="stop loss must be greater than zero",
            )

        if normalized_direction == "SHORT":
            directional_valid = stop_loss > entry_price
        else:
            normalized_direction = "LONG"
            directional_valid = stop_loss < entry_price

        stop_distance = abs(
            entry_price
            - stop_loss
        )

        stop_distance_percent = (
            stop_distance
            / entry_price
            * 100.0
        )

        stop_distance_atr = None

        if atr14 is not None and atr14 > 0:
            stop_distance_atr = stop_distance / atr14

        if not directional_valid:
            reasons.append(
                f"{normalized_direction} stop is on the wrong side of entry"
            )

        if stop_distance_percent > self.max_stop_distance_percent:
            reasons.append(
                "stop distance "
                f"{stop_distance_percent:.2f}% exceeds "
                f"{self.max_stop_distance_percent:.2f}% limit"
            )

        if (
            stop_distance_atr is not None
            and stop_distance_atr > self.max_stop_distance_atr
        ):
            reasons.append(
                "stop distance "
                f"{stop_distance_atr:.2f} ATR exceeds "
                f"{self.max_stop_distance_atr:.2f} ATR limit"
            )

        (
            entry_zone_relation,
            entry_zone_distance_percent,
            zone_reason,
        ) = self._entry_zone_check(
            entry_price=entry_price,
            strategy=strategy,
            signal_metadata=signal_metadata,
        )

        if zone_reason is not None:
            reasons.append(zone_reason)

        valid = len(reasons) == 0

        if valid:
            summary = (
                "Risk geometry valid: stop distance "
                f"{stop_distance_percent:.2f}%"
            )

            if stop_distance_atr is not None:
                summary += f" / {stop_distance_atr:.2f} ATR"

            if entry_zone_distance_percent is not None:
                summary += (
                    f"; entry zone {entry_zone_relation} "
                    f"({entry_zone_distance_percent:.2f}%)."
                )
            else:
                summary += "."

        else:
            summary = (
                "Risk geometry invalid: "
                + "; ".join(reasons)
                + "."
            )

        return RiskGeometryAssessment(
            direction=normalized_direction,
            valid=valid,
            summary=summary,
            reasons=reasons,
            entry_price=entry_price,
            stop_loss=stop_loss,
            stop_distance=stop_distance,
            stop_distance_percent=stop_distance_percent,
            stop_distance_atr=stop_distance_atr,
            entry_zone_relation=entry_zone_relation,
            entry_zone_distance_percent=entry_zone_distance_percent,
        )

    def _entry_zone_check(
        self,
        *,
        entry_price: float,
        strategy: str | None,
        signal_metadata: dict[str, Any] | None,
    ) -> tuple[str, float | None, str | None]:
        metadata = signal_metadata or {}

        normalized_strategy = (
            strategy
            or ""
        ).strip().upper()

        zone_type = str(
            metadata.get(
                "setup_zone_type",
                "",
            )
        ).strip().upper()

        if normalized_strategy != "FVG" and zone_type != "FVG":
            return (
                "unavailable",
                None,
                None,
            )

        lower = metadata.get(
            "setup_zone_lower",
        )
        upper = metadata.get(
            "setup_zone_upper",
        )

        if lower is None or upper is None:
            return (
                "unavailable",
                None,
                None,
            )

        lower = float(lower)
        upper = float(upper)

        if lower > upper:
            lower, upper = upper, lower

        if lower <= entry_price <= upper:
            return (
                "inside",
                0.0,
                None,
            )

        if entry_price < lower:
            distance_percent = (
                (lower - entry_price)
                / entry_price
                * 100.0
            )
            relation = "below"

        else:
            distance_percent = (
                (entry_price - upper)
                / entry_price
                * 100.0
            )
            relation = "above"

        if distance_percent > self.max_entry_zone_distance_percent:
            return (
                relation,
                distance_percent,
                "FVG entry is "
                f"{relation} setup zone by "
                f"{distance_percent:.2f}%, limit is "
                f"{self.max_entry_zone_distance_percent:.2f}%"
            )

        return (
            relation,
            distance_percent,
            None,
        )

    @staticmethod
    def _invalid(
        *,
        direction: str,
        entry_price: float,
        stop_loss: float,
        stop_distance: float,
        stop_distance_percent: float,
        stop_distance_atr: float | None,
        entry_zone_relation: str,
        entry_zone_distance_percent: float | None,
        reason: str,
    ) -> RiskGeometryAssessment:
        return RiskGeometryAssessment(
            direction=direction,
            valid=False,
            summary=f"Risk geometry invalid: {reason}.",
            reasons=[reason],
            entry_price=entry_price,
            stop_loss=stop_loss,
            stop_distance=stop_distance,
            stop_distance_percent=stop_distance_percent,
            stop_distance_atr=stop_distance_atr,
            entry_zone_relation=entry_zone_relation,
            entry_zone_distance_percent=entry_zone_distance_percent,
        )
