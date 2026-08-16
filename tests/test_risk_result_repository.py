"""
MarketHunter

Tests for the durable RiskResultRecord model and the Risk-owned
RiskResultRepository.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.risk_result import RiskResult
from models.risk_result_record import IdentityState, RiskResultRecord
from risk.storage.risk_result_repository import (
    RiskResultConflictError,
    RiskResultLineageError,
    RiskResultRepository,
)


def make_risk_result() -> RiskResult:
    return RiskResult(
        entry=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        risk_reward=2.0,
        position_size=10.0,
        risk_amount=50.0,
        account_size=10000.0,
        risk_percent=0.5,
    )


def make_record(
    *,
    risk_result_id: str = "risk-1",
    revision: int = 1,
    supersedes_revision: int | None = None,
    generated_at: datetime | None = None,
    source_state: IdentityState = IdentityState.KNOWN,
    source_reference_kind: str | None = "signal",
    source_reference: str | None = "sig-1",
    risk_policy_state: IdentityState = IdentityState.KNOWN,
    risk_policy_version: str | None = "policy-v1",
    strategy_name: str | None = "core-breakout",
    strategy_version_state: IdentityState = IdentityState.KNOWN,
    strategy_version: str | None = "1.0.0",
) -> RiskResultRecord:
    return RiskResultRecord.from_risk_result(
        make_risk_result(),
        risk_result_id=risk_result_id,
        revision=revision,
        generated_at=generated_at or datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        supersedes_revision=supersedes_revision,
        source_state=source_state,
        source_reference_kind=source_reference_kind,
        source_reference=source_reference,
        risk_policy_state=risk_policy_state,
        risk_policy_version=risk_policy_version,
        strategy_name=strategy_name,
        strategy_version_state=strategy_version_state,
        strategy_version=strategy_version,
    )


class RiskResultRecordTests(unittest.TestCase):
    def test_frozen_record(self) -> None:
        record = make_record()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.entry = 999.0  # type: ignore[misc]

    def test_unknown_source_requires_null_kind_and_reference(self) -> None:
        record = make_record(
            source_state=IdentityState.UNKNOWN,
            source_reference_kind=None,
            source_reference=None,
        )

        self.assertEqual(record.source_state, IdentityState.UNKNOWN)
        self.assertIsNone(record.source_reference_kind)
        self.assertIsNone(record.source_reference)

    def test_unknown_strategy_version_requires_null_value(self) -> None:
        record = make_record(
            strategy_version_state=IdentityState.UNKNOWN,
            strategy_version=None,
        )

        self.assertEqual(record.strategy_version_state, IdentityState.UNKNOWN)
        self.assertIsNone(record.strategy_version)

    def test_unknown_risk_policy_requires_null_version(self) -> None:
        record = make_record(
            risk_policy_state=IdentityState.UNKNOWN,
            risk_policy_version=None,
        )

        self.assertEqual(record.risk_policy_state, IdentityState.UNKNOWN)
        self.assertIsNone(record.risk_policy_version)

    def test_known_source_with_null_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(
                source_state=IdentityState.KNOWN,
                source_reference_kind=None,
                source_reference=None,
            )

    def test_known_risk_policy_with_null_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(
                risk_policy_state=IdentityState.KNOWN,
                risk_policy_version=None,
            )

    def test_unknown_source_with_non_null_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(
                source_state=IdentityState.UNKNOWN,
                source_reference_kind="signal",
                source_reference=None,
            )

    def test_blank_risk_result_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(risk_result_id="   ")

    def test_blank_optional_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(source_reference="   ")

    def test_naive_generated_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(generated_at=datetime(2026, 8, 15, 12, 0))

    def test_non_utc_generated_at_rejected(self) -> None:
        offset_tz = timezone(timedelta(hours=-5))

        with self.assertRaises(ValueError):
            make_record(generated_at=datetime(2026, 8, 15, 12, 0, tzinfo=offset_tz))

    def test_from_risk_result_requires_explicit_id(self) -> None:
        with self.assertRaises(TypeError):
            RiskResultRecord.from_risk_result(  # type: ignore[call-arg]
                make_risk_result(),
                revision=1,
                generated_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
                source_state=IdentityState.UNKNOWN,
                risk_policy_state=IdentityState.UNKNOWN,
                strategy_version_state=IdentityState.UNKNOWN,
            )

    def test_module_does_not_import_research_trade(self) -> None:
        import models.risk_result_record as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import ResearchTrade", source)
        self.assertNotIn("research.models.trade", source)
        self.assertFalse(hasattr(module, "ResearchTrade"))


class RiskResultRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "risk_result.db"
        self.repository = RiskResultRepository(self.db_path)

    def tearDown(self) -> None:
        self.repository.connection.close()
        self.temp_dir.cleanup()

    def test_round_trip_payload_and_provenance(self) -> None:
        record = make_record()
        self.repository.append_first(record)

        fetched = self.repository.get("risk-1", 1)

        self.assertEqual(fetched, record)

    def test_append_first_stores_revision_one(self) -> None:
        record = make_record(revision=1, supersedes_revision=None)
        stored = self.repository.append_first(record)

        self.assertEqual(stored.revision, 1)
        self.assertIsNone(stored.supersedes_revision)

    def test_append_first_rejects_non_first_revision(self) -> None:
        with self.assertRaises(RiskResultLineageError):
            self.repository.append_first(
                make_record(revision=2, supersedes_revision=1)
            )

    def test_valid_supersession(self) -> None:
        first = make_record(revision=1, supersedes_revision=None)
        self.repository.append_first(first)

        second = make_record(
            revision=2,
            supersedes_revision=1,
            source_reference="sig-2",
        )
        stored = self.repository.append_superseding(second)

        self.assertEqual(stored.revision, 2)
        self.assertEqual(stored.supersedes_revision, 1)

    def test_historical_revision_unchanged_after_supersession(self) -> None:
        first = make_record(revision=1, supersedes_revision=None)
        self.repository.append_first(first)

        second = make_record(
            revision=2,
            supersedes_revision=1,
            source_reference="sig-2",
        )
        self.repository.append_superseding(second)

        historical = self.repository.get("risk-1", 1)

        self.assertEqual(historical, first)

    def test_deterministic_latest_revision(self) -> None:
        first = make_record(revision=1, supersedes_revision=None)
        self.repository.append_first(first)

        second = make_record(
            revision=2,
            supersedes_revision=1,
            source_reference="sig-2",
        )
        self.repository.append_superseding(second)

        latest = self.repository.get_latest("risk-1")

        self.assertEqual(latest, second)

    def test_identical_duplicate_append_is_idempotent(self) -> None:
        record = make_record()
        self.repository.append_first(record)
        result = self.repository.append_first(record)

        self.assertEqual(result, record)

        cursor = self.repository.connection.execute(
            "SELECT COUNT(*) FROM risk_result_records "
            "WHERE risk_result_id = ? AND revision = ?",
            ("risk-1", 1),
        )
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_differing_duplicate_raises_conflict(self) -> None:
        self.repository.append_first(make_record())

        with self.assertRaises(RiskResultConflictError):
            self.repository.append_first(
                make_record(source_reference="sig-different")
            )

    def test_missing_predecessor_raises_lineage_error(self) -> None:
        second = make_record(revision=2, supersedes_revision=1)

        with self.assertRaises(RiskResultLineageError):
            self.repository.append_superseding(second)

    def test_get_missing_record_returns_none(self) -> None:
        self.assertIsNone(self.repository.get("missing", 1))

    def test_get_latest_missing_lineage_returns_none(self) -> None:
        self.assertIsNone(self.repository.get_latest("missing"))

    def test_no_update_or_delete_surface(self) -> None:
        public_methods = {
            name
            for name in dir(RiskResultRepository)
            if not name.startswith("_")
            and callable(getattr(RiskResultRepository, name))
        }

        self.assertNotIn("update", public_methods)
        self.assertNotIn("delete", public_methods)
        self.assertEqual(
            public_methods,
            {
                "create_schema",
                "append_first",
                "append_superseding",
                "get",
                "get_latest",
            },
        )


if __name__ == "__main__":
    unittest.main()
