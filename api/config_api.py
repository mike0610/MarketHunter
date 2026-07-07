"""
MarketHunter

api/config_api.py
"""

from __future__ import annotations

from fastapi import APIRouter

from config.config import settings


router = APIRouter(

    prefix="/config",

    tags=["Config"],

)


@router.get("")

def config():

    return settings.__dict__