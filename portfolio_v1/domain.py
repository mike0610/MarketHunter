"""
MarketHunter

Module:
Portfolio v1 Domain

Responsibilities:
- Define the Portfolio v1 Slice 1 value objects: ExposureAssessment,
  PositionSizingDecision, PortfolioDecision.
- Enforce explicit MEASURED/UNKNOWN/NOT_APPLICABLE and
  APPROVED/BLOCKED/UNKNOWN/NOT_APPLICABLE states so nothing is
  silently reported as a real measurement or a real decision when the
  underlying data does not support one.

Non-goals (see project boundaries for this slice):
- No Order/Position lifecycle ownership (no order_id, no fill/open/
  close status - see the existing, unrelated `portfolio/` and
  `models/position.py` for that separate, unused legacy surface).
- No numeric Risk Engine policy (no max-risk %, leverage, drawdown,
  Kelly, allocation thresholds). Fields such as `requested_notional`
  are read-only references to values already produced upstream
  (e.g. ResearchTrade.notional) - this module never computes them.
- No persistence, API surface, or execution facts.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ExposureState(Enum):
    MEASURED = "MEASURED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SizingState(Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PortfolioOutcome(Enum):
    PROCEED = "PROCEED"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ExposureAssessment:
    """
    One exposure measurement over an existing, already-supported input
    scope (e.g. a market, a direction, or the whole book). Does not
    aggregate trades itself - the caller supplies whatever it already
    computed or already knows; this object only guarantees the result
    is internally consistent and honestly labelled.
    """

    assessment_id: str
    scope: str
    provenance: str
    generated_at: str
    state: ExposureState = ExposureState.UNKNOWN
    position_count: int | None = None
    total_notional: float | None = None

    def __post_init__(self) -> None:
        if not self.assessment_id:
            raise ValueError(
                "ExposureAssessment requires a stable assessment_id"
            )

        if not self.scope:
            raise ValueError(
                "ExposureAssessment requires an explicit scope"
            )

        if not self.provenance:
            raise ValueError(
                "ExposureAssessment requires provenance"
            )

        if not self.generated_at:
            raise ValueError(
                "ExposureAssessment requires generated_at"
            )

        if self.state == ExposureState.MEASURED:
            if self.position_count is None or self.total_notional is None:
                raise ValueError(
                    "MEASURED ExposureAssessment requires both "
                    "position_count and total_notional"
                )

            if self.position_count < 0:
                raise ValueError(
                    "ExposureAssessment.position_count cannot be negative"
                )

        elif (
            self.position_count is not None
            or self.total_notional is not None
        ):
            raise ValueError(
                "position_count/total_notional must stay unset unless "
                "state is MEASURED - do not report numbers for an "
                "UNKNOWN or NOT_APPLICABLE assessment"
            )


@dataclass(frozen=True)
class PositionSizingDecision:
    """
    Records whether a proposed position size is portfolio-approved,
    not what the size should be. `requested_notional` is a read-only
    reference to a value already produced upstream (e.g.
    ResearchTrade.notional from the existing signal pipeline);
    `capital_available` is left NOT_APPLICABLE until a real capital
    source exists somewhere in this codebase - there is none today.
    """

    decision_id: str
    candidate_reference: str
    provenance: str
    decided_at: str
    state: SizingState = SizingState.UNKNOWN
    requested_notional: float | None = None
    capital_available: float | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError(
                "PositionSizingDecision requires a stable decision_id"
            )

        if not self.candidate_reference:
            raise ValueError(
                "PositionSizingDecision requires a candidate_reference "
                "back to an existing signal/trade fact"
            )

        if not self.provenance:
            raise ValueError(
                "PositionSizingDecision requires provenance"
            )

        if not self.decided_at:
            raise ValueError(
                "PositionSizingDecision requires decided_at"
            )

        if self.state == SizingState.APPROVED and self.requested_notional is None:
            raise ValueError(
                "APPROVED PositionSizingDecision requires "
                "requested_notional"
            )

        if (
            self.state in (SizingState.UNKNOWN, SizingState.NOT_APPLICABLE)
            and not self.reasons
        ):
            raise ValueError(
                "UNKNOWN/NOT_APPLICABLE PositionSizingDecision requires "
                "at least one reason explaining why"
            )

        if self.state == SizingState.BLOCKED and not self.reasons:
            raise ValueError(
                "BLOCKED PositionSizingDecision requires at least one "
                "reason"
            )


@dataclass(frozen=True)
class PortfolioDecision:
    """
    Top-level Portfolio v1 decision record combining one
    ExposureAssessment and one PositionSizingDecision for a single
    candidate. `outcome` may only be PROCEED when both inputs are
    themselves in a positive/known state - an UNKNOWN or
    NOT_APPLICABLE input can never be silently upgraded into a
    PROCEED outcome.
    """

    decision_id: str
    candidate_reference: str
    provenance: str
    decided_at: str
    exposure: ExposureAssessment
    sizing: PositionSizingDecision
    outcome: PortfolioOutcome = PortfolioOutcome.UNKNOWN
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError(
                "PortfolioDecision requires a stable decision_id"
            )

        if not self.candidate_reference:
            raise ValueError(
                "PortfolioDecision requires a candidate_reference back "
                "to an existing signal/trade fact"
            )

        if not self.provenance:
            raise ValueError(
                "PortfolioDecision requires provenance"
            )

        if not self.decided_at:
            raise ValueError(
                "PortfolioDecision requires decided_at"
            )

        if self.outcome != PortfolioOutcome.PROCEED and not self.reasons:
            raise ValueError(
                "Non-PROCEED PortfolioDecision requires at least one "
                "reason"
            )

        if self.outcome == PortfolioOutcome.PROCEED:
            if self.exposure.state != ExposureState.MEASURED:
                raise ValueError(
                    "PROCEED requires a MEASURED exposure assessment"
                )

            if self.sizing.state != SizingState.APPROVED:
                raise ValueError(
                    "PROCEED requires an APPROVED sizing decision"
                )
