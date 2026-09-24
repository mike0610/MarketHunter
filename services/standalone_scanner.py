"""Isolated, read-only MarketHunter manual scanner MVP.

Run from repository root:
  python -m uvicorn services.standalone_scanner:app --host 127.0.0.1 --port 8010
No imports from MarketHunter's worker, research pipeline, or trading modules.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from models.candle import Candle
from services.snapshot_builder import SnapshotBuilder
from strategies.breakout import BreakoutStrategy
from strategies.compression import CompressionStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.premium_discount import PremiumDiscountStrategy

DB_PATH = Path(os.getenv("STANDALONE_SCANNER_DB", "data/standalone_scanner.db"))
INTERVAL_MS = {"15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
INTERVALS = {"15m", "1h", "4h", "1d"}
MAX_UNIVERSE = 2500
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,25}$")
STRATEGIES={"level_breakout","compression","order_block","premium_discount","breakout","all"}
RESEARCH_STRATEGIES={"compression":CompressionStrategy,"order_block":OrderBlockStrategy,"premium_discount":PremiumDiscountStrategy,"breakout":BreakoutStrategy}
_lock = asyncio.Lock()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          status TEXT NOT NULL, market TEXT NOT NULL, timeframe TEXT NOT NULL,
          symbols_total INTEGER NOT NULL, symbols_done INTEGER NOT NULL DEFAULT 0,
          error TEXT)""")
        rc={row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        if "exchange" not in rc: conn.execute("ALTER TABLE runs ADD COLUMN exchange TEXT NOT NULL DEFAULT 'binance'")
        if "strategy" not in rc: conn.execute("ALTER TABLE runs ADD COLUMN strategy TEXT NOT NULL DEFAULT 'level_breakout'")
        # Per-symbol counters are populated for new scans. Older runs have no
        # reliable analyzed/skipped/error breakdown and retain zero defaults.
        for column in ("symbols_analyzed", "symbols_skipped", "symbols_errors"):
            if column not in rc:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        conn.execute("""CREATE TABLE IF NOT EXISTS observations (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, symbol TEXT NOT NULL,
          market TEXT NOT NULL, timeframe TEXT NOT NULL, observed_at TEXT NOT NULL,
          candle_closed_at TEXT NOT NULL, close_price REAL NOT NULL,
          breakout_high REAL NOT NULL, breakdown_low REAL NOT NULL,
          direction TEXT NOT NULL, status TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(id))""")
        oc={row[1] for row in conn.execute("PRAGMA table_info(observations)")}
        if "exchange" not in oc: conn.execute("ALTER TABLE observations ADD COLUMN exchange TEXT NOT NULL DEFAULT 'binance'")
        if "strategy" not in oc: conn.execute("ALTER TABLE observations ADD COLUMN strategy TEXT NOT NULL DEFAULT 'level_breakout'")
        if "score" not in oc: conn.execute("ALTER TABLE observations ADD COLUMN score REAL")
        if "reasons" not in oc: conn.execute("ALTER TABLE observations ADD COLUMN reasons TEXT")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    with db() as conn:
        conn.execute("UPDATE runs SET status='failed', finished_at=?, error='Server restarted during scan' WHERE status='running'", (utcnow(),))
    yield


app = FastAPI(title="MarketHunter Isolated Manual Scanner", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


class ScanRequest(BaseModel):
    exchange: str = "binance"
    market: str = "spot"
    timeframe: str = "1h"
    mode: str = "selected"
    strategy: str = "level_breakout"
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"], max_length=20)


WEEX_BASE = {"spot": "https://api-spot.weex.com/api/v3", "futures": "https://api-contract.weex.com/capi/v3"}


def kline_endpoint(exchange: str, market: str, historical: bool = False) -> str:
    if exchange == "binance":
        return "https://api.binance.com/api/v3/klines" if market == "spot" else "https://fapi.binance.com/fapi/v1/klines"
    suffix = "/market/historyKlines" if historical else "/market/klines"
    return WEEX_BASE[market] + suffix


async def _get_with_retry(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    """Retry only transient failures of public, idempotent GET requests.

    HTTP 400/404 is never retried or silently converted to an unsupported pair.
    At most four requests are made, including the first attempt.
    """
    for attempt in range(4):
        try:
            response = await client.get(url, params=params)
        except (httpx.ReadError, httpx.ReadTimeout):
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
            continue
        if response.status_code in (418, 429) or response.status_code >= 500:
            if attempt == 3:
                response.raise_for_status()
            retry = response.headers.get("Retry-After", "")
            delay = min(60, max(2, int(retry))) if retry.isdigit() else min(60, 2 ** (attempt + 1))
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("Unreachable retry state")


def _weex_spot_invalid_candle_symbol(exc: httpx.HTTPStatusError, request: ScanRequest) -> bool:
    """Classify only the WEEX Spot candle error confirmed by the bounded probe."""
    if (request.exchange, request.market, exc.response.status_code) != ("weex", "spot", 400):
        return False
    if exc.request.url.path not in ("/api/v3/market/klines", "/api/v3/market/historyKlines"):
        return False
    try:
        payload = exc.response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("code") == -1142


def _candle_http_error(exc: httpx.HTTPStatusError) -> str:
    """Include bounded, non-secret exchange error details for unexpected HTTP failures."""
    try:
        payload = exc.response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        code = payload.get("code")
        message = str(payload.get("msg", payload.get("message", "")))[:160]
        return f"HTTP {exc.response.status_code} code={code} msg={message} path={exc.request.url.path}"
    return f"HTTP {exc.response.status_code} path={exc.request.url.path}"


async def fetch_candles(client: httpx.AsyncClient, exchange: str, market: str, timeframe: str, symbol: str, required: int) -> list[dict]:
    """Fetch enough candles for one scanner decision without touching trading code.

    Binance and WEEX Futures can satisfy the requested history from their regular
    kline endpoints. WEEX Spot historical data is paged through the documented
    historyKlines endpoint, whose limit is capped at 100 rows per request.
    """
    if exchange == "binance":
        response = await _get_with_retry(client, kline_endpoint(exchange, market), {
            "symbol": symbol,
            "interval": timeframe,
            "limit": min(max(required + 5, 23), 1000),
        })
        return parse_candles(response.json(), exchange, timeframe)

    if market == "futures":
        response = await _get_with_retry(client, kline_endpoint(exchange, market), {
            "symbol": symbol,
            "interval": timeframe,
            "limit": min(max(required + 5, 23), 1000),
        })
        return parse_candles(response.json(), exchange, timeframe)

    # WEEX Spot. Lightweight level-breakout only needs 21 closed candles, and
    # the current klines endpoint is already proven to serve that reliably.
    if required <= 21:
        response = await _get_with_retry(client, kline_endpoint(exchange, market), {
            "symbol": symbol,
            "interval": timeframe,
            "limit": 100,
        })
        return parse_candles(response.json(), exchange, timeframe)

    # Research strategies need >=200 CLOSED candles. Use fixed 100-row historical
    # pages instead of asking WEEX for a Binance-style 200+ limit. The diagnostic
    # run on BTCUSDT/ETHUSDT proved historyKlines returns HTTP 200 but commonly
    # 98-99 rows per bounded page, so keep paging until the CLOSED-candle target
    # is actually reached rather than assuming page_size == returned rows.
    endpoint = kline_endpoint(exchange, market, historical=True)
    interval_ms = INTERVAL_MS[timeframe]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Anchor the first page to the most recent fully closed interval. This removes
    # the partial-current-bar ambiguity that produced 98/99-row windows when the
    # request end time was not aligned to the timeframe boundary.
    current_open_ms = (now_ms // interval_ms) * interval_ms
    page_end_ms = current_open_ms - 1

    # Keep some headroom above SnapshotBuilder's 200-candle minimum.
    target_closed = max(required, 220)
    by_open: dict[int, dict] = {}
    max_pages = 8

    for _iteration in range(1, max_pages + 1):
        page_start_ms = max(0, page_end_ms - (100 * interval_ms) + 1)
        response = await _get_with_retry(client, endpoint, {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": page_start_ms,
            "endTime": page_end_ms,
            "limit": 100,
        })
        page = parse_candles(response.json(), exchange, timeframe)
        closed_page = [c for c in page if c["close_time"] < now_ms]
        if not closed_page:
            break

        before = len(by_open)
        for candle in closed_page:
            by_open[candle["open_time"]] = candle

        if len(by_open) >= target_closed:
            break

        earliest_open = min(c["open_time"] for c in closed_page)
        next_end_ms = earliest_open - 1

        # Fail closed if WEEX repeats a page or otherwise stops moving backward.
        if next_end_ms >= page_end_ms or len(by_open) == before:
            break

        page_end_ms = next_end_ms
        await asyncio.sleep(0.05)

    return sorted(by_open.values(), key=lambda c: c["open_time"])[-target_closed:]


def parse_candles(rows: object, exchange: str, timeframe: str) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("Invalid candle response")
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("Invalid candle row")
        opened = int(row[0])
        # Normalize close time to the last millisecond of the interval.
        # WEEX documents a close_time field, but normalizing avoids 1 ms boundary variants.
        closed = opened + INTERVAL_MS[timeframe] - 1 if exchange == "weex" else int(row[6])
        candle = {"open_time": opened, "close_time": closed, "open": float(row[1]),
                  "high": float(row[2]), "low": float(row[3]), "close": float(row[4]),
                  "volume": float(row[5])}
        if candle["low"] > min(candle["open"], candle["close"]) or candle["high"] < max(candle["open"], candle["close"]):
            raise ValueError("Invalid OHLC candle")
        parsed.append(candle)
    return sorted({c["open_time"]: c for c in parsed}.values(), key=lambda c: c["open_time"])


async def fetch_universe(client: httpx.AsyncClient, exchange: str, market: str) -> list[str]:
    """Currently listed USDT Spot pairs or USDT perpetual contracts."""
    if exchange == "binance":
        endpoint = "https://api.binance.com/api/v3/exchangeInfo" if market == "spot" else "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = await client.get(endpoint)
        response.raise_for_status()
        items = response.json()["symbols"]
        symbols = [item["symbol"] for item in items if item.get("status") == "TRADING"
                   and item.get("quoteAsset") == "USDT" and
                   (item.get("isSpotTradingAllowed", True) if market == "spot" else item.get("contractType") == "PERPETUAL")]
    else:
        endpoint = WEEX_BASE[market] + ("/exchangeInfo" if market == "spot" else "/market/exchangeInfo")
        response = await client.get(endpoint, params={"symbolStatus": "TRADING"} if market == "spot" else {"contractType": "PERPETUAL"})
        response.raise_for_status()
        payload = response.json()
        items = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("Invalid WEEX exchangeInfo response")
        symbols = [item["symbol"] for item in items if item.get("quoteAsset") == "USDT"
                   and item.get("status", "TRADING") == "TRADING"
                   and (market == "spot" or item.get("contractType") == "PERPETUAL")
                   and isinstance(item.get("symbol"), str)]
    result = sorted({symbol for symbol in symbols if SYMBOL_RE.fullmatch(symbol)})
    if not result or len(result) > MAX_UNIVERSE:
        raise ValueError("Empty or unexpectedly large symbol universe")
    return result


def _mc(rows):
    return [Candle(open_time=datetime.fromtimestamp(r["open_time"]/1000,timezone.utc),open=r["open"],high=r["high"],low=r["low"],close=r["close"],volume=r["volume"],close_time=datetime.fromtimestamp(r["close_time"]/1000,timezone.utc),quote_volume=0.0,trades=0,taker_buy_base_volume=0.0,taker_buy_quote_volume=0.0) for r in rows]

def _level(closed):
    last,prev=closed[-1],closed[-21:-1]; hi=max(r["high"] for r in prev); lo=min(r["low"] for r in prev)
    d="up" if last["close"]>hi else "down" if last["close"]<lo else "none"
    return {"strategy":"level_breakout","direction":d,"score":None,"reasons":["Пробій опору" if d=="up" else "Пробій підтримки" if d=="down" else "Пробою рівня немає"],"high":hi,"low":lo}

async def _research(symbol,closed,selected):
    if len(closed)<200: raise ValueError("Fewer than 200 closed candles for MarketHunter research strategies")
    snap=SnapshotBuilder().build(symbol,_mc(closed)); out=[]
    for key in (RESEARCH_STRATEGIES if selected=="all" else [selected]):
        sig=await RESEARCH_STRATEGIES[key]().analyze(snap)
        if sig is not None: out.append({"strategy":key,"direction":str(sig.direction).lower(),"score":float(sig.score),"reasons":list(sig.reasons),"high":closed[-1]["high"],"low":closed[-1]["low"]})
    return out

def _store(run_id,request,symbol,last,item):
    with db() as conn:
        conn.execute("""INSERT INTO observations (id,run_id,symbol,market,timeframe,observed_at,candle_closed_at,close_price,breakout_high,breakdown_low,direction,status,exchange,strategy,score,reasons) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(str(uuid.uuid4()),run_id,symbol,request.market,request.timeframe,utcnow(),datetime.fromtimestamp(last["close_time"]/1000,timezone.utc).isoformat(),last["close"],item["high"],item["low"],item["direction"],"observation",request.exchange,item["strategy"],item.get("score"),json.dumps(item.get("reasons",[]),ensure_ascii=False)))


async def perform_scan(run_id: str, request: ScanRequest):
    errors=[]; skipped=[]
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            symbols=await fetch_universe(client,request.exchange,request.market) if request.mode=="all" else request.symbols
            with db() as conn: conn.execute("UPDATE runs SET symbols_total=? WHERE id=?",(len(symbols),run_id))
            for symbol in symbols:
                outcome = "error"
                try:
                    required=21 if request.strategy=="level_breakout" else 200
                    rows=await fetch_candles(client,request.exchange,request.market,request.timeframe,symbol,required)
                    now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
                    closed=[r for r in rows if r["close_time"]<now_ms]
                    if len(closed)<required:
                        skipped.append(f"{symbol}: insufficient closed history ({len(closed)}/{required})")
                        outcome = "skipped"
                        continue
                    items=[]
                    if request.strategy in {"level_breakout","all"}: items.append(_level(closed))
                    if request.strategy!="level_breakout": items.extend(await _research(symbol,closed,request.strategy))
                    for item in items: _store(run_id,request,symbol,closed[-1],item)
                    outcome = "analyzed"
                except httpx.HTTPStatusError as exc:
                    if _weex_spot_invalid_candle_symbol(exc, request):
                        skipped.append(f"{symbol}: WEEX Spot candle symbol invalid (API -1142)")
                        outcome = "skipped"
                    else:
                        errors.append(f"{symbol}: {_candle_http_error(exc)}")
                except (httpx.HTTPError,ValueError,TypeError,KeyError,IndexError) as exc:
                    errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
                finally:
                    with db() as conn:
                        conn.execute("""UPDATE runs SET symbols_done=symbols_done+1,
                            symbols_analyzed=symbols_analyzed+?,
                            symbols_skipped=symbols_skipped+?,
                            symbols_errors=symbols_errors+? WHERE id=?""",
                            (int(outcome == "analyzed"), int(outcome == "skipped"),
                             int(outcome == "error"), run_id))
                await asyncio.sleep(.15)
        messages=[]
        if skipped: messages.append(f"{len(skipped)} symbols skipped. Examples: "+"; ".join(skipped[:5]))
        if errors: messages.append(f"{len(errors)} symbol errors. Examples: "+"; ".join(errors[:5]))
        with db() as conn: conn.execute("UPDATE runs SET status=?,finished_at=?,error=? WHERE id=?",(
            "completed" if not errors else "partial" if len(errors)<len(symbols) else "failed",
            utcnow(), " | ".join(messages) if messages else None, run_id))
    except asyncio.CancelledError:
        with db() as conn: conn.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE id=?",(utcnow(),"Scan interrupted (server stopped)",run_id))
        raise
    except Exception as exc:
        with db() as conn: conn.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE id=?",(utcnow(),f"{type(exc).__name__}: {exc}"[:2000],run_id))
    finally: _lock.release()


@app.get("/manual-scanner/diagnostics/weex-spot-history")
async def diagnose_weex_spot_history(
    symbols: str = Query("BTCUSDT,ETHUSDT"),
    timeframe: str = Query("1h"),
):
    """Read-only, bounded diagnostic for public WEEX Spot candle semantics.

    This endpoint does NOT change scanner loading logic. It records the exact
    request/response evidence needed before any pagination fix is attempted.
    """
    if timeframe not in INTERVALS:
        raise HTTPException(422, "Invalid timeframe")

    requested = [item.upper().strip() for item in symbols.split(",") if item.strip()]
    if not requested or len(requested) > 5 or any(not SYMBOL_RE.fullmatch(item) for item in requested):
        raise HTTPException(422, "Invalid symbols")

    interval_ms = INTERVAL_MS[timeframe]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    current_endpoint = kline_endpoint("weex", "spot", historical=False)
    history_endpoint = kline_endpoint("weex", "spot", historical=True)

    def iso_ms(value):
        try:
            return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    async def raw_probe(client, *, probe, iteration, url, params):
        record = {
            "probe": probe,
            "iteration": iteration,
            "endpoint": url,
            "params": dict(params),
        }
        try:
            response = await client.get(url, params=params)
            record["request_url"] = str(response.request.url)
            record["http_status"] = response.status_code
            record["content_type"] = response.headers.get("content-type")
            record["body_preview"] = response.text[:2000]
            try:
                payload = response.json()
                record["json_type"] = type(payload).__name__
                if isinstance(payload, dict):
                    record["api_code"] = payload.get("code")
                    record["api_message"] = payload.get("msg", payload.get("message"))
                    record["returned_candles"] = None
                elif isinstance(payload, list):
                    record["returned_candles"] = len(payload)
                    opens = [row[0] for row in payload if isinstance(row, list) and row]
                    if opens:
                        record["earliest_open"] = min(opens)
                        record["latest_open"] = max(opens)
                        record["earliest_open_utc"] = iso_ms(min(opens))
                        record["latest_open_utc"] = iso_ms(max(opens))
                else:
                    record["returned_candles"] = None
            except Exception as exc:
                record["json_parse_error"] = f"{type(exc).__name__}: {exc}"
            return record
        except httpx.HTTPError as exc:
            record["transport_error"] = f"{type(exc).__name__}: {exc}"
            return record

    evidence = []
    async with httpx.AsyncClient(timeout=20) as client:
        for symbol in requested:
            current_params = {"symbol": symbol, "interval": timeframe, "limit": 100}
            evidence.append(await raw_probe(
                client, probe="klines", iteration=1,
                url=current_endpoint, params=current_params,
            ))

            # Bounded 3-page diagnostic only. Do not use this as scanner loader logic.
            end_ms = now_ms - 1
            for iteration in range(1, 4):
                start_ms = max(0, end_ms - 99 * interval_ms)
                history_params = {
                    "symbol": symbol,
                    "interval": timeframe,
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": 100,
                }
                record = await raw_probe(
                    client, probe="historyKlines", iteration=iteration,
                    url=history_endpoint, params=history_params,
                )
                evidence.append(record)
                if record.get("http_status") != 200 or not record.get("returned_candles"):
                    break
                earliest = record.get("earliest_open")
                if earliest is None:
                    break
                next_end = int(earliest) - 1
                if next_end >= end_ms:
                    break
                end_ms = next_end
                await asyncio.sleep(0.05)

    return {
        "read_only": True,
        "diagnostic_only": True,
        "exchange": "weex",
        "market": "spot",
        "symbols": requested,
        "timeframe": timeframe,
        "evidence": evidence,
    }


@app.post("/manual-scanner/runs", status_code=202)
async def start_scan(request: ScanRequest):
    request.exchange = request.exchange.lower().strip()
    if request.exchange not in {"binance", "weex"}:
        raise HTTPException(422, "Supported exchanges: binance/weex")
    request.market = request.market.lower().strip()
    if request.market not in {"spot", "futures"} or request.timeframe not in INTERVALS:
        raise HTTPException(422, "Supported markets: spot/futures; timeframes: 15m, 1h, 4h, 1d")
    request.mode = request.mode.lower().strip()
    request.strategy=request.strategy.lower().strip()
    if request.strategy not in STRATEGIES: raise HTTPException(422,"Unsupported strategy")
    if request.mode not in {"selected", "all"}:
        raise HTTPException(422, "Mode must be selected or all")
    request.symbols = [symbol.upper().strip() for symbol in request.symbols]
    if request.mode == "selected" and not request.symbols:
        raise HTTPException(422, "Select at least one symbol")
    if any(not SYMBOL_RE.fullmatch(symbol) for symbol in request.symbols) or len(set(request.symbols)) != len(request.symbols):
        raise HTTPException(422, "Symbols must be unique trading symbols (letters/digits only)")
    if _lock.locked():
        raise HTTPException(409, "Manual scan already running")
    await _lock.acquire()
    run_id = str(uuid.uuid4())
    try:
        with db() as conn:
            conn.execute("INSERT INTO runs (id, started_at, status, market, timeframe, symbols_total, exchange, strategy) VALUES (?,?,?,?,?,?,?,?)", (
                run_id, utcnow(), "running", request.market, request.timeframe, 0 if request.mode == "all" else len(request.symbols), request.exchange, request.strategy))
        asyncio.create_task(perform_scan(run_id, request))
    except Exception:
        _lock.release()
        raise
    return {"run_id": run_id, "status": "running", "read_only": True}


@app.get("/manual-scanner/runs")
def list_runs():
    with db() as conn:
        return {"runs": [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 30")]}


@app.get("/manual-scanner/runs/{run_id}")
def get_run(run_id: str):
    with db() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Unknown run")
        observations = [dict(row) for row in conn.execute("SELECT * FROM observations WHERE run_id=? ORDER BY symbol", (run_id,))]
        # Keep existing observation rows for UI compatibility. In "all" mode,
        # level_breakout stores direction="none" even when no breakout occurred.
        # Explicit counts let clients distinguish signal candidates from no-trade rows.
        signals = sum(item["direction"] != "none" for item in observations)
        no_breakout = sum(item["strategy"] == "level_breakout" and item["direction"] == "none"
                          for item in observations)
        summary = {"symbols_analyzed": run["symbols_analyzed"],
                   "symbols_skipped": run["symbols_skipped"],
                   "symbols_errors": run["symbols_errors"],
                   "observation_rows": len(observations),
                   "signal_candidates": signals,
                   "no_breakout_rows": no_breakout}
        return {"run": dict(run), "observations": observations,
                "summary": summary, "read_only": True}


@app.get("/manual-scanner/candles")
async def get_chart_candles(
    symbol: str = Query(..., min_length=2, max_length=25),
    exchange: str = Query("binance"),
    market: str = Query(...),
    timeframe: str = Query(...),
    candle_closed_at: datetime = Query(...),
):
    """Read-only historical candles ending at the selected observation, not live trading data."""
    symbol = symbol.upper().strip()
    if not SYMBOL_RE.fullmatch(symbol) or market not in {"spot", "futures"} or timeframe not in INTERVALS or exchange not in {"binance", "weex"}:
        raise HTTPException(422, "Invalid symbol, market or timeframe")
    if candle_closed_at.tzinfo is None:
        raise HTTPException(422, "candle_closed_at must include a timezone")
    end_ms = int(candle_closed_at.timestamp() * 1000)
    if end_ms > int(datetime.now(timezone.utc).timestamp() * 1000):
        raise HTTPException(422, "Observation cannot be in the future")
    endpoint = kline_endpoint(exchange, market, historical=True)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            params = {"symbol": symbol, "interval": timeframe, "limit": 90}
            if exchange == "binance":
                params["endTime"] = end_ms
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            rows = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"{exchange.upper()} candle request failed: {type(exc).__name__}") from exc
    if not isinstance(rows, list):
        raise HTTPException(502, f"Invalid {exchange.upper()} candle response")
    try:
        candles = [c for c in parse_candles(rows, exchange, timeframe) if c["close_time"] <= end_ms]
    except (TypeError, ValueError, IndexError) as exc:
        raise HTTPException(502, f"Invalid {exchange.upper()} candle data") from exc
    return {"symbol": symbol, "exchange": exchange, "market": market, "timeframe": timeframe,
            "observation_close_time": end_ms, "candles": candles, "historical": True}
