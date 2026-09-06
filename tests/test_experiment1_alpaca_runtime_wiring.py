from __future__ import annotations
import asyncio,sqlite3,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from experiment1.models import (
    AccountKind,DecisionAction,MarketDataEvidence,OrderIntent,PriceType,QuoteMode,SessionState
)
from tools.experiment1_runtime.runtime import build_quote_source

class FakeAlpaca:
    async def evidence_for(self,instrument):
        now=datetime.now(timezone.utc)
        return MarketDataEvidence(
            provider="ALPACA_SIP",instrument=instrument,provider_symbol=instrument,
            exchange="ALPACA_SIP",currency="USD",price=Decimal("500"),
            price_type=PriceType.MID,source_timestamp=now,receive_timestamp=now,
            session_state=SessionState.REGULAR,mode=QuoteMode.REALTIME,
            source_reference="fake-alpaca",
        )

def scanner_db(path:Path,sec_type:str):
    with sqlite3.connect(path) as c:
        c.execute("create table trading_scanner_candidates(symbol text,sec_type text,discovered_at text,dedupe_key text)")
        c.execute("insert into trading_scanner_candidates values(?,?,?,?)",("SPY",sec_type,datetime.now(timezone.utc).isoformat(),"d1"))

def intent():
    return OrderIntent("i1",datetime.now(timezone.utc),AccountKind.SPOT,DecisionAction.BUY,"SPY",Decimal("1"),"test")

def test_alpaca_sip_routes_only_scanner_classified_stock():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"scanner.db";scanner_db(db,"STK")
        with patch.dict("os.environ",{"TRADING_SCANNER_DB_PATH":str(db)},clear=False),              patch("tools.experiment1_runtime.runtime.build_alpaca_sip_evidence_source",return_value=FakeAlpaca()):
            q=asyncio.run(build_quote_source().quote_for(intent()))
        assert q is not None
        assert q.source=="ALPACA_SIP"
        assert q.price==Decimal("500")

def test_futures_never_route_to_alpaca_stock_feed():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"scanner.db";scanner_db(db,"FUT")
        with patch.dict("os.environ",{"TRADING_SCANNER_DB_PATH":str(db)},clear=False),              patch("tools.experiment1_runtime.runtime.build_alpaca_sip_evidence_source",return_value=FakeAlpaca()):
            q=asyncio.run(build_quote_source().quote_for(intent()))
        assert q is None

def test_missing_alpaca_credentials_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"scanner.db";scanner_db(db,"STK")
        with patch.dict("os.environ",{"TRADING_SCANNER_DB_PATH":str(db)},clear=False),              patch("tools.experiment1_runtime.runtime.build_alpaca_sip_evidence_source",return_value=None):
            q=asyncio.run(build_quote_source().quote_for(intent()))
        assert q is None
