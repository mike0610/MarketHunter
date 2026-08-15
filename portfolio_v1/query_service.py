"""
MarketHunter

Module:
Portfolio v1 Query Service (Slice 3)

Responsibilities:
- Read persisted ResearchTrade records via the existing
  ResearchRepository and hand an explicit, filtered collection to the
  existing portfolio_v1.assessment.assess_exposure() function.
- Build a human-readable scope/provenance label describing which
  filters were applied.

Non-goals (see portfolio_v1/assessment.py and project boundaries):
- No exposure aggregation logic here. assess_exposure() remains the
  sole owner of position_count/total_notional math; this module only
  selects which ResearchTrade records to hand it.
- No new SQLite queries. ResearchRepository.list_all() already
  returns every persisted ResearchTrade; filtering happens in Python
  over already-existing ResearchTrade fields.
- No sizing/decision/policy. This module returns an ExposureAssessment
  only - never a PositionSizingDecision or PortfolioDecision, never an
  APPROVED or PROCEED outcome.
- No new classification concepts. Filters are limited to fields that
  already exist on ResearchTrade (status, market, direction,
  research_group, strategy).
"""

from __future__ import annotations

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository

from portfolio_v1.assessment import assess_exposure
from portfolio_v1.domain import ExposureAssessment


def _describe_scope(
    *,
    status: TradeStatus | None,
    market: str | None,
    direction: str | None,
    research_group: str | None,
    strategy: str | None,
) -> str:
    """
    Build a deterministic, human-readable scope label from whichever
    filters were actually supplied.
    """

    filters = []

    if status is not None:
        filters.append(f"status={status.value}")

    if market is not None:
        filters.append(f"market={market}")

    if direction is not None:
        filters.append(f"direction={direction}")

    if research_group is not None:
        filters.append(f"research_group={research_group}")

    if strategy is not None:
        filters.append(f"strategy={strategy}")

    if not filters:
        return "persisted_research_trades:all"

    return "persisted_research_trades:" + ",".join(filters)


def _matches(
    trade: ResearchTrade,
    *,
    status: TradeStatus | None,
    market: str | None,
    direction: str | None,
    research_group: str | None,
    strategy: str | None,
) -> bool:
    if status is not None and trade.status != status:
        return False

    if market is not None and trade.market != market:
        return False

    if direction is not None and trade.direction != direction:
        return False

    if (
        research_group is not None
        and trade.research_group != research_group
    ):
        return False

    if strategy is not None and trade.strategy != strategy:
        return False

    return True


def query_exposure(
    repository: ResearchRepository,
    *,
    assessment_id: str,
    generated_at: str,
    status: TradeStatus | None = None,
    market: str | None = None,
    direction: str | None = None,
    research_group: str | None = None,
    strategy: str | None = None,
) -> ExposureAssessment:
    """
    Read persisted ResearchTrade records, apply an explicit filter
    over existing fields, and hand the resulting collection to
    assess_exposure().

    Every parameter left as None matches every trade for that field -
    passing no filters at all returns exposure over every persisted
    trade. A filter combination that matches zero trades is still a
    successfully answered, MEASURED query (position_count=0,
    total_notional=0.0), not an UNKNOWN one.
    """

    trades = repository.list_all()

    matched = [
        trade
        for trade in trades
        if _matches(
            trade,
            status=status,
            market=market,
            direction=direction,
            research_group=research_group,
            strategy=strategy,
        )
    ]

    scope = _describe_scope(
        status=status,
        market=market,
        direction=direction,
        research_group=research_group,
        strategy=strategy,
    )

    return assess_exposure(
        matched,
        scope=scope,
        assessment_id=assessment_id,
        generated_at=generated_at,
    )
