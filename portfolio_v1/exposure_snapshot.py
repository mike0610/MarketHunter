"""
MarketHunter

Module:
Portfolio v1 Exposure Snapshot (Slice 4)

Responsibilities:
- Define PortfolioExposureSnapshot: an immutable composition of
  already-built ExposureAssessment objects into one structured
  snapshot.
- Define compose_exposure_snapshot(): a pure function that classifies
  the snapshot's overall state from its children's states and
  constructs the snapshot. It does not measure anything itself.

Non-goals (see portfolio_v1/assessment.py, query_service.py, domain.py
and project boundaries):
- No exposure math. assess_exposure() remains the sole owner of
  position_count/total_notional; this module never inspects those
  fields, only each assessment's `state`.
- No ResearchRepository/ResearchTrade access. This module accepts
  already-built ExposureAssessment objects only - it does not query,
  filter, or aggregate trades itself.
- No sizing or decision semantics. This module never produces a
  PositionSizingDecision or PortfolioDecision, and never reaches
  APPROVED/BLOCKED/PROCEED.
- No canonical universe. Which scopes belong in a snapshot (all
  trades, active only, spot only, ...) is entirely the caller's
  choice; this module has no opinion about it.
"""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_v1.domain import ExposureAssessment, ExposureState


@dataclass(frozen=True)
class PortfolioExposureSnapshot:
    """
    An immutable composition of one or more ExposureAssessment
    objects, with one truthfully-derived overall state.

    Deliberately carries no second `position_count`/`total_notional`
    at the snapshot level - this is a composition of measurements,
    not a second aggregation engine. Callers that need a combined
    number should read it from the individual `assessments`.
    """

    snapshot_id: str
    generated_at: str
    provenance: str
    assessments: tuple[ExposureAssessment, ...]
    state: ExposureState = ExposureState.UNKNOWN
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError(
                "PortfolioExposureSnapshot requires a stable snapshot_id"
            )

        if not self.generated_at:
            raise ValueError(
                "PortfolioExposureSnapshot requires generated_at"
            )

        if not self.provenance:
            raise ValueError(
                "PortfolioExposureSnapshot requires provenance"
            )

        if not isinstance(self.assessments, tuple):
            raise ValueError(
                "PortfolioExposureSnapshot.assessments must be a tuple"
            )

        if not self.assessments:
            raise ValueError(
                "PortfolioExposureSnapshot requires at least one "
                "ExposureAssessment - an empty snapshot has no "
                "well-defined semantics"
            )

        for item in self.assessments:
            if not isinstance(item, ExposureAssessment):
                raise ValueError(
                    "PortfolioExposureSnapshot.assessments may only "
                    "contain ExposureAssessment instances"
                )

        seen_ids: set[str] = set()

        for item in self.assessments:
            if item.assessment_id in seen_ids:
                raise ValueError(
                    "PortfolioExposureSnapshot cannot contain "
                    "duplicate assessment_id "
                    f"{item.assessment_id!r} - this makes the "
                    "snapshot ambiguous about which measurement it "
                    "refers to"
                )

            seen_ids.add(item.assessment_id)

        if (
            self.state in (ExposureState.UNKNOWN, ExposureState.NOT_APPLICABLE)
            and not self.reasons
        ):
            raise ValueError(
                "UNKNOWN/NOT_APPLICABLE PortfolioExposureSnapshot "
                "requires at least one reason"
            )

        if self.state == ExposureState.MEASURED and self.reasons:
            raise ValueError(
                "MEASURED PortfolioExposureSnapshot must not carry "
                "reasons - reasons imply uncertainty this snapshot "
                "does not have"
            )


def _describe_non_measured(
    assessments: tuple[ExposureAssessment, ...],
    target_state: ExposureState,
) -> str:
    offending = [
        item
        for item in assessments
        if item.state == target_state
    ]

    labels = ", ".join(
        f"{item.assessment_id}({item.scope})"
        for item in offending
    )

    return (
        f"{len(offending)} of {len(assessments)} assessment(s) are "
        f"{target_state.value}: {labels}"
    )


def compose_exposure_snapshot(
    assessments: list[ExposureAssessment],
    *,
    snapshot_id: str,
    generated_at: str,
    provenance: str,
) -> PortfolioExposureSnapshot:
    """
    Compose already-built ExposureAssessment objects into one
    PortfolioExposureSnapshot.

    Overall state:
    - any child UNKNOWN -> snapshot UNKNOWN (checked first: an
      inability to establish some facts outranks a merely
      not-applicable one when both are present);
    - else any child NOT_APPLICABLE -> snapshot NOT_APPLICABLE;
    - else (all children MEASURED) -> snapshot MEASURED.

    Never recomputes exposure, never touches ResearchTrade or
    ResearchRepository, never invents a numeric snapshot-level total.
    """

    ordered = tuple(assessments)

    states = {item.state for item in ordered}

    if ExposureState.UNKNOWN in states:
        return PortfolioExposureSnapshot(
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            provenance=provenance,
            assessments=ordered,
            state=ExposureState.UNKNOWN,
            reasons=(
                _describe_non_measured(
                    ordered,
                    ExposureState.UNKNOWN,
                ),
            ),
        )

    if ExposureState.NOT_APPLICABLE in states:
        return PortfolioExposureSnapshot(
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            provenance=provenance,
            assessments=ordered,
            state=ExposureState.NOT_APPLICABLE,
            reasons=(
                _describe_non_measured(
                    ordered,
                    ExposureState.NOT_APPLICABLE,
                ),
            ),
        )

    return PortfolioExposureSnapshot(
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        provenance=provenance,
        assessments=ordered,
        state=ExposureState.MEASURED,
    )
