"""
MarketHunter

api/health_api.py
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")

def health():

    return {

        "status": "ok",

        "service": "MarketHunter",

        "version": "1.0.0",

    }