"""
Direct paper bridge for selected evidence-positive MarketHunter crypto strategies.

This producer bypasses GIL/Slack entirely. It watches Research trades and, for
newly-created ACTIVE crypto trades from the Product Owner allowlist, creates a
canonical TradingDecision in Experiment1. Experiment1 remains the sole paper
execution/risk-policy/lifecycle engine.

Important:
- paper/simulation only
- no broker/live execution
- bootstrap is forward-only: historical trades are never replayed
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    SizingIntent,
    SizingMode,
    TriggerType,
)
from experiment1.trading_decision import TradingDecision, decision_to_json
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


DEFAULT_RESEARCH_DB = Path("data/research.db")
DEFAULT_CHECKPOINT = Path("data/direct_positive_strategy_bridge.json")
ENV_ENABLED = "DIRECT_POSITIVE_STRATEGY_BRIDGE_ENABLED"
ENV_RESEARCH_DB = "RESEARCH_DB_PATH"
ENV_CHECKPOINT = "DIRECT_POSITIVE_STRATEGY_BRIDGE_CHECKPOINT"
ENV_MAX_NOTIONAL = "DIRECT_POSITIVE_STRATEGY_MAX_NOTIONAL"

ALLOWED_STRATEGIES = frozenset(
    {
        "PremiumDiscount",
        "Breakout",
        "OrderBlock",
        "Compression",
        "LiquiditySweep",
    }
)


@dataclass(frozen=True, slots=True)
class DirectBridgeSummary:
    enabled: bool
    bootstrapped: bool
    eligible: int
    queued: int
    skipped_existing: int
    skipped_unsupported: int


def enabled_from_env() -> bool:
    return os.getenv(ENV_ENABLED, "").strip().lower() in {"1", "true", "yes", "on"}


def _checkpoint_path() -> Path:
    raw = os.getenv(ENV_CHECKPOINT)
    return Path(raw) if raw else DEFAULT_CHECKPOINT


def _research_path() -> Path:
    raw = os.getenv(ENV_RESEARCH_DB)
    return Path(raw) if raw else DEFAULT_RESEARCH_DB


def _load_floor(path: Path) -> datetime | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["activation_floor_utc"])


def _save_floor(path: Path, floor: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"activation_floor_utc": floor.isoformat()}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _decision_for(trade) -> TradingDecision | None:
    market = str(trade.market).strip().lower()
    direction = str(trade.direction).strip().upper()

    if market == "spot":
        if direction != "LONG":
            return None
        account = AccountKind.SPOT
        action = DecisionAction.BUY
    elif market == "futures":
        account = AccountKind.FUTURES
        if direction == "LONG":
            action = DecisionAction.LONG
        elif direction == "SHORT":
            action = DecisionAction.SHORT
        else:
            return None
    else:
        return None

    max_notional = Decimal(os.getenv(ENV_MAX_NOTIONAL, "200"))
    if max_notional <= 0:
        raise ValueError(f"{ENV_MAX_NOTIONAL} must be positive")

    return TradingDecision(
        decision_id=f"research-direct:{trade.id}",
        decided_at=datetime.now(timezone.utc),
        account=account,
        action=action,
        symbol=trade.symbol,
        thesis=(
            f"Direct Product Owner activation from Research strategy "
            f"{trade.strategy}; research_trade_id={trade.id}"
        ),
        quantity=None,
        leverage=Decimal("1"),
        stop_loss=Decimal(str(trade.stop_loss)),
        take_profit=Decimal(str(trade.take_profit)),
        trigger=ExecutionTrigger(
            trigger_type=TriggerType.IMMEDIATE,
            note="Research trade already ACTIVE; execute only on fresh Experiment1 quote",
        ),
        sizing=SizingIntent(
            mode=SizingMode.MAX_NOTIONAL,
            max_notional=max_notional,
        ),
    )


def run_direct_positive_strategy_bridge(
    engine: Experiment1Engine,
    *,
    now: datetime | None = None,
) -> DirectBridgeSummary:
    if not enabled_from_env():
        return DirectBridgeSummary(False, False, 0, 0, 0, 0)

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    checkpoint = _checkpoint_path()
    floor = _load_floor(checkpoint)
    if floor is None:
        _save_floor(checkpoint, moment)
        return DirectBridgeSummary(True, True, 0, 0, 0, 0)

    repo = ResearchRepository(path=_research_path())
    try:
        trades = repo.list_all()
    finally:
        repo.close()

    eligible = queued = skipped_existing = skipped_unsupported = 0

    for trade in trades:
        if trade.strategy not in ALLOWED_STRATEGIES:
            continue
        if trade.status is not TradeStatus.ACTIVE:
            continue
        if trade.created_at < floor:
            continue
        if not str(trade.symbol).upper().endswith("USDT"):
            # The evidence that justified this direct activation is crypto
            # Research evidence. Do not silently project it onto equities.
            skipped_unsupported += 1
            continue

        eligible += 1
        decision = _decision_for(trade)
        if decision is None:
            skipped_unsupported += 1
            continue

        if engine.trading_decision_inbox_status(decision.decision_id) is not None:
            skipped_existing += 1
            continue

        engine.receive_trading_decision(
            decision.decision_id,
            decision_to_json(decision),
            now=moment,
        )
        queued += 1

    return DirectBridgeSummary(
        True,
        False,
        eligible,
        queued,
        skipped_existing,
        skipped_unsupported,
    )
