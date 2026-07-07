"""
MarketHunter

api/backtest_api.py
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(

    prefix="/backtest",

    tags=["Backtest"],

)


@router.post("/run")

async def run_backtest():

    return {

        "success": True,

        "message": "Backtest started",

    }