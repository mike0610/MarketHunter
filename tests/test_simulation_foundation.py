"""
MarketHunter

Tests for Demo / Paper Trade Simulator v1 - TEST MODE - Slice 1
(simulation/foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from simulation.foundation import (
    CandidateSnapshot,
    DispositionRecord,
    ForwardEligibilityAssessment,
    ForwardEligibilityReason,
    ForwardEligibilityStatus,
    MarketObservationEvidence,
    MarketObservationReference,
    SameBarSequenceAssessment,
    SameBarSequenceReason,
    SameBarSequenceStatus,
    ShadowEvaluation,
    ShadowOutcome,
    SimulationCampaignReference,
    SimulationCandidateReference,
    SimulationDisposition,
    SimulationEvent,
    SimulationEventReference,
    SimulationEventType,
    SimulationMechanicsPolicyReference,
    SimulationPolicyReference,
    SimulationReasonReference,
    SimulationReplayAssessment,
    SimulationReplayReason,
    SimulationReplayStatus,
    SimulationStrategyReference,
    assess_forward_observation_eligibility,
    assess_same_bar_sequence,
    replay_simulation_events,
)
from time_semantics.foundation import (
    LineageRelation,
    TemporalDisposition,
    TemporalFact,
    TemporalReference,
    TemporalRole,
)

AWARE_EARLY = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
AWARE_LATE = datetime(2026, 8, 19, 11, 0, tzinfo=timezone.utc)


def make_campaign(**overrides) -> SimulationCampaignReference:
    kwargs = dict(campaign_id="campaign-1", revision=1)
    kwargs.update(overrides)
    return SimulationCampaignReference(**kwargs)


def make_candidate(**overrides) -> SimulationCandidateReference:
    kwargs = dict(
        source_domain="research",
        source_type="ResearchTrade",
        source_id="candidate-1",
        revision_or_version="1",
    )
    kwargs.update(overrides)
    return SimulationCandidateReference(**kwargs)


def make_strategy(**overrides) -> SimulationStrategyReference:
    kwargs = dict(strategy_id="strategy-1", version="1")
    kwargs.update(overrides)
    return SimulationStrategyReference(**kwargs)


def make_policy(**overrides) -> SimulationPolicyReference:
    kwargs = dict(policy_kind="selection", policy_id="policy-1", version="1")
    kwargs.update(overrides)
    return SimulationPolicyReference(**kwargs)


def make_mechanics(**overrides) -> SimulationMechanicsPolicyReference:
    kwargs = dict(mechanics_policy_id="mechanics-1", version="1")
    kwargs.update(overrides)
    return SimulationMechanicsPolicyReference(**kwargs)


def make_temporal_reference(**overrides) -> TemporalReference:
    kwargs = dict(
        reference_kind="market_observation", reference_id="obs-1", revision_or_version=None
    )
    kwargs.update(overrides)
    return TemporalReference(**kwargs)


def make_temporal_fact(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=make_temporal_reference(),
        role=TemporalRole.OBSERVED_TIME,
        timestamp=AWARE_EARLY,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


def make_detection(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=make_temporal_reference(reference_id="detection-1"),
        role=TemporalRole.OBSERVED_TIME,
        timestamp=AWARE_EARLY,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


def make_recorded_fact(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=make_temporal_reference(reference_id="record-1"),
        role=TemporalRole.RECORDED_TIME,
        timestamp=AWARE_EARLY,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


def make_reason_reference(**overrides) -> SimulationReasonReference:
    kwargs = dict(
        reason_namespace="simulation.eligibility",
        reason_code="LIQUIDITY_INSUFFICIENT",
        reason_version="1",
    )
    kwargs.update(overrides)
    return SimulationReasonReference(**kwargs)


def make_snapshot(**overrides) -> CandidateSnapshot:
    kwargs = dict(
        candidate=make_candidate(),
        strategy=make_strategy(),
        instrument="BTCUSDT",
        venue="binance",
        market="spot",
        timeframe="1h",
        direction="LONG",
        entry_trigger="BREAKOUT",
        entry=Decimal("100"),
        invalidation=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        detection=make_detection(),
        policy_references=(make_policy(),),
    )
    kwargs.update(overrides)
    return CandidateSnapshot(**kwargs)


def make_observation_reference(**overrides) -> MarketObservationReference:
    kwargs = dict(
        source_kind="exchange_rest",
        source_id="binance",
        instrument="BTCUSDT",
        granularity="1h",
        revision_or_hash="abc123",
    )
    kwargs.update(overrides)
    return MarketObservationReference(**kwargs)


def make_observation_evidence(**overrides) -> MarketObservationEvidence:
    shared_ref = overrides.pop("shared_reference", make_temporal_reference(reference_id="obs-evidence-1"))
    event_time = overrides.pop(
        "event_time",
        TemporalFact(
            reference=shared_ref,
            role=TemporalRole.EVENT_TIME,
            timestamp=AWARE_LATE,
            disposition=TemporalDisposition.KNOWN,
        ),
    )
    observed_time = overrides.pop(
        "observed_time",
        TemporalFact(
            reference=shared_ref,
            role=TemporalRole.OBSERVED_TIME,
            timestamp=AWARE_LATE,
            disposition=TemporalDisposition.KNOWN,
        ),
    )
    recorded_time = overrides.pop(
        "recorded_time",
        TemporalFact(
            reference=shared_ref,
            role=TemporalRole.RECORDED_TIME,
            timestamp=AWARE_LATE,
            disposition=TemporalDisposition.KNOWN,
        ),
    )
    kwargs = dict(
        reference=make_observation_reference(),
        event_time=event_time,
        observed_time=observed_time,
        recorded_time=recorded_time,
    )
    kwargs.update(overrides)
    return MarketObservationEvidence(**kwargs)


def make_event_reference(**overrides) -> SimulationEventReference:
    kwargs = dict(case_id="case-1", attempt_id="attempt-1", sequence=1)
    kwargs.update(overrides)
    return SimulationEventReference(**kwargs)


def make_event(**overrides) -> SimulationEvent:
    kwargs = dict(
        reference=make_event_reference(),
        campaign=make_campaign(),
        candidate=make_candidate(),
        event_type=SimulationEventType.WAITING_ENTRY,
        mechanics=None,
        observation=None,
        recorded_fact=make_recorded_fact(),
    )
    kwargs.update(overrides)
    return SimulationEvent(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in SimulationDisposition},
            {"ADMITTED_FOR_SIMULATION", "REJECTED", "BLOCKED", "NO_TRADE"},
        )

    def test_event_type_values(self) -> None:
        self.assertEqual(
            {m.value for m in SimulationEventType},
            {
                "WAITING_ENTRY",
                "SIMULATED_FILL",
                "ACTIVE",
                "TERMINAL_OUTCOME",
                "CENSORED",
                "UNKNOWN",
            },
        )

    def test_no_simulated_entered_disposition(self) -> None:
        self.assertNotIn(
            "SIMULATED_ENTERED", {m.value for m in SimulationDisposition}
        )


class SimulationCampaignReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        campaign = make_campaign()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            campaign.revision = 2  # type: ignore[misc]

    def test_blank_campaign_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_campaign(campaign_id="  ")

    def test_zero_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_campaign(revision=0)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_campaign(revision=True)  # type: ignore[arg-type]


class SimulationCandidateReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        candidate = make_candidate()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.source_id = "other"  # type: ignore[misc]

    def test_blank_source_domain_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_candidate(source_domain="")

    def test_optional_revision_none_accepted(self) -> None:
        candidate = make_candidate(revision_or_version=None)
        self.assertIsNone(candidate.revision_or_version)


class SimulationStrategyReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        strategy = make_strategy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            strategy.version = "2"  # type: ignore[misc]

    def test_blank_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_strategy(version=" ")


class SimulationPolicyReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        policy = make_policy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.policy_id = "other"  # type: ignore[misc]

    def test_blank_policy_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_policy(policy_kind="")


class SimulationMechanicsPolicyReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        mechanics = make_mechanics()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            mechanics.version = "2"  # type: ignore[misc]

    def test_blank_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_mechanics(mechanics_policy_id=" ")


class CandidateSnapshotTests(unittest.TestCase):
    def test_frozen(self) -> None:
        snapshot = make_snapshot()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.entry = Decimal("200")  # type: ignore[misc]

    def test_no_capital_sizing_notional_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(CandidateSnapshot)}
        for forbidden in ("capital", "notional", "position_size", "equity"):
            self.assertNotIn(forbidden, field_names)

    def test_entry_none_accepted(self) -> None:
        snapshot = make_snapshot(entry=None)
        self.assertIsNone(snapshot.entry)

    def test_invalidation_none_accepted(self) -> None:
        snapshot = make_snapshot(invalidation=None)
        self.assertIsNone(snapshot.invalidation)

    def test_empty_targets_accepted(self) -> None:
        snapshot = make_snapshot(targets=())
        self.assertEqual(snapshot.targets, ())

    def test_negative_entry_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(entry=Decimal("-1"))

    def test_zero_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(targets=(Decimal("0"),))

    def test_non_decimal_entry_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_snapshot(entry=100)  # type: ignore[arg-type]

    def test_detection_must_be_observed_time(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(
                detection=make_detection(role=TemporalRole.EVENT_TIME)
            )

    def test_detection_must_be_known(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(
                detection=make_detection(
                    disposition=TemporalDisposition.UNKNOWN, timestamp=None
                )
            )

    def test_blank_direction_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(direction="")

    def test_wrong_policy_references_element_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_snapshot(policy_references=("not-a-policy",))  # type: ignore[arg-type]


class DispositionRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = DispositionRecord(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
            reason_references=(),
            recorded_fact=make_recorded_fact(),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.reason_references = (make_reason_reference(),)  # type: ignore[misc]

    def test_admitted_with_no_reason_references_accepted(self) -> None:
        record = DispositionRecord(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
            reason_references=(),
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(record.reason_references, ())

    def test_reason_notes_default_empty(self) -> None:
        record = DispositionRecord(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
            reason_references=(),
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(record.reason_notes, ())

    def test_rejected_without_reason_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.REJECTED,
                reason_references=(),
                recorded_fact=make_recorded_fact(),
            )

    def test_rejected_with_only_notes_and_no_reference_rejected(self) -> None:
        # reason_notes is an annotation only - it can never satisfy the
        # non-admitted typed-reason requirement on its own.
        with self.assertRaises(ValueError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.REJECTED,
                reason_references=(),
                recorded_fact=make_recorded_fact(),
                reason_notes=("liquidity insufficient",),
            )

    def test_blocked_with_reason_reference_accepted(self) -> None:
        record = DispositionRecord(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.BLOCKED,
            reason_references=(make_reason_reference(),),
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(record.disposition, SimulationDisposition.BLOCKED)

    def test_blocked_with_reason_reference_and_notes_accepted(self) -> None:
        record = DispositionRecord(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.BLOCKED,
            reason_references=(make_reason_reference(),),
            recorded_fact=make_recorded_fact(),
            reason_notes=("manual review flagged low liquidity",),
        )
        self.assertEqual(
            record.reason_notes, ("manual review flagged low liquidity",)
        )

    def test_no_trade_without_reason_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.NO_TRADE,
                reason_references=(),
                recorded_fact=make_recorded_fact(),
            )

    def test_recorded_fact_must_be_recorded_time(self) -> None:
        with self.assertRaises(ValueError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
                reason_references=(),
                recorded_fact=make_detection(),
            )

    def test_wrong_reason_references_element_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.REJECTED,
                reason_references=("not-a-reason-reference",),  # type: ignore[arg-type]
                recorded_fact=make_recorded_fact(),
            )

    def test_blank_reason_note_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DispositionRecord(
                campaign=make_campaign(),
                snapshot=make_snapshot(),
                disposition=SimulationDisposition.REJECTED,
                reason_references=(make_reason_reference(),),
                recorded_fact=make_recorded_fact(),
                reason_notes=("  ",),
            )


class SimulationReasonReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_reason_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.reason_code = "OTHER"  # type: ignore[misc]

    def test_blank_namespace_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reason_reference(reason_namespace="  ")

    def test_blank_code_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reason_reference(reason_code="")

    def test_blank_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reason_reference(reason_version="")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_reason_reference(reason_code=123)  # type: ignore[arg-type]

    def test_distinct_codes_are_not_equal(self) -> None:
        self.assertNotEqual(
            make_reason_reference(reason_code="A"),
            make_reason_reference(reason_code="B"),
        )


class MarketObservationReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_observation_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.source_id = "other"  # type: ignore[misc]

    def test_blank_revision_or_hash_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_observation_reference(revision_or_hash=" ")


class MarketObservationEvidenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = make_observation_evidence()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.event_time = make_temporal_fact()  # type: ignore[misc]

    def test_wrong_event_time_role_rejected(self) -> None:
        shared_ref = make_temporal_reference(reference_id="bad-role")
        with self.assertRaises(ValueError):
            make_observation_evidence(
                shared_reference=shared_ref,
                event_time=TemporalFact(
                    reference=shared_ref,
                    role=TemporalRole.OBSERVED_TIME,
                    timestamp=AWARE_LATE,
                    disposition=TemporalDisposition.KNOWN,
                ),
            )

    def test_mismatched_reference_rejected(self) -> None:
        ref_a = make_temporal_reference(reference_id="ref-a")
        ref_b = make_temporal_reference(reference_id="ref-b")
        with self.assertRaises(ValueError):
            MarketObservationEvidence(
                reference=make_observation_reference(),
                event_time=TemporalFact(
                    reference=ref_a,
                    role=TemporalRole.EVENT_TIME,
                    timestamp=AWARE_LATE,
                    disposition=TemporalDisposition.KNOWN,
                ),
                observed_time=TemporalFact(
                    reference=ref_b,
                    role=TemporalRole.OBSERVED_TIME,
                    timestamp=AWARE_LATE,
                    disposition=TemporalDisposition.KNOWN,
                ),
                recorded_time=TemporalFact(
                    reference=ref_a,
                    role=TemporalRole.RECORDED_TIME,
                    timestamp=AWARE_LATE,
                    disposition=TemporalDisposition.KNOWN,
                ),
            )

    def test_matching_reference_accepted(self) -> None:
        evidence = make_observation_evidence()
        self.assertEqual(
            evidence.event_time.reference, evidence.observed_time.reference
        )


class SimulationEventReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_event_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.sequence = 2  # type: ignore[misc]

    def test_zero_sequence_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_event_reference(sequence=0)

    def test_negative_sequence_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_event_reference(sequence=-1)


class SimulationEventTests(unittest.TestCase):
    def test_frozen(self) -> None:
        event = make_event()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.event_type = SimulationEventType.ACTIVE  # type: ignore[misc]

    def test_waiting_entry_without_mechanics_or_observation_accepted(self) -> None:
        event = make_event(event_type=SimulationEventType.WAITING_ENTRY)
        self.assertIsNone(event.mechanics)
        self.assertIsNone(event.observation)

    def test_simulated_fill_requires_mechanics(self) -> None:
        with self.assertRaises(ValueError):
            make_event(
                event_type=SimulationEventType.SIMULATED_FILL,
                mechanics=None,
                observation=make_observation_evidence(),
            )

    def test_simulated_fill_requires_observation(self) -> None:
        with self.assertRaises(ValueError):
            make_event(
                event_type=SimulationEventType.SIMULATED_FILL,
                mechanics=make_mechanics(),
                observation=None,
            )

    def test_simulated_fill_with_both_accepted(self) -> None:
        event = make_event(
            event_type=SimulationEventType.SIMULATED_FILL,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
        )
        self.assertEqual(event.event_type, SimulationEventType.SIMULATED_FILL)

    def test_active_requires_mechanics_and_observation(self) -> None:
        with self.assertRaises(ValueError):
            make_event(event_type=SimulationEventType.ACTIVE)

    def test_terminal_outcome_requires_mechanics_and_observation(self) -> None:
        with self.assertRaises(ValueError):
            make_event(event_type=SimulationEventType.TERMINAL_OUTCOME)

    def test_censored_without_mechanics_or_observation_accepted(self) -> None:
        event = make_event(event_type=SimulationEventType.CENSORED)
        self.assertIsNone(event.mechanics)

    def test_unknown_without_mechanics_or_observation_accepted(self) -> None:
        event = make_event(event_type=SimulationEventType.UNKNOWN)
        self.assertIsNone(event.mechanics)

    def test_recorded_fact_must_be_recorded_time(self) -> None:
        with self.assertRaises(ValueError):
            make_event(recorded_fact=make_detection())

    def test_wrong_mechanics_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_event(
                event_type=SimulationEventType.WAITING_ENTRY,
                mechanics="not-mechanics",  # type: ignore[arg-type]
            )


class ForwardEligibilityAssessmentTests(unittest.TestCase):
    def test_not_eligible_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            ForwardEligibilityAssessment(
                status=ForwardEligibilityStatus.NOT_ELIGIBLE, reasons=()
            )

    def test_eligible_forbids_reasons(self) -> None:
        with self.assertRaises(ValueError):
            ForwardEligibilityAssessment(
                status=ForwardEligibilityStatus.ELIGIBLE,
                reasons=(ForwardEligibilityReason.OBSERVATION_TEMPORAL_UNKNOWN,),
            )


class AssessForwardObservationEligibilityTests(unittest.TestCase):
    def test_observation_after_detection_is_eligible(self) -> None:
        detection = make_detection(timestamp=AWARE_EARLY)
        evidence = make_observation_evidence(
            observed_time=TemporalFact(
                reference=make_temporal_reference(reference_id="obs-x"),
                role=TemporalRole.OBSERVED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            event_time=TemporalFact(
                reference=make_temporal_reference(reference_id="obs-x"),
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=make_temporal_reference(reference_id="obs-x"),
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.ELIGIBLE)

    def test_observation_before_detection_not_eligible(self) -> None:
        detection = make_detection(timestamp=AWARE_LATE)
        ref = make_temporal_reference(reference_id="obs-y")
        evidence = make_observation_evidence(
            shared_reference=ref,
            observed_time=TemporalFact(
                reference=ref,
                role=TemporalRole.OBSERVED_TIME,
                timestamp=AWARE_EARLY,
                disposition=TemporalDisposition.KNOWN,
            ),
            event_time=TemporalFact(
                reference=ref,
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_EARLY,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=ref,
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_EARLY,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.NOT_ELIGIBLE)
        self.assertIn(
            ForwardEligibilityReason.OBSERVATION_NOT_AFTER_DETECTION,
            result.reasons,
        )

    def test_event_time_alone_never_qualifies(self) -> None:
        # EVENT_TIME on the observation is set to a time strictly
        # AFTER detection, but OBSERVED_TIME is not after detection -
        # eligibility must be based on OBSERVED_TIME only.
        detection = make_detection(timestamp=AWARE_EARLY)
        ref = make_temporal_reference(reference_id="obs-z")
        evidence = make_observation_evidence(
            shared_reference=ref,
            event_time=TemporalFact(
                reference=ref,
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            observed_time=TemporalFact(
                reference=ref,
                role=TemporalRole.OBSERVED_TIME,
                timestamp=AWARE_EARLY,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=ref,
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.NOT_ELIGIBLE)

    def test_unknown_observed_disposition_fails_closed(self) -> None:
        detection = make_detection(timestamp=AWARE_EARLY)
        ref = make_temporal_reference(reference_id="obs-unknown")
        evidence = make_observation_evidence(
            shared_reference=ref,
            observed_time=TemporalFact(
                reference=ref,
                role=TemporalRole.OBSERVED_TIME,
                timestamp=None,
                disposition=TemporalDisposition.UNKNOWN,
            ),
            event_time=TemporalFact(
                reference=ref,
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=ref,
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.NOT_ELIGIBLE)
        self.assertIn(
            ForwardEligibilityReason.OBSERVATION_TEMPORAL_UNKNOWN, result.reasons
        )

    def test_conflict_observed_disposition_fails_closed(self) -> None:
        detection = make_detection(timestamp=AWARE_EARLY)
        ref = make_temporal_reference(reference_id="obs-conflict")
        evidence = make_observation_evidence(
            shared_reference=ref,
            observed_time=TemporalFact(
                reference=ref,
                role=TemporalRole.OBSERVED_TIME,
                timestamp=None,
                disposition=TemporalDisposition.CONFLICT,
            ),
            event_time=TemporalFact(
                reference=ref,
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=ref,
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.NOT_ELIGIBLE)
        self.assertIn(
            ForwardEligibilityReason.OBSERVATION_TEMPORAL_CONFLICT, result.reasons
        )

    def test_candidate_detection_not_usable_fails_closed(self) -> None:
        detection = make_detection(role=TemporalRole.EVENT_TIME)
        evidence = make_observation_evidence()

        result = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(result.status, ForwardEligibilityStatus.NOT_ELIGIBLE)
        self.assertIn(
            ForwardEligibilityReason.CANDIDATE_DETECTION_NOT_USABLE,
            result.reasons,
        )

    def test_wrong_candidate_detection_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_forward_observation_eligibility(
                "not-a-fact", make_observation_evidence()  # type: ignore[arg-type]
            )

    def test_wrong_observation_evidence_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_forward_observation_eligibility(
                make_detection(), "not-evidence"  # type: ignore[arg-type]
            )

    def test_deterministic_replay(self) -> None:
        detection = make_detection(timestamp=AWARE_EARLY)
        ref = make_temporal_reference(reference_id="obs-det")
        evidence = make_observation_evidence(
            shared_reference=ref,
            observed_time=TemporalFact(
                reference=ref,
                role=TemporalRole.OBSERVED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            event_time=TemporalFact(
                reference=ref,
                role=TemporalRole.EVENT_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                reference=ref,
                role=TemporalRole.RECORDED_TIME,
                timestamp=AWARE_LATE,
                disposition=TemporalDisposition.KNOWN,
            ),
        )

        first = assess_forward_observation_eligibility(detection, evidence)
        second = assess_forward_observation_eligibility(detection, evidence)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.reasons, second.reasons)


class AssessSameBarSequenceTests(unittest.TestCase):
    def test_no_evidence_is_unknown(self) -> None:
        left = make_temporal_reference(reference_id="entry-hit")
        right = make_temporal_reference(reference_id="sl-hit")

        result = assess_same_bar_sequence(left, right)
        self.assertEqual(result.status, SameBarSequenceStatus.UNKNOWN)
        self.assertIn(
            SameBarSequenceReason.NO_GOVERNED_ORDERING_EVIDENCE, result.reasons
        )

    def test_direct_lineage_proves_order(self) -> None:
        left = make_temporal_reference(reference_id="entry-hit")
        right = make_temporal_reference(reference_id="sl-hit")

        result = assess_same_bar_sequence(
            left, right, (LineageRelation(left, right),)
        )
        self.assertEqual(result.status, SameBarSequenceStatus.PROVEN)
        self.assertIn(
            SameBarSequenceReason.DIRECT_LINEAGE_PRECEDENCE, result.reasons
        )

    def test_contradictory_lineage_is_unknown_never_favorable(self) -> None:
        left = make_temporal_reference(reference_id="entry-hit")
        right = make_temporal_reference(reference_id="tp-hit")

        result = assess_same_bar_sequence(
            left,
            right,
            (
                LineageRelation(left, right),
                LineageRelation(right, left),
            ),
        )
        self.assertEqual(result.status, SameBarSequenceStatus.UNKNOWN)

    def test_wrong_left_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_same_bar_sequence(
                "not-a-reference", make_temporal_reference()  # type: ignore[arg-type]
            )

    def test_assessment_always_carries_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            SameBarSequenceAssessment(status=SameBarSequenceStatus.PROVEN, reasons=())


class ShadowEvaluationTests(unittest.TestCase):
    def _make(self, **overrides) -> ShadowEvaluation:
        kwargs = dict(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(),
        )
        kwargs.update(overrides)
        return ShadowEvaluation(**kwargs)

    def test_frozen(self) -> None:
        evaluation = self._make()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evaluation.counterfactual = False  # type: ignore[misc]

    def test_rejected_accepted(self) -> None:
        evaluation = self._make(disposition=SimulationDisposition.REJECTED)
        self.assertEqual(evaluation.disposition, SimulationDisposition.REJECTED)

    def test_blocked_accepted(self) -> None:
        evaluation = self._make(disposition=SimulationDisposition.BLOCKED)
        self.assertEqual(evaluation.disposition, SimulationDisposition.BLOCKED)

    def test_no_trade_accepted(self) -> None:
        evaluation = self._make(disposition=SimulationDisposition.NO_TRADE)
        self.assertEqual(evaluation.disposition, SimulationDisposition.NO_TRADE)

    def test_admitted_disposition_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._make(
                disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION
            )

    def test_counterfactual_false_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._make(counterfactual=False)

    def test_order_created_true_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._make(order_created=True)

    def test_trade_created_true_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._make(trade_created=True)


class ShadowOutcomeTests(unittest.TestCase):
    def _make_evaluation(self) -> ShadowEvaluation:
        return ShadowEvaluation(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(),
        )

    def test_frozen(self) -> None:
        outcome = ShadowOutcome(
            evaluation=self._make_evaluation(),
            outcome_type=SimulationEventType.CENSORED,
            observation=None,
            recorded_fact=make_recorded_fact(),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            outcome.outcome_type = SimulationEventType.UNKNOWN  # type: ignore[misc]

    def test_terminal_outcome_accepted(self) -> None:
        outcome = ShadowOutcome(
            evaluation=self._make_evaluation(),
            outcome_type=SimulationEventType.TERMINAL_OUTCOME,
            observation=make_observation_evidence(),
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(
            outcome.outcome_type, SimulationEventType.TERMINAL_OUTCOME
        )

    def test_censored_accepted(self) -> None:
        outcome = ShadowOutcome(
            evaluation=self._make_evaluation(),
            outcome_type=SimulationEventType.CENSORED,
            observation=None,
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(outcome.outcome_type, SimulationEventType.CENSORED)

    def test_unknown_accepted(self) -> None:
        outcome = ShadowOutcome(
            evaluation=self._make_evaluation(),
            outcome_type=SimulationEventType.UNKNOWN,
            observation=None,
            recorded_fact=make_recorded_fact(),
        )
        self.assertEqual(outcome.outcome_type, SimulationEventType.UNKNOWN)

    def test_waiting_entry_outcome_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ShadowOutcome(
                evaluation=self._make_evaluation(),
                outcome_type=SimulationEventType.WAITING_ENTRY,
                observation=None,
                recorded_fact=make_recorded_fact(),
            )

    def test_simulated_fill_outcome_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ShadowOutcome(
                evaluation=self._make_evaluation(),
                outcome_type=SimulationEventType.SIMULATED_FILL,
                observation=make_observation_evidence(),
                recorded_fact=make_recorded_fact(),
            )

    def test_active_outcome_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ShadowOutcome(
                evaluation=self._make_evaluation(),
                outcome_type=SimulationEventType.ACTIVE,
                observation=make_observation_evidence(),
                recorded_fact=make_recorded_fact(),
            )


class SimulationReplayAssessmentTests(unittest.TestCase):
    def test_invalid_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            SimulationReplayAssessment(
                status=SimulationReplayStatus.INVALID, reasons=(), final_state=None
            )

    def test_invalid_forbids_final_state(self) -> None:
        with self.assertRaises(ValueError):
            SimulationReplayAssessment(
                status=SimulationReplayStatus.INVALID,
                reasons=(SimulationReplayReason.EVENTS_EMPTY,),
                final_state=SimulationEventType.WAITING_ENTRY,
            )

    def test_valid_forbids_reasons(self) -> None:
        with self.assertRaises(ValueError):
            SimulationReplayAssessment(
                status=SimulationReplayStatus.VALID,
                reasons=(SimulationReplayReason.EVENTS_EMPTY,),
                final_state=SimulationEventType.WAITING_ENTRY,
            )

    def test_valid_requires_final_state(self) -> None:
        with self.assertRaises(ValueError):
            SimulationReplayAssessment(
                status=SimulationReplayStatus.VALID, reasons=(), final_state=None
            )


class ReplaySimulationEventsTests(unittest.TestCase):
    def _waiting_entry(self, sequence: int, case_id: str = "case-1", attempt_id: str = "attempt-1") -> SimulationEvent:
        return make_event(
            reference=make_event_reference(
                case_id=case_id, attempt_id=attempt_id, sequence=sequence
            ),
            event_type=SimulationEventType.WAITING_ENTRY,
        )

    def _filled(self, sequence: int, case_id: str = "case-1", attempt_id: str = "attempt-1") -> SimulationEvent:
        return make_event(
            reference=make_event_reference(
                case_id=case_id, attempt_id=attempt_id, sequence=sequence
            ),
            event_type=SimulationEventType.SIMULATED_FILL,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
        )

    def _active(self, sequence: int, case_id: str = "case-1", attempt_id: str = "attempt-1") -> SimulationEvent:
        return make_event(
            reference=make_event_reference(
                case_id=case_id, attempt_id=attempt_id, sequence=sequence
            ),
            event_type=SimulationEventType.ACTIVE,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
        )

    def _terminal(self, sequence: int, case_id: str = "case-1", attempt_id: str = "attempt-1") -> SimulationEvent:
        return make_event(
            reference=make_event_reference(
                case_id=case_id, attempt_id=attempt_id, sequence=sequence
            ),
            event_type=SimulationEventType.TERMINAL_OUTCOME,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
        )

    def test_wrong_events_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            replay_simulation_events([self._waiting_entry(1)])  # type: ignore[arg-type]

    def test_empty_events_invalid(self) -> None:
        result = replay_simulation_events(())
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(SimulationReplayReason.EVENTS_EMPTY, result.reasons)

    def test_single_waiting_entry_valid(self) -> None:
        result = replay_simulation_events((self._waiting_entry(1),))
        self.assertEqual(result.status, SimulationReplayStatus.VALID)
        self.assertEqual(result.final_state, SimulationEventType.WAITING_ENTRY)

    def test_full_admitted_lineage_valid(self) -> None:
        events = (
            self._waiting_entry(1),
            self._filled(2),
            self._active(3),
            self._terminal(4),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.VALID)
        self.assertEqual(result.final_state, SimulationEventType.TERMINAL_OUTCOME)

    def test_waiting_entry_to_censored_valid(self) -> None:
        censored = make_event(
            reference=make_event_reference(sequence=2),
            event_type=SimulationEventType.CENSORED,
        )
        events = (self._waiting_entry(1), censored)
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.VALID)
        self.assertEqual(result.final_state, SimulationEventType.CENSORED)

    def test_not_starting_with_waiting_entry_invalid(self) -> None:
        result = replay_simulation_events((self._filled(1),))
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.INVALID_START_STATE, result.reasons
        )

    def test_invalid_transition_fails_closed(self) -> None:
        events = (self._waiting_entry(1), self._active(2))
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.INVALID_TRANSITION, result.reasons
        )

    def test_terminal_outcome_cannot_be_followed(self) -> None:
        events = (
            self._waiting_entry(1),
            self._filled(2),
            self._active(3),
            self._terminal(4),
            self._waiting_entry(5),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.INVALID_TRANSITION, result.reasons
        )

    def test_duplicate_sequence_invalid(self) -> None:
        events = (
            self._waiting_entry(1),
            self._filled(1),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.DUPLICATE_SEQUENCE, result.reasons
        )

    def test_non_contiguous_sequence_invalid(self) -> None:
        events = (
            self._waiting_entry(1),
            self._filled(3),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.NON_CONTIGUOUS_SEQUENCE, result.reasons
        )

    def test_sequence_reordering_produces_valid_lineage(self) -> None:
        # Sequence 2 supplied before sequence 1 in the input tuple -
        # ordering must come from the explicit sequence field, not
        # insertion/input order.
        events = (self._filled(2), self._waiting_entry(1))
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.VALID)
        self.assertEqual(result.final_state, SimulationEventType.SIMULATED_FILL)

    def test_multiple_cases_invalid(self) -> None:
        events = (
            self._waiting_entry(1, case_id="case-1"),
            self._filled(2, case_id="case-2"),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.MULTIPLE_CASES_OR_ATTEMPTS, result.reasons
        )

    def test_multiple_attempts_invalid(self) -> None:
        events = (
            self._waiting_entry(1, attempt_id="attempt-1"),
            self._filled(2, attempt_id="attempt-2"),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.INVALID)
        self.assertIn(
            SimulationReplayReason.MULTIPLE_CASES_OR_ATTEMPTS, result.reasons
        )

    def test_deterministic_replay(self) -> None:
        events = (self._waiting_entry(1), self._filled(2))
        first = replay_simulation_events(events)
        second = replay_simulation_events(events)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(first.final_state, second.final_state)

    def test_does_not_mutate_inputs(self) -> None:
        events = (self._waiting_entry(1), self._filled(2))
        before = tuple(dataclasses.astuple(e) for e in events)

        replay_simulation_events(events)

        after = tuple(dataclasses.astuple(e) for e in events)
        self.assertEqual(before, after)

    def test_no_sorted_or_latest_used_to_order_events(self) -> None:
        # Feeding events far out of natural insertion order still
        # replays correctly purely from the explicit sequence field.
        events = (
            self._terminal(4),
            self._waiting_entry(1),
            self._active(3),
            self._filled(2),
        )
        result = replay_simulation_events(events)
        self.assertEqual(result.status, SimulationReplayStatus.VALID)
        self.assertEqual(result.final_state, SimulationEventType.TERMINAL_OUTCOME)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import ast
        from pathlib import Path

        import simulation.foundation as module

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self) -> set[str]:
        import ast

        imported: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def _referenced_names(self) -> set[str]:
        import ast

        tree = self._module_tree()
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only_plus_time_semantics(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "decimal",
            "enum",
            "time_semantics",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_time_semantics_import_is_the_named_narrow_set_only(self) -> None:
        import ast

        imported_from_time_semantics: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "time_semantics.foundation"
            ):
                for alias in node.names:
                    imported_from_time_semantics.add(alias.name)

        self.assertEqual(
            imported_from_time_semantics,
            {
                "LineageRelation",
                "TemporalDisposition",
                "TemporalFact",
                "TemporalReference",
                "TemporalRelation",
                "TemporalRole",
                "assess_temporal_relation",
            },
        )

    def test_no_source_domain_or_execution_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "research",
            "services",
            "exchange",
            "portfolio",
            "portfolio_v1",
            "risk",
            "trade_orchestration",
            "execution",
            "strategies",
            "models",
            "explainability",
            "audit_read_model",
            "manual_review",
            "api",
            "dashboard",
        ):
            self.assertNotIn(forbidden, imported)
            for name in imported:
                self.assertFalse(
                    name.startswith(forbidden + "."),
                    f"unexpected cross-domain import: {name}",
                )

    def test_no_source_domain_object_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "ResearchTrade",
            "ResearchRepository",
            "MarketDataService",
            "OrderIntent",
            "ExecutionOrder",
            "ExecutionFill",
            "TradeOrder",
            "TradeResult",
            "TradeExecutor",
            "PaperExecutor",
            "Position",
            "RiskResult",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_research_trade_notional_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("notional", referenced)

    def test_no_capital_equity_leverage_funding_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in ("capital", "equity", "leverage", "funding", "position_size"):
            self.assertNotIn(forbidden, referenced)

    def test_no_wall_clock_random_db_filesystem_network_scheduler(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("utcnow", referenced)
        self.assertNotIn("uuid4", referenced)

        imported = self._imported_names()
        for forbidden in (
            "sqlite3",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "fastapi",
            "httpx",
            "socket",
            "ntplib",
            "datetime",
            "random",
            "asyncio",
            "sched",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_persistence_api_ui_reports_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "APIRouter",
            "FastAPI",
            "Report",
            "Dashboard",
            "Repository",
            "Session",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_significance_or_promotion_logic(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "p_value",
            "significance",
            "sample_size",
            "promote",
            "promotion",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_sort_or_min_max_selector_calls(self) -> None:
        import ast

        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")

    def test_no_latest_or_current_selector_exported(self) -> None:
        import simulation.foundation as module

        for forbidden in ("latest", "current", "get_current", "get_latest"):
            self.assertFalse(hasattr(module, forbidden))

    def test_no_hidden_economic_default_fields(self) -> None:
        import simulation.foundation as module

        for cls_name in (
            "SimulationMechanicsPolicyReference",
            "SimulationEvent",
            "CandidateSnapshot",
        ):
            cls = getattr(module, cls_name)
            field_names = {f.name for f in dataclasses.fields(cls)}
            for forbidden in ("fee", "slippage", "fill_price", "commission"):
                self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
