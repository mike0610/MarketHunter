"""
MarketHunter

research/models/trade_status.py
"""

from __future__ import annotations

from enum import StrEnum


class TradeStatus(StrEnum):
    CANDIDATE = "candidate"
    WAITING_ENTRY = "waiting_entry"
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"