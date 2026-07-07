"""
MarketHunter

api/router.py
"""

from __future__ import annotations

from fastapi import APIRouter

from api.health_api import router as health

from api.scanner_api import router as scanner

from api.backtest_api import router as backtest

from api.portfolio_api import router as portfolio

from api.signal_api import router as signals

from api.config_api import router as config


router = APIRouter()

router.include_router(health)

router.include_router(scanner)

router.include_router(backtest)

router.include_router(portfolio)

router.include_router(signals)

router.include_router(config)