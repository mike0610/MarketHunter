from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from market_data.foundation import MarketDataUnavailable
from market_data.twelve_data_provider import ENV_TWELVE_DATA_API_KEY


@dataclass(frozen=True, slots=True)
class TwelveDataStock:
    symbol: str
    name: str
    exchange: str
    country: str
    security_type: str


class TwelveDataStockListProvider:
    """Current Twelve Data symbol master for bounded research discovery.

    This is explicitly CURRENT-state metadata. It must not be represented as
    historical point-in-time membership and therefore carries survivorship risk.
    """

    BASE_URL = "https://api.twelvedata.com/stocks"

    def __init__(self, *, api_key: str | None = None, fetch_text: Callable[[str], str] | None = None) -> None:
        key=(api_key if api_key is not None else os.getenv(ENV_TWELVE_DATA_API_KEY,"")).strip()
        if not key: raise ValueError("TWELVE_DATA_API_KEY is required")
        self._api_key=key
        self._fetch_text=fetch_text or self._http_get_text

    async def us_common_stocks(self) -> tuple[TwelveDataStock,...]:
        params=urllib.parse.urlencode({"country":"United States","apikey":self._api_key})
        raw=await asyncio.to_thread(self._fetch_text,f"{self.BASE_URL}?{params}")
        try: payload=json.loads(raw)
        except json.JSONDecodeError as exc: raise MarketDataUnavailable("invalid Twelve Data stocks JSON") from exc
        rows=payload.get("data") if isinstance(payload,dict) else None
        if not isinstance(rows,list): raise MarketDataUnavailable("no Twelve Data stock master data")
        out=[]
        for row in rows:
            if not isinstance(row,dict): continue
            symbol=str(row.get("symbol") or "").strip().upper()
            name=str(row.get("name") or "").strip()
            exchange=str(row.get("exchange") or "").strip().upper()
            country=str(row.get("country") or "").strip()
            typ=str(row.get("type") or "").strip()
            if not symbol or not name: continue
            if exchange not in {"NASDAQ","NYSE","NYSE ARCA","NYSE AMERICAN"}: continue
            if typ.lower() not in {"common stock","common stocks"}: continue
            out.append(TwelveDataStock(symbol,name,exchange,country,typ))
        return tuple(sorted(out,key=lambda x:x.symbol))

    @staticmethod
    def _http_get_text(url:str)->str:
        req=urllib.request.Request(url,headers={"User-Agent":"MarketHunter/1.0","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=20) as response:
            return response.read().decode("utf-8")
