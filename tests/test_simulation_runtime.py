"""
MarketHunter

Tests for Demo / Paper Trade Simulator v1 - Slice 3
(simulation/runtime/contracts.py, simulation/runtime/orchestrator.py).
"""

from __future__ import annotations

import dataclasses
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
)
from simulation.runtime.contracts import (
    CandidateSourceRead,
    EnvelopeCycleResult,
    ForwardObservationRead,
    MechanicsEvaluation,
    MechanicsEvaluationStatus,
    RuntimeCandidateEnvelope,
    RuntimeOperationalStatus,
    RuntimePlanKind,
    RuntimeSourceState,
    RuntimeTransitionPlan,
)
from simulation.runtime.orchestrator import SimulationRuntime, SimulationRuntimeLeaseError
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
        targets=(Decimal("110"),),
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


def make_envelope(**overrides) -> RuntimeCandidateEnvelope:
    kwargs = dict(
        campaign=make_campaign(), snapshot=make_snapshot(), disposition=make_disposition()
    )
    kwargs.update(overrides)
    return RuntimeCandidateEnvelope(**kwargs)


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


def make_waiting_entry_event(**overrides) -> SimulationEvent:
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


def make_reason_reference(**overrides) -> SimulationReasonReference:
    kwargs = dict(
        reason_namespace="simulation.eligibility",
        reason_code="LIQUIDITY_INSUFFICIENT",
        reason_version="1",
    )
    kwargs.update(overrides)
    return SimulationReasonReference(**kwargs)


class FakeCandidateSource:
    def __init__(
        self,
        state: RuntimeSourceState = RuntimeSourceState.AVAILABLE,
        envelopes: tuple[RuntimeCandidateEnvelope, ...] = (),
    ) -> None:
        self.state = state
        self.envelopes = envelopes
        self.read_count = 0

    def read_candidates(self) -> CandidateSourceRead:
        self.read_count += 1
        return CandidateSourceRead(state=self.state, envelopes=self.envelopes)


class FakeObservationSource:
    def __init__(
        self,
        state: RuntimeSourceState = RuntimeSourceState.AVAILABLE,
        observation: MarketObservationEvidence | None = None,
    ) -> None:
        self.state = state
        self.observation = observation

    def read_observation(self, envelope: RuntimeCandidateEnvelope) -> ForwardObservationRead:
        return ForwardObservationRead(state=self.state, observation=self.observation)


class FakeMechanicsEvaluator:
    def __init__(self, policy=None, status=MechanicsEvaluationStatus.READY, plan_fn=None) -> None:
        self._policy = policy or make_mechanics()
        self._status = status
        self._plan_fn = plan_fn or (lambda envelope, persisted_events, observation: RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE))
        self.evaluate_calls = []

    @property
    def mechanics_policy(self) -> SimulationMechanicsPolicyReference:
        return self._policy

    def evaluate(self, envelope, persisted_events, observation) -> MechanicsEvaluation:
        self.evaluate_calls.append((envelope, persisted_events, observation))

        if self._status is MechanicsEvaluationStatus.BLOCKED:
            return MechanicsEvaluation(status=MechanicsEvaluationStatus.BLOCKED, plan=None)

        plan = self._plan_fn(envelope, persisted_events, observation)
        return MechanicsEvaluation(status=MechanicsEvaluationStatus.READY, plan=plan)


class RuntimeCandidateEnvelopeTests(unittest.TestCase):
    def test_frozen(self) -> None:
        envelope = make_envelope()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            envelope.campaign = make_campaign()  # type: ignore[misc]

    def test_matching_identity_accepted(self) -> None:
        envelope = make_envelope()
        self.assertEqual(envelope.campaign, make_campaign())

    def test_disposition_campaign_mismatch_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_envelope(
                disposition=make_disposition(campaign=make_campaign(campaign_id="other"))
            )

    def test_disposition_snapshot_mismatch_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_envelope(
                disposition=make_disposition(
                    snapshot=make_snapshot(instrument="ETHUSDT")
                )
            )

    def test_wrong_campaign_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_envelope(campaign="not-a-campaign")  # type: ignore[arg-type]


class CandidateSourceReadTests(unittest.TestCase):
    def test_available_with_envelopes_accepted(self) -> None:
        read = CandidateSourceRead(
            state=RuntimeSourceState.AVAILABLE, envelopes=(make_envelope(),)
        )
        self.assertEqual(len(read.envelopes), 1)

    def test_unavailable_with_envelopes_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CandidateSourceRead(
                state=RuntimeSourceState.UNAVAILABLE, envelopes=(make_envelope(),)
            )

    def test_stale_with_envelopes_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CandidateSourceRead(
                state=RuntimeSourceState.STALE, envelopes=(make_envelope(),)
            )

    def test_unavailable_with_no_envelopes_accepted(self) -> None:
        read = CandidateSourceRead(state=RuntimeSourceState.UNAVAILABLE, envelopes=())
        self.assertEqual(read.envelopes, ())


class ForwardObservationReadTests(unittest.TestCase):
    def test_available_requires_observation(self) -> None:
        with self.assertRaises(ValueError):
            ForwardObservationRead(state=RuntimeSourceState.AVAILABLE, observation=None)

    def test_available_with_observation_accepted(self) -> None:
        read = ForwardObservationRead(
            state=RuntimeSourceState.AVAILABLE, observation=make_observation_evidence()
        )
        self.assertIsNotNone(read.observation)

    def test_unavailable_forbids_observation(self) -> None:
        with self.assertRaises(ValueError):
            ForwardObservationRead(
                state=RuntimeSourceState.UNAVAILABLE,
                observation=make_observation_evidence(),
            )

    def test_stale_forbids_observation(self) -> None:
        with self.assertRaises(ValueError):
            ForwardObservationRead(
                state=RuntimeSourceState.STALE, observation=make_observation_evidence()
            )


class RuntimeTransitionPlanTests(unittest.TestCase):
    def test_no_change_default(self) -> None:
        plan = RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE)
        self.assertEqual(plan.events, ())

    def test_no_change_with_events_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeTransitionPlan(
                kind=RuntimePlanKind.NO_CHANGE, events=(make_waiting_entry_event(),)
            )

    def test_events_requires_nonempty(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=())

    def test_events_with_shadow_fields_rejected(self) -> None:
        evaluation = ShadowEvaluation(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )
        with self.assertRaises(ValueError):
            RuntimeTransitionPlan(
                kind=RuntimePlanKind.EVENTS,
                events=(make_waiting_entry_event(),),
                shadow_evaluation=evaluation,
            )

    def test_shadow_requires_evaluation(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeTransitionPlan(kind=RuntimePlanKind.SHADOW)

    def test_shadow_with_events_rejected(self) -> None:
        evaluation = ShadowEvaluation(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
            disposition=SimulationDisposition.REJECTED,
            counterfactual=True,
            order_created=False,
            trade_created=False,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow", "s-1", None)
            ),
        )
        with self.assertRaises(ValueError):
            RuntimeTransitionPlan(
                kind=RuntimePlanKind.SHADOW,
                events=(make_waiting_entry_event(),),
                shadow_evaluation=evaluation,
            )

    def test_shadow_with_optional_outcome_accepted(self) -> None:
        evaluation = ShadowEvaluation(
            campaign=make_campaign(),
            snapshot=make_snapshot(),
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
            outcome_type=SimulationEventType.CENSORED,
            observation=None,
            recorded_fact=make_recorded_fact(
                reference=TemporalReference("shadow-outcome", "o-1", None)
            ),
        )
        plan = RuntimeTransitionPlan(
            kind=RuntimePlanKind.SHADOW,
            shadow_evaluation=evaluation,
            shadow_outcome=outcome,
        )
        self.assertEqual(plan.shadow_outcome, outcome)


class MechanicsEvaluationTests(unittest.TestCase):
    def test_ready_requires_plan(self) -> None:
        with self.assertRaises(ValueError):
            MechanicsEvaluation(status=MechanicsEvaluationStatus.READY, plan=None)

    def test_blocked_forbids_plan(self) -> None:
        with self.assertRaises(ValueError):
            MechanicsEvaluation(
                status=MechanicsEvaluationStatus.BLOCKED,
                plan=RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE),
            )

    def test_ready_with_plan_accepted(self) -> None:
        evaluation = MechanicsEvaluation(
            status=MechanicsEvaluationStatus.READY,
            plan=RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE),
        )
        self.assertIsNotNone(evaluation.plan)


class EnvelopeCycleResultTests(unittest.TestCase):
    def test_source_level_status_with_envelope_accepted(self) -> None:
        # The observation source is per-envelope, so an
        # UNAVAILABLE/STALE reading from it still carries the exact
        # envelope being evaluated.
        result = EnvelopeCycleResult(
            envelope=make_envelope(),
            status=RuntimeOperationalStatus.SOURCE_UNAVAILABLE,
        )
        self.assertIsNotNone(result.envelope)

    def test_source_level_status_without_envelope_accepted(self) -> None:
        # The candidate source itself failing means no envelope was
        # ever available to process.
        result = EnvelopeCycleResult(
            envelope=None, status=RuntimeOperationalStatus.SOURCE_UNAVAILABLE
        )
        self.assertIsNone(result.envelope)

    def test_no_change_without_envelope_accepted(self) -> None:
        result = EnvelopeCycleResult(envelope=None, status=RuntimeOperationalStatus.NO_CHANGE)
        self.assertIsNone(result.envelope)

    def test_progressed_requires_plan(self) -> None:
        with self.assertRaises(ValueError):
            EnvelopeCycleResult(
                envelope=make_envelope(), status=RuntimeOperationalStatus.PROGRESSED
            )

    def test_progressed_requires_envelope(self) -> None:
        with self.assertRaises(ValueError):
            EnvelopeCycleResult(
                envelope=None,
                status=RuntimeOperationalStatus.PROGRESSED,
                plan=RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE),
            )

    def test_non_progressed_forbids_plan(self) -> None:
        with self.assertRaises(ValueError):
            EnvelopeCycleResult(
                envelope=make_envelope(),
                status=RuntimeOperationalStatus.NO_CHANGE,
                plan=RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE),
            )

class RuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "simulation.db"
        self._open_runtimes: list[SimulationRuntime] = []

    def tearDown(self) -> None:
        for runtime in self._open_runtimes:
            runtime.close()
        self._tmpdir.cleanup()

    def make_runtime(self, candidate_source, observation_source, mechanics_evaluator) -> SimulationRuntime:
        runtime = SimulationRuntime(
            self.db_path, candidate_source, observation_source, mechanics_evaluator
        )
        self._open_runtimes.append(runtime)
        return runtime


class ProcessLeaseTests(RuntimeTestCase):
    def test_no_default_db_path(self) -> None:
        with self.assertRaises(TypeError):
            SimulationRuntime(  # type: ignore[call-arg]
                candidate_source=FakeCandidateSource(),
                observation_source=FakeObservationSource(),
                mechanics_evaluator=FakeMechanicsEvaluator(),
            )

    def test_second_runtime_same_db_fails_before_write(self) -> None:
        self.make_runtime(FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator())

        schema_before = self.db_path.read_bytes()

        with self.assertRaises(SimulationRuntimeLeaseError):
            SimulationRuntime(
                self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
            )

        # the failed second construction never reached repository
        # construction/create_schema(), so the database is untouched
        self.assertEqual(self.db_path.read_bytes(), schema_before)

    def test_release_allows_reacquisition(self) -> None:
        runtime = SimulationRuntime(
            self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        )
        runtime.close()

        second = SimulationRuntime(
            self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        )
        self._open_runtimes.append(second)

    def test_context_manager_releases_on_exit(self) -> None:
        with SimulationRuntime(
            self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        ):
            pass

        second = SimulationRuntime(
            self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        )
        self._open_runtimes.append(second)

    def test_distinct_db_paths_independent(self) -> None:
        other_db_path = Path(self._tmpdir.name) / "other.db"

        first = self.make_runtime(FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator())
        second = SimulationRuntime(
            other_db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        )
        self._open_runtimes.append(second)
        # both constructed without raising - independence confirmed

    def test_closed_runtime_rejects_run_cycle(self) -> None:
        runtime = SimulationRuntime(
            self.db_path, FakeCandidateSource(), FakeObservationSource(), FakeMechanicsEvaluator()
        )
        runtime.close()

        with self.assertRaises(SimulationRuntimeLeaseError):
            runtime.run_cycle()


class RuntimeCycleSourceTests(RuntimeTestCase):
    def test_candidate_source_unavailable(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.UNAVAILABLE),
            FakeObservationSource(),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, RuntimeOperationalStatus.SOURCE_UNAVAILABLE)
        self.assertIsNone(results[0].envelope)

    def test_candidate_source_stale(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.STALE),
            FakeObservationSource(),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.SOURCE_STALE)

    def test_no_envelopes_available_returns_empty(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, ()),
            FakeObservationSource(),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results, ())

    def test_candidate_source_has_no_mutation_seam(self) -> None:
        for forbidden in ("ack", "update", "delete", "write", "mutate"):
            self.assertFalse(hasattr(FakeCandidateSource, forbidden))

    def test_observation_source_unavailable(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.UNAVAILABLE),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, RuntimeOperationalStatus.SOURCE_UNAVAILABLE)
        self.assertIsNotNone(results[0].envelope)

    def test_observation_source_stale_caller_supplied_only(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.STALE),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.SOURCE_STALE)


class RuntimeCycleEligibilityTests(RuntimeTestCase):
    def test_observation_before_detection_awaiting_evidence(self) -> None:
        stale_observation = make_observation_evidence(
            shared_reference=TemporalReference("observation", "before", None),
            event_time=TemporalFact(
                TemporalReference("observation", "before", None),
                TemporalRole.EVENT_TIME,
                AWARE_EARLY,
                TemporalDisposition.KNOWN,
            ),
            observed_time=TemporalFact(
                TemporalReference("observation", "before", None),
                TemporalRole.OBSERVED_TIME,
                AWARE_EARLY,
                TemporalDisposition.KNOWN,
            ),
            recorded_time=TemporalFact(
                TemporalReference("observation", "before", None),
                TemporalRole.RECORDED_TIME,
                AWARE_EARLY,
                TemporalDisposition.KNOWN,
            ),
        )
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, stale_observation),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.AWAITING_EVIDENCE)

    def test_observation_unknown_disposition_awaiting_evidence(self) -> None:
        ref = TemporalReference("observation", "unk", None)
        unknown_observation = MarketObservationEvidence(
            reference=MarketObservationReference(
                "exchange_rest", "binance", "BTCUSDT", "1h", "hash-1"
            ),
            event_time=TemporalFact(
                ref, TemporalRole.EVENT_TIME, AWARE_LATE, TemporalDisposition.KNOWN
            ),
            observed_time=TemporalFact(
                ref, TemporalRole.OBSERVED_TIME, None, TemporalDisposition.UNKNOWN
            ),
            recorded_time=TemporalFact(
                ref, TemporalRole.RECORDED_TIME, AWARE_LATE, TemporalDisposition.KNOWN
            ),
        )
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, unknown_observation),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.AWAITING_EVIDENCE)

    def test_eligible_observation_reaches_mechanics_evaluator(self) -> None:
        evaluator = FakeMechanicsEvaluator()
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            evaluator,
        )
        runtime.run_cycle()
        self.assertEqual(len(evaluator.evaluate_calls), 1)


class RuntimeCycleMechanicsTests(RuntimeTestCase):
    def test_blocked_mechanics(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(status=MechanicsEvaluationStatus.BLOCKED),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.BLOCKED_MECHANICS)

    def test_mechanics_reference_mismatch_blocks(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            event = make_waiting_entry_event(
                event_type=SimulationEventType.SIMULATED_FILL,
                mechanics=make_mechanics(mechanics_policy_id="other-mechanics"),
                observation=make_observation_evidence(),
            )
            return RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=(event,))

        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.BLOCKED_MECHANICS)

    def test_no_change_plan(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.NO_CHANGE)


class RuntimeCycleAdmittedTests(RuntimeTestCase):
    def _plan_fn(self, envelope, persisted_events, observation):
        if persisted_events:
            return RuntimeTransitionPlan(kind=RuntimePlanKind.NO_CHANGE)
        event = make_waiting_entry_event(
            campaign=envelope.campaign, candidate=envelope.snapshot.candidate
        )
        return RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=(event,))

    def test_events_plan_progresses_and_persists(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=self._plan_fn),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.PROGRESSED)
        self.assertIsNotNone(results[0].plan)

        events = runtime._repository.get_case_events(
            make_campaign(), make_candidate(), "case-1", "attempt-1"
        )
        self.assertEqual(len(events), 1)

    def test_duplicate_observation_does_not_double_advance(self) -> None:
        candidate_source = FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),))
        runtime = self.make_runtime(
            candidate_source,
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=self._plan_fn),
        )
        first = runtime.run_cycle()
        second = runtime.run_cycle()

        self.assertEqual(first[0].status, RuntimeOperationalStatus.PROGRESSED)
        self.assertEqual(second[0].status, RuntimeOperationalStatus.NO_CHANGE)

        events = runtime._repository.get_case_events(
            make_campaign(), make_candidate(), "case-1", "attempt-1"
        )
        self.assertEqual(len(events), 1)

    def test_shadow_plan_kind_rejected_for_admitted(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            evaluation = ShadowEvaluation(
                campaign=envelope.campaign,
                snapshot=envelope.snapshot,
                disposition=SimulationDisposition.REJECTED,
                counterfactual=True,
                order_created=False,
                trade_created=False,
                recorded_fact=make_recorded_fact(
                    reference=TemporalReference("shadow", "s-1", None)
                ),
            )
            return RuntimeTransitionPlan(
                kind=RuntimePlanKind.SHADOW, shadow_evaluation=evaluation
            )

        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.FAILED)

    def test_restart_replay_equivalence(self) -> None:
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=self._plan_fn),
        )
        runtime.run_cycle()
        events_before = runtime._repository.get_case_events(
            make_campaign(), make_candidate(), "case-1", "attempt-1"
        )
        runtime.close()
        self._open_runtimes.remove(runtime)

        reopened = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, ()),
            FakeObservationSource(),
            FakeMechanicsEvaluator(),
        )
        events_after = reopened._repository.get_case_events(
            make_campaign(), make_candidate(), "case-1", "attempt-1"
        )

        self.assertEqual(events_before, events_after)

        from simulation.foundation import replay_simulation_events

        self.assertEqual(
            replay_simulation_events(events_before).final_state,
            replay_simulation_events(events_after).final_state,
        )

    def test_censored_outcome_preserved(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            if not persisted_events:
                event = make_waiting_entry_event(
                    campaign=envelope.campaign, candidate=envelope.snapshot.candidate
                )
                return RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=(event,))

            censored = SimulationEvent(
                reference=SimulationEventReference("case-1", "attempt-1", 2),
                campaign=envelope.campaign,
                candidate=envelope.snapshot.candidate,
                event_type=SimulationEventType.CENSORED,
                mechanics=None,
                observation=None,
                recorded_fact=make_recorded_fact(
                    reference=TemporalReference("event", "e-2", None)
                ),
            )
            return RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=(censored,))

        candidate_source = FakeCandidateSource(RuntimeSourceState.AVAILABLE, (make_envelope(),))
        runtime = self.make_runtime(
            candidate_source,
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        runtime.run_cycle()
        second = runtime.run_cycle()

        self.assertEqual(second[0].status, RuntimeOperationalStatus.PROGRESSED)

        events = runtime._repository.get_case_events(
            make_campaign(), make_candidate(), "case-1", "attempt-1"
        )
        self.assertEqual(events[-1].event_type, SimulationEventType.CENSORED)


class RuntimeCycleShadowTests(RuntimeTestCase):
    def _shadow_envelope(self) -> RuntimeCandidateEnvelope:
        disposition = make_disposition(
            disposition=SimulationDisposition.REJECTED,
            reason_references=(make_reason_reference(),),
        )
        return make_envelope(disposition=disposition)

    def test_shadow_plan_persists_shadow_only(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            evaluation = ShadowEvaluation(
                campaign=envelope.campaign,
                snapshot=envelope.snapshot,
                disposition=SimulationDisposition.REJECTED,
                counterfactual=True,
                order_created=False,
                trade_created=False,
                recorded_fact=make_recorded_fact(
                    reference=TemporalReference("shadow", "s-1", None)
                ),
            )
            return RuntimeTransitionPlan(
                kind=RuntimePlanKind.SHADOW, shadow_evaluation=evaluation
            )

        envelope = self._shadow_envelope()
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (envelope,)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.PROGRESSED)

        shadow_evaluation = runtime._repository.get_shadow_evaluation(
            make_campaign(), make_candidate()
        )
        self.assertIsNotNone(shadow_evaluation)

        events = runtime._repository._get_all_events_for_candidate(
            make_campaign(), make_candidate()
        )
        self.assertEqual(events, (), "shadow lineage must never create SimulationEvent rows")

    def test_events_plan_kind_rejected_for_shadow(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            event = make_waiting_entry_event(
                campaign=envelope.campaign, candidate=envelope.snapshot.candidate
            )
            return RuntimeTransitionPlan(kind=RuntimePlanKind.EVENTS, events=(event,))

        envelope = self._shadow_envelope()
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (envelope,)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        results = runtime.run_cycle()
        self.assertEqual(results[0].status, RuntimeOperationalStatus.FAILED)

    def test_shadow_redelivery_idempotent_no_change(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            evaluation = ShadowEvaluation(
                campaign=envelope.campaign,
                snapshot=envelope.snapshot,
                disposition=SimulationDisposition.REJECTED,
                counterfactual=True,
                order_created=False,
                trade_created=False,
                recorded_fact=make_recorded_fact(
                    reference=TemporalReference("shadow", "s-1", None)
                ),
            )
            return RuntimeTransitionPlan(
                kind=RuntimePlanKind.SHADOW, shadow_evaluation=evaluation
            )

        envelope = self._shadow_envelope()
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (envelope,)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        first = runtime.run_cycle()
        second = runtime.run_cycle()

        self.assertEqual(first[0].status, RuntimeOperationalStatus.PROGRESSED)
        self.assertEqual(second[0].status, RuntimeOperationalStatus.NO_CHANGE)

    def test_unknown_shadow_outcome_preserved(self) -> None:
        def plan_fn(envelope, persisted_events, observation):
            evaluation = ShadowEvaluation(
                campaign=envelope.campaign,
                snapshot=envelope.snapshot,
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
            return RuntimeTransitionPlan(
                kind=RuntimePlanKind.SHADOW,
                shadow_evaluation=evaluation,
                shadow_outcome=outcome,
            )

        envelope = self._shadow_envelope()
        runtime = self.make_runtime(
            FakeCandidateSource(RuntimeSourceState.AVAILABLE, (envelope,)),
            FakeObservationSource(RuntimeSourceState.AVAILABLE, make_observation_evidence()),
            FakeMechanicsEvaluator(plan_fn=plan_fn),
        )
        runtime.run_cycle()

        outcome = runtime._repository.get_shadow_outcome(make_campaign(), make_candidate())
        self.assertEqual(outcome.outcome_type, SimulationEventType.UNKNOWN)


class RuntimeCycleRedeliveryTests(RuntimeTestCase):
    def test_candidate_disposition_redelivery_idempotent(self) -> None:
        candidate_source = FakeCandidateSource(
            RuntimeSourceState.AVAILABLE, (make_envelope(),)
        )
        runtime = self.make_runtime(
            candidate_source,
            FakeObservationSource(RuntimeSourceState.UNAVAILABLE),
            FakeMechanicsEvaluator(),
        )
        first = runtime.run_cycle()
        second = runtime.run_cycle()

        self.assertEqual(first[0].status, RuntimeOperationalStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(second[0].status, RuntimeOperationalStatus.SOURCE_UNAVAILABLE)

        stored = runtime._repository.get_candidate(make_campaign(), make_candidate())
        self.assertIsNotNone(stored)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self, module):
        import ast

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self, module) -> set[str]:
        import ast

        imported: set[str] = set()
        for node in ast.walk(self._module_tree(module)):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def _referenced_names(self, module) -> set[str]:
        import ast

        tree = self._module_tree(module)
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_contracts_module_is_stdlib_plus_foundation_only(self) -> None:
        import simulation.runtime.contracts as module

        imported = self._imported_names(module)
        allowed_prefixes = ("__future__", "dataclasses", "enum", "typing", "simulation.foundation")
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import in contracts.py: {name}",
            )

    def test_orchestrator_module_allowed_imports_only(self) -> None:
        import simulation.runtime.orchestrator as module

        imported = self._imported_names(module)
        allowed_prefixes = (
            "__future__",
            "pathlib",
            "types",
            "fcntl",
            "msvcrt",
            "simulation.foundation",
            "simulation.runtime.contracts",
            "simulation.storage.repository",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import in orchestrator.py: {name}",
            )

    def test_no_forbidden_domain_imports(self) -> None:
        import simulation.runtime.contracts as contracts_module
        import simulation.runtime.orchestrator as orchestrator_module

        for module in (contracts_module, orchestrator_module):
            imported = self._imported_names(module)
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
                        f"unexpected cross-domain import in {module.__name__}: {name}",
                    )

    def test_no_forbidden_object_references(self) -> None:
        import simulation.runtime.contracts as contracts_module
        import simulation.runtime.orchestrator as orchestrator_module

        for module in (contracts_module, orchestrator_module):
            referenced = self._referenced_names(module)
            for forbidden in (
                "ResearchTrade",
                "ResearchRepository",
                "MarketDataService",
                "ExecutionOrder",
                "ExecutionFill",
                "RiskResult",
                "PortfolioDecision",
            ):
                self.assertNotIn(forbidden, referenced)

    def test_no_network_scheduler_sleep_api_ui(self) -> None:
        import simulation.runtime.contracts as contracts_module
        import simulation.runtime.orchestrator as orchestrator_module

        for module in (contracts_module, orchestrator_module):
            imported = self._imported_names(module)
            for forbidden in (
                "socket",
                "requests",
                "httpx",
                "fastapi",
                "sched",
                "asyncio",
                "subprocess",
            ):
                self.assertNotIn(forbidden, imported)

            referenced = self._referenced_names(module)
            self.assertNotIn("sleep", referenced)
            self.assertNotIn("APIRouter", referenced)
            self.assertNotIn("FastAPI", referenced)

    def test_no_wal_research_db_random_uuid_wall_clock(self) -> None:
        import simulation.runtime.orchestrator as module

        referenced = self._referenced_names(module)
        for forbidden in ("now", "utcnow", "uuid4", "WAL", "research"):
            self.assertNotIn(forbidden, referenced)

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("research.db", source)
        self.assertNotIn("journal_mode", source)

        imported = self._imported_names(module)
        for forbidden in ("random", "uuid", "datetime", "time"):
            self.assertNotIn(forbidden, imported)

    def test_no_statistical_verdict_references(self) -> None:
        import simulation.runtime.contracts as contracts_module
        import simulation.runtime.orchestrator as orchestrator_module

        for module in (contracts_module, orchestrator_module):
            referenced = self._referenced_names(module)
            for forbidden in ("significance", "p_value", "expectancy", "pnl", "promote"):
                self.assertNotIn(forbidden, referenced)

    def test_no_loop_construct_in_orchestrator_run_cycle(self) -> None:
        import ast

        import simulation.runtime.orchestrator as module

        tree = self._module_tree(module)
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.While)


if __name__ == "__main__":
    unittest.main()
