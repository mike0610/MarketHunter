"""
MarketHunter

api/portfolio_api.py
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(

    prefix="/portfolio",

    tags=["Portfolio"],

)


@router.get("/status")

def status():

    return {

        "balance": 0,

        "equity": 0,

        "positions": [],

    }