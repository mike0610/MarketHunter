from __future__ import annotations
import asyncio
from datetime import datetime,timezone
from decimal import Decimal
import httpx
from experiment1.twelve_data_evidence import TwelveDataEvidenceSource
from experiment1.models import QuoteMode,PriceType

NOW=datetime(2026,9,8,15,0,tzinfo=timezone.utc)
def client(payload,status=200):
 async def h(req):return httpx.Response(status,json=payload,request=req)
 return httpx.AsyncClient(transport=httpx.MockTransport(h))
def test_valid_quote_becomes_realtime_trade_evidence():
 p={"symbol":"SPY","exchange":"NYSE ARCA","currency":"USD","close":"650.25","timestamp":str(int(NOW.timestamp()))}
 s=TwelveDataEvidenceSource("secret",client(p),clock=lambda:NOW)
 e=asyncio.run(s.evidence_for("SPY"))
 assert e and e.price==Decimal("650.25") and e.mode is QuoteMode.REALTIME and e.price_type is PriceType.TRADE
 assert "secret" not in e.source_reference
def test_provider_error_fails_closed():
 s=TwelveDataEvidenceSource("secret",client({"status":"error","message":"limit"}),clock=lambda:NOW)
 assert asyncio.run(s.evidence_for("SPY")) is None
def test_missing_timestamp_fails_closed():
 s=TwelveDataEvidenceSource("secret",client({"symbol":"SPY","close":"650"}),clock=lambda:NOW)
 assert asyncio.run(s.evidence_for("SPY")) is None
