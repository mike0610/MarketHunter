import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

OBJECT_ID = "MH-STAGE2-SCANNER-LIVE-PROOF-001"
EXPECTED_SHA = "2cb2339a18fcb63ef6e7fa443dddff7ecce4aa64"
UNIVERSE = "SPY,QQQ,AAPL,MSFT,NVDA"


def emit(output, state, **extra):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"object_id": OBJECT_ID, "terminal_state": state, **extra}
    (out / "terminal_result.json").write_text(json.dumps(payload, indent=2, sort_keys=True))


def main(job_path, output):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "repo"
    db = out / "trading_scanner_stage2_proof.db"

    try:
        job = json.loads(Path(job_path).read_text())
        if job.get("object_id") != OBJECT_ID:
            raise RuntimeError("object id mismatch")

        subprocess.run(
            ["git", "clone", "--quiet", "https://github.com/mike0610/MarketHunter.git", str(work)],
            check=True,
            timeout=120,
        )
        subprocess.run(["git", "-C", str(work), "checkout", "--quiet", EXPECTED_SHA], check=True, timeout=30)
        actual_sha = subprocess.check_output(["git", "-C", str(work), "rev-parse", "HEAD"], text=True).strip()
        if actual_sha != EXPECTED_SHA:
            emit(output, "BLOCKED-RUNTIME", reason="sha-mismatch", expected_sha=EXPECTED_SHA, actual_sha=actual_sha)
            return

        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(work),
                "TRADING_SCANNER_DB_PATH": str(db),
                "TRADING_SCANNER_MARKET_DATA_PROVIDER": "stooq",
                "TRADING_SCANNER_UNIVERSE_SYMBOLS": UNIVERSE,
                "TRADING_SCANNER_MAX_DATA_AGE_SECONDS": "345600",
            }
        )
        cmd = [str(work / ".venv" / "bin" / "python"), "-m", "tools.gil_trading_scanner_runtime.runtime"]
        if not Path(cmd[0]).exists():
            cmd[0] = "python3"

        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=240)
        (out / "runtime.stdout.log").write_text(proc.stdout)
        (out / "runtime.stderr.log").write_text(proc.stderr)

        if proc.returncode != 0:
            emit(
                output,
                "BLOCKED-RUNTIME",
                reason="scanner-runtime-nonzero",
                returncode=proc.returncode,
                stdout_tail=proc.stdout[-3000:],
                stderr_tail=proc.stderr[-3000:],
                exact_command=" ".join(cmd),
                expected_sha=EXPECTED_SHA,
                actual_sha=actual_sha,
            )
            return

        if not db.exists():
            emit(output, "BLOCKED-RUNTIME", reason="scanner-db-missing", expected_sha=EXPECTED_SHA, actual_sha=actual_sha)
            return

        con = sqlite3.connect(db)
        try:
            tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            if "trading_scanner_candidates" not in tables:
                emit(output, "BLOCKED-RUNTIME", reason="candidate-table-missing", tables=sorted(tables))
                return

            row_count = con.execute("select count(*) from trading_scanner_candidates").fetchone()[0]
            summary = [
                {"symbol": r[0], "setup_family": r[1], "queue_state": r[2], "count": r[3]}
                for r in con.execute(
                    "select symbol, setup_family, queue_state, count(*) "
                    "from trading_scanner_candidates "
                    "group by symbol, setup_family, queue_state "
                    "order by symbol, setup_family, queue_state"
                )
            ]
            forbidden_tables = sorted(
                t for t in tables
                if any(k in t.lower() for k in ("order", "fill", "intent", "position", "ledger", "trade_execution"))
            )
        finally:
            con.close()

        if row_count <= 0:
            emit(
                output,
                "BLOCKED-EVIDENCE",
                reason="zero-candidates-recorded",
                exact_command=" ".join(cmd),
                expected_sha=EXPECTED_SHA,
                actual_sha=actual_sha,
                row_count=row_count,
                summary=summary,
            )
            return

        if forbidden_tables:
            emit(
                output,
                "BLOCKED-RUNTIME",
                reason="unexpected-trading-artifact-tables",
                forbidden_tables=forbidden_tables,
                row_count=row_count,
                summary=summary,
            )
            return

        emit(
            output,
            "PASS",
            expected_sha=EXPECTED_SHA,
            actual_sha=actual_sha,
            provider="stooq",
            universe=UNIVERSE.split(","),
            exact_command=" ".join(cmd),
            runtime_returncode=proc.returncode,
            candidate_row_count=row_count,
            candidate_summary=summary,
            sqlite_artifact=str(db.name),
            trading_artifact_tables=[],
            note="one-shot VPS proof via existing research execution harness; no deploy, no timer, no Slack execution, no orders/fills",
        )
    except subprocess.TimeoutExpired as exc:
        emit(output, "BLOCKED-RUNTIME", reason="timeout", detail=repr(exc))
    except Exception as exc:
        emit(output, "BLOCKED-RUNTIME", reason="exception", detail=repr(exc))
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    main(a.job, a.output)
