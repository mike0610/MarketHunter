import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

OBJECT_ID = "SL-VAL-TAKER-FLOW-ARCHIVE-EQUIVALENCE-EXEC-001"
ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT"]
INTERVAL = "1h"
START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 1, tzinfo=timezone.utc)
ARCHIVE_ROOT = "https://data.binance.vision/data/spot/monthly/klines"
REST_ROOT = "https://api.binance.com/api/v3/klines"
USER_AGENT = "MarketHunter-Research/1.0"
MAX_EXAMPLES = 50
FIELDS = ("open", "close", "volume", "taker_buy_base_volume")


def emit(output_dir, terminal_state, **payload):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    body = {"object_id": OBJECT_ID, "terminal_state": terminal_state, **payload}
    (out / "terminal_result.json").write_text(
        json.dumps(body, indent=2, sort_keys=True), encoding="utf-8"
    )


def request_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def month_iter(start, end):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        first = datetime(y, m, 1, tzinfo=timezone.utc)
        if m == 12:
            nxt = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
        else:
            nxt = datetime(y, m + 1, 1, tzinfo=timezone.utc)
        yield first, nxt
        y, m = nxt.year, nxt.month


def normalize_open_time_seconds(raw):
    x = int(raw)
    if x > 10**14:
        return x // 1_000_000
    return x // 1_000


def decimal_value(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal value: {raw!r}") from exc


def parse_archive(zip_bytes, symbol, first):
    rows = {}
    duplicates = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = sorted(n for n in zf.namelist() if not n.endswith("/"))
        if len(members) != 1:
            raise ValueError(f"unexpected archive member count for {symbol} {first:%Y-%m}: {members}")
        with zf.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            for line_no, row in enumerate(reader, 1):
                if not row:
                    continue
                try:
                    ts = normalize_open_time_seconds(row[0])
                    values = {
                        "open": decimal_value(row[1]),
                        "close": decimal_value(row[4]),
                        "volume": decimal_value(row[5]),
                        "taker_buy_base_volume": decimal_value(row[9]),
                    }
                except (ValueError, IndexError):
                    if line_no == 1 and row[0].lower().startswith("open"):
                        continue
                    raise
                if ts in rows:
                    if len(duplicates) < MAX_EXAMPLES:
                        duplicates.append(ts)
                else:
                    rows[ts] = values
    return rows, duplicates


def fetch_archive(symbol, first):
    name = f"{symbol}-{INTERVAL}-{first.year}-{first.month:02d}.zip"
    url = f"{ARCHIVE_ROOT}/{symbol}/{INTERVAL}/{name}"
    zip_bytes = request_bytes(url)
    checksum_text = request_bytes(url + ".CHECKSUM").decode("utf-8", errors="strict").strip()
    expected = checksum_text.split()[0].lower()
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if expected != actual:
        raise ValueError(f"checksum mismatch for {name}: expected={expected} actual={actual}")
    rows, duplicates = parse_archive(zip_bytes, symbol, first)
    return rows, duplicates, {
        "symbol": symbol,
        "month": f"{first.year}-{first.month:02d}",
        "archive_url": url,
        "sha256": actual,
        "rows": len(rows),
    }


def fetch_rest_month(symbol, first, nxt):
    start_ms = int(first.timestamp() * 1000)
    end_ms = int(nxt.timestamp() * 1000) - 1
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    })
    url = REST_ROOT + "?" + params
    payload = json.loads(request_bytes(url).decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"unexpected REST payload for {symbol} {first:%Y-%m}: {payload!r}")
    rows = {}
    duplicates = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 10:
            raise ValueError(f"malformed REST kline for {symbol} {first:%Y-%m}: {row!r}")
        ts = normalize_open_time_seconds(row[0])
        values = {
            "open": decimal_value(row[1]),
            "close": decimal_value(row[4]),
            "volume": decimal_value(row[5]),
            "taker_buy_base_volume": decimal_value(row[9]),
        }
        if ts in rows:
            if len(duplicates) < MAX_EXAMPLES:
                duplicates.append(ts)
        else:
            rows[ts] = values
    return rows, duplicates, {"rest_url": url, "rows": len(rows)}


def add_example(examples, item):
    if len(examples) < MAX_EXAMPLES:
        examples.append(item)


def compare_month(symbol, first, archive_rows, archive_dups, rest_rows, rest_dups, examples):
    counts = {
        "archive_duplicates": len(archive_dups),
        "rest_duplicates": len(rest_dups),
        "archive_only_timestamps": 0,
        "rest_only_timestamps": 0,
        "field_mismatches": {field: 0 for field in FIELDS},
    }
    for ts in archive_dups:
        add_example(examples, {"symbol": symbol, "month": f"{first:%Y-%m}", "kind": "archive_duplicate", "open_time": ts})
    for ts in rest_dups:
        add_example(examples, {"symbol": symbol, "month": f"{first:%Y-%m}", "kind": "rest_duplicate", "open_time": ts})

    a_times = set(archive_rows)
    r_times = set(rest_rows)
    only_a = sorted(a_times - r_times)
    only_r = sorted(r_times - a_times)
    counts["archive_only_timestamps"] = len(only_a)
    counts["rest_only_timestamps"] = len(only_r)
    for ts in only_a[:MAX_EXAMPLES]:
        add_example(examples, {"symbol": symbol, "month": f"{first:%Y-%m}", "kind": "archive_only_timestamp", "open_time": ts})
    for ts in only_r[:MAX_EXAMPLES]:
        add_example(examples, {"symbol": symbol, "month": f"{first:%Y-%m}", "kind": "rest_only_timestamp", "open_time": ts})

    for ts in sorted(a_times & r_times):
        a = archive_rows[ts]
        r = rest_rows[ts]
        for field in FIELDS:
            if a[field] != r[field]:
                counts["field_mismatches"][field] += 1
                add_example(examples, {
                    "symbol": symbol,
                    "month": f"{first:%Y-%m}",
                    "kind": "field_mismatch",
                    "open_time": ts,
                    "field": field,
                    "archive": str(a[field]),
                    "rest": str(r[field]),
                })
    return counts


def mismatch_total(counts):
    return (
        counts["archive_duplicates"]
        + counts["rest_duplicates"]
        + counts["archive_only_timestamps"]
        + counts["rest_only_timestamps"]
        + sum(counts["field_mismatches"].values())
    )


def main(output_dir, job_path):
    try:
        job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    except Exception as exc:
        emit(output_dir, "PROVIDER-BLOCKED", reason=f"job-read-failure: {exc!r}")
        return

    expected_states = ["ARCHIVE-EQUIVALENT", "ARCHIVE-MISMATCH", "PROVIDER-BLOCKED"]
    if (
        job.get("object_id") != OBJECT_ID
        or job.get("executor") != "vps"
        or job.get("terminal_states") != expected_states
        or not (1 <= int(job.get("timeout_minutes", 0)) <= 20)
    ):
        emit(output_dir, "PROVIDER-BLOCKED", reason="job-contract-mismatch", job=job)
        return

    provenance = []
    month_results = []
    examples = []
    total_mismatches = 0

    try:
        for symbol in ASSETS:
            for first, nxt in month_iter(START, END):
                archive_rows, archive_dups, archive_prov = fetch_archive(symbol, first)
                rest_rows, rest_dups, rest_prov = fetch_rest_month(symbol, first, nxt)
                counts = compare_month(
                    symbol, first, archive_rows, archive_dups, rest_rows, rest_dups, examples
                )
                month_mismatches = mismatch_total(counts)
                total_mismatches += month_mismatches
                provenance.append({**archive_prov, **rest_prov})
                month_results.append({
                    "symbol": symbol,
                    "month": f"{first:%Y-%m}",
                    "archive_rows": len(archive_rows),
                    "rest_rows": len(rest_rows),
                    "mismatch_count": month_mismatches,
                    **counts,
                })
    except Exception as exc:
        emit(
            output_dir,
            "PROVIDER-BLOCKED",
            reason=repr(exc),
            contract={
                "assets": ASSETS,
                "venue": "Binance Spot",
                "interval": INTERVAL,
                "window": "[2023-01-01T00:00:00Z, 2026-08-01T00:00:00Z)",
                "gate_fields": ["open_time", *FIELDS],
                "comparison": "monthly archive with verified CHECKSUM vs official /api/v3/klines; Decimal numeric equality; exact normalized timestamp coverage",
                "outcome_blind": True,
            },
            completed_months=len(month_results),
            mismatch_count_so_far=total_mismatches,
            mismatch_examples=examples,
            source_provenance=provenance,
        )
        return

    terminal = "ARCHIVE-EQUIVALENT" if total_mismatches == 0 else "ARCHIVE-MISMATCH"
    emit(
        output_dir,
        terminal,
        contract={
            "assets": ASSETS,
            "venue": "Binance Spot",
            "interval": INTERVAL,
            "window": "[2023-01-01T00:00:00Z, 2026-08-01T00:00:00Z)",
            "gate_fields": ["open_time", *FIELDS],
            "timestamp_normalization": "archive >1e14 interpreted as microseconds, otherwise milliseconds; REST normalized mechanically to seconds; no tolerance",
            "numeric_equality": "Decimal semantic equality, not binary float or formatting-string equality",
            "coverage_gate": "exact per-symbol timestamp-set equality; duplicates are mismatches",
            "outcome_blind": True,
            "no_signal_or_pnl_calculation": True,
            "parameter_tuning": False,
        },
        summary={
            "symbols": len(ASSETS),
            "months_per_symbol": sum(1 for _ in month_iter(START, END)),
            "symbol_months_checked": len(month_results),
            "total_mismatches": total_mismatches,
        },
        mismatch_examples=examples,
        month_results=month_results,
        source_provenance=provenance,
        limitations=[
            "REST is the present-day official representation and historical rows may have been revised by Binance.",
            "This audit tests only fields consumed by the frozen Taker-Flow prescreen, not broader exchange microstructure truth.",
            "No archive repair, provider substitution, strategy outcome inspection, signal calculation, or P&L calculation is performed.",
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    main(args.output, args.job)
