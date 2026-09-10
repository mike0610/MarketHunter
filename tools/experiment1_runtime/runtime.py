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
import sqlite3
import sys
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from investments.autonomous_loop import AutonomousInvestmentStore
from investments.opportunity_discovery import InvestmentOpportunityDiscovery
from investments.research_executor import USInvestmentResearchExecutor
from investments.research_provider import LocalGILResearchProvider
from investments.research_queue import InvestmentResearchQueue
from investments.research_worker import InvestmentResearchWorker
from investments.sec_evidence import SECCompanyFactsProvider
from investments.sec_identity import SECCompanyTickerResolver
from investments.stage8_store import Stage8InvestmentStore
from market_data.twelve_data_provider import TwelveDataDailyProvider

from experiment1.alpaca_sip_evidence import build_alpaca_sip_evidence_source
from experiment1.twelve_data_evidence import build_twelve_data_evidence_source
from experiment1.engine import Experiment1Engine, Experiment1Error, STARTING_CASH
from experiment1.gil_decision import GilIngestionResult, drain_gil_decision_inbox
from experiment1.lifecycle import LifecycleResult, run_protective_exit_cycle
from experiment1.market_data_evidence import EvidenceGrade, EvidenceGuardedQuoteSource
from experiment1.market_data_providers import (
    AssetClass,
    FreshnessGuardedQuoteSource,
    MultiAssetQuoteSource,
)
from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import OrderIntent
from experiment1.mtm import MtmCycleResult, run_mtm_cycle
from experiment1.runtime import AsyncQuoteSource, CycleResult, run_market_cycle
from experiment1.trading_decision import TradingIngestionResult, drain_trading_decision_inbox
from experiment1.slack_transport import (
    SlackTransportError,
    client_from_env,
    config_from_env,
    poll_slack_gil_decisions,
    transport_enabled_from_env,
)
from experiment1.trading_slack_transport import (
    TradingSlackTransportError,
    config_from_env as trading_config_from_env,
    poll_slack_trading_decisions,
    transport_enabled_from_env as trading_transport_enabled_from_env,
)

ENV_DB_PATH = "EXPERIMENT1_DB_PATH"
DEFAULT_DB_PATH = Path("data/experiment1.db")
DEFAULT_FRESHNESS_MAX_AGE = timedelta(minutes=5)
DEFAULT_SCANNER_DB_PATH = Path("data/trading_scanner.db")
ENV_SCANNER_DB_PATH = "TRADING_SCANNER_DB_PATH"
ENV_INVESTMENT_RESEARCH_DB_PATH = "INVESTMENT_RESEARCH_DB_PATH"
DEFAULT_INVESTMENT_RESEARCH_DB_PATH = Path("data/investment_research.db")
ENV_SEC_USER_AGENT = "GIL_SEC_USER_AGENT"
ENV_INVESTMENT_DISCOVERY_SYMBOLS = "INVESTMENT_DISCOVERY_SYMBOLS"

logger = logging.getLogger("experiment1_runtime.runtime")

EXIT_OK = 0
EXIT_FAILURE = 1


def _resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else DEFAULT_DB_PATH


def _scanner_asset_class(symbol: str) -> AssetClass | None:
    db_path = Path(os.getenv(ENV_SCANNER_DB_PATH, str(DEFAULT_SCANNER_DB_PATH)))
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT sec_type FROM trading_scanner_candidates "
                "WHERE symbol=? ORDER BY discovered_at DESC, dedupe_key DESC LIMIT 1",
                (symbol.upper(),),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    sec_type = str(row[0]).upper()
    if sec_type == "STK":
        return AssetClass.STOCK
    if sec_type == "ETF":
        return AssetClass.ETF
    return None


def _classify(intent: OrderIntent) -> AssetClass | None:
    if intent.symbol.endswith("USDT"):
        return AssetClass.CRYPTO
    return _scanner_asset_class(intent.symbol)


def build_quote_source(*, freshness_max_age: timedelta = DEFAULT_FRESHNESS_MAX_AGE) -> AsyncQuoteSource:
    crypto_source = FreshnessGuardedQuoteSource(
        BinanceExperiment1QuoteSource(), max_age=freshness_max_age
    )
    providers = {AssetClass.CRYPTO: crypto_source}

    alpaca = build_alpaca_sip_evidence_source()
    if alpaca is not None:
        execution_age = timedelta(
            seconds=int(os.getenv("EXPERIMENT1_ALPACA_EXECUTION_MAX_AGE_SECONDS", "30"))
        )
        valuation_age = timedelta(
            seconds=int(os.getenv("EXPERIMENT1_ALPACA_VALUATION_MAX_AGE_SECONDS", "300"))
        )
        fee_bps = Decimal(os.getenv("EXPERIMENT1_ALPACA_PAPER_FEE_BPS", "0"))
        slippage_bps = Decimal(os.getenv("EXPERIMENT1_ALPACA_PAPER_SLIPPAGE_BPS", "0"))
        alpaca_quotes = EvidenceGuardedQuoteSource(
            alpaca,
            EvidenceGrade.EXECUTION,
            expected_currency="USD",
            expected_exchange=None,
            execution_max_age=execution_age,
            valuation_max_age=valuation_age,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        providers[AssetClass.STOCK] = alpaca_quotes
        providers[AssetClass.ETF] = alpaca_quotes
        logger.info("Alpaca SIP paper execution evidence: enabled for scanner-classified STK/ETF")
    else:
        logger.info("Alpaca SIP paper execution evidence: unavailable (credentials not configured)")
        twelve = build_twelve_data_evidence_source()
        if twelve is not None:
            execution_age = timedelta(seconds=int(os.getenv("EXPERIMENT1_TWELVE_DATA_EXECUTION_MAX_AGE_SECONDS", "90")))
            valuation_age = timedelta(seconds=int(os.getenv("EXPERIMENT1_TWELVE_DATA_VALUATION_MAX_AGE_SECONDS", "300")))
            twelve_quotes = EvidenceGuardedQuoteSource(
                twelve, EvidenceGrade.EXECUTION, expected_currency="USD", expected_exchange=None,
                execution_max_age=execution_age, valuation_max_age=valuation_age,
                fee_bps=Decimal(os.getenv("EXPERIMENT1_TWELVE_DATA_PAPER_FEE_BPS", "0")),
                slippage_bps=Decimal(os.getenv("EXPERIMENT1_TWELVE_DATA_PAPER_SLIPPAGE_BPS", "0")),
            )
            providers[AssetClass.STOCK] = twelve_quotes
            providers[AssetClass.ETF] = twelve_quotes
            logger.info("Twelve Data paper execution evidence: enabled for scanner-classified STK/ETF")
        else:
            logger.info("Twelve Data paper execution evidence: unavailable (credential not configured)")

    return MultiAssetQuoteSource(providers=providers, classify=_classify)


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
    trading_ingestion_results: tuple[TradingIngestionResult, ...]


async def run_experiment1_cycle(
    engine: Experiment1Engine, quote_source: AsyncQuoteSource
) -> Experiment1CycleSummary:
    gil_ingestion_results = await drain_gil_decision_inbox(engine, quote_source)
    trading_ingestion_results = await drain_trading_decision_inbox(engine, quote_source)
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
        market_fill_results, protective_exit_results, tuple(mtm_results), gil_ingestion_results, trading_ingestion_results
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
    logger.info(
        "trading ingestion: %d decision(s) - blocked=%d waiting=%d",
        len(summary.trading_ingestion_results),
        _count(summary.trading_ingestion_results, "BLOCKED"),
        _count(summary.trading_ingestion_results, "WAITING_EVIDENCE"),
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



def _poll_optional_trading_slack_transport(engine: Experiment1Engine) -> None:
    if not trading_transport_enabled_from_env():
        logger.info("Trading Slack transport: disabled")
        return
    token = os.getenv("TRADING_SLACK_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("Trading Slack transport unavailable - TRADING_SLACK_BOT_TOKEN is not configured")
        return
    try:
        from experiment1.slack_transport import SlackWebApiHistoryClient

        summary = poll_slack_trading_decisions(
            engine,
            SlackWebApiHistoryClient(token),
            config=trading_config_from_env(),
        )
    except (TradingSlackTransportError, SlackTransportError) as exc:
        logger.warning("Trading Slack transport unavailable - %s", exc)
        return
    logger.info(
        "Trading Slack transport: bootstrapped=%s seen=%d ignored=%d accepted=%d rejected=%d checkpoint=%s",
        summary.bootstrapped,
        summary.messages_seen,
        summary.ordinary_ignored,
        summary.accepted,
        summary.rejected,
        summary.checkpoint,
    )




def run_optional_investment_discovery() -> str:
    raw_symbols = os.getenv(ENV_INVESTMENT_DISCOVERY_SYMBOLS, "").strip()
    if not raw_symbols:
        return "DISABLED_NO_SYMBOLS"
    symbols = tuple(s.strip().upper() for s in raw_symbols.split(",") if s.strip())
    path = Path(os.getenv(ENV_INVESTMENT_RESEARCH_DB_PATH, str(DEFAULT_INVESTMENT_RESEARCH_DB_PATH)))
    try:
        provider = TwelveDataDailyProvider(symbols)
        summary = asyncio.run(
            InvestmentOpportunityDiscovery(provider=provider, db_path=path).run_once()
        )
    except Exception as exc:
        logger.warning("GIL investment discovery blocked - %s", exc)
        return "BLOCKED_EVIDENCE"
    if summary.scanned == 0:
        return "IDLE_DAILY"
    detail = ""
    if summary.failure_reasons:
        detail = " ERRORS=" + " | ".join(summary.failure_reasons)
    return f"SCANNED={summary.scanned} ADMITTED={summary.admitted} REJECTED={summary.rejected} FAILED={summary.failed}{detail}"

def run_optional_investment_research() -> str:
    user_agent = os.getenv(ENV_SEC_USER_AGENT, "").strip()
    if not user_agent:
        return "DISABLED_NO_SEC_IDENTITY"
    path = Path(os.getenv(ENV_INVESTMENT_RESEARCH_DB_PATH, str(DEFAULT_INVESTMENT_RESEARCH_DB_PATH)))
    queue = InvestmentResearchQueue(path)
    worker = InvestmentResearchWorker(queue)
    if not queue.pending():
        return "IDLE"
    executor = USInvestmentResearchExecutor(
        worker=worker,
        store=AutonomousInvestmentStore(path),
        identity=SECCompanyTickerResolver(user_agent=user_agent),
        fundamentals=SECCompanyFactsProvider(user_agent=user_agent),
        reasoner=LocalGILResearchProvider(
            base_url=os.getenv("GIL_LOCAL_LLM_BASE_URL", "http://127.0.0.1:8081")
        ),
    )
    try:
        record = executor.run_once()
    except Exception as exc:
        logger.warning("GIL investment research blocked - %s", exc)
        return "BLOCKED_EVIDENCE"
    return "DECIDED" if record is not None else "BLOCKED_EVIDENCE"

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
    _poll_optional_trading_slack_transport(engine)
    logger.info("GIL investment discovery: %s", run_optional_investment_discovery())
    logger.info("GIL investment research: %s", run_optional_investment_research())

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
