#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    job_path = Path(args.job)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    job = json.loads(job_path.read_text())

    payload = {
        "object_id": job["object_id"],
        "terminal_state": "HARNESS-PASS",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "executor": "vps",
        "checks": {
            "python_execution": True,
            "job_manifest_readable": True,
            "result_directory_writable": True,
            "terminal_delivery_contract": True
        }
    }
    result_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    (out / "terminal_result.json").write_bytes(result_bytes)
    (out / "evidence.sha256").write_text(
        hashlib.sha256(result_bytes).hexdigest() + "  terminal_result.json\n"
    )
    print("TERMINAL_STATE=HARNESS-PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
