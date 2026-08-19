"""
MarketHunter

Tests for Demo / Paper Trade Simulator v1 - Slice 2
(simulation/storage/repository.py).
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from simulation.foundation import (
    CandidateSnapshot,
    DispositionRecord,
    MarketObservationEvidence,
    MarketObservationReference,
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
    SimulationStrategyReference,
    replay_simulation_events,
)
from simulation.storage.repository import (
    SimulationConflictError,
    SimulationEvidenceBundle,
    SimulationEvidenceQuery,
    SimulationLineageError,
    SimulationPersistenceError,
    SimulationRepository,
    SimulationRepositoryError,
    SimulationSchemaVersionError,
)
from time_semantics.foundation import (
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


def make_snapshot(**overrides) -> CandidateSnapshot:
    kwargs = dict(
        candidate=make_candidate(),
        strategy=SimulationStrategyReference("strategy-1", "1"),
        instrument="BTCUSDT",
        venue="binance",
        market="spot",
        timeframe="1h",
        direction="LONG",
        entry_trigger="BREAKOUT",
        entry=Decimal("100"),
        invalidation=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        detection=TemporalFact(
            reference=TemporalReference("candidate", "candidate-1", None),
            role=TemporalRole.OBSERVED_TIME,
            timestamp=AWARE_EARLY,
            disposition=TemporalDisposition.KNOWN,
        ),
        policy_references=(SimulationPolicyReference("selection", "policy-1", "1"),),
    )
    kwargs.update(overrides)
    return CandidateSnapshot(**kwargs)


def make_reason_reference(**overrides) -> SimulationReasonReference:
    kwargs = dict(
        reason_namespace="simulation.eligibility",
        reason_code="LIQUIDITY_INSUFFICIENT",
        reason_version="1",
    )
    kwargs.update(overrides)
    return SimulationReasonReference(**kwargs)


def make_recorded_fact(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=TemporalReference("record", "record-1", None),
        role=TemporalRole.RECORDED_TIME,
        timestamp=AWARE_EARLY,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


def make_disposition(**overrides) -> DispositionRecord:
    kwargs = dict(
        campaign=make_campaign(),
        snapshot=make_snapshot(),
        disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
        reason_references=(),
        recorded_fact=make_recorded_fact(),
    )
    kwargs.update(overrides)
    return DispositionRecord(**kwargs)


def make_observation_evidence(**overrides) -> MarketObservationEvidence:
    shared_ref = overrides.pop(
        "shared_reference", TemporalReference("observation", "obs-1", None)
    )
    kwargs = dict(
        reference=MarketObservationReference(
            "exchange_rest", "binance", "BTCUSDT", "1h", "hash-1"
        ),
        event_time=TemporalFact(
            shared_ref, TemporalRole.EVENT_TIME, AWARE_LATE, TemporalDisposition.KNOWN
        ),
        observed_time=TemporalFact(
            shared_ref, TemporalRole.OBSERVED_TIME, AWARE_LATE, TemporalDisposition.KNOWN
        ),
        recorded_time=TemporalFact(
            shared_ref, TemporalRole.RECORDED_TIME, AWARE_LATE, TemporalDisposition.KNOWN
        ),
    )
    kwargs.update(overrides)
    return MarketObservationEvidence(**kwargs)


def make_mechanics(**overrides) -> SimulationMechanicsPolicyReference:
    kwargs = dict(mechanics_policy_id="mechanics-1", version="1")
    kwargs.update(overrides)
    return SimulationMechanicsPolicyReference(**kwargs)


def make_event(**overrides) -> SimulationEvent:
    kwargs = dict(
        reference=SimulationEventReference("case-1", "attempt-1", 1),
        campaign=make_campaign(),
        candidate=make_candidate(),
        event_type=SimulationEventType.WAITING_ENTRY,
        mechanics=None,
        observation=None,
        recorded_fact=make_recorded_fact(reference=TemporalReference("event", "e-1", None)),
    )
    kwargs.update(overrides)
    return SimulationEvent(**kwargs)


class RepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "simulation.db"
        self.repo = SimulationRepository(self.db_path)

    def tearDown(self) -> None:
        self.repo.connection.close()
        self._tmpdir.cleanup()


class SchemaTests(RepositoryTestCase):
    def test_creates_only_simulation_tables(self) -> None:
        cursor = self.repo.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        table_names = {row["name"] for row in cursor.fetchall()}
        self.assertEqual(
            table_names,
            {
                "simulation_schema_metadata",
                "simulation_candidates",
                "simulation_dispositions",
                "simulation_events",
                "simulation_shadow_evaluations",
                "simulation_shadow_outcomes",
            },
        )

    def test_no_research_or_other_domain_tables(self) -> None:
        cursor = self.repo.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        table_names = {row["name"] for row in cursor.fetchall()}
        for forbidden in (
            "research_trades",
            "scan_journal",
            "risk_result_records",
            "portfolio_decisions",
        ):
            self.assertNotIn(forbidden, table_names)

    def test_schema_version_recorded(self) -> None:
        cursor = self.repo.connection.execute(
            "SELECT schema_version FROM simulation_schema_metadata "
            "WHERE schema_key = 'simulation'"
        )
        row = cursor.fetchone()
        self.assertEqual(row["schema_version"], 1)

    def test_unsupported_schema_version_fails_closed(self) -> None:
        self.repo.connection.execute(
            "UPDATE simulation_schema_metadata SET schema_version = 2 "
            "WHERE schema_key = 'simulation'"
        )
        self.repo.connection.commit()

        with self.assertRaises(SimulationSchemaVersionError):
            self.repo.create_schema()

    def test_no_default_db_path(self) -> None:
        with self.assertRaises(TypeError):
            SimulationRepository()  # type: ignore[call-arg]

    def test_error_hierarchy(self) -> None:
        self.assertTrue(issubclass(SimulationConflictError, SimulationRepositoryError))
        self.assertTrue(issubclass(SimulationLineageError, SimulationRepositoryError))
        self.assertTrue(
            issubclass(SimulationPersistenceError, SimulationRepositoryError)
        )
        self.assertTrue(
            issubclass(SimulationSchemaVersionError, SimulationRepositoryError)
        )


class CandidateAppendGetTests(RepositoryTestCase):
    def test_absent_identity_inserts(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()

        result = self.repo.append_candidate(campaign, snapshot)
        self.assertEqual(result, snapshot)

    def test_get_missing_returns_none(self) -> None:
        result = self.repo.get_candidate(make_campaign(), make_candidate())
        self.assertIsNone(result)

    def test_exact_round_trip(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()

        self.repo.append_candidate(campaign, snapshot)
        reloaded = self.repo.get_candidate(campaign, snapshot.candidate)

        self.assertEqual(reloaded, snapshot)

    def test_decimal_round_trips_exactly(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot(
            entry=Decimal("100.12345678"),
            invalidation=Decimal("95.00000001"),
            targets=(Decimal("110.5"), Decimal("120.25")),
        )

        self.repo.append_candidate(campaign, snapshot)
        reloaded = self.repo.get_candidate(campaign, snapshot.candidate)

        self.assertEqual(reloaded.entry, Decimal("100.12345678"))
        self.assertEqual(reloaded.invalidation, Decimal("95.00000001"))
        self.assertEqual(reloaded.targets, (Decimal("110.5"), Decimal("120.25")))

    def test_none_entry_invalidation_round_trip(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot(entry=None, invalidation=None, targets=())

        self.repo.append_candidate(campaign, snapshot)
        reloaded = self.repo.get_candidate(campaign, snapshot.candidate)

        self.assertIsNone(reloaded.entry)
        self.assertIsNone(reloaded.invalidation)
        self.assertEqual(reloaded.targets, ())

    def test_optional_revision_none_round_trips(self) -> None:
        campaign = make_campaign()
        candidate = make_candidate(revision_or_version=None)
        snapshot = make_snapshot(candidate=candidate)

        self.repo.append_candidate(campaign, snapshot)
        reloaded = self.repo.get_candidate(campaign, candidate)

        self.assertIsNone(reloaded.candidate.revision_or_version)

    def test_null_and_non_null_revision_are_distinct_identities(self) -> None:
        campaign = make_campaign()
        candidate_null = make_candidate(source_id="dup", revision_or_version=None)
        candidate_value = make_candidate(source_id="dup", revision_or_version="1")
        snapshot_null = make_snapshot(candidate=candidate_null)
        snapshot_value = make_snapshot(candidate=candidate_value)

        self.repo.append_candidate(campaign, snapshot_null)
        self.repo.append_candidate(campaign, snapshot_value)

        self.assertEqual(
            self.repo.get_candidate(campaign, candidate_null), snapshot_null
        )
        self.assertEqual(
            self.repo.get_candidate(campaign, candidate_value), snapshot_value
        )

    def test_identical_duplicate_is_idempotent(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()

        first = self.repo.append_candidate(campaign, snapshot)
        second = self.repo.append_candidate(campaign, snapshot)

        self.assertEqual(first, second)

    def test_conflicting_duplicate_hard_fails(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        conflicting = make_snapshot(instrument="ETHUSDT")

        self.repo.append_candidate(campaign, snapshot)

        with self.assertRaises(SimulationConflictError):
            self.repo.append_candidate(campaign, conflicting)

        # no overwrite occurred
        self.assertEqual(
            self.repo.get_candidate(campaign, snapshot.candidate), snapshot
        )

    def test_policy_references_round_trip_ordered(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot(
            policy_references=(
                SimulationPolicyReference("selection", "p1", "1"),
                SimulationPolicyReference("universe", "p2", "1"),
            )
        )

        self.repo.append_candidate(campaign, snapshot)
        reloaded = self.repo.get_candidate(campaign, snapshot.candidate)

        self.assertEqual(reloaded.policy_references, snapshot.policy_references)

    def test_wrong_campaign_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.repo.append_candidate("not-a-campaign", make_snapshot())  # type: ignore[arg-type]

    def test_wrong_snapshot_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.repo.append_candidate(make_campaign(), "not-a-snapshot")  # type: ignore[arg-type]


class DispositionAppendGetTests(RepositoryTestCase):
    def test_candidate_must_exist_first(self) -> None:
        disposition = make_disposition()

        with self.assertRaises(SimulationLineageError):
            self.repo.append_disposition(disposition)

    def test_exact_round_trip(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)

        disposition = make_disposition(campaign=campaign, snapshot=snapshot)
        self.repo.append_disposition(disposition)
        reloaded = self.repo.get_disposition(campaign, snapshot.candidate)

        self.assertEqual(reloaded, disposition)

    def test_typed_reason_references_round_trip(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)

        disposition = make_disposition(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            reason_references=(make_reason_reference(),),
            reason_notes=("manual annotation",),
        )
        self.repo.append_disposition(disposition)
        reloaded = self.repo.get_disposition(campaign, snapshot.candidate)

        self.assertEqual(reloaded.reason_references, (make_reason_reference(),))
        self.assertEqual(reloaded.reason_notes, ("manual annotation",))

    def test_exactly_one_disposition_per_candidate_identical_idempotent(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)

        disposition = make_disposition(campaign=campaign, snapshot=snapshot)
        first = self.repo.append_disposition(disposition)
        second = self.repo.append_disposition(disposition)

        self.assertEqual(first, second)

    def test_conflicting_disposition_hard_fails(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)

        disposition = make_disposition(campaign=campaign, snapshot=snapshot)
        self.repo.append_disposition(disposition)

        conflicting = make_disposition(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            reason_references=(make_reason_reference(),),
        )

        with self.assertRaises(SimulationConflictError):
            self.repo.append_disposition(conflicting)

    def test_snapshot_mismatch_with_stored_candidate_rejected(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)

        mismatched_snapshot = make_snapshot(instrument="ETHUSDT")
        disposition = make_disposition(
            campaign=campaign, snapshot=mismatched_snapshot
        )

        with self.assertRaises(SimulationConflictError):
            self.repo.append_disposition(disposition)


class EventAppendGetTests(RepositoryTestCase):
    def _admit(self) -> tuple[SimulationCampaignReference, SimulationCandidateReference, CandidateSnapshot]:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(make_disposition(campaign=campaign, snapshot=snapshot))
        return campaign, snapshot.candidate, snapshot

    def test_event_requires_admitted_disposition(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(
            make_disposition(
                campaign=campaign,
                snapshot=snapshot,
                disposition=SimulationDisposition.REJECTED,
                reason_references=(make_reason_reference(),),
            )
        )

        event = make_event(campaign=campaign, candidate=snapshot.candidate)

        with self.assertRaises(SimulationLineageError):
            self.repo.append_event(event)

    def test_first_event_must_be_waiting_entry(self) -> None:
        campaign, candidate, _ = self._admit()

        bad_first = make_event(
            campaign=campaign,
            candidate=candidate,
            event_type=SimulationEventType.ACTIVE,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_event(bad_first)

    def test_valid_lineage_persists_and_reloads(self) -> None:
        campaign, candidate, _ = self._admit()

        ev1 = make_event(campaign=campaign, candidate=candidate)
        ev2 = make_event(
            campaign=campaign,
            candidate=candidate,
            reference=SimulationEventReference("case-1", "attempt-1", 2),
            event_type=SimulationEventType.SIMULATED_FILL,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("event", "e-2", None)
            ),
        )

        self.repo.append_event(ev1)
        self.repo.append_event(ev2)

        events = self.repo.get_case_events(campaign, candidate, "case-1", "attempt-1")
        self.assertEqual(events, (ev1, ev2))

    def test_reload_replay_equals_pre_persistence_replay(self) -> None:
        campaign, candidate, _ = self._admit()

        ev1 = make_event(campaign=campaign, candidate=candidate)
        ev2 = make_event(
            campaign=campaign,
            candidate=candidate,
            reference=SimulationEventReference("case-1", "attempt-1", 2),
            event_type=SimulationEventType.SIMULATED_FILL,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("event", "e-2", None)
            ),
        )
        self.repo.append_event(ev1)
        self.repo.append_event(ev2)

        expected = replay_simulation_events((ev1, ev2))
        events = self.repo.get_case_events(campaign, candidate, "case-1", "attempt-1")
        actual = replay_simulation_events(events)

        self.assertEqual(expected.status, actual.status)
        self.assertEqual(expected.final_state, actual.final_state)

    def test_invalid_transition_event_rejected(self) -> None:
        campaign, candidate, _ = self._admit()
        self.repo.append_event(make_event(campaign=campaign, candidate=candidate))

        bad_second = make_event(
            campaign=campaign,
            candidate=candidate,
            reference=SimulationEventReference("case-1", "attempt-1", 2),
            event_type=SimulationEventType.ACTIVE,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("event", "e-2", None)
            ),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_event(bad_second)

    def test_duplicate_sequence_conflict(self) -> None:
        campaign, candidate, _ = self._admit()
        self.repo.append_event(make_event(campaign=campaign, candidate=candidate))

        conflicting = make_event(
            campaign=campaign,
            candidate=candidate,
            event_type=SimulationEventType.CENSORED,
        )

        with self.assertRaises(SimulationConflictError):
            self.repo.append_event(conflicting)

    def test_identical_duplicate_event_idempotent(self) -> None:
        campaign, candidate, _ = self._admit()
        event = make_event(campaign=campaign, candidate=candidate)

        first = self.repo.append_event(event)
        second = self.repo.append_event(event)

        self.assertEqual(first, second)

    def test_gap_in_sequence_rejected(self) -> None:
        campaign, candidate, _ = self._admit()
        self.repo.append_event(make_event(campaign=campaign, candidate=candidate))

        gapped = make_event(
            campaign=campaign,
            candidate=candidate,
            reference=SimulationEventReference("case-1", "attempt-1", 3),
            event_type=SimulationEventType.SIMULATED_FILL,
            mechanics=make_mechanics(),
            observation=make_observation_evidence(),
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("event", "e-3", None)
            ),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_event(gapped)

    def test_second_attempt_rejected(self) -> None:
        campaign, candidate, _ = self._admit()
        self.repo.append_event(make_event(campaign=campaign, candidate=candidate))

        other_attempt = make_event(
            campaign=campaign,
            candidate=candidate,
            reference=SimulationEventReference("case-1", "attempt-2", 1),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_event(other_attempt)

    def test_no_repair_of_gaps_no_sequence_mutation(self) -> None:
        # Confirms there is no method available to patch/backfill a
        # missing sequence number - only append_event exists.
        self.assertFalse(hasattr(self.repo, "update_event"))
        self.assertFalse(hasattr(self.repo, "repair_sequence"))
        self.assertFalse(hasattr(self.repo, "delete_event"))

    def test_wrong_event_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.repo.append_event("not-an-event")  # type: ignore[arg-type]


class ShadowAppendGetTests(RepositoryTestCase):
    def _reject(self) -> tuple[SimulationCampaignReference, CandidateSnapshot]:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(
            make_disposition(
                campaign=campaign,
                snapshot=snapshot,
                disposition=SimulationDisposition.REJECTED,
                reason_references=(make_reason_reference(),),
            )
        )
        return campaign, snapshot

    def test_shadow_evaluation_requires_existing_non_admitted_disposition(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(make_disposition(campaign=campaign, snapshot=snapshot))

        evaluation = ShadowEvaluation(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_shadow_evaluation(evaluation)

    def test_shadow_evaluation_and_outcome_round_trip(self) -> None:
        campaign, snapshot = self._reject()

        evaluation = ShadowEvaluation(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )
        self.repo.append_shadow_evaluation(evaluation)

        outcome = ShadowOutcome(
            evaluation=evaluation,
            outcome_type=SimulationEventType.CENSORED,
            observation=None,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow-outcome", "o-1", None)
            ),
        )
        self.repo.append_shadow_outcome(outcome)

        reloaded_evaluation = self.repo.get_shadow_evaluation(
            campaign, snapshot.candidate
        )
        reloaded_outcome = self.repo.get_shadow_outcome(campaign, snapshot.candidate)

        self.assertEqual(reloaded_evaluation, evaluation)
        self.assertEqual(reloaded_outcome, outcome)

    def test_shadow_outcome_requires_matching_evaluation(self) -> None:
        campaign, snapshot = self._reject()

        evaluation = ShadowEvaluation(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )
        outcome = ShadowOutcome(
            evaluation=evaluation,
            outcome_type=SimulationEventType.UNKNOWN,
            observation=None,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow-outcome", "o-1", None)
            ),
        )

        with self.assertRaises(SimulationLineageError):
            self.repo.append_shadow_outcome(outcome)

    def test_shadow_never_appears_as_admitted_event(self) -> None:
        campaign, snapshot = self._reject()

        events = self.repo._get_all_events_for_candidate(campaign, snapshot.candidate)
        self.assertEqual(events, ())

    def test_identical_duplicate_shadow_evaluation_idempotent(self) -> None:
        campaign, snapshot = self._reject()

        evaluation = ShadowEvaluation(
            campaign=campaign,
            snapshot=snapshot,
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )
        first = self.repo.append_shadow_evaluation(evaluation)
        second = self.repo.append_shadow_evaluation(evaluation)

        self.assertEqual(first, second)


class QueryEvidenceTests(RepositoryTestCase):
    def test_wrong_query_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.repo.query_evidence("not-a-query")  # type: ignore[arg-type]

    def test_filters_by_disposition(self) -> None:
        campaign = make_campaign()

        admitted_snapshot = make_snapshot(
            candidate=make_candidate(source_id="admitted-1")
        )
        self.repo.append_candidate(campaign, admitted_snapshot)
        self.repo.append_disposition(
            make_disposition(campaign=campaign, snapshot=admitted_snapshot)
        )

        rejected_snapshot = make_snapshot(
            candidate=make_candidate(source_id="rejected-1")
        )
        self.repo.append_candidate(campaign, rejected_snapshot)
        self.repo.append_disposition(
            make_disposition(
                campaign=campaign,
                snapshot=rejected_snapshot,
                disposition=SimulationDisposition.REJECTED,
                reason_references=(make_reason_reference(),),
            )
        )

        results = self.repo.query_evidence(
            SimulationEvidenceQuery(disposition=SimulationDisposition.REJECTED)
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].candidate.source_id, "rejected-1")

    def test_filters_by_reason_reference(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot()
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(
            make_disposition(
                campaign=campaign,
                snapshot=snapshot,
                disposition=SimulationDisposition.NO_TRADE,
                reason_references=(make_reason_reference(reason_code="A"),),
            )
        )

        matching = self.repo.query_evidence(
            SimulationEvidenceQuery(reason_reference=make_reason_reference(reason_code="A"))
        )
        non_matching = self.repo.query_evidence(
            SimulationEvidenceQuery(reason_reference=make_reason_reference(reason_code="B"))
        )

        self.assertEqual(len(matching), 1)
        self.assertEqual(len(non_matching), 0)

    def test_filters_by_admitted_only(self) -> None:
        campaign = make_campaign()

        admitted_snapshot = make_snapshot(candidate=make_candidate(source_id="a"))
        self.repo.append_candidate(campaign, admitted_snapshot)
        self.repo.append_disposition(
            make_disposition(campaign=campaign, snapshot=admitted_snapshot)
        )

        shadow_snapshot = make_snapshot(candidate=make_candidate(source_id="b"))
        self.repo.append_candidate(campaign, shadow_snapshot)
        self.repo.append_disposition(
            make_disposition(
                campaign=campaign,
                snapshot=shadow_snapshot,
                disposition=SimulationDisposition.BLOCKED,
                reason_references=(make_reason_reference(),),
            )
        )

        admitted_only = self.repo.query_evidence(
            SimulationEvidenceQuery(admitted_only=True)
        )
        shadow_only = self.repo.query_evidence(
            SimulationEvidenceQuery(admitted_only=False)
        )

        self.assertEqual({b.candidate.source_id for b in admitted_only}, {"a"})
        self.assertEqual({b.candidate.source_id for b in shadow_only}, {"b"})

    def test_filters_by_instrument_timeframe_direction(self) -> None:
        campaign = make_campaign()
        snapshot = make_snapshot(instrument="ETHUSDT", timeframe="4h", direction="SHORT")
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(
            make_disposition(campaign=campaign, snapshot=snapshot)
        )

        matches = self.repo.query_evidence(
            SimulationEvidenceQuery(
                instrument="ETHUSDT", timeframe="4h", direction="SHORT"
            )
        )
        no_matches = self.repo.query_evidence(
            SimulationEvidenceQuery(instrument="BTCUSDT")
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(len(no_matches), 0)

    def test_no_matching_filters_returns_empty(self) -> None:
        results = self.repo.query_evidence(
            SimulationEvidenceQuery(campaign=make_campaign(campaign_id="nonexistent"))
        )
        self.assertEqual(results, ())

    def test_bundle_preserves_full_provenance(self) -> None:
        campaign, candidate, snapshot = (
            make_campaign(),
            make_candidate(),
            make_snapshot(),
        )
        self.repo.append_candidate(campaign, snapshot)
        self.repo.append_disposition(
            make_disposition(campaign=campaign, snapshot=snapshot)
        )
        self.repo.append_event(make_event(campaign=campaign, candidate=candidate))

        results = self.repo.query_evidence(SimulationEvidenceQuery(campaign=campaign))
        self.assertEqual(len(results), 1)
        bundle = results[0]
        self.assertIsInstance(bundle, SimulationEvidenceBundle)
        self.assertEqual(bundle.snapshot, snapshot)
        self.assertEqual(len(bundle.events), 1)

    def test_no_ranking_pnl_or_significance_fields_on_query_or_bundle(self) -> None:
        import dataclasses

        for cls in (SimulationEvidenceQuery, SimulationEvidenceBundle):
            field_names = {f.name for f in dataclasses.fields(cls)}
            for forbidden in (
                "pnl",
                "expectancy",
                "significance",
                "p_value",
                "rank",
                "score",
                "promoted",
            ):
                self.assertNotIn(forbidden, field_names)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import ast

        import simulation.storage.repository as module

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

    def test_module_is_stdlib_plus_simulation_and_time_semantics_only(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "datetime",
            "decimal",
            "json",
            "pathlib",
            "sqlite3",
            "threading",
            "simulation",
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

    def test_no_forbidden_domain_imports(self) -> None:
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

    def test_no_forbidden_object_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "ResearchTrade",
            "ResearchRepository",
            "ScanJournalRepository",
            "MarketDataService",
            "ExecutionOrder",
            "ExecutionFill",
            "RiskResult",
            "PortfolioDecision",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_notional_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("notional", referenced)

    def test_no_wall_clock_random_network_scheduler(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("utcnow", referenced)
        self.assertNotIn("uuid4", referenced)

        imported = self._imported_names()
        for forbidden in (
            "os",
            "subprocess",
            "requests",
            "fastapi",
            "httpx",
            "socket",
            "random",
            "asyncio",
            "sched",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_api_ui_reports_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in ("APIRouter", "FastAPI", "Report", "Dashboard"):
            self.assertNotIn(forbidden, referenced)

    def test_no_update_delete_replace_upsert_methods(self) -> None:
        import simulation.storage.repository as module

        repo_methods = {
            name
            for name in dir(module.SimulationRepository)
            if not name.startswith("_")
        }
        for forbidden in ("update", "delete", "replace", "upsert", "overwrite"):
            for method_name in repo_methods:
                self.assertNotIn(forbidden, method_name.lower())

    def test_no_sort_or_min_max_selector_calls(self) -> None:
        import ast

        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")


if __name__ == "__main__":
    unittest.main()
