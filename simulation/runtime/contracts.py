"""
MarketHunter

simulation/runtime/contracts.py

Module:
Demo / Paper Trade Simulator v1 - Slice 3 (automatic TEST-MODE
runtime foundation) - immutable runtime contracts only

Responsibilities:
- Define RuntimeCandidateEnvelope: an exact, frozen binding of one
  campaign + CandidateSnapshot + DispositionRecord. Runtime never
  rebuilds setup/rules from mutable source rows - only this frozen
  envelope is consumed.
- Define RuntimeSourceState, CandidateSourceRead, CandidateSource:
  a read-only candidate intake seam. No ack/update/delete/source
  mutation of any kind.
- Define ForwardObservationRead, ForwardObservationSource: a
  read-only forward-observation seam. AVAILABLE requires an exact
  MarketObservationEvidence; this seam never synthesizes OBSERVED_TIME.
- Define MechanicsEvaluationStatus, RuntimePlanKind,
  RuntimeTransitionPlan, MechanicsEvaluation,
  SimulationMechanicsEvaluator: an injected, version-bound mechanics
  evaluation seam that proposes a deterministic 0..N event plan or a
  shadow plan - never both, never neither for a READY evaluation.
- Define RuntimeOperationalStatus and EnvelopeCycleResult: the
  operational (never trading-truth) result of one runtime cycle
  step.

Non-goals (frozen by MH-DEMO-SIMULATOR-V1-SLICE3-ARCH-001 Council
decision):
- No concrete candidate adapter, market-data adapter, or mechanics
  provider. These are Protocol/ABC-style seams the caller implements
  and injects - this module defines contracts only.
- No wall clock, random, uuid, network, or scheduler usage anywhere.
  case_id, attempt_id, sequence, recorded TemporalFacts, observation
  references, and mechanics versions are never invented here - they
  are always caller/evaluator supplied.
- RuntimeOperationalStatus is operational health only - it is never
  Simulation truth and never influences persisted evidence.
- This module never imports simulation.storage, time_semantics
  directly, ResearchTrade, MarketDataService, or any Portfolio/Risk/
  TOP/Execution/exchange model - only simulation.foundation and
  stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from simulation.foundation import (
    CandidateSnapshot,
    DispositionRecord,
    MarketObservationEvidence,
    ShadowEvaluation,
    ShadowOutcome,
    SimulationCampaignReference,
    SimulationEvent,
    SimulationMechanicsPolicyReference,
)


class RuntimeSourceState(str, Enum):
    """
    Caller-supplied only. This module never computes availability or
    staleness from a wall-clock threshold.
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class MechanicsEvaluationStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class RuntimePlanKind(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    EVENTS = "EVENTS"
    SHADOW = "SHADOW"


class RuntimeOperationalStatus(str, Enum):
    """
    Operational health only - never Simulation truth.
    """

    PROGRESSED = "PROGRESSED"
    NO_CHANGE = "NO_CHANGE"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    BLOCKED_MECHANICS = "BLOCKED_MECHANICS"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_STALE = "SOURCE_STALE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RuntimeCandidateEnvelope:
    """
    Frozen binding of one campaign + CandidateSnapshot +
    DispositionRecord. campaign, snapshot.candidate, and the
    disposition's own campaign/snapshot must all agree exactly, or
    construction fails - the envelope can never carry a disposition
    for a different candidate or campaign than the one it wraps.
    """

    campaign: SimulationCampaignReference
    snapshot: CandidateSnapshot
    disposition: DispositionRecord

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(self.snapshot, CandidateSnapshot):
            raise TypeError("snapshot must be a CandidateSnapshot")

        if not isinstance(self.disposition, DispositionRecord):
            raise TypeError("disposition must be a DispositionRecord")

        if self.disposition.campaign != self.campaign:
            raise ValueError(
                "disposition.campaign must exactly match envelope.campaign"
            )

        if self.disposition.snapshot != self.snapshot:
            raise ValueError(
                "disposition.snapshot must exactly match envelope.snapshot"
            )


@dataclass(frozen=True, slots=True)
class CandidateSourceRead:
    """
    UNAVAILABLE/STALE carry no envelopes - a degraded source can
    never smuggle candidate data through a non-AVAILABLE state.
    """

    state: RuntimeSourceState
    envelopes: tuple[RuntimeCandidateEnvelope, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, RuntimeSourceState):
            raise TypeError("state must be a RuntimeSourceState")

        if not isinstance(self.envelopes, tuple) or not all(
            isinstance(item, RuntimeCandidateEnvelope) for item in self.envelopes
        ):
            raise TypeError(
                "envelopes must be a tuple of RuntimeCandidateEnvelope"
            )

        if self.state is not RuntimeSourceState.AVAILABLE and self.envelopes:
            raise ValueError(
                "envelopes must be empty unless state is AVAILABLE"
            )


class CandidateSource(Protocol):
    """
    Read-only candidate intake seam. No ack/update/delete/source
    mutation method exists on this protocol - a source may re-deliver
    identical envelopes freely.
    """

    def read_candidates(self) -> CandidateSourceRead: ...


@dataclass(frozen=True, slots=True)
class ForwardObservationRead:
    """
    AVAILABLE requires an exact MarketObservationEvidence; every
    other state forbids one - this seam never synthesizes OBSERVED_TIME.
    """

    state: RuntimeSourceState
    observation: MarketObservationEvidence | None

    def __post_init__(self) -> None:
        if not isinstance(self.state, RuntimeSourceState):
            raise TypeError("state must be a RuntimeSourceState")

        if self.observation is not None and not isinstance(
            self.observation, MarketObservationEvidence
        ):
            raise TypeError(
                "observation must be a MarketObservationEvidence or None"
            )

        if self.state is RuntimeSourceState.AVAILABLE:
            if self.observation is None:
                raise ValueError("AVAILABLE requires an observation")
        else:
            if self.observation is not None:
                raise ValueError(
                    f"{self.state.value} must not carry an observation"
                )


class ForwardObservationSource(Protocol):
    """
    Read-only forward-observation seam, bound to one envelope at a
    time. No mutation method exists on this protocol.
    """

    def read_observation(
        self, envelope: RuntimeCandidateEnvelope
    ) -> ForwardObservationRead: ...


@dataclass(frozen=True, slots=True)
class RuntimeTransitionPlan:
    """
    Immutable transition plan. EVENTS carries a nonempty ordered
    tuple[SimulationEvent, ...] only. SHADOW carries an existing
    ShadowEvaluation and an optional ShadowOutcome only. NO_CHANGE
    carries neither - there is never an admitted+shadow mixture.
    """

    kind: RuntimePlanKind
    events: tuple[SimulationEvent, ...] = ()
    shadow_evaluation: ShadowEvaluation | None = None
    shadow_outcome: ShadowOutcome | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimePlanKind):
            raise TypeError("kind must be a RuntimePlanKind")

        if not isinstance(self.events, tuple) or not all(
            isinstance(item, SimulationEvent) for item in self.events
        ):
            raise TypeError("events must be a tuple of SimulationEvent")

        if self.shadow_evaluation is not None and not isinstance(
            self.shadow_evaluation, ShadowEvaluation
        ):
            raise TypeError("shadow_evaluation must be a ShadowEvaluation or None")

        if self.shadow_outcome is not None and not isinstance(
            self.shadow_outcome, ShadowOutcome
        ):
            raise TypeError("shadow_outcome must be a ShadowOutcome or None")

        if self.kind is RuntimePlanKind.NO_CHANGE:
            if self.events or self.shadow_evaluation is not None or self.shadow_outcome is not None:
                raise ValueError("NO_CHANGE must not carry events or shadow records")
        elif self.kind is RuntimePlanKind.EVENTS:
            if not self.events:
                raise ValueError("EVENTS requires a nonempty events tuple")

            if self.shadow_evaluation is not None or self.shadow_outcome is not None:
                raise ValueError("EVENTS must not carry shadow records")
        else:
            if self.events:
                raise ValueError("SHADOW must not carry events")

            if self.shadow_evaluation is None:
                raise ValueError("SHADOW requires a shadow_evaluation")


@dataclass(frozen=True, slots=True)
class MechanicsEvaluation:
    """
    READY requires a plan. BLOCKED has no plan - a blocked evaluation
    can never smuggle a fabricated transition through.
    """

    status: MechanicsEvaluationStatus
    plan: RuntimeTransitionPlan | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, MechanicsEvaluationStatus):
            raise TypeError("status must be a MechanicsEvaluationStatus")

        if self.plan is not None and not isinstance(
            self.plan, RuntimeTransitionPlan
        ):
            raise TypeError("plan must be a RuntimeTransitionPlan or None")

        if self.status is MechanicsEvaluationStatus.READY and self.plan is None:
            raise ValueError("READY requires a plan")

        if self.status is MechanicsEvaluationStatus.BLOCKED and self.plan is not None:
            raise ValueError("BLOCKED must not carry a plan")


class SimulationMechanicsEvaluator(Protocol):
    """
    Injected, version-bound mechanics evaluation seam. mechanics_policy
    identifies the exact mechanics policy this evaluator is bound to;
    evaluate() proposes a deterministic plan from the frozen envelope,
    the exact persisted event lineage (empty for non-admitted
    candidates), and the exact eligible observation only.
    """

    @property
    def mechanics_policy(self) -> SimulationMechanicsPolicyReference: ...

    def evaluate(
        self,
        envelope: RuntimeCandidateEnvelope,
        persisted_events: tuple[SimulationEvent, ...],
        observation: MarketObservationEvidence,
    ) -> MechanicsEvaluation: ...


@dataclass(frozen=True, slots=True)
class EnvelopeCycleResult:
    """
    One runtime cycle step's operational result. envelope is None
    only when no envelope was ever available to process (the
    candidate source itself was UNAVAILABLE/STALE, before any
    envelope was read) - every other cause of SOURCE_UNAVAILABLE/
    SOURCE_STALE (e.g. the per-envelope forward-observation source)
    still carries the exact envelope it was evaluating. Only
    PROGRESSED carries the executed plan, and PROGRESSED always
    requires a known envelope.
    """

    envelope: RuntimeCandidateEnvelope | None
    status: RuntimeOperationalStatus
    plan: RuntimeTransitionPlan | None = None

    def __post_init__(self) -> None:
        if self.envelope is not None and not isinstance(
            self.envelope, RuntimeCandidateEnvelope
        ):
            raise TypeError("envelope must be a RuntimeCandidateEnvelope or None")

        if not isinstance(self.status, RuntimeOperationalStatus):
            raise TypeError("status must be a RuntimeOperationalStatus")

        if self.plan is not None and not isinstance(
            self.plan, RuntimeTransitionPlan
        ):
            raise TypeError("plan must be a RuntimeTransitionPlan or None")

        if self.status is RuntimeOperationalStatus.PROGRESSED:
            if self.plan is None:
                raise ValueError("PROGRESSED requires a plan")

            if self.envelope is None:
                raise ValueError("PROGRESSED requires a known envelope")
        else:
            if self.plan is not None:
                raise ValueError("only PROGRESSED carries a plan")
