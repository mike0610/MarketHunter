"""
MarketHunter

simulation/runtime/orchestrator.py

Module:
Demo / Paper Trade Simulator v1 - Slice 3 (automatic TEST-MODE
runtime foundation) - the single-writer runtime cycle

Responsibilities:
- Acquire an OS-level, nonblocking, exclusive process lease on a
  sibling lock file derived from the caller-supplied Simulation DB
  path, held for the runtime's lifetime, before any repository write
  - a second runtime process against the same DB fails closed before
  touching storage.
- Expose run_cycle() only: read candidates, append candidate+
  disposition idempotently, source the exact forward observation,
  gate every transition on assess_forward_observation_eligibility(),
  consult the injected mechanics evaluator, and persist the proposed
  plan through the existing repository - EVENTS only for admitted
  lineage, SHADOW only for non-admitted lineage, never both.
- Never invent case_id, attempt_id, sequence, recorded TemporalFacts,
  observation references, or mechanics versions - every persisted
  fact is caller/evaluator supplied.

Non-goals (frozen by MH-DEMO-SIMULATOR-V1-SLICE3-ARCH-001 Council
decision):
- No loop, sleep, scheduler, daemon, CLI, or network of any kind.
  run_cycle() is one bounded pass over one CandidateSourceRead.
- No default database path - simulation_db_path is always required.
- No WAL and no multi-writer tuning; the process lease is the only
  concurrency contract in this slice.
- No concrete candidate adapter, market-data adapter, or mechanics
  provider - candidate_source, observation_source, and
  mechanics_evaluator are injected by the caller.
- No wall-clock freshness computation. SOURCE_STALE is only ever
  caller/source supplied through RuntimeSourceState.
- No source-domain, execution, exchange, API, UI, or statistical
  verdict imports of any kind. Only simulation.foundation,
  simulation.storage, simulation.runtime.contracts, and stdlib
  pathlib/OS lock modules are imported here.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

try:
    import fcntl
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - platform dependent
    msvcrt = None  # type: ignore[assignment]

from simulation.foundation import (
    ForwardEligibilityStatus,
    SimulationDisposition,
    assess_forward_observation_eligibility,
)
from simulation.runtime.contracts import (
    CandidateSource,
    EnvelopeCycleResult,
    ForwardObservationSource,
    MechanicsEvaluationStatus,
    RuntimeCandidateEnvelope,
    RuntimeOperationalStatus,
    RuntimePlanKind,
    RuntimeSourceState,
    SimulationMechanicsEvaluator,
)
from simulation.storage.repository import (
    SimulationEvidenceQuery,
    SimulationRepository,
    SimulationRepositoryError,
)


class SimulationRuntimeLeaseError(Exception):
    """A process-level Simulation runtime lease could not be acquired."""


class _ProcessLease:
    """
    An OS-level, nonblocking, exclusive lease on a sibling lock file
    derived from the Simulation DB path. Lock-file persistence is
    irrelevant - the held OS handle lock is the only truth. No WAL.
    """

    def __init__(self, db_path: Path) -> None:
        self._lock_path = db_path.with_name(db_path.name + ".lock")
        self._file = None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            handle = open(self._lock_path, "a+b")
        except OSError as exc:
            raise SimulationRuntimeLeaseError(
                f"could not open lease file {self._lock_path}: {exc}"
            ) from exc

        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                raise SimulationRuntimeLeaseError(
                    "another Simulation runtime process already holds the "
                    f"lease for {self._lock_path}"
                ) from exc
        elif msvcrt is not None:
            try:
                if handle.seek(0, 2) == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                handle.close()
                raise SimulationRuntimeLeaseError(
                    "another Simulation runtime process already holds the "
                    f"lease for {self._lock_path}"
                ) from exc
        else:  # pragma: no cover - no supported platform lock available
            handle.close()
            raise SimulationRuntimeLeaseError(
                "no supported process-level file locking mechanism is "
                "available on this platform"
            )

        self._file = handle

    def release(self) -> None:
        if self._file is None:
            return

        try:
            if fcntl is not None:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._file.close()
            self._file = None


class SimulationRuntime:
    """
    One fail-closed, single-writer Simulation runtime cycle.
    simulation_db_path is always required - there is no default. The
    process lease is acquired before create_schema()/any repository
    write and held until close(); use as a context manager or call
    close() explicitly.
    """

    def __init__(
        self,
        simulation_db_path: str | Path,
        candidate_source: CandidateSource,
        observation_source: ForwardObservationSource,
        mechanics_evaluator: SimulationMechanicsEvaluator,
    ) -> None:
        self._db_path = Path(simulation_db_path)
        self._candidate_source = candidate_source
        self._observation_source = observation_source
        self._mechanics_evaluator = mechanics_evaluator
        self._closed = False

        self._lease = _ProcessLease(self._db_path)
        self._lease.acquire()

        try:
            self._repository = SimulationRepository(self._db_path)
        except Exception:
            self._lease.release()
            raise

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._lease.release()

    def __enter__(self) -> SimulationRuntime:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def run_cycle(self) -> tuple[EnvelopeCycleResult, ...]:
        """
        One bounded pass: read candidates once, process each envelope
        once. No loop, no sleep, no retry scheduling.
        """

        if self._closed:
            raise SimulationRuntimeLeaseError("runtime is closed")

        read = self._candidate_source.read_candidates()

        if read.state is RuntimeSourceState.UNAVAILABLE:
            return (
                EnvelopeCycleResult(
                    envelope=None,
                    status=RuntimeOperationalStatus.SOURCE_UNAVAILABLE,
                ),
            )

        if read.state is RuntimeSourceState.STALE:
            return (
                EnvelopeCycleResult(
                    envelope=None, status=RuntimeOperationalStatus.SOURCE_STALE
                ),
            )

        return tuple(
            self._process_envelope(envelope) for envelope in read.envelopes
        )

    def _process_envelope(
        self, envelope: RuntimeCandidateEnvelope
    ) -> EnvelopeCycleResult:
        try:
            self._repository.append_candidate(envelope.campaign, envelope.snapshot)
            self._repository.append_disposition(envelope.disposition)
        except SimulationRepositoryError:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.FAILED
            )

        if (
            envelope.disposition.disposition
            is SimulationDisposition.ADMITTED_FOR_SIMULATION
        ):
            return self._process_admitted_envelope(envelope)

        return self._process_shadow_envelope(envelope)

    def _load_persisted_events(self, envelope: RuntimeCandidateEnvelope) -> tuple:
        bundles = self._repository.query_evidence(
            SimulationEvidenceQuery(campaign=envelope.campaign)
        )

        for bundle in bundles:
            if bundle.candidate == envelope.snapshot.candidate:
                return bundle.events

        return ()

    def _read_eligible_observation(
        self, envelope: RuntimeCandidateEnvelope
    ) -> tuple[EnvelopeCycleResult | None, object | None]:
        """
        Returns (early_result, observation). early_result is not None
        when the caller should return it immediately without further
        processing.
        """

        observation_read = self._observation_source.read_observation(envelope)

        if observation_read.state is RuntimeSourceState.UNAVAILABLE:
            return (
                EnvelopeCycleResult(
                    envelope=envelope,
                    status=RuntimeOperationalStatus.SOURCE_UNAVAILABLE,
                ),
                None,
            )

        if observation_read.state is RuntimeSourceState.STALE:
            return (
                EnvelopeCycleResult(
                    envelope=envelope, status=RuntimeOperationalStatus.SOURCE_STALE
                ),
                None,
            )

        observation = observation_read.observation

        eligibility = assess_forward_observation_eligibility(
            envelope.snapshot.detection, observation
        )

        if eligibility.status is not ForwardEligibilityStatus.ELIGIBLE:
            return (
                EnvelopeCycleResult(
                    envelope=envelope,
                    status=RuntimeOperationalStatus.AWAITING_EVIDENCE,
                ),
                None,
            )

        return None, observation

    def _process_admitted_envelope(
        self, envelope: RuntimeCandidateEnvelope
    ) -> EnvelopeCycleResult:
        persisted_events = self._load_persisted_events(envelope)

        early_result, observation = self._read_eligible_observation(envelope)
        if early_result is not None:
            return early_result

        evaluation = self._mechanics_evaluator.evaluate(
            envelope, persisted_events, observation
        )

        if evaluation.status is MechanicsEvaluationStatus.BLOCKED:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.BLOCKED_MECHANICS
            )

        plan = evaluation.plan

        if plan.kind is RuntimePlanKind.NO_CHANGE:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.NO_CHANGE
            )

        if plan.kind is not RuntimePlanKind.EVENTS:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.FAILED
            )

        mechanics_policy = self._mechanics_evaluator.mechanics_policy

        for event in plan.events:
            if event.mechanics is not None and event.mechanics != mechanics_policy:
                return EnvelopeCycleResult(
                    envelope=envelope,
                    status=RuntimeOperationalStatus.BLOCKED_MECHANICS,
                )

        try:
            self._repository.append_events_atomic(plan.events)
        except SimulationRepositoryError:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.FAILED
            )

        after = self._load_persisted_events(envelope)

        if after == persisted_events:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.NO_CHANGE
            )

        return EnvelopeCycleResult(
            envelope=envelope, status=RuntimeOperationalStatus.PROGRESSED, plan=plan
        )

    def _process_shadow_envelope(
        self, envelope: RuntimeCandidateEnvelope
    ) -> EnvelopeCycleResult:
        before_evaluation = self._repository.get_shadow_evaluation(
            envelope.campaign, envelope.snapshot.candidate
        )
        before_outcome = self._repository.get_shadow_outcome(
            envelope.campaign, envelope.snapshot.candidate
        )

        early_result, observation = self._read_eligible_observation(envelope)
        if early_result is not None:
            return early_result

        evaluation = self._mechanics_evaluator.evaluate(envelope, (), observation)

        if evaluation.status is MechanicsEvaluationStatus.BLOCKED:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.BLOCKED_MECHANICS
            )

        plan = evaluation.plan

        if plan.kind is RuntimePlanKind.NO_CHANGE:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.NO_CHANGE
            )

        if plan.kind is not RuntimePlanKind.SHADOW:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.FAILED
            )

        try:
            after_evaluation = self._repository.append_shadow_evaluation(
                plan.shadow_evaluation
            )
            after_outcome = before_outcome

            if plan.shadow_outcome is not None:
                after_outcome = self._repository.append_shadow_outcome(
                    plan.shadow_outcome
                )
        except SimulationRepositoryError:
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.FAILED
            )

        if (before_evaluation, before_outcome) == (after_evaluation, after_outcome):
            return EnvelopeCycleResult(
                envelope=envelope, status=RuntimeOperationalStatus.NO_CHANGE
            )

        return EnvelopeCycleResult(
            envelope=envelope, status=RuntimeOperationalStatus.PROGRESSED, plan=plan
        )
