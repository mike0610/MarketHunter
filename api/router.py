"""
MarketHunter

Module:
API Router

Responsibilities:
- Combine all API route groups.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.backtest_api import router as backtest
from api.config_api import router as config
from api.experiment1_api import router as experiment1
from api.health_api import router as health
from api.portfolio_api import router as portfolio
from api.research_api import router as research
from api.scanner_api import router as scanner
from api.signal_api import router as signals
from api.trading_scanner_api import router as trading_scanner


router = APIRouter()

router.include_router(health)
router.include_router(scanner)
router.include_router(backtest)
router.include_router(portfolio)
router.include_router(signals)
router.include_router(config)
router.include_router(research)
router.include_router(experiment1)
router.include_router(trading_scanner)
