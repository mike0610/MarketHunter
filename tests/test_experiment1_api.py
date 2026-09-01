"""
MarketHunter

Tests for the Experiment 1 API (api/experiment1_api.py), in particular
GET /experiment1/state after the Investments ledger split - the legacy
AccountKind.INVESTMENTS is no longer created for a fresh deployment and
must not crash the endpoint.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api.app import app


class Experiment1StateEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "experiment1.db"
        self.env_patch = mock.patch.dict(
            "os.environ", {"EXPERIMENT1_DB_PATH": str(self.db_path)}
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)

    def test_state_does_not_crash_on_fresh_deployment(self) -> None:
        response = self.client.get("/experiment1/state")
        self.assertEqual(response.status_code, 200)

    def test_state_reports_exactly_the_five_canonical_accounts(self) -> None:
        response = self.client.get("/experiment1/state")
        accounts = {row["account"] for row in response.json()["accounts"]}
        self.assertEqual(
            accounts,
            {
                "INVESTMENTS_DEFENSIVE",
                "INVESTMENTS_BALANCED",
                "INVESTMENTS_GROWTH",
                "SPOT",
                "FUTURES",
            },
        )

    def test_investments_ledgers_start_at_5000_spot_futures_at_2000(self) -> None:
        response = self.client.get("/experiment1/state")
        by_account = {row["account"]: row for row in response.json()["accounts"]}
        for ledger in ("INVESTMENTS_DEFENSIVE", "INVESTMENTS_BALANCED", "INVESTMENTS_GROWTH"):
            self.assertEqual(by_account[ledger]["cash"], "5000")
        self.assertEqual(by_account["SPOT"]["cash"], "2000")
        self.assertEqual(by_account["FUTURES"]["cash"], "2000")


class GilDecisionInboxEndpointTests(unittest.TestCase):
    """
    POST /experiment1/gil-decisions -> durable inbox only. This
    endpoint never calls submit_intent/execute_pending itself - see
    experiment1.gil_decision.drain_gil_decision_inbox (run by the
    tools/experiment1_runtime scheduler) for the actual processing.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "experiment1.db"
        self.env_patch = mock.patch.dict(
            "os.environ", {"EXPERIMENT1_DB_PATH": str(self.db_path)}
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)

    def _payload(self, **overrides) -> dict:
        data = {
            "decision_id": "gil-001",
            "decided_at": "2026-09-01T03:00:00+00:00",
            "account": "FUTURES",
            "action": "LONG",
            "symbol": "BTCUSDT",
            "thesis": "breakout confirmed above resistance",
            "quantity": "1",
            "leverage": "2",
        }
        data.update(overrides)
        return data

    def test_post_accepts_a_valid_decision_as_pending_drain(self) -> None:
        response = self.client.post("/experiment1/gil-decisions", json=self._payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision_id"], "gil-001")
        self.assertEqual(body["status"], "PENDING_DRAIN")
        self.assertIsNone(body["outcome"])

        # Nothing executable exists yet - only the drain cycle processes it.
        state = self.client.get("/experiment1/state").json()
        futures = next(a for a in state["accounts"] if a["account"] == "FUTURES")
        self.assertEqual(futures["positions"], [])

    def test_post_rejects_a_non_action_research_state_at_the_schema_level(self) -> None:
        response = self.client.post(
            "/experiment1/gil-decisions", json=self._payload(action="CANDIDATE")
        )
        # FastAPI/Pydantic schema validation rejects it before any
        # domain logic runs - never coerced into a trade action.
        self.assertEqual(response.status_code, 422)

    def test_post_rejects_a_naive_decided_at_as_malformed_and_persists_it(self) -> None:
        response = self.client.post(
            "/experiment1/gil-decisions",
            json=self._payload(decision_id="gil-naive", decided_at="2026-09-01T03:00:00"),
        )
        self.assertEqual(response.status_code, 400)

        status = self.client.get("/experiment1/gil-decisions/gil-naive").json()
        self.assertEqual(status["status"], "MALFORMED")
        self.assertIn("timezone-aware", status["outcome_reason"])

    def test_post_identical_resubmission_is_idempotent(self) -> None:
        payload = self._payload(decision_id="gil-dup")
        first = self.client.post("/experiment1/gil-decisions", json=payload)
        second = self.client.post("/experiment1/gil-decisions", json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())

    def test_post_same_decision_id_different_content_is_a_conflict(self) -> None:
        self.client.post("/experiment1/gil-decisions", json=self._payload(decision_id="gil-conflict"))
        response = self.client.post(
            "/experiment1/gil-decisions",
            json=self._payload(decision_id="gil-conflict", quantity="5"),
        )
        self.assertEqual(response.status_code, 409)

    def test_get_readback_returns_404_for_unknown_decision(self) -> None:
        response = self.client.get("/experiment1/gil-decisions/never-submitted")
        self.assertEqual(response.status_code, 404)

    def test_get_readback_matches_the_post_response_before_drain(self) -> None:
        post_body = self.client.post(
            "/experiment1/gil-decisions", json=self._payload(decision_id="gil-readback")
        ).json()
        get_body = self.client.get("/experiment1/gil-decisions/gil-readback").json()

        self.assertEqual(post_body, get_body)


if __name__ == "__main__":
    unittest.main()
