"""
MarketHunter

simulation/foundation.py

Module:
Demo / Paper Trade Simulator v1 - TEST MODE - Slice 1 (immutable
provenance + forward-observation eligibility + deterministic replay
only)

Responsibilities:
- Define SimulationCampaignReference, SimulationCandidateReference,
  SimulationStrategyReference, SimulationPolicyReference,
  SimulationMechanicsPolicyReference: immutable, caller-supplied
  identity for the campaign, upstream candidate, strategy, selection/
  parameter/universe/regime policies, and mechanics policy.
- Define CandidateSnapshot: a frozen, exact-provenance snapshot of
  one candidate at detection time. No capital/sizing/notional
  semantics of any kind.
- Define SimulationDisposition and DispositionRecord: exactly four
  pre-entry dispositions with append-only, RECORDED_TIME-stamped
  provenance.
- Define MarketObservationReference and MarketObservationEvidence:
  exact, caller-supplied market-observation identity plus EVENT_TIME/
  OBSERVED_TIME/RECORDED_TIME evidence about the same observation.
- Define SimulationEventReference, SimulationEventType, and
  SimulationEvent: append-only simulation lifecycle events with
  explicit attempt/sequence lineage. SimulationFill is never
  ExecutionFill.
- Define assess_forward_observation_eligibility(): a pure function
  that proves a market observation may be used as forward evidence
  only when its governed OBSERVED_TIME is strictly after candidate
  detection under same-role semantics. EVENT_TIME alone never
  qualifies.
- Define assess_same_bar_sequence(): a pure function that proves
  same-bar competing outcome ordering only from explicit governed
  lineage evidence; otherwise fails closed to UNKNOWN.
- Define ShadowEvaluation and ShadowOutcome: explicitly counterfactual
  records for REJECTED/BLOCKED/NO_TRADE candidates that can never be
  represented as a real order or trade.
- Define replay_simulation_events(): a pure function that validates
  one case/campaign/candidate/attempt's explicit, contiguous event
  sequence against the frozen lifecycle transition table and derives
  a rebuildable final state - never a mutable truth.

Non-goals (frozen by MH-DEMO-SIMULATOR-V1-ARCH-001 Council decision):
- SIMULATION != LIVE. Zero real orders, real capital, account equity,
  approved exposure, live positions, or execution authority.
  SimulationFill is never ExecutionFill.
- No reinterpretation of ResearchTrade as the canonical Simulator
  event log. No Research/Strategy/Portfolio/Risk/TOP/Execution/
  exchange model imports or writes. No MarketDataService/candle
  loader dependency - every market observation is caller-supplied.
- ADMITTED_FOR_SIMULATION, REJECTED, BLOCKED, NO_TRADE are the only
  dispositions. SIMULATED_ENTERED is not a disposition - entry/fill
  is a later mechanics event.
- No hidden perfect-fill, zero-fee, or zero-slippage default of any
  kind. Mechanics policy is identity/version only in this slice.
- No historical backtest, replay, or late-recovered observation may
  masquerade as forward evidence. A historical/late-recovered
  observation cannot retroactively qualify merely because its
  EVENT_TIME is after candidate detection.
- Same-bar competing entry/SL/TP ordering is UNKNOWN unless finer
  governed evidence proves sequence. No favorable-path selection.
- v1 is exactly one attempt per candidate/campaign case. Re-entry/
  retry requires a later governed lineage extension.
- Shadow records are explicitly counterfactual/no-order/no-trade and
  can never be represented as, or promoted into, a real trade.
- No significance, sample-size, multiple-testing, or strategy
  promotion logic. No persistence, repository, API, UI, runtime,
  scheduler, network, wall clock, or random usage anywhere.
- No ResearchTrade.notional reference or inference of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from time_semantics.foundation import (
    LineageRelation,
    TemporalDisposition,
    TemporalFact,
    TemporalReference,
    TemporalRelation,
    TemporalRole,
    assess_temporal_relation,
)


class SimulationDisposition(str, Enum):
    ADMITTED_FOR_SIMULATION = "ADMITTED_FOR_SIMULATION"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    NO_TRADE = "NO_TRADE"


class SimulationEventType(str, Enum):
    WAITING_ENTRY = "WAITING_ENTRY"
    SIMULATED_FILL = "SIMULATED_FILL"
    ACTIVE = "ACTIVE"
    TERMINAL_OUTCOME = "TERMINAL_OUTCOME"
    CENSORED = "CENSORED"
    UNKNOWN = "UNKNOWN"


class ForwardEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class ForwardEligibilityReason(str, Enum):
    CANDIDATE_DETECTION_NOT_USABLE = "CANDIDATE_DETECTION_NOT_USABLE"
    OBSERVATION_NOT_AFTER_DETECTION = "OBSERVATION_NOT_AFTER_DETECTION"
    OBSERVATION_TEMPORAL_UNKNOWN = "OBSERVATION_TEMPORAL_UNKNOWN"
    OBSERVATION_TEMPORAL_CONFLICT = "OBSERVATION_TEMPORAL_CONFLICT"
    OBSERVATION_NOT_COMPARABLE = "OBSERVATION_NOT_COMPARABLE"


class SameBarSequenceStatus(str, Enum):
    PROVEN = "PROVEN"
    UNKNOWN = "UNKNOWN"


class SameBarSequenceReason(str, Enum):
    DIRECT_LINEAGE_PRECEDENCE = "DIRECT_LINEAGE_PRECEDENCE"
    NO_GOVERNED_ORDERING_EVIDENCE = "NO_GOVERNED_ORDERING_EVIDENCE"


class SimulationReplayStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class SimulationReplayReason(str, Enum):
    EVENTS_EMPTY = "EVENTS_EMPTY"
    MULTIPLE_CASES_OR_ATTEMPTS = "MULTIPLE_CASES_OR_ATTEMPTS"
    DUPLICATE_SEQUENCE = "DUPLICATE_SEQUENCE"
    NON_CONTIGUOUS_SEQUENCE = "NON_CONTIGUOUS_SEQUENCE"
    INVALID_START_STATE = "INVALID_START_STATE"
    INVALID_TRANSITION = "INVALID_TRANSITION"


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_optional_nonblank(value: object, field_name: str) -> None:
    if value is not None:
        _require_nonblank(value, field_name)


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")

    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_positive_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")

    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_recorded_time_known(value: object, field_name: str) -> None:
    if not isinstance(value, TemporalFact):
        raise TypeError(f"{field_name} must be a TemporalFact")

    if value.role is not TemporalRole.RECORDED_TIME:
        raise ValueError(f"{field_name} must carry role RECORDED_TIME")

    if value.disposition is not TemporalDisposition.KNOWN:
        raise ValueError(f"{field_name} must carry disposition KNOWN")


@dataclass(frozen=True, slots=True)
class SimulationCampaignReference:
    campaign_id: str
    revision: int

    def __post_init__(self) -> None:
        _require_nonblank(self.campaign_id, "campaign_id")
        _require_positive_int(self.revision, "revision")


@dataclass(frozen=True, slots=True)
class SimulationCandidateReference:
    """
    Opaque, exact upstream identity. Never resolved, fetched, or
    interpreted by this module - the caller supplies the exact
    candidate provenance.
    """

    source_domain: str
    source_type: str
    source_id: str
    revision_or_version: str | None

    def __post_init__(self) -> None:
        _require_nonblank(self.source_domain, "source_domain")
        _require_nonblank(self.source_type, "source_type")
        _require_nonblank(self.source_id, "source_id")
        _require_optional_nonblank(
            self.revision_or_version, "revision_or_version"
        )


@dataclass(frozen=True, slots=True)
class SimulationStrategyReference:
    strategy_id: str
    version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.strategy_id, "strategy_id")
        _require_nonblank(self.version, "version")


@dataclass(frozen=True, slots=True)
class SimulationPolicyReference:
    """
    Explicit, versioned reference for a selection/mechanics/
    parameter/universe/regime policy, as needed by the caller.
    """

    policy_kind: str
    policy_id: str
    version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.policy_kind, "policy_kind")
        _require_nonblank(self.policy_id, "policy_id")
        _require_nonblank(self.version, "version")


@dataclass(frozen=True, slots=True)
class SimulationMechanicsPolicyReference:
    """
    Identity/version only in this slice - no fee/slippage/fill
    numeric defaults or provider behavior.
    """

    mechanics_policy_id: str
    version: str

    def __post_init__(self) -> None:
        _require_nonblank(self.mechanics_policy_id, "mechanics_policy_id")
        _require_nonblank(self.version, "version")


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """
    Frozen, exact-provenance snapshot of one candidate at detection
    time. Rules freeze here; later evidence may evaluate but never
    rewrite this snapshot. No capital/sizing/notional field exists
    on this contract.
    """

    candidate: SimulationCandidateReference
    strategy: SimulationStrategyReference
    instrument: str
    venue: str
    market: str
    timeframe: str
    direction: str
    entry_trigger: str
    entry: Decimal | None
    invalidation: Decimal | None
    targets: tuple[Decimal, ...]
    detection: TemporalFact
    policy_references: tuple[SimulationPolicyReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, SimulationCandidateReference):
            raise TypeError(
                "candidate must be a SimulationCandidateReference"
            )

        if not isinstance(self.strategy, SimulationStrategyReference):
            raise TypeError("strategy must be a SimulationStrategyReference")

        _require_nonblank(self.instrument, "instrument")
        _require_nonblank(self.venue, "venue")
        _require_nonblank(self.market, "market")
        _require_nonblank(self.timeframe, "timeframe")
        _require_nonblank(self.direction, "direction")
        _require_nonblank(self.entry_trigger, "entry_trigger")

        if self.entry is not None:
            _require_positive_decimal(self.entry, "entry")

        if self.invalidation is not None:
            _require_positive_decimal(self.invalidation, "invalidation")

        if not isinstance(self.targets, tuple) or not all(
            isinstance(item, Decimal) for item in self.targets
        ):
            raise TypeError("targets must be a tuple of Decimal")

        for target in self.targets:
            _require_positive_decimal(target, "targets item")

        if not isinstance(self.detection, TemporalFact):
            raise TypeError("detection must be a TemporalFact")

        if self.detection.role is not TemporalRole.OBSERVED_TIME:
            raise ValueError("detection must carry role OBSERVED_TIME")

        if self.detection.disposition is not TemporalDisposition.KNOWN:
            raise ValueError("detection must carry disposition KNOWN")

        if not isinstance(self.policy_references, tuple) or not all(
            isinstance(item, SimulationPolicyReference)
            for item in self.policy_references
        ):
            raise TypeError(
                "policy_references must be a tuple of "
                "SimulationPolicyReference"
            )


@dataclass(frozen=True, slots=True)
class DispositionRecord:
    """
    Append-only pre-entry disposition. A non-admitted disposition
    must carry at least one reason - fail-closed rejection is never
    silent.
    """

    campaign: SimulationCampaignReference
    snapshot: CandidateSnapshot
    disposition: SimulationDisposition
    reasons: tuple[str, ...]
    recorded_fact: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(self.snapshot, CandidateSnapshot):
            raise TypeError("snapshot must be a CandidateSnapshot")

        if not isinstance(self.disposition, SimulationDisposition):
            raise TypeError("disposition must be a SimulationDisposition")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, str) for item in self.reasons
        ):
            raise TypeError("reasons must be a tuple of str")

        for reason in self.reasons:
            _require_nonblank(reason, "reasons item")

        _require_recorded_time_known(self.recorded_fact, "recorded_fact")

        if (
            self.disposition is not SimulationDisposition.ADMITTED_FOR_SIMULATION
            and not self.reasons
        ):
            raise ValueError(
                "a non-admitted disposition requires at least one reason"
            )


@dataclass(frozen=True, slots=True)
class MarketObservationReference:
    source_kind: str
    source_id: str
    instrument: str
    granularity: str
    revision_or_hash: str

    def __post_init__(self) -> None:
        _require_nonblank(self.source_kind, "source_kind")
        _require_nonblank(self.source_id, "source_id")
        _require_nonblank(self.instrument, "instrument")
        _require_nonblank(self.granularity, "granularity")
        _require_nonblank(self.revision_or_hash, "revision_or_hash")


@dataclass(frozen=True, slots=True)
class MarketObservationEvidence:
    """
    Exact, caller-supplied EVENT_TIME/OBSERVED_TIME/RECORDED_TIME
    evidence about the same observation - the three facts must share
    one temporal reference.
    """

    reference: MarketObservationReference
    event_time: TemporalFact
    observed_time: TemporalFact
    recorded_time: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.reference, MarketObservationReference):
            raise TypeError(
                "reference must be a MarketObservationReference"
            )

        if not isinstance(self.event_time, TemporalFact):
            raise TypeError("event_time must be a TemporalFact")

        if not isinstance(self.observed_time, TemporalFact):
            raise TypeError("observed_time must be a TemporalFact")

        if not isinstance(self.recorded_time, TemporalFact):
            raise TypeError("recorded_time must be a TemporalFact")

        if self.event_time.role is not TemporalRole.EVENT_TIME:
            raise ValueError("event_time must carry role EVENT_TIME")

        if self.observed_time.role is not TemporalRole.OBSERVED_TIME:
            raise ValueError("observed_time must carry role OBSERVED_TIME")

        if self.recorded_time.role is not TemporalRole.RECORDED_TIME:
            raise ValueError("recorded_time must carry role RECORDED_TIME")

        if not (
            self.event_time.reference
            == self.observed_time.reference
            == self.recorded_time.reference
        ):
            raise ValueError(
                "event_time, observed_time, and recorded_time must share "
                "one temporal reference"
            )


@dataclass(frozen=True, slots=True)
class SimulationEventReference:
    case_id: str
    attempt_id: str
    sequence: int

    def __post_init__(self) -> None:
        _require_nonblank(self.case_id, "case_id")
        _require_nonblank(self.attempt_id, "attempt_id")
        _require_positive_int(self.sequence, "sequence")


_MECHANICS_AND_OBSERVATION_MANDATORY_EVENT_TYPES = (
    SimulationEventType.SIMULATED_FILL,
    SimulationEventType.ACTIVE,
    SimulationEventType.TERMINAL_OUTCOME,
)


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    """
    One append-only simulation lifecycle event. Mechanics and
    observation are mandatory for SIMULATED_FILL/ACTIVE/
    TERMINAL_OUTCOME. SimulationFill is never ExecutionFill - this
    module owns simulation-mechanics events only and never imports or
    aliases execution-domain fill types.
    """

    reference: SimulationEventReference
    campaign: SimulationCampaignReference
    candidate: SimulationCandidateReference
    event_type: SimulationEventType
    mechanics: SimulationMechanicsPolicyReference | None
    observation: MarketObservationEvidence | None
    recorded_fact: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.reference, SimulationEventReference):
            raise TypeError("reference must be a SimulationEventReference")

        if not isinstance(self.campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(self.candidate, SimulationCandidateReference):
            raise TypeError(
                "candidate must be a SimulationCandidateReference"
            )

        if not isinstance(self.event_type, SimulationEventType):
            raise TypeError("event_type must be a SimulationEventType")

        if self.mechanics is not None and not isinstance(
            self.mechanics, SimulationMechanicsPolicyReference
        ):
            raise TypeError(
                "mechanics must be a SimulationMechanicsPolicyReference "
                "or None"
            )

        if self.observation is not None and not isinstance(
            self.observation, MarketObservationEvidence
        ):
            raise TypeError(
                "observation must be a MarketObservationEvidence or None"
            )

        _require_recorded_time_known(self.recorded_fact, "recorded_fact")

        if self.event_type in _MECHANICS_AND_OBSERVATION_MANDATORY_EVENT_TYPES:
            if self.mechanics is None:
                raise ValueError(
                    f"{self.event_type.value} requires a mechanics reference"
                )

            if self.observation is None:
                raise ValueError(
                    f"{self.event_type.value} requires observation evidence"
                )


@dataclass(frozen=True, slots=True)
class ForwardEligibilityAssessment:
    status: ForwardEligibilityStatus
    reasons: tuple[ForwardEligibilityReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ForwardEligibilityStatus):
            raise TypeError("status must be a ForwardEligibilityStatus")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, ForwardEligibilityReason)
            for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of ForwardEligibilityReason"
            )

        if (
            self.status is ForwardEligibilityStatus.NOT_ELIGIBLE
            and not self.reasons
        ):
            raise ValueError("NOT_ELIGIBLE requires at least one reason")

        if self.status is ForwardEligibilityStatus.ELIGIBLE and self.reasons:
            raise ValueError(
                "ELIGIBLE must not carry reasons - reasons imply this "
                "observation is not actually eligible"
            )


def assess_forward_observation_eligibility(
    candidate_detection: TemporalFact,
    observation_evidence: MarketObservationEvidence,
) -> ForwardEligibilityAssessment:
    """
    A market observation may be used as forward evidence only when
    its governed OBSERVED_TIME is strictly after candidate detection
    under same-role clock comparison. EVENT_TIME is never read by
    this function - a historical/late-recovered observation can never
    qualify merely because its EVENT_TIME is after detection.
    """

    if not isinstance(candidate_detection, TemporalFact):
        raise TypeError("candidate_detection must be a TemporalFact")

    if not isinstance(observation_evidence, MarketObservationEvidence):
        raise TypeError(
            "observation_evidence must be a MarketObservationEvidence"
        )

    if (
        candidate_detection.role is not TemporalRole.OBSERVED_TIME
        or candidate_detection.disposition is not TemporalDisposition.KNOWN
    ):
        return ForwardEligibilityAssessment(
            status=ForwardEligibilityStatus.NOT_ELIGIBLE,
            reasons=(ForwardEligibilityReason.CANDIDATE_DETECTION_NOT_USABLE,),
        )

    assessment = assess_temporal_relation(
        candidate_detection, observation_evidence.observed_time
    )

    if assessment.relation is TemporalRelation.BEFORE:
        return ForwardEligibilityAssessment(
            status=ForwardEligibilityStatus.ELIGIBLE, reasons=()
        )

    if assessment.relation in (TemporalRelation.AFTER, TemporalRelation.EQUAL):
        reason = ForwardEligibilityReason.OBSERVATION_NOT_AFTER_DETECTION
    elif assessment.relation is TemporalRelation.UNKNOWN:
        reason = ForwardEligibilityReason.OBSERVATION_TEMPORAL_UNKNOWN
    elif assessment.relation is TemporalRelation.CONFLICT:
        reason = ForwardEligibilityReason.OBSERVATION_TEMPORAL_CONFLICT
    else:
        reason = ForwardEligibilityReason.OBSERVATION_NOT_COMPARABLE

    return ForwardEligibilityAssessment(
        status=ForwardEligibilityStatus.NOT_ELIGIBLE, reasons=(reason,)
    )


@dataclass(frozen=True, slots=True)
class SameBarSequenceAssessment:
    status: SameBarSequenceStatus
    reasons: tuple[SameBarSequenceReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, SameBarSequenceStatus):
            raise TypeError("status must be a SameBarSequenceStatus")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, SameBarSequenceReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of SameBarSequenceReason"
            )

        if not self.reasons:
            raise ValueError(
                "reasons must contain at least one explanatory reason"
            )


def assess_same_bar_sequence(
    left: TemporalReference,
    right: TemporalReference,
    lineage_relations: tuple[LineageRelation, ...] = (),
) -> SameBarSequenceAssessment:
    """
    Competing same-bar outcomes (entry/SL/TP) are PROVEN ordered only
    when explicit direct lineage evidence exists between the exact
    references; otherwise this fails closed to UNKNOWN. Never selects
    a favorable order from an absence of evidence.
    """

    if not isinstance(left, TemporalReference):
        raise TypeError("left must be a TemporalReference")

    if not isinstance(right, TemporalReference):
        raise TypeError("right must be a TemporalReference")

    if not isinstance(lineage_relations, tuple) or not all(
        isinstance(item, LineageRelation) for item in lineage_relations
    ):
        raise TypeError(
            "lineage_relations must be a tuple of LineageRelation"
        )

    left_fact = TemporalFact(
        reference=left,
        role=TemporalRole.LINEAGE_ORDER,
        timestamp=None,
        disposition=TemporalDisposition.KNOWN,
    )
    right_fact = TemporalFact(
        reference=right,
        role=TemporalRole.LINEAGE_ORDER,
        timestamp=None,
        disposition=TemporalDisposition.KNOWN,
    )

    assessment = assess_temporal_relation(left_fact, right_fact, lineage_relations)

    if assessment.relation in (TemporalRelation.BEFORE, TemporalRelation.AFTER):
        return SameBarSequenceAssessment(
            status=SameBarSequenceStatus.PROVEN,
            reasons=(SameBarSequenceReason.DIRECT_LINEAGE_PRECEDENCE,),
        )

    return SameBarSequenceAssessment(
        status=SameBarSequenceStatus.UNKNOWN,
        reasons=(SameBarSequenceReason.NO_GOVERNED_ORDERING_EVIDENCE,),
    )


_SHADOW_ELIGIBLE_DISPOSITIONS = (
    SimulationDisposition.REJECTED,
    SimulationDisposition.BLOCKED,
    SimulationDisposition.NO_TRADE,
)

_SHADOW_OUTCOME_EVENT_TYPES = (
    SimulationEventType.TERMINAL_OUTCOME,
    SimulationEventType.CENSORED,
    SimulationEventType.UNKNOWN,
)


@dataclass(frozen=True, slots=True)
class ShadowEvaluation:
    """
    Explicitly counterfactual evaluation for a REJECTED/BLOCKED/
    NO_TRADE candidate. counterfactual/order_created/trade_created
    are fixed markers, never caller-tunable - a shadow evaluation can
    never be represented as a real order or trade.
    """

    campaign: SimulationCampaignReference
    snapshot: CandidateSnapshot
    disposition: SimulationDisposition
    counterfactual: bool
    order_created: bool
    trade_created: bool
    recorded_fact: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(self.snapshot, CandidateSnapshot):
            raise TypeError("snapshot must be a CandidateSnapshot")

        if not isinstance(self.disposition, SimulationDisposition):
            raise TypeError("disposition must be a SimulationDisposition")

        if self.disposition not in _SHADOW_ELIGIBLE_DISPOSITIONS:
            raise ValueError(
                "ShadowEvaluation is only valid for REJECTED, BLOCKED, "
                "or NO_TRADE dispositions"
            )

        if not isinstance(self.counterfactual, bool):
            raise TypeError("counterfactual must be a bool")

        if self.counterfactual is not True:
            raise ValueError("counterfactual must be True")

        if not isinstance(self.order_created, bool):
            raise TypeError("order_created must be a bool")

        if self.order_created is not False:
            raise ValueError("order_created must be False")

        if not isinstance(self.trade_created, bool):
            raise TypeError("trade_created must be a bool")

        if self.trade_created is not False:
            raise ValueError("trade_created must be False")

        _require_recorded_time_known(self.recorded_fact, "recorded_fact")


@dataclass(frozen=True, slots=True)
class ShadowOutcome:
    """
    A hypothetical outcome for a shadow evaluation. outcome_type is
    restricted to TERMINAL_OUTCOME/CENSORED/UNKNOWN - a shadow outcome
    can never carry WAITING_ENTRY/SIMULATED_FILL/ACTIVE, which would
    imply a real order/fill was created.
    """

    evaluation: ShadowEvaluation
    outcome_type: SimulationEventType
    observation: MarketObservationEvidence | None
    recorded_fact: TemporalFact

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation, ShadowEvaluation):
            raise TypeError("evaluation must be a ShadowEvaluation")

        if not isinstance(self.outcome_type, SimulationEventType):
            raise TypeError("outcome_type must be a SimulationEventType")

        if self.outcome_type not in _SHADOW_OUTCOME_EVENT_TYPES:
            raise ValueError(
                "outcome_type must be TERMINAL_OUTCOME, CENSORED, or UNKNOWN"
            )

        if self.observation is not None and not isinstance(
            self.observation, MarketObservationEvidence
        ):
            raise TypeError(
                "observation must be a MarketObservationEvidence or None"
            )

        _require_recorded_time_known(self.recorded_fact, "recorded_fact")


@dataclass(frozen=True, slots=True)
class SimulationReplayAssessment:
    status: SimulationReplayStatus
    reasons: tuple[SimulationReplayReason, ...]
    final_state: SimulationEventType | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SimulationReplayStatus):
            raise TypeError("status must be a SimulationReplayStatus")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, SimulationReplayReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of SimulationReplayReason"
            )

        if self.final_state is not None and not isinstance(
            self.final_state, SimulationEventType
        ):
            raise TypeError("final_state must be a SimulationEventType or None")

        if self.status is SimulationReplayStatus.INVALID:
            if not self.reasons:
                raise ValueError("INVALID requires at least one reason")

            if self.final_state is not None:
                raise ValueError("INVALID must not carry a final_state")

        if self.status is SimulationReplayStatus.VALID:
            if self.reasons:
                raise ValueError(
                    "VALID must not carry reasons - reasons imply this "
                    "replay is not actually valid"
                )

            if self.final_state is None:
                raise ValueError("VALID requires a final_state")


_REPLAY_TRANSITIONS: dict[SimulationEventType, tuple[SimulationEventType, ...]] = {
    SimulationEventType.WAITING_ENTRY: (
        SimulationEventType.SIMULATED_FILL,
        SimulationEventType.CENSORED,
        SimulationEventType.UNKNOWN,
    ),
    SimulationEventType.SIMULATED_FILL: (SimulationEventType.ACTIVE,),
    SimulationEventType.ACTIVE: (
        SimulationEventType.TERMINAL_OUTCOME,
        SimulationEventType.CENSORED,
        SimulationEventType.UNKNOWN,
    ),
}


def replay_simulation_events(
    events: tuple[SimulationEvent, ...],
) -> SimulationReplayAssessment:
    """
    Validate one case/campaign/candidate/attempt's explicit,
    contiguous event sequence and derive a rebuildable final state.
    Order is established strictly from each event's explicit
    reference.sequence - never from a timestamp, insertion order, or
    a latest/max selection. Invalid lineage fails closed.
    """

    if not isinstance(events, tuple) or not all(
        isinstance(item, SimulationEvent) for item in events
    ):
        raise TypeError("events must be a tuple of SimulationEvent")

    if not events:
        return SimulationReplayAssessment(
            status=SimulationReplayStatus.INVALID,
            reasons=(SimulationReplayReason.EVENTS_EMPTY,),
            final_state=None,
        )

    first = events[0]
    campaign = first.campaign
    candidate = first.candidate
    case_id = first.reference.case_id
    attempt_id = first.reference.attempt_id

    reasons: list[SimulationReplayReason] = []

    if any(
        event.campaign != campaign
        or event.candidate != candidate
        or event.reference.case_id != case_id
        or event.reference.attempt_id != attempt_id
        for event in events
    ):
        reasons.append(SimulationReplayReason.MULTIPLE_CASES_OR_ATTEMPTS)

    sequences = [event.reference.sequence for event in events]

    if len(sequences) != len(set(sequences)):
        reasons.append(SimulationReplayReason.DUPLICATE_SEQUENCE)

    if set(sequences) != set(range(1, len(events) + 1)):
        reasons.append(SimulationReplayReason.NON_CONTIGUOUS_SEQUENCE)

    if reasons:
        return SimulationReplayAssessment(
            status=SimulationReplayStatus.INVALID,
            reasons=tuple(reasons),
            final_state=None,
        )

    by_sequence = {event.reference.sequence: event for event in events}
    ordered = tuple(by_sequence[i] for i in range(1, len(events) + 1))

    if ordered[0].event_type is not SimulationEventType.WAITING_ENTRY:
        reasons.append(SimulationReplayReason.INVALID_START_STATE)

    for index in range(len(ordered) - 1):
        current_type = ordered[index].event_type
        next_type = ordered[index + 1].event_type
        allowed = _REPLAY_TRANSITIONS.get(current_type, ())

        if next_type not in allowed:
            reasons.append(SimulationReplayReason.INVALID_TRANSITION)
            break

    if reasons:
        return SimulationReplayAssessment(
            status=SimulationReplayStatus.INVALID,
            reasons=tuple(reasons),
            final_state=None,
        )

    return SimulationReplayAssessment(
        status=SimulationReplayStatus.VALID,
        reasons=(),
        final_state=ordered[-1].event_type,
    )
