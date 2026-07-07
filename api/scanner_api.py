"""
MarketHunter

api/scanner_api.py
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(
    prefix="/scanner",
    tags=["Scanner"],
)


@router.get("/run")

async def run_scan():

    #
    # TODO:
    # Scanner.scan_many(...)
    #

    return {

        "success": True,

        "message": "Scanner started",

    }