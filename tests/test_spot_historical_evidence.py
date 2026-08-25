from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.spot_historical_evidence import (
    EvidenceError,
    INTERVAL_MS,
    PageEvidence,
    SYMBOL,
    acquire,
    parse_page,
    parse_utc,
    validate_dataset,
    validate_request,
)

HOUR = INTERVAL_MS["1h"]
START_MS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR)


def row(open_ms: int, *, open_price: str = "100", high: str = "110", low: str = "90", close: str = "105") -> list[object]:
    return [
        open_ms,
        open_price,
        high,
        low,
        close,
        "12.5",
        open_ms + HOUR - 1,
        "1280.0",
        42,
        "6.0",
        "615.0",
        "0",
    ]


def page_bytes(rows: list[list[object]]) -> bytes:
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class BoundsTests(unittest.TestCase):
    def test_parse_utc_rejects_naive(self) -> None:
        with self.assertRaises(EvidenceError):
            parse_utc("2026-01-01T00:00:00")

    def test_request_is_btcusdt_only(self) -> None:
        with self.assertRaises(EvidenceError):
            validate_request(
                symbol="ETHUSDT",
                interval="1h",
                start=dt(START_MS),
                end=dt(START_MS + HOUR),
                now_utc=lambda: dt(START_MS + 10 * HOUR),
            )

    def test_rejects_future_end(self) -> None:
        with self.assertRaises(EvidenceError):
            validate_request(
                symbol=SYMBOL,
                interval="1h",
                start=dt(START_MS),
                end=dt(START_MS + 2 * HOUR),
                now_utc=lambda: dt(START_MS + HOUR),
            )

    def test_rejects_unaligned_bounds(self) -> None:
        with self.assertRaises(EvidenceError):
            validate_request(
                symbol=SYMBOL,
                interval="1h",
                start=dt(START_MS + 1_000),
                end=dt(START_MS + HOUR),
                now_utc=lambda: dt(START_MS + 10 * HOUR),
            )


class PayloadIntegrityTests(unittest.TestCase):
    def test_parse_page_rejects_non_list(self) -> None:
        with self.assertRaises(EvidenceError):
            parse_page(b'{"error":"shape"}')

    def test_raw_page_hash_is_exact_bytes(self) -> None:
        raw = b'[[1,"1","1","1","1","0",1,"0",0,"0","0","0"]]\n'
        page = PageEvidence(
            index=0,
            request_start_ms=1,
            raw_bytes=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            rows=parse_page(raw),
        )
        self.assertEqual(page.sha256, hashlib.sha256(raw).hexdigest())

    def test_dataset_rejects_duplicate_timestamp(self) -> None:
        rows = (row(START_MS), row(START_MS))
        page = PageEvidence(0, START_MS, b"x", "h", rows)
        with self.assertRaises(EvidenceError):
            validate_dataset(
                (page,),
                start_ms=START_MS,
                end_ms=START_MS + 2 * HOUR,
                interval_ms=HOUR,
            )

    def test_dataset_rejects_gap(self) -> None:
        rows = (row(START_MS), row(START_MS + 2 * HOUR))
        page = PageEvidence(0, START_MS, b"x", "h", rows)
        with self.assertRaises(EvidenceError):
            validate_dataset(
                (page,),
                start_ms=START_MS,
                end_ms=START_MS + 3 * HOUR,
                interval_ms=HOUR,
            )

    def test_dataset_rejects_invalid_ohlc(self) -> None:
        rows = (row(START_MS, high="99"),)
        page = PageEvidence(0, START_MS, b"x", "h", rows)
        with self.assertRaises(EvidenceError):
            validate_dataset(
                (page,),
                start_ms=START_MS,
                end_ms=START_MS + HOUR,
                interval_ms=HOUR,
            )

    def test_dataset_rejects_partial_final_interval(self) -> None:
        rows = (row(START_MS),)
        page = PageEvidence(0, START_MS, b"x", "h", rows)
        with self.assertRaises(EvidenceError):
            validate_dataset(
                (page,),
                start_ms=START_MS,
                end_ms=START_MS + 2 * HOUR,
                interval_ms=HOUR,
            )

    def test_canonical_hash_is_deterministic(self) -> None:
        rows = (row(START_MS), row(START_MS + HOUR))
        page = PageEvidence(0, START_MS, b"x", "h", rows)
        first = validate_dataset(
            (page,),
            start_ms=START_MS,
            end_ms=START_MS + 2 * HOUR,
            interval_ms=HOUR,
        )
        second = validate_dataset(
            (page,),
            start_ms=START_MS,
            end_ms=START_MS + 2 * HOUR,
            interval_ms=HOUR,
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)


class AcquisitionTests(unittest.TestCase):
    def test_paginates_and_preserves_raw_pages(self) -> None:
        total_rows = 1002
        provider_rows = [row(START_MS + index * HOUR) for index in range(total_rows)]
        requests: list[httpx.Request] = []
        raw_pages: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            cursor = int(request.url.params["startTime"])
            offset = (cursor - START_MS) // HOUR
            payload_rows = provider_rows[offset : offset + 1000]
            raw = page_bytes(payload_rows)
            raw_pages.append(raw)
            return httpx.Response(200, content=raw, headers={"content-type": "application/json"})

        transport = httpx.MockTransport(handler)
        now = dt(START_MS + (total_rows + 5) * HOUR)

        with tempfile.TemporaryDirectory() as tmp:
            with httpx.Client(transport=transport) as client:
                run_dir = acquire(
                    interval="1h",
                    start=dt(START_MS),
                    end=dt(START_MS + total_rows * HOUR),
                    output_dir=Path(tmp),
                    client=client,
                    now_utc=lambda: now,
                )

            self.assertEqual(len(requests), 2)
            self.assertEqual(
                int(requests[1].url.params["startTime"]),
                START_MS + 1000 * HOUR,
            )
            self.assertEqual((run_dir / "page_0000.json").read_bytes(), raw_pages[0])
            self.assertEqual((run_dir / "page_0001.json").read_bytes(), raw_pages[1])

            manifest = json.loads((run_dir / "manifest.json").read_text())
            self.assertEqual(manifest["provider"], "Binance Spot")
            self.assertEqual(manifest["symbol"], SYMBOL)
            self.assertEqual(manifest["page_count"], 2)
            self.assertEqual(manifest["row_count"], total_rows)
            self.assertEqual(
                manifest["pages"][0]["sha256"],
                hashlib.sha256(raw_pages[0]).hexdigest(),
            )
            dataset_bytes = (run_dir / "dataset.json").read_bytes()
            self.assertEqual(
                manifest["dataset_sha256"],
                hashlib.sha256(dataset_bytes).hexdigest(),
            )

    def test_fails_closed_on_empty_page(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"[]")
        )
        with tempfile.TemporaryDirectory() as tmp:
            with httpx.Client(transport=transport) as client:
                with self.assertRaises(EvidenceError):
                    acquire(
                        interval="1h",
                        start=dt(START_MS),
                        end=dt(START_MS + HOUR),
                        output_dir=Path(tmp),
                        client=client,
                        now_utc=lambda: dt(START_MS + 10 * HOUR),
                    )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_fails_closed_on_http_error(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(429, content=b'{"code":-1003}')
        )
        with tempfile.TemporaryDirectory() as tmp:
            with httpx.Client(transport=transport) as client:
                with self.assertRaises(EvidenceError):
                    acquire(
                        interval="1h",
                        start=dt(START_MS),
                        end=dt(START_MS + HOUR),
                        output_dir=Path(tmp),
                        client=client,
                        now_utc=lambda: dt(START_MS + 10 * HOUR),
                    )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_fails_closed_on_provider_overlap_non_progress(self) -> None:
        payload = page_bytes([row(START_MS)])
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, content=payload)

        transport = httpx.MockTransport(handler)
        with tempfile.TemporaryDirectory() as tmp:
            with httpx.Client(transport=transport) as client:
                with self.assertRaises(EvidenceError):
                    acquire(
                        interval="1h",
                        start=dt(START_MS),
                        end=dt(START_MS + 2 * HOUR),
                        output_dir=Path(tmp),
                        client=client,
                        now_utc=lambda: dt(START_MS + 10 * HOUR),
                    )
            self.assertGreaterEqual(calls, 2)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
