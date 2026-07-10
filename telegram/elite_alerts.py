"""
MarketHunter

telegram/elite_alerts.py

Responsibilities:
- Send Telegram alerts only for elite signals.
- Read Telegram settings from .env.
- Avoid duplicate alerts for the same elite setup.
- Suppress repeated alerts while price is moving around the same setup.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from models.signal import Signal
from telegram.message_builder import MessageBuilder
from telegram.notifier import TelegramNotifier


ENV_PATH = Path(".env")
STATE_PATH = Path("data/telegram_elite_alerts.json")

DUPLICATE_ALERT_COOLDOWN_HOURS = 12


def load_env_values() -> dict[str, str]:
    """
    Load simple KEY=VALUE pairs from .env.
    """

    values: dict[str, str] = {}

    if not ENV_PATH.exists():
        return values

    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def telegram_is_enabled(
    values: dict[str, str],
) -> bool:
    """
    Check whether Telegram alerts are enabled and configured.
    """

    enabled = (
        values.get(
            "ENABLE_TELEGRAM",
            "False",
        ).lower()
        == "true"
    )

    token = values.get(
        "TELEGRAM_TOKEN",
        "",
    )

    chat_id = values.get(
        "TELEGRAM_CHAT_ID",
        "",
    )

    return bool(
        enabled
        and token
        and chat_id
    )


def parse_datetime(
    value: str,
) -> datetime | None:
    """
    Parse datetime from state file.
    """

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=timezone.utc,
        )

    return parsed.astimezone(
        timezone.utc,
    )


def load_sent_alerts() -> dict[str, datetime]:
    """
    Load sent alert ids from local state file.

    Backward compatible:
    - old format: list[str]
    - new format: dict[str, str datetime]
    """

    if not STATE_PATH.exists():
        return {}

    try:
        payload: Any = json.loads(
            STATE_PATH.read_text()
        )

    except json.JSONDecodeError:
        return {}

    now = datetime.now(
        timezone.utc,
    )

    if isinstance(
        payload,
        list,
    ):
        return {
            str(item): now
            for item in payload
        }

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    sent_alerts: dict[str, datetime] = {}

    for key, value in payload.items():
        if not isinstance(
            key,
            str,
        ):
            continue

        if not isinstance(
            value,
            str,
        ):
            continue

        parsed = parse_datetime(
            value,
        )

        if parsed is None:
            continue

        sent_alerts[key] = parsed

    return sent_alerts


def save_sent_alerts(
    sent_alerts: dict[str, datetime],
) -> None:
    """
    Save sent alert ids with timestamps.
    """

    STATE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        key: value.astimezone(
            timezone.utc,
        ).isoformat()
        for key, value in sorted(
            sent_alerts.items()
        )
    }

    STATE_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def prune_old_alerts(
    sent_alerts: dict[str, datetime],
    now: datetime,
) -> dict[str, datetime]:
    """
    Remove old alert records after cooldown.
    """

    cooldown = timedelta(
        hours=DUPLICATE_ALERT_COOLDOWN_HOURS,
    )

    return {
        key: sent_at
        for key, sent_at in sent_alerts.items()
        if now - sent_at < cooldown
    }


def build_signal_key(
    signal: Signal,
) -> str:
    """
    Build a stable de-duplication key for an elite setup.

    Important:
    Do not include entry, stop_loss, take_profit, score, or probability here.
    Those values can change while price moves around the same setup.
    Telegram should not send repeated alerts for the same setup just because
    risk geometry changed slightly.
    """

    payload = {
        "symbol": signal.symbol,
        "market": signal.market,
        "timeframe": signal.timeframe,
        "strategy": signal.strategy,
        "direction": signal.direction,
    }

    raw = json.dumps(
        payload,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8",
        )
    ).hexdigest()


def signal_label(
    signal: Signal,
) -> str:
    """
    Human readable signal label for logs.
    """

    return (
        f"{signal.symbol} "
        f"{signal.market} "
        f"{signal.timeframe} "
        f"{signal.strategy} "
        f"{signal.direction}"
    )


def notify_elite_signals(
    signals: Iterable[Signal],
) -> int:
    """
    Send Telegram alerts for new elite signals.

    Returns number of sent alerts.
    """

    elite_signals = list(
        signals,
    )

    if not elite_signals:
        return 0

    values = load_env_values()

    if not telegram_is_enabled(
        values,
    ):
        logger.info(
            "Telegram elite alerts disabled or not configured."
        )

        return 0

    notifier = TelegramNotifier(
        token=values["TELEGRAM_TOKEN"],
        chat_id=values["TELEGRAM_CHAT_ID"],
    )

    builder = MessageBuilder()

    now = datetime.now(
        timezone.utc,
    )

    sent_alerts = prune_old_alerts(
        sent_alerts=load_sent_alerts(),
        now=now,
    )

    sent_count = 0

    for signal in elite_signals:
        alert_key = build_signal_key(
            signal,
        )

        sent_at = sent_alerts.get(
            alert_key,
        )

        if sent_at is not None:
            logger.info(
                "Telegram elite alert skipped as duplicate | {} | Last sent: {} | Cooldown: {}h",
                signal_label(
                    signal,
                ),
                sent_at.isoformat(),
                DUPLICATE_ALERT_COOLDOWN_HOURS,
            )

            continue

        text = builder.build(
            signal,
        )

        notifier.send(
            text,
        )

        sent_alerts[alert_key] = now

        sent_count += 1

        logger.info(
            "Telegram elite alert sent | {}",
            signal_label(
                signal,
            ),
        )

    save_sent_alerts(
        sent_alerts,
    )

    return sent_count