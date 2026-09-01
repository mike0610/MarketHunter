"""
MarketHunter

tools/experiment1_runtime/runtime.py

One bounded Experiment 1 paper-runtime pass. A systemd timer invokes this
module repeatedly. Each pass first polls the optional strict Slack GIL
transport, then drains the durable GIL Decision Inbox, runs market fills,
protective exits and MTM. The Slack transport is disabled unless explicitly
configured and can only accept exact GIL DECISION ENVELOPE v1 messages from
the canonical GIL channel/user; ordinary research prose is never parsed.
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
from experiment1.slack_transport import (
    SlackTransportError,
    client_from_env,
    config_from_env,
    poll_slack_gil_decisions,
    transport_enabled_from_env,
)

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
    return AssetClass.CRYPTO if intent.symbol.endswith("USDT") else None


def build_quote_source(*, freshness_max_age: timedelta = DEFAULT_FRESHNESS_MAX_AGE) -> AsyncQuoteSource:
    crypto_source = FreshnessGuardedQuoteSource(
        BinanceExperiment1QuoteSource(), max_age=freshness_max_age
    )
    return MultiAssetQuoteSource(providers={AssetClass.CRYPTO: crypto_source}, classify=_classify)


def _protective_exit_candidates(engine: Experiment1Engine) -> tuple[str, ...]:
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


async def run_experiment1_cycle(
    engine: Experiment1Engine, quote_source: AsyncQuoteSource
) -> Experiment1CycleSummary:
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
            logger.warning("mtm cycle skipped for %s: %s", account.value, exc)

    return Experiment1CycleSummary(
        market_fill_results, protective_exit_results, tuple(mtm_results), gil_ingestion_results
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
    partial = sum(
        1 for r in summary.mtm_results if r.completeness.value == "PARTIAL_EVIDENCE_FALLBACK"
    )
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


def _poll_optional_slack_transport(engine: Experiment1Engine) -> None:
    if not transport_enabled_from_env():
        logger.info("GIL Slack transport: disabled")
        return
    try:
        summary = poll_slack_gil_decisions(engine, client_from_env(), config=config_from_env())
    except SlackTransportError as exc:
        # Fail closed for delivery without taking down the independent paper
        # monitoring/accounting runtime. No message is converted into a decision
        # when transport evidence/credentials are unavailable.
        logger.warning("GIL Slack transport unavailable - %s", exc)
        return
    logger.info(
        "GIL Slack transport: bootstrapped=%s seen=%d ignored=%d accepted=%d rejected=%d checkpoint=%s",
        summary.bootstrapped,
        summary.messages_seen,
        summary.ordinary_ignored,
        summary.accepted,
        summary.rejected,
        summary.checkpoint,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="experiment1-runtime")
    parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_path = _resolve_db_path()
    logger.info("experiment1 runtime cycle starting - db=%s", db_path)

    engine = Experiment1Engine(db_path)
    quote_source = build_quote_source()

    _poll_optional_slack_transport(engine)

    try:
        summary = asyncio.run(run_experiment1_cycle(engine, quote_source))
    except Exception:
        logger.exception("experiment1 runtime cycle failed")
        sys.exit(EXIT_FAILURE)

    _log_summary(summary)
    logger.info("experiment1 runtime cycle complete")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
