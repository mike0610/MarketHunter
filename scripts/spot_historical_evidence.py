"""Research-local Binance Spot BTCUSDT historical evidence acquisition.

This script is intentionally narrow. It fetches exact Binance Spot kline
response bytes for one explicit UTC interval, validates the returned rows,
and writes immutable raw-page, canonical-dataset and provenance artifacts.
It does not inspect strategy outcomes or modify MarketHunter runtime state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import httpx

# Allow both `python -m scripts.spot_historical_evidence` and direct
# `python scripts/spot_historical_evidence.py` execution from the repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from exchange.endpoints import SPOT_BASE_URL, SPOT_KLINES  # noqa: E402

SYMBOL = "BTCUSDT"
MAX_PAGE_SIZE = 1000
# Fixed-duration Binance intervals only. `1M` is deliberately excluded,
# and `1w` is excluded because its Monday boundary is not Unix-epoch modulo
# one week; accepting it here would make the generic alignment test false.
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
}


class EvidenceError(RuntimeError):
    """Fail-closed acquisition or integrity error."""


@dataclass(frozen=True, slots=True)
class PageEvidence:
    index: int
    request_start_ms: int
    raw_bytes: bytes
    sha256: str
    rows: tuple[list[object], ...]


@dataclass(frozen=True, slots=True)
class ValidatedDataset:
    rows: tuple[list[object], ...]
    first_open_ms: int
    last_open_ms: int
    canonical_bytes: bytes
    sha256: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise EvidenceError("UTC bound must not be blank")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"invalid datetime {value!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise EvidenceError("naive datetime is not allowed")
    return result.astimezone(timezone.utc)


def to_epoch_ms(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("naive datetime is not allowed")
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def validate_request(
    *,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    now_utc: Callable[[], datetime] = utcnow,
) -> tuple[int, int, int]:
    if symbol != SYMBOL:
        raise EvidenceError(f"only {SYMBOL} is allowed")
    interval_ms = INTERVAL_MS.get(interval)
    if interval_ms is None:
        raise EvidenceError(f"unsupported fixed interval: {interval!r}")
    start_ms = to_epoch_ms(start)
    end_ms = to_epoch_ms(end)
    if start_ms >= end_ms:
        raise EvidenceError("start must be earlier than end")
    if end > now_utc().astimezone(timezone.utc):
        raise EvidenceError("end bound must not be in the future")
    if start_ms % interval_ms != 0 or end_ms % interval_ms != 0:
        raise EvidenceError("start/end must align to the requested interval")
    return start_ms, end_ms, interval_ms


def _row_open_ms(row: list[object]) -> int:
    if not isinstance(row, list) or len(row) < 12:
        raise EvidenceError("provider row schema drift: expected >=12 fields")
    value = row[0]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError("provider open timestamp is not numeric")
    if int(value) != value:
        raise EvidenceError("provider open timestamp must be an integer")
    return int(value)


def _finite_float(value: object, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid numeric field {field}") from exc
    if not math.isfinite(result):
        raise EvidenceError(f"non-finite numeric field {field}")
    return result


def validate_row(row: list[object]) -> int:
    open_ms = _row_open_ms(row)
    open_price = _finite_float(row[1], "open")
    high = _finite_float(row[2], "high")
    low = _finite_float(row[3], "low")
    close = _finite_float(row[4], "close")
    volume = _finite_float(row[5], "volume")
    quote_volume = _finite_float(row[7], "quote_volume")
    taker_base = _finite_float(row[9], "taker_base")
    taker_quote = _finite_float(row[10], "taker_quote")
    if high < max(open_price, close) or low > min(open_price, close) or high < low:
        raise EvidenceError(f"invalid OHLC geometry at {open_ms}")
    if min(volume, quote_volume, taker_base, taker_quote) < 0:
        raise EvidenceError(f"negative volume field at {open_ms}")
    trades = row[8]
    if isinstance(trades, bool) or not isinstance(trades, (int, float)) or int(trades) != trades or int(trades) < 0:
        raise EvidenceError(f"invalid trade count at {open_ms}")
    return open_ms


def parse_page(raw_bytes: bytes) -> tuple[list[object], ...]:
    try:
        payload = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("provider payload is not valid JSON") from exc
    if not isinstance(payload, list):
        raise EvidenceError("provider payload is not a list")
    rows: list[list[object]] = []
    for item in payload:
        if not isinstance(item, list):
            raise EvidenceError("provider row is not a list")
        rows.append(item)
    return tuple(rows)


def validate_dataset(
    pages: Iterable[PageEvidence],
    *,
    start_ms: int,
    end_ms: int,
    interval_ms: int,
) -> ValidatedDataset:
    rows: list[list[object]] = []
    previous_open: int | None = None
    seen: set[int] = set()

    for page in pages:
        for row in page.rows:
            open_ms = validate_row(row)
            if not (start_ms <= open_ms < end_ms):
                raise EvidenceError(f"row outside requested bounds: {open_ms}")
            if open_ms in seen:
                raise EvidenceError(f"duplicate timestamp: {open_ms}")
            if previous_open is not None:
                if open_ms <= previous_open:
                    raise EvidenceError("timestamps are not strictly increasing")
                if open_ms - previous_open != interval_ms:
                    raise EvidenceError(
                        f"interval gap: previous={previous_open} current={open_ms}"
                    )
            seen.add(open_ms)
            previous_open = open_ms
            rows.append(row)

    if not rows:
        raise EvidenceError("provider returned no rows for requested interval")
    first_open = _row_open_ms(rows[0])
    last_open = _row_open_ms(rows[-1])
    if first_open != start_ms:
        raise EvidenceError(
            f"dataset starts at {first_open}, expected exact bound {start_ms}"
        )
    expected_last = end_ms - interval_ms
    if last_open != expected_last:
        raise EvidenceError(
            f"partial dataset: last={last_open}, expected={expected_last}"
        )

    canonical_bytes = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return ValidatedDataset(
        rows=tuple(rows),
        first_open_ms=first_open,
        last_open_ms=last_open,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def fetch_pages(
    client: httpx.Client,
    *,
    interval: str,
    start_ms: int,
    end_ms: int,
    interval_ms: int,
) -> tuple[PageEvidence, ...]:
    pages: list[PageEvidence] = []
    cursor = start_ms
    page_index = 0

    while cursor < end_ms:
        response = client.get(
            SPOT_BASE_URL + SPOT_KLINES,
            params={
                "symbol": SYMBOL,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": MAX_PAGE_SIZE,
            },
        )
        raw_bytes = response.content
        if response.status_code != 200:
            raise EvidenceError(f"provider returned HTTP {response.status_code}")
        rows = parse_page(raw_bytes)
        if not rows:
            raise EvidenceError(f"empty provider page at cursor {cursor}")

        opens = [validate_row(row) for row in rows]
        if any(current <= previous for previous, current in zip(opens, opens[1:])):
            raise EvidenceError("provider page timestamps are not increasing")
        first_open = opens[0]
        last_open = opens[-1]
        if first_open != cursor:
            raise EvidenceError(
                f"provider page did not begin at cursor: {first_open} != {cursor}"
            )
        if last_open >= end_ms:
            raise EvidenceError("provider returned out-of-window row")

        pages.append(
            PageEvidence(
                index=page_index,
                request_start_ms=cursor,
                raw_bytes=raw_bytes,
                sha256=hashlib.sha256(raw_bytes).hexdigest(),
                rows=rows,
            )
        )
        next_cursor = last_open + interval_ms
        if next_cursor <= cursor:
            raise EvidenceError("pagination did not make progress")
        cursor = next_cursor
        page_index += 1

    return tuple(pages)


def write_artifacts(
    *,
    output_dir: Path,
    interval: str,
    start: datetime,
    end: datetime,
    retrieved_at: datetime,
    pages: tuple[PageEvidence, ...],
    dataset: ValidatedDataset,
) -> Path:
    run_id = retrieved_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / run_id
    if run_dir.exists():
        raise EvidenceError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    page_records: list[dict[str, object]] = []
    for page in pages:
        filename = f"page_{page.index:04d}.json"
        (run_dir / filename).write_bytes(page.raw_bytes)
        page_records.append(
            {
                "index": page.index,
                "filename": filename,
                "request_start_ms": page.request_start_ms,
                "byte_count": len(page.raw_bytes),
                "sha256": page.sha256,
                "row_count": len(page.rows),
            }
        )

    dataset_filename = "dataset.json"
    (run_dir / dataset_filename).write_bytes(dataset.canonical_bytes)
    manifest = {
        "provider": "Binance Spot",
        "base_url": SPOT_BASE_URL,
        "endpoint": SPOT_KLINES,
        "symbol": SYMBOL,
        "interval": interval,
        "requested_start_utc": start.astimezone(timezone.utc).isoformat(),
        "requested_end_utc_exclusive": end.astimezone(timezone.utc).isoformat(),
        "retrieved_at_utc": retrieved_at.astimezone(timezone.utc).isoformat(),
        "page_count": len(pages),
        "row_count": len(dataset.rows),
        "first_open_ms": dataset.first_open_ms,
        "last_open_ms": dataset.last_open_ms,
        "dataset_filename": dataset_filename,
        "dataset_sha256": dataset.sha256,
        "integrity": {
            "strictly_increasing": True,
            "unique_timestamps": True,
            "continuous_interval": True,
            "bounds_respected": True,
            "ohlcv_semantics": True,
        },
        "pages": page_records,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return run_dir


def acquire(
    *,
    interval: str,
    start: datetime,
    end: datetime,
    output_dir: Path,
    client: httpx.Client,
    now_utc: Callable[[], datetime] = utcnow,
) -> Path:
    start_ms, end_ms, interval_ms = validate_request(
        symbol=SYMBOL,
        interval=interval,
        start=start,
        end=end,
        now_utc=now_utc,
    )
    retrieved_at = now_utc().astimezone(timezone.utc)
    pages = fetch_pages(
        client,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
        interval_ms=interval_ms,
    )
    dataset = validate_dataset(
        pages,
        start_ms=start_ms,
        end_ms=end_ms,
        interval_ms=interval_ms,
    )
    return write_artifacts(
        output_dir=output_dir,
        interval=interval,
        start=start,
        end=end,
        retrieved_at=retrieved_at,
        pages=pages,
        dataset=dataset,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", required=True, choices=sorted(INTERVAL_MS))
    parser.add_argument("--start", required=True, help="UTC ISO-8601 inclusive")
    parser.add_argument("--end", required=True, help="UTC ISO-8601 exclusive")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        start = parse_utc(args.start)
        end = parse_utc(args.end)
        with httpx.Client(timeout=30.0) as client:
            run_dir = acquire(
                interval=args.interval,
                start=start,
                end=end,
                output_dir=args.output_dir,
                client=client,
            )
    except (EvidenceError, httpx.HTTPError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
