"""
MarketHunter

Module:
Support / Resistance Zone Engine

Responsibilities:
- Detect simple support and resistance zones from candle pivots.
- Merge nearby pivot levels into price zones.
- Calculate RR target prices.
- Check whether a target is blocked by a support/resistance zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Literal


ZoneType = Literal[
    "support",
    "resistance",
]

Direction = Literal[
    "LONG",
    "SHORT",
]


@dataclass(slots=True)
class SupportResistanceZone:
    """
    Price zone built from one or more pivot touches.
    """

    zone_type: ZoneType

    lower: float
    upper: float
    center: float

    touches: int
    strength: float

    last_touched_at: datetime | None

    distance_to_entry_percent: float | None = None
    distance_to_target_percent: float | None = None


@dataclass(slots=True)
class TargetZoneAssessment:
    """
    Result of checking whether an RR target is clean or blocked.
    """

    direction: Direction

    entry_price: float
    stop_loss: float

    target_rr: float
    target_price: float

    target_clear: bool

    zones: list[SupportResistanceZone]
    blocking_zones: list[SupportResistanceZone]

    summary: str


@dataclass(slots=True)
class _Pivot:
    """
    Internal pivot representation.
    """

    zone_type: ZoneType
    price: float
    touched_at: datetime | None


class SupportResistanceDetector:
    """
    Detect support and resistance zones using local pivot highs/lows.

    This is intentionally simple and deterministic:
    - pivot high -> resistance candidate
    - pivot low -> support candidate
    - nearby pivots are merged into zones
    """

    def __init__(
        self,
        *,
        lookback_candles: int = 160,
        pivot_window: int = 2,
        min_touches: int = 1,
        range_tolerance_multiplier: float = 0.35,
        min_zone_width_percent: float = 0.10,
        max_zones: int = 12,
    ) -> None:
        if lookback_candles < 20:
            raise ValueError(
                "lookback_candles must be at least 20."
            )

        if pivot_window < 1:
            raise ValueError(
                "pivot_window must be at least 1."
            )

        if min_touches < 1:
            raise ValueError(
                "min_touches must be at least 1."
            )

        if range_tolerance_multiplier <= 0:
            raise ValueError(
                "range_tolerance_multiplier must be positive."
            )

        if min_zone_width_percent <= 0:
            raise ValueError(
                "min_zone_width_percent must be positive."
            )

        if max_zones < 1:
            raise ValueError(
                "max_zones must be at least 1."
            )

        self.lookback_candles = lookback_candles
        self.pivot_window = pivot_window
        self.min_touches = min_touches
        self.range_tolerance_multiplier = (
            range_tolerance_multiplier
        )
        self.min_zone_width_percent = min_zone_width_percent
        self.max_zones = max_zones

    def detect(
        self,
        candles: list[object],
        *,
        entry_price: float | None = None,
        target_price: float | None = None,
    ) -> list[SupportResistanceZone]:
        """
        Detect support and resistance zones from candles.
        """

        selected_candles = candles[-self.lookback_candles:]

        if len(selected_candles) < (
            self.pivot_window * 2 + 1
        ):
            return []

        tolerance = self._calculate_tolerance(
            selected_candles,
        )

        pivots = self._detect_pivots(
            selected_candles,
        )

        zones = self._merge_pivots(
            pivots=pivots,
            tolerance=tolerance,
        )

        zones = [
            zone
            for zone in zones
            if zone.touches >= self.min_touches
        ]

        if entry_price is not None:
            zones = [
                self._with_entry_distance(
                    zone=zone,
                    entry_price=entry_price,
                )
                for zone in zones
            ]

        if target_price is not None:
            zones = [
                self._with_target_distance(
                    zone=zone,
                    target_price=target_price,
                )
                for zone in zones
            ]

        zones.sort(
            key=lambda zone: (
                zone.strength,
                zone.touches,
            ),
            reverse=True,
        )

        return zones[: self.max_zones]

    def assess_rr_target(
        self,
        candles: list[object],
        *,
        direction: str,
        entry_price: float,
        stop_loss: float,
        target_rr: float = 3.0,
    ) -> TargetZoneAssessment:
        """
        Calculate target for given RR and check if it is blocked.
        """

        normalized_direction = normalize_direction(
            direction,
        )

        target_price = calculate_rr_target(
            direction=normalized_direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_reward=target_rr,
        )

        zones = self.detect(
            candles,
            entry_price=entry_price,
            target_price=target_price,
        )

        blocking_zones = find_blocking_zones(
            zones=zones,
            direction=normalized_direction,
            entry_price=entry_price,
            target_price=target_price,
        )

        target_clear = len(blocking_zones) == 0

        if target_clear:
            summary = (
                f"TP 1:{target_rr:g} looks clear: no blocking "
                "support/resistance zone before target."
            )
        else:
            nearest_zone = blocking_zones[0]
            summary = (
                f"TP 1:{target_rr:g} is blocked by "
                f"{nearest_zone.zone_type} zone around "
                f"{nearest_zone.center:.8f}."
            )

        return TargetZoneAssessment(
            direction=normalized_direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_rr=target_rr,
            target_price=target_price,
            target_clear=target_clear,
            zones=zones,
            blocking_zones=blocking_zones,
            summary=summary,
        )

    def _calculate_tolerance(
        self,
        candles: list[object],
    ) -> float:
        """
        Calculate grouping tolerance from average candle range.
        """

        ranges = [
            max(
                0.0,
                float(getattr(candle, "high"))
                - float(getattr(candle, "low")),
            )
            for candle in candles
        ]

        closes = [
            float(getattr(candle, "close"))
            for candle in candles
        ]

        average_range = mean(ranges)
        average_close = mean(closes)

        range_based_tolerance = (
            average_range
            * self.range_tolerance_multiplier
        )

        minimum_tolerance = (
            average_close
            * self.min_zone_width_percent
            / 100
        )

        return max(
            range_based_tolerance,
            minimum_tolerance,
        )

    def _detect_pivots(
        self,
        candles: list[object],
    ) -> list[_Pivot]:
        """
        Detect local pivot highs and lows.
        """

        pivots: list[_Pivot] = []

        window = self.pivot_window

        for index in range(
            window,
            len(candles) - window,
        ):
            candle = candles[index]

            current_high = float(
                getattr(
                    candle,
                    "high",
                )
            )

            current_low = float(
                getattr(
                    candle,
                    "low",
                )
            )

            neighbors = (
                candles[index - window:index]
                + candles[index + 1:index + window + 1]
            )

            neighbor_highs = [
                float(getattr(item, "high"))
                for item in neighbors
            ]

            neighbor_lows = [
                float(getattr(item, "low"))
                for item in neighbors
            ]

            touched_at = getattr(
                candle,
                "open_time",
                None,
            )

            if current_high > max(neighbor_highs):
                pivots.append(
                    _Pivot(
                        zone_type="resistance",
                        price=current_high,
                        touched_at=touched_at,
                    )
                )

            if current_low < min(neighbor_lows):
                pivots.append(
                    _Pivot(
                        zone_type="support",
                        price=current_low,
                        touched_at=touched_at,
                    )
                )

        return pivots

    def _merge_pivots(
        self,
        *,
        pivots: list[_Pivot],
        tolerance: float,
    ) -> list[SupportResistanceZone]:
        """
        Merge nearby pivots of the same type into zones.
        """

        groups: list[dict[str, object]] = []

        for pivot in pivots:
            matched_group: dict[str, object] | None = None

            for group in groups:
                if group["zone_type"] != pivot.zone_type:
                    continue

                group_center = float(
                    group["center"]
                )

                if abs(pivot.price - group_center) <= tolerance:
                    matched_group = group
                    break

            if matched_group is None:
                groups.append(
                    {
                        "zone_type": pivot.zone_type,
                        "prices": [pivot.price],
                        "center": pivot.price,
                        "last_touched_at": pivot.touched_at,
                    }
                )
                continue

            prices = list(
                matched_group["prices"]
            )

            prices.append(
                pivot.price,
            )

            matched_group["prices"] = prices
            matched_group["center"] = mean(prices)

            if pivot.touched_at is not None:
                matched_group["last_touched_at"] = (
                    pivot.touched_at
                )

        zones: list[SupportResistanceZone] = []

        for group in groups:
            prices = [
                float(price)
                for price in group["prices"]
            ]

            center = float(
                group["center"]
            )

            lower = min(prices) - tolerance
            upper = max(prices) + tolerance
            touches = len(prices)

            strength = min(
                100.0,
                25.0 + touches * 18.0,
            )

            zones.append(
                SupportResistanceZone(
                    zone_type=group["zone_type"],
                    lower=lower,
                    upper=upper,
                    center=center,
                    touches=touches,
                    strength=strength,
                    last_touched_at=group["last_touched_at"],
                )
            )

        return zones

    def _with_entry_distance(
        self,
        *,
        zone: SupportResistanceZone,
        entry_price: float,
    ) -> SupportResistanceZone:
        """
        Add distance from entry to zone center.
        """

        return SupportResistanceZone(
            zone_type=zone.zone_type,
            lower=zone.lower,
            upper=zone.upper,
            center=zone.center,
            touches=zone.touches,
            strength=zone.strength,
            last_touched_at=zone.last_touched_at,
            distance_to_entry_percent=percentage_distance(
                from_price=entry_price,
                to_price=zone.center,
            ),
            distance_to_target_percent=(
                zone.distance_to_target_percent
            ),
        )

    def _with_target_distance(
        self,
        *,
        zone: SupportResistanceZone,
        target_price: float,
    ) -> SupportResistanceZone:
        """
        Add distance from target to zone center.
        """

        return SupportResistanceZone(
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
            distance_to_target_percent=percentage_distance(
                from_price=target_price,
                to_price=zone.center,
            ),
        )


def normalize_direction(
    direction: str,
) -> Direction:
    """
    Normalize trade direction.
    """

    normalized = direction.strip().upper()

    if normalized not in {
        "LONG",
        "SHORT",
    }:
        raise ValueError(
            f"Unsupported direction: {direction}."
        )

    return normalized  # type: ignore[return-value]


def calculate_rr_target(
    *,
    direction: Direction,
    entry_price: float,
    stop_loss: float,
    risk_reward: float,
) -> float:
    """
    Calculate target price for a specific RR.
    """

    if entry_price <= 0:
        raise ValueError(
            "entry_price must be greater than zero."
        )

    if stop_loss <= 0:
        raise ValueError(
            "stop_loss must be greater than zero."
        )

    if risk_reward <= 0:
        raise ValueError(
            "risk_reward must be greater than zero."
        )

    if direction == "LONG":
        risk = entry_price - stop_loss

        if risk <= 0:
            raise ValueError(
                "LONG stop_loss must be below entry_price."
            )

        return entry_price + risk * risk_reward

    risk = stop_loss - entry_price

    if risk <= 0:
        raise ValueError(
            "SHORT stop_loss must be above entry_price."
        )

    return entry_price - risk * risk_reward


def percentage_distance(
    *,
    from_price: float,
    to_price: float,
) -> float:
    """
    Signed percent distance from one price to another.
    """

    if from_price == 0:
        return 0.0

    return (
        (to_price - from_price)
        / from_price
        * 100
    )


def find_blocking_zones(
    *,
    zones: list[SupportResistanceZone],
    direction: Direction,
    entry_price: float,
    target_price: float,
) -> list[SupportResistanceZone]:
    """
    Return zones located between entry and target.

    LONG targets are blocked by resistance zones.
    SHORT targets are blocked by support zones.
    """

    if direction == "LONG":
        blocking_zones = [
            zone
            for zone in zones
            if zone.zone_type == "resistance"
            and entry_price < zone.center <= target_price
        ]

        blocking_zones.sort(
            key=lambda zone: zone.center,
        )

        return blocking_zones

    blocking_zones = [
        zone
        for zone in zones
        if zone.zone_type == "support"
        and target_price <= zone.center < entry_price
    ]

    blocking_zones.sort(
        key=lambda zone: zone.center,
        reverse=True,
    )

    return blocking_zones