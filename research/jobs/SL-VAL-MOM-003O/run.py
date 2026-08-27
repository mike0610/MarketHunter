import csv
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-MOM-003O"
BASE = "https://data.binance.vision/data/spot"
EXPECTED_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
EXPECTED_END = datetime(2026, 8, 26, tzinfo=timezone.utc)
EXPECTED_ROWS = 238


def emit(outdir, state, **extra):
    payload = {"object_id": OBJECT_ID, "terminal_state": state, **extra}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / "terminal_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MarketHunter-Research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def checked_zip(url):
    data = fetch(url)
    checksum_text = fetch(url + ".CHECKSUM").decode("utf-8", "replace").strip()
    expected = checksum_text.split()[0].lower()
    actual = hashlib.sha256(data).hexdigest()
    if expected != actual:
        raise ValueError(f"checksum mismatch {url}: {expected} != {actual}")
    return data, actual


def parse_zip(data):
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"unexpected zip members: {names}")
        text = io.TextIOWrapper(zf.open(names[0]), encoding="utf-8")
        for row in csv.reader(text):
            if not row:
                continue
            try:
                raw = int(row[0])
            except ValueError:
                continue
            # Binance Spot archive timestamps are microseconds from 2025-01-01 onward.
            ts = raw / 1_000_000 if raw > 10**14 else raw / 1_000
            rows.append((int(ts), row))
    return rows


def main(outdir):
    files = []
    rows = []
    try:
        for month in range(1, 8):
            name = f"BTCUSDT-1d-2026-{month:02d}.zip"
            url = f"{BASE}/monthly/klines/BTCUSDT/1d/{name}"
            data, sha = checked_zip(url)
            part = parse_zip(data)
            files.append({"url": url, "sha256": sha, "rows": len(part)})
            rows.extend(part)
        for day in range(1, 27):
            name = f"BTCUSDT-1d-2026-08-{day:02d}.zip"
            url = f"{BASE}/daily/klines/BTCUSDT/1d/{name}"
            data, sha = checked_zip(url)
            part = parse_zip(data)
            files.append({"url": url, "sha256": sha, "rows": len(part)})
            rows.extend(part)
    except Exception as e:
        emit(outdir, "PROVIDER-BLOCKED", reason=repr(e), files_verified=files)
        return

    timestamps = [x[0] for x in rows]
    unique = sorted(set(timestamps))
    expected_start = int(EXPECTED_START.timestamp())
    expected_end = int(EXPECTED_END.timestamp())
    gaps = [
        {"left": unique[i], "right": unique[i + 1], "delta_seconds": unique[i + 1] - unique[i]}
        for i in range(len(unique) - 1)
        if unique[i + 1] - unique[i] != 86400
    ]
    duplicates = len(timestamps) - len(unique)
    ok = (
        len(rows) == EXPECTED_ROWS
        and len(unique) == EXPECTED_ROWS
        and duplicates == 0
        and not gaps
        and unique[0] == expected_start
        and unique[-1] == expected_end
    )
    dataset_digest = hashlib.sha256(
        "\n".join(str(ts) for ts in unique).encode("utf-8")
    ).hexdigest()
    state = "DATASET-INTEGRITY-PASS" if ok else "DATASET-INTEGRITY-FAIL"
    emit(
        outdir,
        state,
        scope="BTCUSDT Spot 1d 2026-01-01..2026-08-26 UTC",
        expected_rows=EXPECTED_ROWS,
        observed_rows=len(rows),
        unique_rows=len(unique),
        duplicate_rows=duplicates,
        gaps=gaps,
        first_timestamp=unique[0] if unique else None,
        last_timestamp=unique[-1] if unique else None,
        timestamp_unit_rule="microseconds if raw open_time > 1e14; otherwise milliseconds",
        file_count=len(files),
        files=files,
        timestamp_census_sha256=dataset_digest,
        outcomes_opened=False,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: run.py OUTPUT_DIR")
    main(sys.argv[1])
