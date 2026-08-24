"""
MarketHunter

Tests for Outcome Intelligence acquisition
(tools/outcome_intelligence/acquisition.py).
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from tools.outcome_intelligence.acquisition import (
    OutcomeIntelligenceResponseError,
    OutcomeIntelligenceRunConflictError,
    RawSnapshot,
    SETUP_REASONS_ENDPOINT,
    STATISTICS_ENDPOINT,
    capture_outcome_intelligence_run,
    fetch_raw_snapshot,
    list_run_manifests,
    load_run_payload,
)

FIXED_NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)

STATISTICS_BODY = {
    "total": 100,
    "wins": 40,
    "losses": 30,
    "win_rate": 57.1,
}

SETUP_REASONS_BODY = {
    "by_strategy": [
        {
            "label": "Breakout",
            "total": 100,
            "clean_completed": 70,
            "wins": 40,
            "losses": 30,
            "win_rate": 57.1,
            "total_profit": 12.5,
        }
    ],
}


def _client_for(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def _json_handler(body: dict, status_code: int = 200, content_type: str = "application/json"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=json.dumps(body).encode("utf-8"),
            headers={"content-type": content_type},
        )

    return handler


def _routed_handler(routes: dict[str, dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes[request.url.path]
        return httpx.Response(
            200,
            content=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    return handler


class FetchRawSnapshotTests(unittest.TestCase):
    def test_captures_exact_raw_bytes(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY))

        snapshot = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(
            snapshot.raw_bytes, json.dumps(STATISTICS_BODY).encode("utf-8")
        )
        self.assertEqual(json.loads(snapshot.raw_bytes), STATISTICS_BODY)

    def test_sha256_matches_raw_bytes(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY))

        snapshot = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(
            snapshot.sha256, hashlib.sha256(snapshot.raw_bytes).hexdigest()
        )

    def test_byte_count_matches_raw_bytes(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY))

        snapshot = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(snapshot.byte_count, len(snapshot.raw_bytes))

    def test_provenance_fields_recorded(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY))

        snapshot = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(snapshot.endpoint, STATISTICS_ENDPOINT)
        self.assertEqual(snapshot.base_url, "http://example.test")
        self.assertEqual(snapshot.captured_at_utc, FIXED_NOW)
        self.assertEqual(snapshot.http_status, 200)
        self.assertEqual(snapshot.content_type, "application/json")

    def test_non_200_fails_closed(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY, status_code=500))

        with self.assertRaises(OutcomeIntelligenceResponseError):
            fetch_raw_snapshot(
                client=client,
                base_url="http://example.test",
                endpoint=STATISTICS_ENDPOINT,
                now_utc=lambda: FIXED_NOW,
            )

    def test_malformed_json_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"not-json{{{",
                headers={"content-type": "application/json"},
            )

        client = _client_for(handler)

        with self.assertRaises(OutcomeIntelligenceResponseError):
            fetch_raw_snapshot(
                client=client,
                base_url="http://example.test",
                endpoint=STATISTICS_ENDPOINT,
                now_utc=lambda: FIXED_NOW,
            )

    def test_deterministic_given_injected_clock(self) -> None:
        client = _client_for(_json_handler(STATISTICS_BODY))

        first = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )
        second = fetch_raw_snapshot(
            client=client,
            base_url="http://example.test",
            endpoint=STATISTICS_ENDPOINT,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(first.captured_at_utc, second.captured_at_utc)
        self.assertEqual(first.sha256, second.sha256)


class CaptureOutcomeIntelligenceRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_dir = Path(self._tmp.name)

    def test_captures_both_endpoints(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        manifest = capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(len(manifest.snapshots), 2)
        endpoints = {record.endpoint for record in manifest.snapshots}
        self.assertEqual(endpoints, {STATISTICS_ENDPOINT, SETUP_REASONS_ENDPOINT})

    def test_run_id_derived_from_injected_clock(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        manifest = capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        self.assertEqual(manifest.run_id, "20260824T120000Z")

    def test_writes_artifact_files_and_manifest(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        manifest = capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        run_dir = self.output_dir / "runs" / manifest.run_id
        self.assertTrue((run_dir / "statistics.json").is_file())
        self.assertTrue((run_dir / "setup_reasons.json").is_file())
        self.assertTrue((run_dir / "manifest.json").is_file())

        self.assertEqual(
            json.loads((run_dir / "statistics.json").read_text()),
            STATISTICS_BODY,
        )

    def test_second_capture_with_same_clock_conflicts(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        with self.assertRaises(OutcomeIntelligenceRunConflictError):
            capture_outcome_intelligence_run(
                base_url="http://example.test",
                output_dir=self.output_dir,
                client=client,
                now_utc=lambda: FIXED_NOW,
            )

    def test_no_run_directory_written_when_second_endpoint_fails(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == STATISTICS_ENDPOINT:
                return httpx.Response(
                    200,
                    content=json.dumps(STATISTICS_BODY).encode("utf-8"),
                    headers={"content-type": "application/json"},
                )

            return httpx.Response(500, content=b"{}")

        client = _client_for(handler)

        with self.assertRaises(OutcomeIntelligenceResponseError):
            capture_outcome_intelligence_run(
                base_url="http://example.test",
                output_dir=self.output_dir,
                client=client,
                now_utc=lambda: FIXED_NOW,
            )

        self.assertFalse((self.output_dir / "runs").exists())

    def test_list_run_manifests_sorted_ascending(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        earlier = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
        later = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

        capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: later,
        )
        capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: earlier,
        )

        manifests = list_run_manifests(self.output_dir)

        self.assertEqual(
            [manifest.captured_at_utc for manifest in manifests],
            [earlier, later],
        )

    def test_list_run_manifests_empty_when_no_runs(self) -> None:
        self.assertEqual(list_run_manifests(self.output_dir), [])

    def test_load_run_payload_round_trips(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        manifest = capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        payload = load_run_payload(self.output_dir, manifest, STATISTICS_ENDPOINT)

        self.assertEqual(payload, STATISTICS_BODY)

    def test_load_run_payload_detects_tampered_artifact(self) -> None:
        client = _client_for(
            _routed_handler(
                {
                    STATISTICS_ENDPOINT: STATISTICS_BODY,
                    SETUP_REASONS_ENDPOINT: SETUP_REASONS_BODY,
                }
            )
        )

        manifest = capture_outcome_intelligence_run(
            base_url="http://example.test",
            output_dir=self.output_dir,
            client=client,
            now_utc=lambda: FIXED_NOW,
        )

        artifact_path = (
            self.output_dir / "runs" / manifest.run_id / "statistics.json"
        )
        artifact_path.write_text('{"tampered": true}')

        with self.assertRaises(Exception):
            load_run_payload(self.output_dir, manifest, STATISTICS_ENDPOINT)


if __name__ == "__main__":
    unittest.main()
