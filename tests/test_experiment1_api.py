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


if __name__ == "__main__":
    unittest.main()
