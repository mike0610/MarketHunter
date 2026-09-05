import argparse, json, shutil, subprocess
from pathlib import Path

OID = "GIL-BREAKOUT-LONG-EXIT-3R-VALIDATION-001"
SHA = "18e9868cb30668ec1c6d7a5627bd89e7c2bdc475"

def emit(out, state, **extra):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "terminal_result.json").write_text(
        json.dumps({"object_id": OID, "terminal_state": state, **extra}, sort_keys=True)
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
            ["python3", "-m", "research.run_breakout_exit_validation"],
            cwd=repo, capture_output=True, text=True, timeout=300,
        )
        (outp / "breakout-exit-3r.json").write_text(proc.stdout)
        (outp / "runner-stderr.txt").write_text(proc.stderr)
        if proc.returncode != 0:
            emit(out, "BLOCKED-RUNTIME", master_sha=SHA, reason="runner-failed", returncode=proc.returncode)
            return
        payload = json.loads(proc.stdout)
        oos = payload.get("oos_total")
        if not isinstance(oos, dict) or not oos.get("trades"):
            emit(out, "BLOCKED-RUNTIME", master_sha=SHA, reason="missing-oos-exit-evidence")
            return
        emit(
            out,
            "EVIDENCE_READY",
            master_sha=SHA,
            verdict="EXIT_3R_VALIDATION_EVIDENCE_READY",
            hypothesis=payload.get("hypothesis"),
            target_r=payload.get("target_r"),
            oos_total=oos,
            per_symbol=[
                {"symbol": x["symbol"], "oos": x["oos"]}
                for x in payload.get("symbols", [])
            ],
            notes=payload.get("notes", {}),
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
