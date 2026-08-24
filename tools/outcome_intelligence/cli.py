"""
MarketHunter

tools/outcome_intelligence/cli.py

Module:
Outcome Intelligence CLI - manual/externally-scheduled entry point for
`capture`, `daily`, and `weekly` Outcome Intelligence runs.

This module performs no scheduling itself. Running it periodically
(cron, Task Scheduler, or any mechanism outside this repository) is
the caller's responsibility - this file adds no worker/service/VPS
wiring of any kind.

Usage:
    python -m tools.outcome_intelligence.cli capture --base-url <url>
    python -m tools.outcome_intelligence.cli daily
    python -m tools.outcome_intelligence.cli weekly
"""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from tools.outcome_intelligence.acquisition import (
    capture_outcome_intelligence_run,
    list_run_manifests,
    load_run_payload,
    SETUP_REASONS_ENDPOINT,
)
from tools.outcome_intelligence.analysis import (
    PERSISTENCE_MIN_CONSECUTIVE_RUNS,
    daily_analysis,
    render_daily_summary,
    render_weekly_summary,
    weekly_analysis,
)

DEFAULT_OUTPUT_DIR = Path("data/outcome_intelligence")


def _capture(base_url: str, output_dir: Path) -> None:
    with httpx.Client(timeout=30.0) as client:
        manifest = capture_outcome_intelligence_run(
            base_url=base_url,
            output_dir=output_dir,
            client=client,
        )

    print(
        f"Captured run {manifest.run_id} from {manifest.base_url} "
        f"({len(manifest.snapshots)} endpoint(s))."
    )

    for record in manifest.snapshots:
        print(
            f"  - {record.endpoint}: {record.byte_count} bytes, "
            f"sha256={record.sha256}"
        )


def _daily(output_dir: Path) -> None:
    manifests = list_run_manifests(output_dir)

    if len(manifests) < 2:
        print(
            "Daily analysis needs at least 2 captured runs "
            f"(found {len(manifests)}). Run `capture` again later."
        )
        return

    prior_manifest, latest_manifest = manifests[-2], manifests[-1]

    prior_setup_reasons = load_run_payload(
        output_dir, prior_manifest, SETUP_REASONS_ENDPOINT
    )
    latest_setup_reasons = load_run_payload(
        output_dir, latest_manifest, SETUP_REASONS_ENDPOINT
    )

    result = daily_analysis(
        prior_setup_reasons=prior_setup_reasons,
        latest_setup_reasons=latest_setup_reasons,
        prior_run_id=prior_manifest.run_id,
        latest_run_id=latest_manifest.run_id,
    )

    print(render_daily_summary(result))


def _weekly(output_dir: Path) -> None:
    manifests = list_run_manifests(output_dir)
    required_runs = PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1

    if len(manifests) < required_runs:
        print(
            f"Weekly analysis needs at least {required_runs} captured runs "
            f"to form {PERSISTENCE_MIN_CONSECUTIVE_RUNS} independent "
            f"incremental windows (found {len(manifests)}). Run `capture` "
            "again later."
        )
        return

    setup_reasons_by_run = [
        (
            manifest.run_id,
            load_run_payload(output_dir, manifest, SETUP_REASONS_ENDPOINT),
        )
        for manifest in manifests
    ]

    result = weekly_analysis(setup_reasons_by_run)

    print(render_weekly_summary(result))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="outcome-intelligence")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory holding captured run artifacts (default: %(default)s).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser(
        "capture", help="Capture one new Outcome Intelligence run."
    )
    capture_parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL of the authoritative MarketHunter API runtime.",
    )

    subparsers.add_parser(
        "daily", help="Compare the two most recent captured runs."
    )
    subparsers.add_parser(
        "weekly", help="Review persistence across the captured run history."
    )

    args = parser.parse_args(argv)

    if args.command == "capture":
        _capture(base_url=args.base_url, output_dir=args.output_dir)
    elif args.command == "daily":
        _daily(output_dir=args.output_dir)
    elif args.command == "weekly":
        _weekly(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
