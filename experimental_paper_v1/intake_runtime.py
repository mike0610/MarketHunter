"""Forward-only experimental paper intake runtime.

Continuously records only newly first-seen Research signals into the isolated
sandbox. It NEVER creates paper fills, broker orders, or exchange actions.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from forward_gate import ForwardSignalGate


def emit(**payload) -> None:
    payload.setdefault("time_utc", datetime.now(timezone.utc).isoformat())
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def run_once(gate: ForwardSignalGate) -> None:
    armed_at = gate.arm()
    summary = gate.collect()
    emit(
        type="INTAKE_CYCLE",
        armed_at=armed_at,
        source_rows=summary.source_rows,
        previously_seen=summary.previously_seen,
        historical_ignored=summary.historical_ignored,
        invalid_ignored=summary.invalid_ignored,
        new_waiting_evidence=summary.new_waiting_evidence,
        snapshot=gate.snapshot(),
        simulation_only=True,
        fills_enabled=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--sandbox-db", required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.interval_seconds < 15:
        parser.error("--interval-seconds must be >= 15")

    gate = ForwardSignalGate(Path(args.source_db), Path(args.sandbox_db))
    emit(type="INTAKE_STARTED", simulation_only=True, fills_enabled=False)

    while True:
        try:
            run_once(gate)
        except Exception as exc:
            emit(type="INTAKE_ERROR", error_type=type(exc).__name__, message=str(exc))
            if args.once:
                raise
        if args.once:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
