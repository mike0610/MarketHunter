import argparse, json, shutil, subprocess
from pathlib import Path

OID = "GIL-BREAKOUT-LONG-HISTORICAL-VALIDATION-001"
SHA = "828e01e20598c4331d0fa52dd2215661cb41300a"

def emit(out, state, **extra):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "terminal_result.json").write_text(
        json.dumps({"object_id": OID, "terminal_state": state, **extra}, indent=2, sort_keys=True)
    )

def main(job, out):
    outp = Path(out).resolve()
    repo = outp / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--quiet", "https://github.com/mike0610/MarketHunter.git", str(repo)],
            check=True, timeout=120,
        )
        subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", SHA], check=True, timeout=30)
        proc = subprocess.run(
            ["python3", "-m", "research.run_breakout_validation"],
            cwd=repo, capture_output=True, text=True, timeout=300,
        )
        (outp / "breakout-long.txt").write_text(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            emit(out, "BLOCKED-RUNTIME", master_sha=SHA, reason="runner-failed", returncode=proc.returncode)
            return
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not any(line.startswith("OOS TOTAL:") for line in lines):
            emit(out, "BLOCKED-RUNTIME", master_sha=SHA, reason="missing-oos-total", output=lines)
            return
        emit(
            out,
            "EVIDENCE_READY",
            master_sha=SHA,
            verdict="ENTRY_VALIDATION_EVIDENCE_READY",
            universe=["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
            history_bars=1300,
            split="70/30",
            output=lines,
            broker_execution="ZERO",
            live_money="ZERO",
        )
    except Exception as exc:
        emit(out, "BLOCKED-RUNTIME", master_sha=SHA, reason="exception", detail=repr(exc))
    finally:
        if repo.exists():
            shutil.rmtree(repo, ignore_errors=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    main(args.job, args.output)
