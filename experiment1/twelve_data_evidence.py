"""Read-only Twelve Data execution-evidence adapter for GIL US stocks/ETF paper simulation."""
from __future__ import annotations
import os
from datetime import datetime,timezone
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo
import httpx

from experiment1.market_data_evidence import AsyncEvidenceSource
from experiment1.models import MarketDataEvidence,PriceType,QuoteMode,SessionState

BASE_URL="https://api.twelvedata.com"
ENV_TWELVE_DATA_API_KEY="TWELVE_DATA_API_KEY"
_NY=ZoneInfo("America/New_York")

def _session(now:datetime)->SessionState:
    local=now.astimezone(_NY)
    if local.weekday()>=5:return SessionState.CLOSED
    m=local.hour*60+local.minute
    if 570<=m<960:return SessionState.REGULAR
    if 240<=m<570:return SessionState.PRE_MARKET
    if 960<=m<1200:return SessionState.POST_MARKET
    return SessionState.CLOSED

class TwelveDataEvidenceSource:
    def __init__(self,api_key:str,client:httpx.AsyncClient,*,clock:Callable[[],datetime]|None=None):
        if not api_key.strip():raise ValueError("api_key must be non-blank")
        self._key=api_key;self._client=client;self._clock=clock or (lambda:datetime.now(timezone.utc))

    async def evidence_for(self,instrument:str)->MarketDataEvidence|None:
        received=self._clock()
        try:
            r=await self._client.get(f"{BASE_URL}/quote",params={"symbol":instrument,"apikey":self._key})
        except httpx.HTTPError:return None
        if r.status_code!=200:return None
        try:p=r.json()
        except ValueError:return None
        if not isinstance(p,dict) or p.get("status")=="error":return None
        try:price=Decimal(str(p["close"]))
        except (KeyError,ValueError,TypeError,ArithmeticError):return None
        if price<=0:return None
        raw=p.get("timestamp")
        try:ts=datetime.fromtimestamp(int(raw),timezone.utc)
        except (TypeError,ValueError,OverflowError):return None
        return MarketDataEvidence(
            provider="TWELVE_DATA",instrument=instrument,provider_symbol=str(p.get("symbol",instrument)),
            exchange=str(p.get("exchange","TWELVE_DATA")),currency=str(p.get("currency","USD")),
            price=price,price_type=PriceType.TRADE,source_timestamp=ts,receive_timestamp=received,
            session_state=_session(received),mode=QuoteMode.REALTIME,
            source_reference=f"twelve-data:quote:{instrument}:{raw}",
        )

def build_twelve_data_evidence_source(*,client:httpx.AsyncClient|None=None)->AsyncEvidenceSource|None:
    key=os.getenv(ENV_TWELVE_DATA_API_KEY,"").strip()
    if not key:return None
    return TwelveDataEvidenceSource(key,client or httpx.AsyncClient())
