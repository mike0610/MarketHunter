import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

OBJECT_ID = "MH-STAGE3-STRATEGY-LIVE-PROOF-001"
EXPECTED_SHA = "0f31dddf1a8f480eca68794daec598fd00ea8524"
UNIVERSE = "SPY,QQQ,AAPL,MSFT,NVDA"


def emit(output, state, **extra):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "terminal_result.json").write_text(json.dumps(
        {"object_id": OBJECT_ID, "terminal_state": state, **extra}, indent=2, sort_keys=True
    ))


def main(job_path, output):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "repo"
    db = out / "stage3_live_proof.db"
    try:
        job = json.loads(Path(job_path).read_text())
        if job.get("object_id") != OBJECT_ID:
            raise RuntimeError("object id mismatch")
        subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(work)],check=True,timeout=120)
        subprocess.run(["git","-C",str(work),"checkout","--quiet",EXPECTED_SHA],check=True,timeout=30)
        actual = subprocess.check_output(["git","-C",str(work),"rev-parse","HEAD"],text=True).strip()
        if actual != EXPECTED_SHA:
            emit(output,"BLOCKED-RUNTIME",reason="sha-mismatch",actual_sha=actual); return

        vps_python = Path("/home/ubuntu/MarketHunter/.venv/bin/python")
        if not vps_python.exists():
            emit(output,"BLOCKED-RUNTIME",reason="vps-venv-python-missing"); return

        env=os.environ.copy()
        env.update({
            "PYTHONPATH":str(work),
            "TRADING_SCANNER_DB_PATH":str(db),
            "TRADING_SCANNER_MARKET_DATA_PROVIDER":"yahoo",
            "TRADING_SCANNER_UNIVERSE_SYMBOLS":UNIVERSE,
            "TRADING_SCANNER_MAX_DATA_AGE_SECONDS":"345600",
        })
        scan=[str(vps_python),"-m","tools.gil_trading_scanner_runtime.runtime"]
        proc=subprocess.run(scan,cwd=work,env=env,capture_output=True,text=True,timeout=240)
        (out/"scanner.stdout.log").write_text(proc.stdout)
        (out/"scanner.stderr.log").write_text(proc.stderr)
        if proc.returncode != 0:
            emit(output,"BLOCKED-RUNTIME",reason="scanner-runtime-nonzero",stderr_tail=proc.stderr[-3000:]); return

        proof_code = r"""
import os, sqlite3
from datetime import datetime, timezone
from strategies.registry_foundation import StrategyUsability, StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import QueueState
from trading_scanner.store import TradingScannerStore

db=os.environ["TRADING_SCANNER_DB_PATH"]
scanner=TradingScannerStore(db)
store=StrategyDecisionStore(db)
usable=StrategyVersionAssessment(StrategyUsability.USABLE, ())
candidates=scanner.list_candidates(queue_state=QueueState.CANDIDATE)
if not candidates:
    raise SystemExit(21)
for c in candidates:
    store.record(validate_candidate(c,strategy_assessment=usable,decided_at=datetime.now(timezone.utc)))
"""
        stage3=subprocess.run([str(vps_python),"-c",proof_code],cwd=work,env=env,capture_output=True,text=True,timeout=60)
        (out/"strategy.stdout.log").write_text(stage3.stdout)
        (out/"strategy.stderr.log").write_text(stage3.stderr)
        if stage3.returncode == 21:
            emit(output,"BLOCKED-EVIDENCE",reason="zero-real-candidates"); return
        if stage3.returncode != 0:
            emit(output,"BLOCKED-RUNTIME",reason="strategy-runtime-nonzero",stderr_tail=stage3.stderr[-3000:]); return

        con=sqlite3.connect(db)
        tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        rows=[{"symbol":r[0],"outcome":r[1],"strategy_id":r[2],"strategy_version":r[3]}
              for r in con.execute("select symbol,outcome,strategy_id,strategy_version from strategy_decisions order by symbol")]
        candidate_count=con.execute("select count(*) from trading_scanner_candidates where queue_state='CANDIDATE'").fetchone()[0]
        forbidden=sorted(t for t in tables if any(k in t.lower() for k in ("order","fill","position","ledger","intent")))
        con.close()
        if not rows:
            emit(output,"BLOCKED-EVIDENCE",reason="zero-strategy-decisions"); return
        if forbidden:
            emit(output,"BLOCKED-RUNTIME",reason="execution-artifacts-present",forbidden_tables=forbidden); return
        emit(output,"PASS",expected_sha=EXPECTED_SHA,actual_sha=actual,provider="yahoo",
             real_candidate_count=candidate_count,strategy_decision_count=len(rows),decisions=rows,
             trading_artifact_tables=[],sqlite_artifact=db.name,
             note="Stage 3 only: real candidates -> deterministic durable strategy decisions; zero execution artifacts")
    except subprocess.TimeoutExpired as exc:
        emit(output,"BLOCKED-RUNTIME",reason="timeout",detail=repr(exc))
    except Exception as exc:
        emit(output,"BLOCKED-RUNTIME",reason="exception",detail=repr(exc))
    finally:
        if work.exists(): shutil.rmtree(work,ignore_errors=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--job",required=True); p.add_argument("--output",required=True)
    a=p.parse_args(); main(a.job,a.output)
