from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

ASSETS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT")
INTERVAL = "4h"
BAR_SECONDS = 4 * 3600
VOL_WIN, VOL_LOOK, VOL_Q = 42, 540, 0.30
DEV_WIN, DEV_LOOK, DEV_Q = 42, 540, 0.90
HOLD_BARS, DECLUSTER_BARS = 6, 6
ROUND_TRIP_COST = 0.001
BOOK_CAPITAL_USDT = 1000.0
MAX_NOTIONAL_FRAC = 0.10
ENTRY_WINDOW_SECONDS = 30 * 60
DB_PATH = Path(os.getenv("CRYPTO_PAPER_DB_PATH", "data/crypto_paper.db"))


def _get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "MarketHunter-CryptoPaper/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _qtl(values: list[float], q: float) -> float:
    s = sorted(values)
    x = (len(s) - 1) * q
    lo, hi = int(math.floor(x)), int(math.ceil(x))
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def _stdev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))


def _fetch_universes() -> tuple[list[str], list[str]]:
    spot = _get_json("https://api.binance.com/api/v3/exchangeInfo")
    futures = _get_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
    spot_symbols = sorted(
        x["symbol"]
        for x in spot.get("symbols", [])
        if x.get("status") == "TRADING"
        and x.get("quoteAsset") == "USDT"
        and x.get("isSpotTradingAllowed", True)
    )
    futures_symbols = sorted(
        x["symbol"]
        for x in futures.get("symbols", [])
        if x.get("status") == "TRADING"
        and x.get("quoteAsset") == "USDT"
        and x.get("contractType") == "PERPETUAL"
    )
    return spot_symbols, futures_symbols


def _fetch_klines(symbol: str, limit: int = 1000) -> dict[int, tuple[float, float]]:
    rows = _get_json(
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={INTERVAL}&limit={limit}"
    )
    now_ms = int(time.time() * 1000)
    data: dict[int, tuple[float, float]] = {}
    for row in rows:
        if int(row[6]) >= now_ms:
            continue
        data[int(row[0]) // 1000] = (float(row[1]), float(row[4]))
    return data


def _fetch_current_bar_open(symbol: str) -> tuple[int, float] | None:
    rows = _get_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={INTERVAL}&limit=2")
    if not rows:
        return None
    row = rows[-1]
    return int(row[0]) // 1000, float(row[1])


def frozen_events(common_ts: list[int], data: dict[str, dict[int, tuple[float, float]]]) -> list[dict]:
    n = len(common_ts)
    close = {s: [data[s][t][1] for t in common_ts] for s in ASSETS}
    ret = {s: [None] + [math.log(close[s][i] / close[s][i - 1]) for i in range(1, n)] for s in ASSETS}
    market = [None] + [sum(ret[s][i] for s in ASSETS) / len(ASSETS) for i in range(1, n)]
    rv: list[float | None] = [None] * n
    dev: dict[str, list[float | None]] = {s: [None] * n for s in ASSETS}
    for i in range(VOL_WIN + 1, n):
        rv[i] = _stdev(market[i - VOL_WIN + 1 : i + 1])
        for symbol in ASSETS:
            dev[symbol][i] = sum(ret[symbol][j] - market[j] for j in range(i - DEV_WIN + 1, i + 1))
    events: list[dict] = []
    last = -10**9
    floor = max(VOL_LOOK, DEV_LOOK) + VOL_WIN + 1
    for i in range(floor, n):
        if i - last < DECLUSTER_BARS:
            continue
        vol_history = [x for x in rv[i - VOL_LOOK : i] if x is not None]
        if not vol_history or rv[i] > _qtl(vol_history, VOL_Q):
            continue
        dev_history = [
            abs(dev[symbol][j])
            for j in range(i - DEV_LOOK, i)
            for symbol in ASSETS
            if dev[symbol][j] is not None
        ]
        if not dev_history:
            continue
        threshold = _qtl(dev_history, DEV_Q)
        candidate = max(ASSETS, key=lambda symbol: abs(dev[symbol][i]))
        if abs(dev[candidate][i]) <= threshold:
            continue
        side = "SHORT" if dev[candidate][i] > 0 else "LONG"
        events.append({"signal_ts": common_ts[i], "asset": candidate, "side": side})
        last = i
    return events


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS crypto_scan_cycles (
            cycle_id TEXT PRIMARY KEY,
            observed_at INTEGER NOT NULL,
            latest_closed_bar_ts INTEGER NOT NULL,
            spot_count INTEGER NOT NULL,
            futures_count INTEGER NOT NULL,
            spot_hash TEXT NOT NULL,
            futures_hash TEXT NOT NULL,
            evidence_state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crypto_material_states (
            state_key TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            state TEXT NOT NULL,
            strategy TEXT NOT NULL,
            book TEXT NOT NULL,
            symbol TEXT,
            side TEXT,
            signal_ts INTEGER,
            reason TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crypto_paper_orders (
            signal_key TEXT PRIMARY KEY,
            strategy TEXT NOT NULL,
            book TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            signal_ts INTEGER NOT NULL,
            target_entry_ts INTEGER NOT NULL,
            target_exit_ts INTEGER NOT NULL,
            status TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            notional_usdt REAL NOT NULL,
            net_return REAL,
            paper_pnl_usdt REAL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """
    )


def _record_state(conn: sqlite3.Connection, key: str, cycle_id: str, state: str, reason: str, *, symbol=None, side=None, signal_ts=None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO crypto_material_states VALUES (?,?,?,?,?,?,?,?,?,?)",
        (key, cycle_id, state, "Quiet-RV-v1", "SPOT", symbol, side, signal_ts, reason, int(time.time())),
    )


def _queue_signal(conn: sqlite3.Connection, event: dict, cycle_id: str) -> None:
    key = f"Quiet-RV-v1:{event['signal_ts']}:{event['asset']}:{event['side']}"
    now = int(time.time())
    conn.execute(
        """INSERT OR IGNORE INTO crypto_paper_orders
        (signal_key,strategy,book,symbol,side,signal_ts,target_entry_ts,target_exit_ts,status,entry_price,exit_price,notional_usdt,net_return,paper_pnl_usdt,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            key,
            "Quiet-RV-v1",
            "SPOT",
            event["asset"],
            event["side"],
            event["signal_ts"],
            event["signal_ts"] + BAR_SECONDS,
            event["signal_ts"] + HOLD_BARS * BAR_SECONDS,
            "QUEUED",
            None,
            None,
            BOOK_CAPITAL_USDT * MAX_NOTIONAL_FRAC,
            None,
            None,
            now,
            now,
        ),
    )
    _record_state(conn, f"{key}:QUEUED", cycle_id, "PAPER-ENTRY-QUEUED", "frozen signal present; awaiting exact next 4h bar open", symbol=event["asset"], side=event["side"], signal_ts=event["signal_ts"])


def _advance_orders(conn: sqlite3.Connection, cycle_id: str) -> None:
    now = int(time.time())
    rows = conn.execute("SELECT * FROM crypto_paper_orders WHERE status IN ('QUEUED','OPEN') ORDER BY signal_ts").fetchall()
    for row in rows:
        current = _fetch_current_bar_open(row["symbol"])
        if current is None:
            continue
        open_ts, open_price = current
        if row["status"] == "QUEUED":
            if open_ts == row["target_entry_ts"] and 0 <= now - open_ts <= ENTRY_WINDOW_SECONDS:
                conn.execute("UPDATE crypto_paper_orders SET status='OPEN', entry_price=?, updated_at=? WHERE signal_key=?", (open_price, now, row["signal_key"]))
                _record_state(conn, f"{row['signal_key']}:OPEN", cycle_id, "PAPER-ENTRY", "exact next-bar open observed inside entry window", symbol=row["symbol"], side=row["side"], signal_ts=row["signal_ts"])
            elif open_ts > row["target_entry_ts"]:
                conn.execute("UPDATE crypto_paper_orders SET status='NO-FILL', updated_at=? WHERE signal_key=?", (now, row["signal_key"]))
                _record_state(conn, f"{row['signal_key']}:NO-FILL", cycle_id, "NO-FILL", "entry window missed; no retroactive fill allowed", symbol=row["symbol"], side=row["side"], signal_ts=row["signal_ts"])
        elif row["status"] == "OPEN" and open_ts >= row["target_exit_ts"]:
            if open_ts != row["target_exit_ts"] or now - open_ts > ENTRY_WINDOW_SECONDS:
                conn.execute("UPDATE crypto_paper_orders SET status='EXIT-MISSED', updated_at=? WHERE signal_key=?", (now, row["signal_key"]))
                _record_state(conn, f"{row['signal_key']}:EXIT-MISSED", cycle_id, "EXIT-MISSED", "frozen exit open was not observed in time; no synthetic exit", symbol=row["symbol"], side=row["side"], signal_ts=row["signal_ts"])
                continue
            entry = float(row["entry_price"])
            gross = open_price / entry - 1 if row["side"] == "LONG" else entry / open_price - 1
            net = gross - ROUND_TRIP_COST
            pnl = float(row["notional_usdt"]) * net
            conn.execute("UPDATE crypto_paper_orders SET status='CLOSED', exit_price=?, net_return=?, paper_pnl_usdt=?, updated_at=? WHERE signal_key=?", (open_price, net, pnl, now, row["signal_key"]))
            _record_state(conn, f"{row['signal_key']}:CLOSED", cycle_id, "EXIT", "frozen hold completed at exact target 4h open", symbol=row["symbol"], side=row["side"], signal_ts=row["signal_ts"])


def run_cycle() -> dict:
    spot, futures = _fetch_universes()
    missing = [symbol for symbol in ASSETS if symbol not in spot]
    if missing:
        return {"status": "BLOCKED-EVIDENCE", "reason": f"missing frozen spot basket assets: {missing}"}
    data = {symbol: _fetch_klines(symbol) for symbol in ASSETS}
    common = sorted(set.intersection(*[set(data[symbol]) for symbol in ASSETS]))
    required = max(VOL_LOOK, DEV_LOOK) + VOL_WIN + HOLD_BARS + 2
    if len(common) < required:
        return {"status": "BLOCKED-EVIDENCE", "reason": f"only {len(common)} common closed bars"}
    latest = common[-1]
    freshness = int(time.time()) - (latest + BAR_SECONDS)
    if freshness > 8 * 3600:
        return {"status": "BLOCKED-EVIDENCE", "reason": f"closed-bar freshness {freshness}s"}
    spot_hash = hashlib.sha256("\n".join(spot).encode()).hexdigest()
    futures_hash = hashlib.sha256("\n".join(futures).encode()).hexdigest()
    cycle_id = f"BINANCE:4h:{latest}"
    events = frozen_events(common, data)
    current = [event for event in events if event["signal_ts"] == latest]
    with _connect() as conn:
        _init_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO crypto_scan_cycles VALUES (?,?,?,?,?,?,?,?)",
            (cycle_id, int(time.time()), latest, len(spot), len(futures), spot_hash, futures_hash, "OK"),
        )
        if current:
            _queue_signal(conn, current[-1], cycle_id)
        else:
            _record_state(conn, f"{cycle_id}:NO-SIGNAL", cycle_id, "NO-SIGNAL", "latest completed common 4h bar does not satisfy frozen Quiet-RV trigger")
        _advance_orders(conn, cycle_id)
        counts = {
            row["status"]: row["n"]
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM crypto_paper_orders GROUP BY status")
        }
    return {
        "status": "OK",
        "cycle_id": cycle_id,
        "spot_count": len(spot),
        "futures_count": len(futures),
        "latest_closed_bar_ts": latest,
        "current_signal": current[-1] if current else None,
        "paper_order_counts": counts,
        "real_orders": False,
        "paid_services": False,
        "futures_strategy_evaluated": False,
    }


def main() -> None:
    print(json.dumps(run_cycle(), sort_keys=True))


if __name__ == "__main__":
    main()
