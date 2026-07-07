"""
MarketHunter

api/app.py
"""

from __future__ import annotations

from fastapi import FastAPI

from api.router import router


app = FastAPI(

    title="MarketHunter API",

    version="1.0.0",

    docs_url="/docs",

    redoc_url="/redoc",

)

app.include_router(router)