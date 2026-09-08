from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from investments.research_queue import InvestmentResearchQueue, admit_candidate
from investments.stage8_models import InvestmentCandidate, InvestmentCandidateState, InvestmentEvidence
from investments.stage8_store import Stage8InvestmentStore
from market_data.foundation import AsyncMarketDataProvider, MarketDataError


@dataclass(frozen=True, slots=True)
class DiscoverySummary:
    scanned: int
    admitted: int
    rejected: int
    failed: int
    failure_reasons: tuple[str, ...] = ()


class InvestmentOpportunityDiscovery:
    """Cheap, evidence-only screen for research admission.

    This layer never creates an investment decision. It only promotes
    materially liquid candidates into the existing GIL deep-research queue.
    """

    def __init__(
        self,
        *,
        provider: AsyncMarketDataProvider,
        db_path: str | Path,
        materiality_floor: Decimal = Decimal("50"),
        min_dollar_volume: Decimal = Decimal("10000000"),
    ) -> None:
        self.provider = provider
        self.db_path = Path(db_path)
        self.materiality_floor = materiality_floor
        self.min_dollar_volume = min_dollar_volume
        self.stage8 = Stage8InvestmentStore(self.db_path)
        self.queue = InvestmentResearchQueue(self.db_path)
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS investment_discovery_runs(
                run_date TEXT PRIMARY KEY, completed_at TEXT NOT NULL)"""
            )

    def already_ran_today(self, now: datetime | None = None) -> bool:
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        day = moment.astimezone(timezone.utc).date().isoformat()
        with sqlite3.connect(self.db_path) as c:
            row = c.execute(
                "SELECT 1 FROM investment_discovery_runs WHERE run_date=?", (day,)
            ).fetchone()
        return row is not None

    async def run_once(self, now: datetime | None = None) -> DiscoverySummary:
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if self.already_ran_today(moment):
            return DiscoverySummary(0, 0, 0, 0)

        scanned = admitted = rejected = failed = 0
        failure_reasons: list[str] = []
        instruments = await self.provider.universe()
        for instrument in instruments:
            scanned += 1
            try:
                liquidity = await self.provider.liquidity(instrument)
            except MarketDataError as exc:
                failed += 1
                failure_reasons.append(f"{instrument.symbol}: {exc}")
                continue

            liquid = liquidity.average_daily_dollar_volume >= self.min_dollar_volume
            score = Decimal("80") if liquid else Decimal("20")
            state = (
                InvestmentCandidateState.CANDIDATE
                if liquid
                else InvestmentCandidateState.REJECTED
            )
            candidate = InvestmentCandidate(
                candidate_id=(
                    f"discovery:{instrument.symbol}:"
                    f"{liquidity.observed_at.date().isoformat()}"
                ),
                symbol=instrument.symbol,
                universe_id="GLOBAL-OPPORTUNITY-MAP",
                setup_family="LIQUIDITY_CHEAP_SCREEN",
                materiality_score=score,
                deterministic_rule_id=None,
                evidence=InvestmentEvidence(
                    provider=liquidity.provider,
                    observed_at=liquidity.observed_at,
                    source_reference=liquidity.source_reference,
                    market_price=liquidity.last_price,
                    fundamentals_reference=None,
                    event_reference=None,
                    fresh=True,
                ),
                state=state,
                reason=(
                    "liquid candidate for bounded deep research"
                    if liquid
                    else "below cheap-screen liquidity floor"
                ),
            )
            route, added = admit_candidate(
                candidate,
                materiality_floor=self.materiality_floor,
                stage8=self.stage8,
                queue=self.queue,
            )
            if added:
                admitted += 1
            else:
                rejected += 1

        # A complete evidence outage is not a completed daily discovery run.
        # Leave the daily marker absent so the existing runtime cadence retries.
        if scanned > 0 and failed < scanned:
            day = moment.astimezone(timezone.utc).date().isoformat()
            with sqlite3.connect(self.db_path) as c:
                c.execute(
                    "INSERT OR IGNORE INTO investment_discovery_runs VALUES(?,?)",
                    (day, moment.isoformat()),
                )
        return DiscoverySummary(scanned, admitted, rejected, failed, tuple(failure_reasons))
