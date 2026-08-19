"""
MarketHunter

simulation/storage/repository.py

Module:
Demo / Paper Trade Simulator v1 - Slice 2 (append-only persistence +
read-only evidence export)

Responsibilities:
- Persist Slice-1 CandidateSnapshot/DispositionRecord/SimulationEvent/
  ShadowEvaluation/ShadowOutcome records in a dedicated, caller-
  supplied SQLite database - append-only, idempotent on identical
  duplicates, hard-conflict on identity/payload mismatch.
- Enforce lineage: candidate before disposition, ADMITTED_FOR_
  SIMULATION disposition before events, one case/attempt per
  candidate, REJECTED/BLOCKED/NO_TRADE disposition before shadow
  records. Event append is validated through Slice-1
  replay_simulation_events() before it is persisted.
- Expose a read-only SimulationEvidenceQuery/query_evidence() seam
  that returns immutable evidence bundles with exact provenance -
  never a ranking, PnL, expectancy, significance, or promotion
  verdict.

Non-goals (frozen by MH-DEMO-SIMULATOR-V1-SLICE2-ARCH-001 Council
decision):
- SimulationRepository is the sole durable writer for Simulation
  records only. It never imports or writes ResearchTrade,
  ResearchRepository, ScanJournalRepository, MarketDataService, or
  any Portfolio/Risk/TOP/Execution/exchange model.
- No default database path. The caller always supplies db_path -
  this module never defaults to research.db or any shared file.
- No update/delete/replace/upsert-overwrite API for canonical
  records. Every write is append-only: absent identity inserts,
  identical reconstructed payload is idempotent, and a conflicting
  payload at the same identity is a hard SimulationConflictError.
- No latest/current/max-time identity or query semantics. Storage
  identity is derived only from exact domain identity/lineage
  (campaign, exact candidate reference, case_id/attempt_id/sequence)
  - never from a timestamp.
- No ranking, PnL, expectancy, significance, threshold, or promotion
  logic in the repository or query seam.
- No schema migration/backfill machinery. Schema v1 creates only
  Simulation-owned tables; an unsupported/newer schema version fails
  closed with SimulationSchemaVersionError rather than repairing or
  downgrading.
- No runtime worker, scheduler, network, wall clock, or random usage
  anywhere.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock

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
    SimulationReplayStatus,
    SimulationStrategyReference,
    replay_simulation_events,
)
from time_semantics.foundation import TemporalDisposition, TemporalFact, TemporalReference, TemporalRole

_SCHEMA_VERSION = 1
_SCHEMA_KEY = "simulation"
_NULL_KEY_SENTINEL = "\x00__NULL__\x00"

_SHADOW_ELIGIBLE_DISPOSITIONS = (
    SimulationDisposition.REJECTED,
    SimulationDisposition.BLOCKED,
    SimulationDisposition.NO_TRADE,
)


class SimulationRepositoryError(Exception):
    """Base error for SimulationRepository failures."""


class SimulationConflictError(SimulationRepositoryError):
    """Same storage identity already stored with a different payload."""


class SimulationLineageError(SimulationRepositoryError):
    """Requested append violates append-only lineage rules."""


class SimulationPersistenceError(SimulationRepositoryError):
    """Underlying SQLite storage failed."""


class SimulationSchemaVersionError(SimulationRepositoryError):
    """The database carries an unsupported simulation schema version."""


def _null_safe_key(value: str | None) -> str:
    return value if value is not None else _NULL_KEY_SENTINEL


def _candidate_identity_values(
    campaign: SimulationCampaignReference, candidate: SimulationCandidateReference
) -> tuple:
    return (
        campaign.campaign_id,
        campaign.revision,
        candidate.source_domain,
        candidate.source_type,
        candidate.source_id,
        _null_safe_key(candidate.revision_or_version),
    )


def _temporal_reference_to_dict(reference: TemporalReference) -> dict:
    return {
        "reference_kind": reference.reference_kind,
        "reference_id": reference.reference_id,
        "revision_or_version": reference.revision_or_version,
    }


def _temporal_reference_from_dict(data: dict) -> TemporalReference:
    return TemporalReference(
        reference_kind=data["reference_kind"],
        reference_id=data["reference_id"],
        revision_or_version=data["revision_or_version"],
    )


def _temporal_fact_to_dict(fact: TemporalFact) -> dict:
    return {
        "reference": _temporal_reference_to_dict(fact.reference),
        "role": fact.role.value,
        "timestamp": fact.timestamp.isoformat() if fact.timestamp is not None else None,
        "disposition": fact.disposition.value,
    }


def _temporal_fact_from_dict(data: dict) -> TemporalFact:
    return TemporalFact(
        reference=_temporal_reference_from_dict(data["reference"]),
        role=TemporalRole(data["role"]),
        timestamp=(
            datetime.fromisoformat(data["timestamp"])
            if data["timestamp"] is not None
            else None
        ),
        disposition=TemporalDisposition(data["disposition"]),
    )


def _policy_to_dict(policy: SimulationPolicyReference) -> dict:
    return {
        "policy_kind": policy.policy_kind,
        "policy_id": policy.policy_id,
        "version": policy.version,
    }


def _policy_from_dict(data: dict) -> SimulationPolicyReference:
    return SimulationPolicyReference(**data)


def _mechanics_to_dict(mechanics: SimulationMechanicsPolicyReference) -> dict:
    return {
        "mechanics_policy_id": mechanics.mechanics_policy_id,
        "version": mechanics.version,
    }


def _mechanics_from_dict(data: dict) -> SimulationMechanicsPolicyReference:
    return SimulationMechanicsPolicyReference(**data)


def _reason_reference_to_dict(reference: SimulationReasonReference) -> dict:
    return {
        "reason_namespace": reference.reason_namespace,
        "reason_code": reference.reason_code,
        "reason_version": reference.reason_version,
    }


def _reason_reference_from_dict(data: dict) -> SimulationReasonReference:
    return SimulationReasonReference(**data)


def _observation_reference_to_dict(reference: MarketObservationReference) -> dict:
    return {
        "source_kind": reference.source_kind,
        "source_id": reference.source_id,
        "instrument": reference.instrument,
        "granularity": reference.granularity,
        "revision_or_hash": reference.revision_or_hash,
    }


def _observation_reference_from_dict(data: dict) -> MarketObservationReference:
    return MarketObservationReference(**data)


def _observation_evidence_to_dict(evidence: MarketObservationEvidence) -> dict:
    return {
        "reference": _observation_reference_to_dict(evidence.reference),
        "event_time": _temporal_fact_to_dict(evidence.event_time),
        "observed_time": _temporal_fact_to_dict(evidence.observed_time),
        "recorded_time": _temporal_fact_to_dict(evidence.recorded_time),
    }


def _observation_evidence_from_dict(data: dict) -> MarketObservationEvidence:
    return MarketObservationEvidence(
        reference=_observation_reference_from_dict(data["reference"]),
        event_time=_temporal_fact_from_dict(data["event_time"]),
        observed_time=_temporal_fact_from_dict(data["observed_time"]),
        recorded_time=_temporal_fact_from_dict(data["recorded_time"]),
    )


@dataclass(frozen=True, slots=True)
class SimulationEvidenceQuery:
    """
    Optional, exact-match filters only. No free-text reason parsing,
    no latest/current selection, and no ranking/PnL/significance
    field of any kind.
    """

    campaign: SimulationCampaignReference | None = None
    strategy: SimulationStrategyReference | None = None
    disposition: SimulationDisposition | None = None
    reason_reference: SimulationReasonReference | None = None
    instrument: str | None = None
    timeframe: str | None = None
    direction: str | None = None
    mechanics: SimulationMechanicsPolicyReference | None = None
    event_type: SimulationEventType | None = None
    admitted_only: bool | None = None
    policy_reference: SimulationPolicyReference | None = None

    def __post_init__(self) -> None:
        _optional_isinstance(self.campaign, SimulationCampaignReference, "campaign")
        _optional_isinstance(self.strategy, SimulationStrategyReference, "strategy")
        _optional_isinstance(self.disposition, SimulationDisposition, "disposition")
        _optional_isinstance(
            self.reason_reference, SimulationReasonReference, "reason_reference"
        )
        _optional_isinstance(self.instrument, str, "instrument")
        _optional_isinstance(self.timeframe, str, "timeframe")
        _optional_isinstance(self.direction, str, "direction")
        _optional_isinstance(
            self.mechanics, SimulationMechanicsPolicyReference, "mechanics"
        )
        _optional_isinstance(self.event_type, SimulationEventType, "event_type")
        _optional_isinstance(self.admitted_only, bool, "admitted_only")
        _optional_isinstance(
            self.policy_reference, SimulationPolicyReference, "policy_reference"
        )


def _optional_isinstance(value: object, expected_type: type, field_name: str) -> None:
    if value is not None and not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be a {expected_type.__name__} or None")


@dataclass(frozen=True, slots=True)
class SimulationEvidenceBundle:
    """
    One immutable, exact-provenance evidence bundle - never a
    derived verdict. events is populated only for the admitted
    lineage; shadow_evaluation/shadow_outcome are populated only for
    the non-admitted lineage.
    """

    campaign: SimulationCampaignReference
    candidate: SimulationCandidateReference
    snapshot: CandidateSnapshot
    disposition: DispositionRecord
    events: tuple[SimulationEvent, ...]
    shadow_evaluation: ShadowEvaluation | None
    shadow_outcome: ShadowOutcome | None

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(self.candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        if not isinstance(self.snapshot, CandidateSnapshot):
            raise TypeError("snapshot must be a CandidateSnapshot")

        if not isinstance(self.disposition, DispositionRecord):
            raise TypeError("disposition must be a DispositionRecord")

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


class SimulationRepository:
    """
    Sole durable writer for Simulation-owned records. Every write is
    append-only: an absent identity inserts, an identical
    reconstructed payload at an existing identity is idempotent, and
    a conflicting payload at an existing identity hard-fails without
    overwriting anything.
    """

    def __init__(self, db_path: str | Path) -> None:
        database_path = Path(db_path)

        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_path.touch(exist_ok=True)

        self._lock = RLock()

        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

        self.create_schema()

    def create_schema(self) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_schema_metadata (
                    schema_key TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_candidates (
                    campaign_id TEXT NOT NULL,
                    campaign_revision INTEGER NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_or_version TEXT,
                    revision_or_version_key TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    market TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_trigger TEXT NOT NULL,
                    entry TEXT,
                    invalidation TEXT,
                    targets_json TEXT NOT NULL,
                    detection_json TEXT NOT NULL,
                    policy_references_json TEXT NOT NULL,
                    PRIMARY KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    )
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_dispositions (
                    campaign_id TEXT NOT NULL,
                    campaign_revision INTEGER NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_or_version TEXT,
                    revision_or_version_key TEXT NOT NULL,
                    disposition TEXT NOT NULL CHECK (
                        disposition IN (
                            'ADMITTED_FOR_SIMULATION', 'REJECTED',
                            'BLOCKED', 'NO_TRADE'
                        )
                    ),
                    reason_references_json TEXT NOT NULL,
                    reason_notes_json TEXT NOT NULL,
                    recorded_fact_json TEXT NOT NULL,
                    PRIMARY KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ),
                    FOREIGN KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ) REFERENCES simulation_candidates (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    )
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_events (
                    campaign_id TEXT NOT NULL,
                    campaign_revision INTEGER NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_or_version TEXT,
                    revision_or_version_key TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence > 0),
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'WAITING_ENTRY', 'SIMULATED_FILL', 'ACTIVE',
                            'TERMINAL_OUTCOME', 'CENSORED', 'UNKNOWN'
                        )
                    ),
                    mechanics_json TEXT,
                    observation_json TEXT,
                    recorded_fact_json TEXT NOT NULL,
                    PRIMARY KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key,
                        case_id, attempt_id, sequence
                    ),
                    FOREIGN KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ) REFERENCES simulation_candidates (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    )
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_shadow_evaluations (
                    campaign_id TEXT NOT NULL,
                    campaign_revision INTEGER NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_or_version TEXT,
                    revision_or_version_key TEXT NOT NULL,
                    disposition TEXT NOT NULL CHECK (
                        disposition IN ('REJECTED', 'BLOCKED', 'NO_TRADE')
                    ),
                    counterfactual INTEGER NOT NULL CHECK (counterfactual = 1),
                    order_created INTEGER NOT NULL CHECK (order_created = 0),
                    trade_created INTEGER NOT NULL CHECK (trade_created = 0),
                    recorded_fact_json TEXT NOT NULL,
                    PRIMARY KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ),
                    FOREIGN KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ) REFERENCES simulation_dispositions (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    )
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS simulation_shadow_outcomes (
                    campaign_id TEXT NOT NULL,
                    campaign_revision INTEGER NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    revision_or_version TEXT,
                    revision_or_version_key TEXT NOT NULL,
                    outcome_type TEXT NOT NULL CHECK (
                        outcome_type IN (
                            'TERMINAL_OUTCOME', 'CENSORED', 'UNKNOWN'
                        )
                    ),
                    observation_json TEXT,
                    recorded_fact_json TEXT NOT NULL,
                    PRIMARY KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ),
                    FOREIGN KEY (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    ) REFERENCES simulation_shadow_evaluations (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version_key
                    )
                )
                """
            )

            cursor = self.connection.execute(
                "SELECT schema_version FROM simulation_schema_metadata "
                "WHERE schema_key = ?",
                (_SCHEMA_KEY,),
            )
            row = cursor.fetchone()

            if row is None:
                self.connection.execute(
                    "INSERT INTO simulation_schema_metadata "
                    "(schema_key, schema_version) VALUES (?, ?)",
                    (_SCHEMA_KEY, _SCHEMA_VERSION),
                )
            elif row["schema_version"] != _SCHEMA_VERSION:
                raise SimulationSchemaVersionError(
                    f"unsupported simulation schema version "
                    f"{row['schema_version']} (expected {_SCHEMA_VERSION})"
                )

    # -- candidates ---------------------------------------------------

    def append_candidate(
        self,
        campaign: SimulationCampaignReference,
        snapshot: CandidateSnapshot,
    ) -> CandidateSnapshot:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(snapshot, CandidateSnapshot):
            raise TypeError("snapshot must be a CandidateSnapshot")

        row_values = (
            campaign.campaign_id,
            campaign.revision,
            snapshot.candidate.source_domain,
            snapshot.candidate.source_type,
            snapshot.candidate.source_id,
            snapshot.candidate.revision_or_version,
            _null_safe_key(snapshot.candidate.revision_or_version),
            snapshot.strategy.strategy_id,
            snapshot.strategy.version,
            snapshot.instrument,
            snapshot.venue,
            snapshot.market,
            snapshot.timeframe,
            snapshot.direction,
            snapshot.entry_trigger,
            str(snapshot.entry) if snapshot.entry is not None else None,
            str(snapshot.invalidation) if snapshot.invalidation is not None else None,
            json.dumps([str(target) for target in snapshot.targets]),
            json.dumps(_temporal_fact_to_dict(snapshot.detection)),
            json.dumps(
                [_policy_to_dict(policy) for policy in snapshot.policy_references]
            ),
        )

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO simulation_candidates (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version,
                        revision_or_version_key, strategy_id, strategy_version,
                        instrument, venue, market, timeframe, direction,
                        entry_trigger, entry, invalidation, targets_json,
                        detection_json, policy_references_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row_values,
                )
        except sqlite3.IntegrityError:
            existing = self.get_candidate(campaign, snapshot.candidate)

            if existing is not None:
                if existing == snapshot:
                    return existing

                raise SimulationConflictError(
                    "candidate already exists with a different snapshot"
                ) from None

            raise SimulationPersistenceError(
                "candidate insert conflicted but no existing row was found"
            ) from None
        except sqlite3.Error as exc:
            raise SimulationPersistenceError(str(exc)) from exc

        return snapshot

    def get_candidate(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
    ) -> CandidateSnapshot | None:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_candidates WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ?",
                _candidate_identity_values(campaign, candidate),
            )
            row = cursor.fetchone()

        return _row_to_candidate_snapshot(row) if row is not None else None

    # -- dispositions ---------------------------------------------------

    def append_disposition(self, record: DispositionRecord) -> DispositionRecord:
        if not isinstance(record, DispositionRecord):
            raise TypeError("record must be a DispositionRecord")

        existing_candidate = self.get_candidate(record.campaign, record.snapshot.candidate)

        if existing_candidate is None:
            raise SimulationLineageError(
                "candidate must be appended before its disposition"
            )

        if existing_candidate != record.snapshot:
            raise SimulationConflictError(
                "disposition snapshot does not match the stored candidate snapshot"
            )

        row_values = (
            record.campaign.campaign_id,
            record.campaign.revision,
            record.snapshot.candidate.source_domain,
            record.snapshot.candidate.source_type,
            record.snapshot.candidate.source_id,
            record.snapshot.candidate.revision_or_version,
            _null_safe_key(record.snapshot.candidate.revision_or_version),
            record.disposition.value,
            json.dumps(
                [_reason_reference_to_dict(item) for item in record.reason_references]
            ),
            json.dumps(list(record.reason_notes)),
            json.dumps(_temporal_fact_to_dict(record.recorded_fact)),
        )

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO simulation_dispositions (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version,
                        revision_or_version_key, disposition,
                        reason_references_json, reason_notes_json,
                        recorded_fact_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row_values,
                )
        except sqlite3.IntegrityError:
            existing = self.get_disposition(record.campaign, record.snapshot.candidate)

            if existing is not None:
                if existing == record:
                    return existing

                raise SimulationConflictError(
                    "disposition already exists with a different payload"
                ) from None

            raise SimulationPersistenceError(
                "disposition insert conflicted but no existing row was found"
            ) from None
        except sqlite3.Error as exc:
            raise SimulationPersistenceError(str(exc)) from exc

        return record

    def get_disposition(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
    ) -> DispositionRecord | None:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_dispositions WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ?",
                _candidate_identity_values(campaign, candidate),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        snapshot = self.get_candidate(campaign, candidate)

        if snapshot is None:
            raise SimulationPersistenceError(
                "disposition row found without a matching candidate row"
            )

        return _row_to_disposition_record(row, campaign, snapshot)

    # -- events ---------------------------------------------------

    def append_event(self, event: SimulationEvent) -> SimulationEvent:
        if not isinstance(event, SimulationEvent):
            raise TypeError("event must be a SimulationEvent")

        disposition = self.get_disposition(event.campaign, event.candidate)

        if (
            disposition is None
            or disposition.disposition is not SimulationDisposition.ADMITTED_FOR_SIMULATION
        ):
            raise SimulationLineageError(
                "event requires an existing ADMITTED_FOR_SIMULATION disposition"
            )

        existing_events = self._get_all_events_for_candidate(
            event.campaign, event.candidate
        )

        if existing_events and (
            existing_events[0].reference.case_id != event.reference.case_id
            or existing_events[0].reference.attempt_id != event.reference.attempt_id
        ):
            raise SimulationLineageError(
                "only one case/attempt lineage is permitted per candidate in v1"
            )

        existing_at_sequence = next(
            (
                item
                for item in existing_events
                if item.reference.sequence == event.reference.sequence
            ),
            None,
        )

        if existing_at_sequence is not None:
            if existing_at_sequence == event:
                return existing_at_sequence

            raise SimulationConflictError(
                f"event at sequence {event.reference.sequence} already exists "
                "with a different payload"
            )

        prospective = existing_events + (event,)
        replay = replay_simulation_events(prospective)

        if replay.status is not SimulationReplayStatus.VALID:
            raise SimulationLineageError(
                "appending this event would produce an invalid replay: "
                f"{[reason.value for reason in replay.reasons]}"
            )

        row_values = (
            event.campaign.campaign_id,
            event.campaign.revision,
            event.candidate.source_domain,
            event.candidate.source_type,
            event.candidate.source_id,
            event.candidate.revision_or_version,
            _null_safe_key(event.candidate.revision_or_version),
            event.reference.case_id,
            event.reference.attempt_id,
            event.reference.sequence,
            event.event_type.value,
            json.dumps(_mechanics_to_dict(event.mechanics))
            if event.mechanics is not None
            else None,
            json.dumps(_observation_evidence_to_dict(event.observation))
            if event.observation is not None
            else None,
            json.dumps(_temporal_fact_to_dict(event.recorded_fact)),
        )

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO simulation_events (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version,
                        revision_or_version_key, case_id, attempt_id,
                        sequence, event_type, mechanics_json,
                        observation_json, recorded_fact_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row_values,
                )
        except sqlite3.IntegrityError:
            raise SimulationConflictError(
                "event insert conflicted with an existing row"
            ) from None
        except sqlite3.Error as exc:
            raise SimulationPersistenceError(str(exc)) from exc

        return event

    def get_case_events(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
        case_id: str,
        attempt_id: str,
    ) -> tuple[SimulationEvent, ...]:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        if not isinstance(case_id, str):
            raise TypeError("case_id must be a str")

        if not isinstance(attempt_id, str):
            raise TypeError("attempt_id must be a str")

        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_events WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ? AND case_id = ? AND "
                "attempt_id = ? ORDER BY sequence ASC",
                _candidate_identity_values(campaign, candidate) + (case_id, attempt_id),
            )
            rows = cursor.fetchall()

        return tuple(_row_to_event(row) for row in rows)

    def _get_all_events_for_candidate(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
    ) -> tuple[SimulationEvent, ...]:
        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_events WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ? ORDER BY sequence ASC",
                _candidate_identity_values(campaign, candidate),
            )
            rows = cursor.fetchall()

        return tuple(_row_to_event(row) for row in rows)

    # -- shadow evaluation / outcome ---------------------------------------------------

    def append_shadow_evaluation(self, evaluation: ShadowEvaluation) -> ShadowEvaluation:
        if not isinstance(evaluation, ShadowEvaluation):
            raise TypeError("evaluation must be a ShadowEvaluation")

        disposition = self.get_disposition(
            evaluation.campaign, evaluation.snapshot.candidate
        )

        if disposition is None or disposition.disposition not in _SHADOW_ELIGIBLE_DISPOSITIONS:
            raise SimulationLineageError(
                "shadow evaluation requires an existing REJECTED, BLOCKED, "
                "or NO_TRADE disposition"
            )

        if disposition.disposition is not evaluation.disposition:
            raise SimulationConflictError(
                "shadow evaluation disposition does not match the stored disposition"
            )

        row_values = (
            evaluation.campaign.campaign_id,
            evaluation.campaign.revision,
            evaluation.snapshot.candidate.source_domain,
            evaluation.snapshot.candidate.source_type,
            evaluation.snapshot.candidate.source_id,
            evaluation.snapshot.candidate.revision_or_version,
            _null_safe_key(evaluation.snapshot.candidate.revision_or_version),
            evaluation.disposition.value,
            int(evaluation.counterfactual),
            int(evaluation.order_created),
            int(evaluation.trade_created),
            json.dumps(_temporal_fact_to_dict(evaluation.recorded_fact)),
        )

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO simulation_shadow_evaluations (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version,
                        revision_or_version_key, disposition, counterfactual,
                        order_created, trade_created, recorded_fact_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row_values,
                )
        except sqlite3.IntegrityError:
            existing = self.get_shadow_evaluation(
                evaluation.campaign, evaluation.snapshot.candidate
            )

            if existing is not None:
                if existing == evaluation:
                    return existing

                raise SimulationConflictError(
                    "shadow evaluation already exists with a different payload"
                ) from None

            raise SimulationPersistenceError(
                "shadow evaluation insert conflicted but no existing row was found"
            ) from None
        except sqlite3.Error as exc:
            raise SimulationPersistenceError(str(exc)) from exc

        return evaluation

    def get_shadow_evaluation(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
    ) -> ShadowEvaluation | None:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_shadow_evaluations WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ?",
                _candidate_identity_values(campaign, candidate),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        snapshot = self.get_candidate(campaign, candidate)

        if snapshot is None:
            raise SimulationPersistenceError(
                "shadow evaluation row found without a matching candidate row"
            )

        return _row_to_shadow_evaluation(row, campaign, snapshot)

    def append_shadow_outcome(self, outcome: ShadowOutcome) -> ShadowOutcome:
        if not isinstance(outcome, ShadowOutcome):
            raise TypeError("outcome must be a ShadowOutcome")

        campaign = outcome.evaluation.campaign
        candidate = outcome.evaluation.snapshot.candidate

        existing_evaluation = self.get_shadow_evaluation(campaign, candidate)

        if existing_evaluation is None or existing_evaluation != outcome.evaluation:
            raise SimulationLineageError(
                "shadow outcome requires a matching existing shadow evaluation"
            )

        row_values = (
            campaign.campaign_id,
            campaign.revision,
            candidate.source_domain,
            candidate.source_type,
            candidate.source_id,
            candidate.revision_or_version,
            _null_safe_key(candidate.revision_or_version),
            outcome.outcome_type.value,
            json.dumps(_observation_evidence_to_dict(outcome.observation))
            if outcome.observation is not None
            else None,
            json.dumps(_temporal_fact_to_dict(outcome.recorded_fact)),
        )

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO simulation_shadow_outcomes (
                        campaign_id, campaign_revision, source_domain,
                        source_type, source_id, revision_or_version,
                        revision_or_version_key, outcome_type,
                        observation_json, recorded_fact_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row_values,
                )
        except sqlite3.IntegrityError:
            existing = self.get_shadow_outcome(campaign, candidate)

            if existing is not None:
                if existing == outcome:
                    return existing

                raise SimulationConflictError(
                    "shadow outcome already exists with a different payload"
                ) from None

            raise SimulationPersistenceError(
                "shadow outcome insert conflicted but no existing row was found"
            ) from None
        except sqlite3.Error as exc:
            raise SimulationPersistenceError(str(exc)) from exc

        return outcome

    def get_shadow_outcome(
        self,
        campaign: SimulationCampaignReference,
        candidate: SimulationCandidateReference,
    ) -> ShadowOutcome | None:
        if not isinstance(campaign, SimulationCampaignReference):
            raise TypeError("campaign must be a SimulationCampaignReference")

        if not isinstance(candidate, SimulationCandidateReference):
            raise TypeError("candidate must be a SimulationCandidateReference")

        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM simulation_shadow_outcomes WHERE "
                "campaign_id = ? AND campaign_revision = ? AND "
                "source_domain = ? AND source_type = ? AND source_id = ? "
                "AND revision_or_version_key = ?",
                _candidate_identity_values(campaign, candidate),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        evaluation = self.get_shadow_evaluation(campaign, candidate)

        if evaluation is None:
            raise SimulationPersistenceError(
                "shadow outcome row found without a matching shadow evaluation row"
            )

        return _row_to_shadow_outcome(row, evaluation)

    # -- read-only evidence query ---------------------------------------------------

    def query_evidence(
        self, query: SimulationEvidenceQuery
    ) -> tuple[SimulationEvidenceBundle, ...]:
        if not isinstance(query, SimulationEvidenceQuery):
            raise TypeError("query must be a SimulationEvidenceQuery")

        clauses: list[str] = []
        params: list[object] = []

        if query.campaign is not None:
            clauses.append("d.campaign_id = ? AND d.campaign_revision = ?")
            params.extend([query.campaign.campaign_id, query.campaign.revision])

        if query.disposition is not None:
            clauses.append("d.disposition = ?")
            params.append(query.disposition.value)

        if query.instrument is not None:
            clauses.append("c.instrument = ?")
            params.append(query.instrument)

        if query.timeframe is not None:
            clauses.append("c.timeframe = ?")
            params.append(query.timeframe)

        if query.direction is not None:
            clauses.append("c.direction = ?")
            params.append(query.direction)

        if query.strategy is not None:
            clauses.append("c.strategy_id = ? AND c.strategy_version = ?")
            params.extend([query.strategy.strategy_id, query.strategy.version])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            cursor = self.connection.execute(
                f"""
                SELECT d.campaign_id, d.campaign_revision, d.source_domain,
                       d.source_type, d.source_id, d.revision_or_version_key
                FROM simulation_dispositions d
                JOIN simulation_candidates c
                  ON c.campaign_id = d.campaign_id
                 AND c.campaign_revision = d.campaign_revision
                 AND c.source_domain = d.source_domain
                 AND c.source_type = d.source_type
                 AND c.source_id = d.source_id
                 AND c.revision_or_version_key = d.revision_or_version_key
                {where_sql}
                """,
                params,
            )
            identity_rows = cursor.fetchall()

            bundles: list[SimulationEvidenceBundle] = []

            for identity_row in identity_rows:
                campaign = SimulationCampaignReference(
                    campaign_id=identity_row["campaign_id"],
                    revision=identity_row["campaign_revision"],
                )
                candidate_cursor = self.connection.execute(
                    "SELECT * FROM simulation_candidates WHERE "
                    "campaign_id = ? AND campaign_revision = ? AND "
                    "source_domain = ? AND source_type = ? AND source_id = ? "
                    "AND revision_or_version_key = ?",
                    (
                        identity_row["campaign_id"],
                        identity_row["campaign_revision"],
                        identity_row["source_domain"],
                        identity_row["source_type"],
                        identity_row["source_id"],
                        identity_row["revision_or_version_key"],
                    ),
                )
                candidate_row = candidate_cursor.fetchone()
                snapshot = _row_to_candidate_snapshot(candidate_row)
                candidate = snapshot.candidate

                disposition = self.get_disposition(campaign, candidate)
                events = self._get_all_events_for_candidate(campaign, candidate)
                shadow_evaluation = self.get_shadow_evaluation(campaign, candidate)
                shadow_outcome = self.get_shadow_outcome(campaign, candidate)

                bundle = SimulationEvidenceBundle(
                    campaign=campaign,
                    candidate=candidate,
                    snapshot=snapshot,
                    disposition=disposition,
                    events=events,
                    shadow_evaluation=shadow_evaluation,
                    shadow_outcome=shadow_outcome,
                )

                if not _bundle_matches_remaining_filters(bundle, query):
                    continue

                bundles.append(bundle)

        return tuple(bundles)


def _bundle_matches_remaining_filters(
    bundle: SimulationEvidenceBundle, query: SimulationEvidenceQuery
) -> bool:
    if query.reason_reference is not None:
        if query.reason_reference not in bundle.disposition.reason_references:
            return False

    if query.policy_reference is not None:
        if query.policy_reference not in bundle.snapshot.policy_references:
            return False

    if query.mechanics is not None:
        if not any(event.mechanics == query.mechanics for event in bundle.events):
            return False

    if query.event_type is not None:
        matches_event = any(
            event.event_type is query.event_type for event in bundle.events
        )
        matches_shadow_outcome = (
            bundle.shadow_outcome is not None
            and bundle.shadow_outcome.outcome_type is query.event_type
        )
        if not (matches_event or matches_shadow_outcome):
            return False

    if query.admitted_only is not None:
        is_admitted = (
            bundle.disposition.disposition
            is SimulationDisposition.ADMITTED_FOR_SIMULATION
        )
        if query.admitted_only != is_admitted:
            return False

    return True


def _row_to_candidate_snapshot(row: sqlite3.Row) -> CandidateSnapshot:
    return CandidateSnapshot(
        candidate=SimulationCandidateReference(
            source_domain=row["source_domain"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            revision_or_version=row["revision_or_version"],
        ),
        strategy=SimulationStrategyReference(
            strategy_id=row["strategy_id"], version=row["strategy_version"]
        ),
        instrument=row["instrument"],
        venue=row["venue"],
        market=row["market"],
        timeframe=row["timeframe"],
        direction=row["direction"],
        entry_trigger=row["entry_trigger"],
        entry=Decimal(row["entry"]) if row["entry"] is not None else None,
        invalidation=(
            Decimal(row["invalidation"]) if row["invalidation"] is not None else None
        ),
        targets=tuple(Decimal(item) for item in json.loads(row["targets_json"])),
        detection=_temporal_fact_from_dict(json.loads(row["detection_json"])),
        policy_references=tuple(
            _policy_from_dict(item)
            for item in json.loads(row["policy_references_json"])
        ),
    )


def _row_to_disposition_record(
    row: sqlite3.Row,
    campaign: SimulationCampaignReference,
    snapshot: CandidateSnapshot,
) -> DispositionRecord:
    return DispositionRecord(
        campaign=campaign,
        snapshot=snapshot,
        disposition=SimulationDisposition(row["disposition"]),
        reason_references=tuple(
            _reason_reference_from_dict(item)
            for item in json.loads(row["reason_references_json"])
        ),
        recorded_fact=_temporal_fact_from_dict(json.loads(row["recorded_fact_json"])),
        reason_notes=tuple(json.loads(row["reason_notes_json"])),
    )


def _row_to_event(row: sqlite3.Row) -> SimulationEvent:
    return SimulationEvent(
        reference=SimulationEventReference(
            case_id=row["case_id"],
            attempt_id=row["attempt_id"],
            sequence=row["sequence"],
        ),
        campaign=SimulationCampaignReference(
            campaign_id=row["campaign_id"], revision=row["campaign_revision"]
        ),
        candidate=SimulationCandidateReference(
            source_domain=row["source_domain"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            revision_or_version=row["revision_or_version"],
        ),
        event_type=SimulationEventType(row["event_type"]),
        mechanics=(
            _mechanics_from_dict(json.loads(row["mechanics_json"]))
            if row["mechanics_json"] is not None
            else None
        ),
        observation=(
            _observation_evidence_from_dict(json.loads(row["observation_json"]))
            if row["observation_json"] is not None
            else None
        ),
        recorded_fact=_temporal_fact_from_dict(json.loads(row["recorded_fact_json"])),
    )


def _row_to_shadow_evaluation(
    row: sqlite3.Row,
    campaign: SimulationCampaignReference,
    snapshot: CandidateSnapshot,
) -> ShadowEvaluation:
    return ShadowEvaluation(
        campaign=campaign,
        snapshot=snapshot,
        disposition=SimulationDisposition(row["disposition"]),
        counterfactual=bool(row["counterfactual"]),
        order_created=bool(row["order_created"]),
        trade_created=bool(row["trade_created"]),
        recorded_fact=_temporal_fact_from_dict(json.loads(row["recorded_fact_json"])),
    )


def _row_to_shadow_outcome(
    row: sqlite3.Row, evaluation: ShadowEvaluation
) -> ShadowOutcome:
    return ShadowOutcome(
        evaluation=evaluation,
        outcome_type=SimulationEventType(row["outcome_type"]),
        observation=(
            _observation_evidence_from_dict(json.loads(row["observation_json"]))
            if row["observation_json"] is not None
            else None
        ),
        recorded_fact=_temporal_fact_from_dict(json.loads(row["recorded_fact_json"])),
    )
