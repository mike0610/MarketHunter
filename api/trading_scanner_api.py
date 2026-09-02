"""
MarketHunter

api/trading_scanner_api.py

Module:
Read-only API for the GIL Trading Scanner v1's persistent Trading
Candidate Queue. This router only ever calls
TradingScannerStore.list_candidates/get_candidate - it cannot create,
mutate, or delete a candidate, and (like the rest of trading_scanner/)
it never touches experiment1.engine or any OrderIntent path. GIL reads
this queue for its own review; nothing here decides or executes.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from trading_scanner.models import QueueState, SetupFamily
from trading_scanner.store import TradingScannerStore

router = APIRouter(prefix="/trading-scanner", tags=["trading-scanner"])

ENV_DB_PATH = "TRADING_SCANNER_DB_PATH"
DEFAULT_DB_PATH = "data/trading_scanner.db"


def _store() -> TradingScannerStore:
    path = Path(os.getenv(ENV_DB_PATH, DEFAULT_DB_PATH))
    return TradingScannerStore(path)


def _candidate_response(candidate) -> dict:
    return {
        "conid": candidate.conid,
        "symbol": candidate.symbol,
        "sec_type": candidate.sec_type,
        "exchange": candidate.exchange,
        "currency": candidate.currency,
        "setup_family": candidate.setup_family.value,
        "reason_stack": list(candidate.reason_stack),
        "catalyst": None
        if candidate.catalyst is None
        else {
            "description": candidate.catalyst.description,
            "source": candidate.catalyst.source,
            "source_reference": candidate.catalyst.source_reference,
            "observed_at": candidate.catalyst.observed_at.isoformat(),
        },
        "liquidity": {
            "average_daily_volume": str(candidate.liquidity.average_daily_volume),
            "average_daily_dollar_volume": str(candidate.liquidity.average_daily_dollar_volume),
            "last_price": str(candidate.liquidity.last_price),
        },
        "volatility": {"realized_range_pct": str(candidate.volatility.realized_range_pct)},
        "evidence_status": candidate.evidence_status,
        "eligible": candidate.eligible,
        "discovered_at": candidate.discovered_at.isoformat(),
        "scan_cycle_id": candidate.scan_cycle_id,
        "dedupe_key": candidate.dedupe_key,
        "queue_state": candidate.queue_state.value,
        "freshness_note": candidate.freshness_note,
        "invalidation_reference": candidate.invalidation_reference,
        "reject_reason": candidate.reject_reason,
        "simulation_only": True,
    }


@router.get("/candidates")
def list_candidates(
    queue_state: QueueState | None = Query(default=None),
    setup_family: SetupFamily | None = Query(default=None),
    symbol: str | None = Query(default=None),
):
    """
    Latest and historical candidates, filterable by queue_state (e.g.
    CANDIDATE for active discoveries, REJECTED/DATA_FAIL/INELIGIBLE for
    rejection history), setup_family, and/or symbol. All filters are
    optional and combine with AND. Discovery-only - never an
    executable order.
    """
    candidates = _store().list_candidates(queue_state=queue_state)
    if setup_family is not None:
        candidates = tuple(c for c in candidates if c.setup_family is setup_family)
    if symbol is not None:
        candidates = tuple(c for c in candidates if c.symbol == symbol)
    return {"candidates": [_candidate_response(c) for c in candidates], "simulation_only": True}


@router.get("/candidates/{dedupe_key}")
def get_candidate(dedupe_key: str):
    candidate = _store().get_candidate(dedupe_key)
    if candidate is None:
        raise HTTPException(status_code=404, detail="unknown dedupe_key")
    return _candidate_response(candidate)
