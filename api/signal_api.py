"""
MarketHunter

api/signal_api.py
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(

    prefix="/signals",

    tags=["Signals"],

)


@router.get("/latest")

def latest():

    return []



@router.get("/history")

def history():

    return []