"""
MarketHunter

tools/outcome_intelligence/runtime.py

Module:
Outcome Intelligence runtime orchestration - the autonomous entry
point a systemd timer invokes on a daily/weekly cadence (see
deploy/systemd/). This module adds NO analysis logic of its own; it
wires together the already-merged acquisition/analysis library
(tools/outcome_intelligence/acquisition.py,
tools/outcome_intelligence/analysis.py) with Slack delivery
(tools/outcome_intelligence/slack_delivery.py), reading all secrets
and configuration from the environment. It never hardcodes a webhook
URL, API base URL, or any credential.

Cadence contract:
- daily: capture exactly one new run, then - if at least 2 runs now
  exist - render and deliver the daily change summary.
- weekly: does NOT capture (the daily cycle is the only capture
  point). If at least PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1 runs exist,
  render and deliver the weekly persistence summary.

Fail-closed contract:
- Missing required environment variable -> logged, exit 2. No capture,
  no analysis, no Slack message attempted.
- Capture failure (API unreachable, non-200, malformed JSON, run
  conflict) -> logged, exit 1. capture_outcome_intelligence_run() is
  already atomic - a failed capture writes nothing and never
  overwrites a prior artifact, so this never fabricates or corrupts
  history.
- Insufficient run history for the requested cadence -> logged as
  informational, exit 0, NO Slack message sent. This is expected
  during warm-up, not a failure - there is nothing "applicable" to
  report yet.
- Analysis error (malformed/missing required field in a captured
  payload) -> logged, exit 1. No Slack message sent.
- Slack delivery failure -> logged, exit 1. The capture snapshot (for
  the daily cycle) was already durably persisted before delivery was
  attempted, so a delivery failure never loses data.

Non-goals: no auto-disable/promote/trade, no DB/API/dashboard
mutation, no deletion of any run artifact, no retry/backoff policy
(systemd's own timer cadence is the retry mechanism).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx

from tools.outcome_intelligence.acquisition import (
    OutcomeIntelligenceAcquisitionError,
    SETUP_REASONS_ENDPOINT,
    capture_outcome_intelligence_run,
    list_run_manifests,
    load_run_payload,
    utcnow,
)
from tools.outcome_intelligence.analysis import (
    OutcomeIntelligenceAnalysisError,
    PERSISTENCE_MIN_CONSECUTIVE_RUNS,
    daily_analysis,
    render_daily_summary,
    render_weekly_summary,
    weekly_analysis,
)
from tools.outcome_intelligence.slack_delivery import (
    SlackDeliveryError,
    send_slack_report,
)

DEFAULT_OUTPUT_DIR = Path("data/outcome_intelligence")

# Environment variable names - documented in
# deploy/systemd/outcome-intelligence.env.example. Never given a
# hardcoded default value; missing -> fail closed.
ENV_API_BASE_URL = "OUTCOME_INTELLIGENCE_API_BASE_URL"
ENV_SLACK_WEBHOOK_URL = "OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL"
# Optional - defaults to DEFAULT_OUTPUT_DIR when unset.
ENV_OUTPUT_DIR = "OUTCOME_INTELLIGENCE_OUTPUT_DIR"

logger = logging.getLogger("outcome_intelligence.runtime")

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2


class RuntimeConfigError(Exception):
    """A required environment variable is missing - fail closed."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)

    if not value:
        raise RuntimeConfigError(
            f"required environment variable {name!r} is not set"
        )

    return value


def _resolve_output_dir(output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir

    raw = os.environ.get(ENV_OUTPUT_DIR)

    return Path(raw) if raw else DEFAULT_OUTPUT_DIR


def _client_or_default(
    client: httpx.Client | None, timeout: float
) -> tuple[httpx.Client, bool]:
    """Returns (client, owns_client) - owns_client callers must close it."""

    if client is not None:
        return client, False

    return httpx.Client(timeout=timeout), True


def _deliver(webhook_url: str, text: str, slack_client: httpx.Client | None) -> bool:
    client, owns_client = _client_or_default(slack_client, timeout=15.0)

    try:
        send_slack_report(webhook_url=webhook_url, text=text, client=client)
    except SlackDeliveryError as error:
        logger.error("Slack delivery failed: %s", error)
        return False
    finally:
        if owns_client:
            client.close()

    return True


def run_daily_cycle(
    *,
    output_dir: Path | None = None,
    capture_client: httpx.Client | None = None,
    slack_client: httpx.Client | None = None,
    now_utc: Callable[[], datetime] = utcnow,
) -> int:
    """
    Capture one new run, then - if at least 2 runs now exist - render
    and deliver the daily change summary to Slack.
    """

    try:
        base_url = _require_env(ENV_API_BASE_URL)
        webhook_url = _require_env(ENV_SLACK_WEBHOOK_URL)
    except RuntimeConfigError as error:
        logger.error("daily cycle config error: %s", error)
        return EXIT_CONFIG_ERROR

    resolved_output_dir = _resolve_output_dir(output_dir)

    client, owns_client = _client_or_default(capture_client, timeout=30.0)

    try:
        capture_outcome_intelligence_run(
            base_url=base_url,
            output_dir=resolved_output_dir,
            client=client,
            now_utc=now_utc,
        )
    except (OutcomeIntelligenceAcquisitionError, OSError) as error:
        logger.error("daily cycle capture failed: %s", error)
        return EXIT_FAILURE
    finally:
        if owns_client:
            client.close()

    logger.info("daily cycle: capture succeeded")

    manifests = list_run_manifests(resolved_output_dir)

    if len(manifests) < 2:
        logger.info(
            "daily cycle: insufficient history for a report (%d/2 runs) "
            "- nothing to send",
            len(manifests),
        )
        return EXIT_OK

    prior_manifest, latest_manifest = manifests[-2], manifests[-1]

    try:
        prior_setup_reasons = load_run_payload(
            resolved_output_dir, prior_manifest, SETUP_REASONS_ENDPOINT
        )
        latest_setup_reasons = load_run_payload(
            resolved_output_dir, latest_manifest, SETUP_REASONS_ENDPOINT
        )
        result = daily_analysis(
            prior_setup_reasons=prior_setup_reasons,
            latest_setup_reasons=latest_setup_reasons,
            prior_run_id=prior_manifest.run_id,
            latest_run_id=latest_manifest.run_id,
        )
        summary = render_daily_summary(result)
    except (OutcomeIntelligenceAnalysisError, OutcomeIntelligenceAcquisitionError) as error:
        logger.error("daily cycle analysis failed: %s", error)
        return EXIT_FAILURE

    if not _deliver(webhook_url=webhook_url, text=summary, slack_client=slack_client):
        return EXIT_FAILURE

    logger.info("daily cycle: report delivered")
    return EXIT_OK


def run_weekly_cycle(
    *,
    output_dir: Path | None = None,
    slack_client: httpx.Client | None = None,
) -> int:
    """
    Render and deliver the weekly persistence summary to Slack, if
    enough captured history exists. Never captures a new run - the
    daily cycle is the only capture point.
    """

    try:
        webhook_url = _require_env(ENV_SLACK_WEBHOOK_URL)
    except RuntimeConfigError as error:
        logger.error("weekly cycle config error: %s", error)
        return EXIT_CONFIG_ERROR

    resolved_output_dir = _resolve_output_dir(output_dir)
    required_runs = PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1

    manifests = list_run_manifests(resolved_output_dir)

    if len(manifests) < required_runs:
        logger.info(
            "weekly cycle: insufficient history for a report (%d/%d runs) "
            "- nothing to send",
            len(manifests),
            required_runs,
        )
        return EXIT_OK

    try:
        setup_reasons_by_run = [
            (
                manifest.run_id,
                load_run_payload(
                    resolved_output_dir, manifest, SETUP_REASONS_ENDPOINT
                ),
            )
            for manifest in manifests
        ]
        result = weekly_analysis(setup_reasons_by_run)
        summary = render_weekly_summary(result)
    except (OutcomeIntelligenceAnalysisError, OutcomeIntelligenceAcquisitionError) as error:
        logger.error("weekly cycle analysis failed: %s", error)
        return EXIT_FAILURE

    if not _deliver(webhook_url=webhook_url, text=summary, slack_client=slack_client):
        return EXIT_FAILURE

    logger.info("weekly cycle: report delivered")
    return EXIT_OK


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="outcome-intelligence-runtime")
    subparsers = parser.add_subparsers(dest="cycle", required=True)
    subparsers.add_parser(
        "daily", help="Capture + deliver the daily change report."
    )
    subparsers.add_parser(
        "weekly", help="Deliver the weekly persistence report (no capture)."
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cycle == "daily":
        sys.exit(run_daily_cycle())
    else:
        sys.exit(run_weekly_cycle())


if __name__ == "__main__":
    main()
