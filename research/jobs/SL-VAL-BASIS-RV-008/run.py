import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from pathlib import Path

OBJECT_ID = "SL-VAL-BASIS-RV-008"
MONTHS = ("2024-01", "2024-02", "2024-03")
EXPECTED_ROWS = 2184
SPOT_BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h"
FUT_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h"


def emit(outdir, state, **extra):
    Path(outdir).mkdir(parents=True, exist_ok=True)
    payload = {"object_id": OBJECT_ID, "terminal_state": state, **extra}
    (Path(outdir) / "terminal_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MarketHunter-Research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def checked_zip(url):
    data = fetch(url)
    checksum = fetch(url + ".CHECKSUM").decode("utf-8", "replace").strip().split()[0].lower()
    actual = hashlib.sha256(data).hexdigest()
    if checksum != actual:
        raise ValueError(f"checksum mismatch {url}: {checksum} != {actual}")
    return data, actual


def parse_zip(data):
    rows = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"unexpected zip members: {names}")
        text = io.TextIOWrapper(zf.open(names[0]), encoding="utf-8")
        for row in csv.reader(text):
            if not row:
                continue
            try:
                raw_ts = int(row[0])
                close = float(row[4])
            except (ValueError, IndexError):
                continue
            ts = int(raw_ts / 1_000_000 if raw_ts > 10**14 else raw_ts / 1_000)
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"invalid close at {raw_ts}: {close}")
            if ts in rows:
                raise ValueError(f"duplicate timestamp {ts}")
            rows[ts] = close
    return rows


def validate_series(rows):
    ts = sorted(rows)
    gaps = [
        {"left": ts[i], "right": ts[i + 1], "delta_seconds": ts[i + 1] - ts[i]}
        for i in range(len(ts) - 1)
        if ts[i + 1] - ts[i] != 3600
    ]
    return ts, gaps


def validate_job(path):
    job = json.loads(Path(path).read_text(encoding="utf-8"))
    if job.get("object_id") != OBJECT_ID:
        raise ValueError(f"job object_id mismatch: {job.get('object_id')!r}")


def main(outdir):
    spot, fut, files = {}, {}, []
    try:
        for month in MONTHS:
            name = f"BTCUSDT-1h-{month}.zip"
            for leg, base, target in (("spot", SPOT_BASE, spot), ("perp", FUT_BASE, fut)):
                url = f"{base}/{name}"
                data, sha = checked_zip(url)
                part = parse_zip(data)
                overlap = set(target).intersection(part)
                if overlap:
                    raise ValueError(f"duplicate cross-file timestamps {leg}: {len(overlap)}")
                target.update(part)
                files.append({"leg": leg, "url": url, "sha256": sha, "rows": len(part)})
    except Exception as e:
        emit(outdir, "PROVIDER-BLOCKED", reason=repr(e), files_verified=files, outcomes_opened=False)
        return

    spot_ts, spot_gaps = validate_series(spot)
    fut_ts, fut_gaps = validate_series(fut)
    intersection = sorted(set(spot_ts).intersection(fut_ts))
    spot_only = sorted(set(spot_ts) - set(fut_ts))
    fut_only = sorted(set(fut_ts) - set(spot_ts))
    aligned = [
        [ts, format(spot[ts], ".12g"), format(fut[ts], ".12g")]
        for ts in intersection
    ]
    aligned_sha = hashlib.sha256(
        "\n".join(",".join(map(str, r)) for r in aligned).encode("utf-8")
    ).hexdigest()
    ok = (
        len(spot_ts) == EXPECTED_ROWS
        and len(fut_ts) == EXPECTED_ROWS
        and len(intersection) == EXPECTED_ROWS
        and not spot_gaps
        and not fut_gaps
        and not spot_only
        and not fut_only
    )
    state = "ALIGNMENT-PASS" if ok else "ALIGNMENT-FAIL"
    emit(
        outdir,
        state,
        scope="BTCUSDT Spot close vs USD-M perpetual close, 1h UTC, 2024-Q1",
        estimand="b_t = perp_close_t / spot_close_t - 1; NOT computed in this gate",
        expected_rows=EXPECTED_ROWS,
        spot_rows=len(spot_ts),
        perp_rows=len(fut_ts),
        aligned_rows=len(intersection),
        spot_gaps=spot_gaps,
        perp_gaps=fut_gaps,
        spot_only_count=len(spot_only),
        perp_only_count=len(fut_only),
        first_timestamp=intersection[0] if intersection else None,
        last_timestamp=intersection[-1] if intersection else None,
        files=files,
        aligned_price_table_sha256=aligned_sha,
        outcomes_opened=False,
        funding_opened=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        validate_job(args.job)
    except Exception as e:
        emit(args.output, "ALIGNMENT-FAIL", reason=f"job-contract-validation: {e!r}", outcomes_opened=False)
    else:
        main(args.output)
