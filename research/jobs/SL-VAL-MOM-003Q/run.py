import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-MOM-003Q"
BASE = "https://data.binance.vision/data/spot"
DATA_START = date(2025, 10, 1)
DATA_END = date(2026, 8, 26)
OOS_START = date(2026, 1, 5)
OOS_LAST_DECISION = date(2026, 8, 17)
EXPECTED_ROWS = 330
EXPECTED_OBSERVATIONS = 33
FRICTION = 0.002


def emit(outdir, state, **extra):
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "terminal_result.json").write_text(
        json.dumps({"object_id": OBJECT_ID, "terminal_state": state, **extra}, indent=2, sort_keys=True),
        encoding="utf-8",
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
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"unexpected zip members {names}")
        text = io.TextIOWrapper(zf.open(names[0]), encoding="utf-8")
        for row in csv.reader(text):
            if not row:
                continue
            try:
                raw = int(row[0])
                op = float(row[1]); cl = float(row[4])
            except (ValueError, IndexError):
                continue
            ts = raw / 1_000_000 if raw > 10**14 else raw / 1_000
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            if not (op > 0 and cl > 0 and math.isfinite(op) and math.isfinite(cl)):
                raise ValueError(f"invalid OHLC {d}")
            out.append((d, op, cl))
    return out


def max_drawdown(curve):
    peak = curve[0]
    mdd = 0.0
    for x in curve:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1.0)
    return mdd


def main(outdir):
    files = []
    rows = []
    try:
        for y, months in ((2025, range(10, 13)), (2026, range(1, 8))):
            for m in months:
                name = f"BTCUSDT-1d-{y}-{m:02d}.zip"
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

    by_date = {}
    duplicate_dates = []
    for d, op, cl in rows:
        if d in by_date:
            duplicate_dates.append(d.isoformat())
        by_date[d] = {"open": op, "close": cl}

    expected_dates = [DATA_START + timedelta(days=i) for i in range((DATA_END - DATA_START).days + 1)]
    missing = [d.isoformat() for d in expected_dates if d not in by_date]
    extras = sorted(d.isoformat() for d in by_date if d < DATA_START or d > DATA_END)
    if len(rows) != EXPECTED_ROWS or len(by_date) != EXPECTED_ROWS or duplicate_dates or missing or extras:
        emit(outdir, "OOS-EVIDENCE-FAIL", expected_rows=EXPECTED_ROWS, observed_rows=len(rows), unique_rows=len(by_date), duplicate_dates=duplicate_dates, missing_dates=missing, extra_dates=extras, files=files)
        return

    observations = []
    d = OOS_START
    while d <= OOS_LAST_DECISION:
        sunday = d - timedelta(days=1)
        anchor = sunday - timedelta(days=84)
        nxt = d + timedelta(days=7)
        if not all(x in by_date for x in (anchor, sunday, d, nxt)):
            emit(outdir, "OOS-EVIDENCE-FAIL", reason="required decision date missing", decision_date=d.isoformat())
            return
        formation = by_date[sunday]["close"] / by_date[anchor]["close"] - 1.0
        weekly = by_date[nxt]["open"] / by_date[d]["open"] - 1.0
        observations.append({
            "decision_date": d.isoformat(),
            "formation_anchor_date": anchor.isoformat(),
            "formation_end_date": sunday.isoformat(),
            "formation_return": formation,
            "position": "LONG" if formation > 0 else "FLAT",
            "entry_open": by_date[d]["open"],
            "next_open": by_date[nxt]["open"],
            "weekly_return_if_long": weekly,
        })
        d += timedelta(days=7)

    if len(observations) != EXPECTED_OBSERVATIONS:
        emit(outdir, "OOS-EVIDENCE-FAIL", reason="observation count mismatch", expected=EXPECTED_OBSERVATIONS, observed=len(observations))
        return

    gross = 1.0
    stressed = 1.0
    passive = 1.0
    gross_curve = [1.0]
    stressed_curve = [1.0]
    passive_curve = [1.0]
    episodes = []
    current = None
    long_weeks = 0

    for i, obs in enumerate(observations):
        r = obs["weekly_return_if_long"]
        passive *= 1.0 + r
        passive_curve.append(passive)
        is_long = obs["position"] == "LONG"
        if is_long:
            long_weeks += 1
            if current is None:
                current = {"start": obs["decision_date"], "gross_factor": 1.0, "weeks": 0}
            current["gross_factor"] *= 1.0 + r
            current["weeks"] += 1
            gross *= 1.0 + r
            stressed *= 1.0 + r
        next_long = i + 1 < len(observations) and observations[i + 1]["position"] == "LONG"
        if current is not None and not next_long:
            stressed *= 1.0 - FRICTION
            current["end"] = obs["decision_date"]
            current["gross_return"] = current.pop("gross_factor") - 1.0
            current["stressed_return"] = (1.0 + current["gross_return"]) * (1.0 - FRICTION) - 1.0
            episodes.append(current)
            current = None
        gross_curve.append(gross)
        stressed_curve.append(stressed)

    stressed_total = stressed - 1.0
    positive_episode_returns = sorted((max(0.0, e["stressed_return"]) for e in episodes), reverse=True)
    positive_sum = sum(positive_episode_returns)
    top1_share = positive_episode_returns[0] / positive_sum if positive_sum > 0 else None
    top2_share = sum(positive_episode_returns[:2]) / positive_sum if positive_sum > 0 else None
    weeks = len(observations)
    ann_exp = 52.1775 / weeks

    obs_bytes = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    dataset_bytes = "\n".join(f"{d.isoformat()}|{by_date[d]['open']:.12g}|{by_date[d]['close']:.12g}" for d in expected_dates).encode()

    emit(
        outdir,
        "OOS-OUTCOME-COMPLETE",
        contract={
            "symbol": "BTCUSDT Spot 1D",
            "oos_decisions": "2026-01-05..2026-08-17 Monday 00:00 UTC",
            "holding": "Monday open to next Monday open",
            "formation": "84-calendar-day completed Sunday close-to-close",
            "signal": "LONG iff formation_return > 0 else FLAT",
            "friction": "20 bps per completed LONG exposure episode",
            "parameter_tuning": False,
        },
        source_scope="2025-10-01..2026-08-26 UTC context+untouched OOS",
        source_rows=len(by_date),
        source_dataset_sha256=hashlib.sha256(dataset_bytes).hexdigest(),
        weekly_observations_sha256=hashlib.sha256(obs_bytes).hexdigest(),
        weekly_observations=observations,
        observation_count=weeks,
        long_weeks=long_weeks,
        exposure_fraction=long_weeks / weeks,
        long_episode_count=len(episodes),
        episodes=episodes,
        gross_cumulative_return=gross - 1.0,
        stressed_cumulative_return=stressed_total,
        passive_cumulative_return=passive - 1.0,
        stressed_annualized_return=(stressed ** ann_exp - 1.0) if stressed > 0 else -1.0,
        passive_annualized_return=(passive ** ann_exp - 1.0) if passive > 0 else -1.0,
        gross_max_drawdown=max_drawdown(gross_curve),
        stressed_max_drawdown=max_drawdown(stressed_curve),
        passive_max_drawdown=max_drawdown(passive_curve),
        positive_episode_top1_share=top1_share,
        positive_episode_top2_share=top2_share,
        files=files,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    try:
        job = json.loads(Path(args.job).read_text(encoding="utf-8"))
        if job.get("object_id") != OBJECT_ID:
            raise ValueError("job object_id mismatch")
    except Exception as e:
        emit(args.output, "OOS-EVIDENCE-FAIL", reason=f"job-contract-validation: {e!r}")
    else:
        main(args.output)
