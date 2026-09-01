"""
MarketHunter

tools/experiment1_runtime/runtime.py

Module:
The Experiment 1 recurring paper-runtime cycle - one bounded pass that
a systemd timer invokes on a cadence (see deploy/systemd/). Each pass
runs, in order:
  0. GIL Slack envelope ingest (experiment1.gil_slack_adapter.run_gil_slack_ingest_cycle)
     - only when a real Slack read credential is configured (see
     build_gil_slack_reader/ENV_SLACK_BOT_TOKEN below; skipped entirely,
     not fabricated, when it is not) - reads the allowlisted
     #global-investment-lab channel for an explicit
     "GIL DECISION ENVELOPE v1" marker block and forwards ONLY a
     validated envelope into the exact same durable GIL Decision Inbox
     step 1 below already drains. Ordinary Slack prose is never parsed
     into a decision.
  1. GIL-ingestion drain (experiment1.gil_decision.drain_gil_decision_inbox)
     - automatically processes every envelope durably received via
     POST /experiment1/gil-decisions (or the Slack adapter above) since
     the last cycle, submitting each as a PENDING intent (or
     NO_ACTION/BLOCKED/WAITING_EVIDENCE, as applicable) before this same
     pass's fill step runs, so a freshly ingested decision does not have
     to wait for the next cycle to be eligible for a fill. No manual
     operator step: this is the "no parallel execution path" automatic
     drain the GIL Decision Inbox contract requires. A cycle that finds
     nothing PENDING_DRAIN is a normal, successful, no-action outcome.
  2. market fill cycle (experiment1.runtime.run_market_cycle) - fresh
     evidence for every PENDING intent (including one just drained
     above), paper-fills what it can.
  3. protective exit cycle (experiment1.lifecycle.run_protective_exit_cycle)
     - re-checks every FILLED intent that carries a stop_loss/take_profit
     against fresh evidence.
  4. multi-symbol MTM cycle (experiment1.mtm.run_mtm_cycle), once per
     canonical account - recomputes NAV/equity/unrealized P&L/drawdown
     from fresh marks, fails closed to cost-basis fallback per symbol
     exactly as already built (never fabricates a mark).

This module adds no new trading/accounting/quote logic - every step
above calls an already-merged, already-tested function unmodified.
Idempotent and restart-safe by construction, inherited directly from
each of those functions' own tested contracts (PRs #70, #74, #76, #77,
plus the GIL Decision Inbox this module now drains, plus the Slack
ingest adapter's own persisted cursor) - a duplicate or restarted
invocation of this script cannot duplicate an intent, fill, exit, MTM
snapshot, or GIL-decision binding.

Fail-closed contract:
- A quote that is missing, stale, or for a symbol not recognized as a
  verified Binance crypto pair never reaches a fill or a fresh mark -
  see build_quote_source() and experiment1/market_data_providers.py.
- No decision is manufactured to prove GIL ingestion "works" - a
  cycle with zero pending GIL decisions is a normal, successful,
  no-action outcome, not a failure to work around.
- A decision carrying an execution_condition (a subjective condition
  GIL could not structure) is never guessed into an executable order -
  it fails closed as WAITING_EVIDENCE, since no evaluator exists that
  can objectively verify an arbitrary condition against approved market
  evidence.
- A decision carrying a structured ExecutionTrigger not yet satisfied,
  or a sizing mode that needs a fresh quote that is not currently
  available, stays PENDING_DRAIN and is re-evaluated next cycle - it is
  never submitted early and never guessed at.
- A Slack message without the exact envelope marker, an edited message,
  or a malformed/unparseable envelope block is never guessed into a
  decision - see experiment1/gil_slack_adapter.py.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from experiment1.engine import Experiment1Engine, Experiment1Error, STARTING_CASH
from experiment1.gil_decision import GilIngestionResult, drain_gil_decision_inbox
from experiment1.gil_slack_adapter import (
    SlackChannelReader,
    SlackIngestResult,
    build_gil_slack_reader,
    resolve_gil_channel_id,
    run_gil_slack_ingest_cycle,
)
from experiment1.lifecycle import LifecycleResult, run_protective_exit_cycle
from experiment1.market_data_providers import (
    AssetClass,
    FreshnessGuardedQuoteSource,
    MultiAssetQuoteSource,
)
from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import OrderIntent
from experiment1.mtm import MtmCycleResult, run_mtm_cycle
from experiment1.runtime import AsyncQuoteSource, CycleResult, run_market_cycle

# Matches api/experiment1_api.py's own EXPERIMENT1_DB_PATH convention
# exactly - one canonical env var name for the db path across every
# Experiment 1 entry point, never a second/duplicate name invented here.
ENV_DB_PATH = "EXPERIMENT1_DB_PATH"
DEFAULT_DB_PATH = Path("data/experiment1.db")

DEFAULT_FRESHNESS_MAX_AGE = timedelta(minutes=5)

logger = logging.getLogger("experiment1_runtime.runtime")

EXIT_OK = 0
EXIT_FAILURE = 1


def _resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else DEFAULT_DB_PATH


def _classify(intent: OrderIntent) -> AssetClass | None:
    """
    The only asset-class classification this repo has real evidence
    for: a Binance USDT-quoted pair is CRYPTO. Everything else returns
    None - MultiAssetQuoteSource already fails that closed to
    WAITING_EVIDENCE (see experiment1/market_data_providers.py) rather
    than guessing which non-crypto class an unrecognized symbol might
    belong to.
    """
    return AssetClass.CRYPTO if intent.symbol.endswith("USDT") else None


def build_quote_source(*, freshness_max_age: timedelta = DEFAULT_FRESHNESS_MAX_AGE) -> AsyncQuoteSource:
    """
    The exact same verified crypto path (BinanceExperiment1QuoteSource)
    used throughout Experiment 1's tests, wrapped in the existing
    freshness guard and multi-asset router from PR #74 - no new
    freshness or routing logic. Only CRYPTO has a registered provider;
    every other asset class stays BLOCKED-EVIDENCE by omission, not by
    a fabricated always-unavailable entry for classes this script
    cannot tell apart anyway.
    """
    crypto_source = FreshnessGuardedQuoteSource(
        BinanceExperiment1QuoteSource(), max_age=freshness_max_age
    )
    return MultiAssetQuoteSource(providers={AssetClass.CRYPTO: crypto_source}, classify=_classify)


def _protective_exit_candidates(engine: Experiment1Engine) -> tuple[str, ...]:
    """
    Every currently FILLED intent carrying a stop_loss or take_profit -
    run_protective_exit_cycle itself already safely no-ops
    (NO_PROTECTIVE_RULE / ALREADY_CLOSED) on anything else, but there is
    no reason to even ask it about an entry with neither rule set.
    """
    candidates = []
    for intent_id in engine.filled_intent_ids():
        intent = engine.get_intent(intent_id)
        if intent.stop_loss is not None or intent.take_profit is not None:
            candidates.append(intent_id)
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class Experiment1CycleSummary:
    market_fill_results: tuple[CycleResult, ...]
    protective_exit_results: tuple[LifecycleResult, ...]
    mtm_results: tuple[MtmCycleResult, ...]
    gil_ingestion_results: tuple[GilIngestionResult, ...]
    slack_ingest_results: tuple[SlackIngestResult, ...] = ()


async def run_experiment1_cycle(
    engine: Experiment1Engine,
    quote_source: AsyncQuoteSource,
    *,
    slack_reader: SlackChannelReader | None = None,
) -> Experiment1CycleSummary:
    # GIL Slack envelope ingest FIRST, when a reader is actually wired -
    # a validated envelope becomes a durable inbox row before the drain
    # step below runs, so it is eligible the same pass rather than
    # waiting a full cycle. slack_reader=None (no credential configured)
    # is a normal, successful skip - never an error.
    slack_ingest_results: tuple[SlackIngestResult, ...] = ()
    if slack_reader is not None:
        slack_ingest_results = await run_gil_slack_ingest_cycle(engine, slack_reader, resolve_gil_channel_id())

    # Automatic drain of the durable GIL Decision Inbox - no manual
    # operator step - so a freshly ingested decision (whether from the
    # HTTP endpoint or the Slack adapter above) becomes a PENDING intent
    # before this same pass's market fill cycle runs, rather than
    # waiting for the next timer tick. An empty result (nothing
    # PENDING_DRAIN) is a normal, successful outcome.
    gil_ingestion_results = await drain_gil_decision_inbox(engine, quote_source)

    market_fill_results = await run_market_cycle(engine, quote_source)

    protective_exit_results = await run_protective_exit_cycle(
        engine, quote_source, _protective_exit_candidates(engine)
    )

    mtm_results: list[MtmCycleResult] = []
    for account in STARTING_CASH:
        try:
            mtm_results.append(await run_mtm_cycle(engine, quote_source, account))
        except Experiment1Error as exc:
            # Every STARTING_CASH account is created by Experiment1Engine's
            # own __init__ - this should never actually happen, but a
            # not-yet-initialized account must never crash the whole
            # cycle for every other account.
            logger.warning("mtm cycle skipped for %s: %s", account.value, exc)

    return Experiment1CycleSummary(
        market_fill_results,
        protective_exit_results,
        tuple(mtm_results),
        gil_ingestion_results,
        slack_ingest_results,
    )


def _count(results, outcome: str) -> int:
    return sum(1 for r in results if r.outcome == outcome)


def _log_summary(summary: Experiment1CycleSummary) -> None:
    logger.info(
        "market fill: %d intent(s) - filled=%d waiting=%d skipped=%d source_error=%d",
        len(summary.market_fill_results),
        _count(summary.market_fill_results, "PAPER_FILLED"),
        _count(summary.market_fill_results, "WAITING_EVIDENCE"),
        _count(summary.market_fill_results, "SKIPPED"),
        _count(summary.market_fill_results, "SOURCE_ERROR"),
    )
    logger.info(
        "protective exit: %d entr(y/ies) checked - triggered=%d active=%d already_closed=%d waiting=%d",
        len(summary.protective_exit_results),
        _count(summary.protective_exit_results, "STOP_LOSS") + _count(summary.protective_exit_results, "TAKE_PROFIT"),
        _count(summary.protective_exit_results, "ACTIVE"),
        _count(summary.protective_exit_results, "ALREADY_CLOSED"),
        _count(summary.protective_exit_results, "WAITING_EVIDENCE"),
    )
    partial = sum(1 for r in summary.mtm_results if r.completeness.value == "PARTIAL_EVIDENCE_FALLBACK")
    logger.info(
        "mtm: %d account(s) repriced - partial_evidence_fallback=%d",
        len(summary.mtm_results),
        partial,
    )
    logger.info(
        "gil ingestion: %d decision(s) - blocked=%d",
        len(summary.gil_ingestion_results),
        _count(summary.gil_ingestion_results, "BLOCKED"),
    )
    logger.info(
        "gil slack ingest: %d message(s) - received=%d malformed=%d edited_ambiguous=%d ignored=%d",
        len(summary.slack_ingest_results),
        sum(1 for r in summary.slack_ingest_results if r.status == "RECEIVED"),
        sum(1 for r in summary.slack_ingest_results if r.status in ("MALFORMED", "MALFORMED_SHAPE")),
        sum(1 for r in summary.slack_ingest_results if r.status == "EDITED_AMBIGUOUS"),
        sum(1 for r in summary.slack_ingest_results if r.status == "IGNORED_NO_MARKER"),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="experiment1-runtime")
    parser.parse_args(argv)  # no subcommands - one bounded cycle per invocation

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_path = _resolve_db_path()
    logger.info("experiment1 runtime cycle starting - db=%s", db_path)

    engine = Experiment1Engine(db_path)
    quote_source = build_quote_source()
    # None (no EXPERIMENT1_GIL_SLACK_BOT_TOKEN configured) is a normal,
    # successful skip of the Slack ingest step - see
    # experiment1/gil_slack_adapter.py's credential boundary.
    slack_reader = build_gil_slack_reader()

    try:
        summary = asyncio.run(run_experiment1_cycle(engine, quote_source, slack_reader=slack_reader))
    except Exception:
        logger.exception("experiment1 runtime cycle failed")
        sys.exit(EXIT_FAILURE)

    _log_summary(summary)
    logger.info("experiment1 runtime cycle complete")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
