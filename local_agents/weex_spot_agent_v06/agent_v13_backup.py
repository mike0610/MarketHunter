"""WEEX spot-only accumulation/breakout radar. Public endpoints; NEVER places orders."""
import argparse
import os
import sys
import traceback
import json
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = 'https://api-spot.weex.com'
ROOT = Path(__file__).resolve().parent
DB = ROOT / 'signals_v05.sqlite3'
CONFIG = ROOT / 'config.json'
LOG = ROOT / 'agent.log'
PID = ROOT / 'agent.pid'
# Delivery retries are stored in SQLite; never log Telegram credentials.
BAR_MS = 900000
HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * HOUR_MS
NEGATIVE_1D_TTL = 6 * HOUR_MS / 1000.0
NEGATIVE_1H_TTL = 2 * HOUR_MS / 1000.0
FAST_TIMEOUT = 5
FAST_ATTEMPTS = 2
# Diagnostic counters are process-local; no credentials or request URLs are logged.
METRICS = None
CURRENT_SYMBOL = None


def emit(**data):
    line = json.dumps(data, ensure_ascii=False)
    with LOG.open('a', encoding='utf-8') as log:
        log.write(line + '\n')
    print(line, flush=True)


def telegram(event):
    """Send only user-relevant v0.8 alerts. Never places orders."""
    if not CONFIG.exists():
        return False
    try:
        cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
        token = str(cfg.get('bot_token', '')).strip()
        chat_id = str(cfg.get('chat_id', '')).strip()
        if not token or not chat_id or token.startswith('PASTE_') or chat_id.startswith('PASTE_'):
            return False

        state = event.get('state')
        if state == 'BREAKOUT_CANDIDATE':
            msg = (f"🟡 BREAKOUT CANDIDATE · {event.get('direction','LONG')} | WEEX SPOT {event['symbol']}\n"
                   f"Діапазон: {event['range_low']:.8g} – {event['range_high']:.8g}\n"
                   f"Закриття: {event['trigger_close']:.8g} | Обсяг: {event['volume_ratio']}×\n"
                   'Лише спостереження. Ордерів немає.')
        elif state == 'BREAKOUT_CONFIRMED_PAPER':
            msg = (f"🟢 BREAKOUT CONFIRMED (PAPER) · {event.get('direction','LONG')} | WEEX SPOT {event['symbol']}\n"
                   f"Рівень: {event.get('breakout_level', event['range_high']):.8g}\n"
                   f"Підтвердження: {event['trigger_close']:.8g}\n"
                   'Наступна 15m свічка підтвердила напрямок. PAPER ONLY, ордерів немає.')
        elif state == 'BREAKOUT_INVALIDATED':
            msg = (f"🔴 BREAKOUT INVALIDATED · {event.get('direction','LONG')} | WEEX SPOT {event['symbol']}\n"
                   f"Рівень: {event.get('breakout_level', event['range_high']):.8g}\n"
                   f"Закриття: {event['trigger_close']:.8g}\n"
                   'Paper-сигнал скасовано. Ордерів немає.')
        elif state == 'SYSTEM_ERROR':
            msg = ('🚨 WEEX AGENT SYSTEM ERROR\n'
                   f"{event.get('message', 'Repeated cycle failures')}\n"
                   'Агент залишається PAPER ONLY. Перевір журнал agent.log.')
        elif state == 'DAILY_SUMMARY':
            msg = ('📊 WEEX AGENT · 24H SUMMARY\n'
                   f"Candidates: {event.get('candidates', 0)}\n"
                   f"Confirmed paper: {event.get('confirmed', 0)}\n"
                   f"Invalidated: {event.get('invalidated', 0)}\n"
                   f"Expired (DB only): {event.get('expired', 0)}\n"
                   f"Errors: {event.get('errors', 0)}\n"
                   'PAPER ONLY · ордерів немає.')
        else:
            # WATCH / EXPIRED / UNVERIFIED / technical states stay in DB/log only.
            return True

        body = json.dumps({'chat_id': chat_id, 'text': msg}).encode('utf-8')
        req = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
                                     data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            answer = json.load(response)
        if not answer.get('ok'):
            raise ValueError('Telegram returned not ok')
        emit(type='TELEGRAM_SENT', symbol=event['symbol'], state=state)
        return True
    except Exception as exc:
        emit(type='TELEGRAM_ERROR', symbol=event.get('symbol'), state=event.get('state'), error_type=type(exc).__name__)
        return False


def queue_notification(conn, event):
    # Only these three signal states belong in Telegram outbox.
    if event.get('state') not in ('BREAKOUT_CANDIDATE', 'BREAKOUT_CONFIRMED_PAPER', 'BREAKOUT_INVALIDATED'):
        return
    key = f"{event['symbol']}:{event.get('signal_candle_ms', event['candle_close_ms'])}:{event['state']}:{event['candle_close_ms']}"
    conn.execute('INSERT OR IGNORE INTO notification_outbox (event_key,payload_json) VALUES (?,?)',
                 (key, json.dumps(event, ensure_ascii=False)))


def meta_get(conn, key, default=None):
    row = conn.execute('SELECT value FROM agent_meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def meta_set(conn, key, value):
    conn.execute('INSERT INTO agent_meta(key,value) VALUES (?,?) '
                 'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))


def migrate_outbox_once(conn):
    """One-time v0.8.1 migration: retire only backlog that existed before this install.

    The marker makes this non-repeatable. Notifications queued after migration survive restarts.
    """
    if meta_get(conn, 'telegram_outbox_migration_v081') == 'done':
        return
    cutoff = conn.execute('SELECT COALESCE(MAX(rowid), 0) FROM notification_outbox').fetchone()[0]
    pending = conn.execute('SELECT COUNT(*) FROM notification_outbox WHERE delivered_at IS NULL AND rowid <= ?',
                           (cutoff,)).fetchone()[0]
    if pending:
        conn.execute('UPDATE notification_outbox SET delivered_at=? WHERE delivered_at IS NULL AND rowid <= ?',
                     (now(), cutoff))
    meta_set(conn, 'telegram_outbox_migration_v081', 'done')
    meta_set(conn, 'telegram_outbox_migration_cutoff_rowid', cutoff)
    meta_set(conn, 'daily_summary_started_at', time.time())
    conn.commit()
    emit(type='OUTBOX_MIGRATION_V081', retired=pending, cutoff_rowid=cutoff)


def maybe_daily_summary(conn):
    current = time.time()
    started = float(meta_get(conn, 'daily_summary_started_at', current))
    last = float(meta_get(conn, 'daily_summary_last_sent_at', 0) or 0)
    anchor = last if last > 0 else started
    if current - anchor < 24 * 60 * 60:
        return
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    candidates = conn.execute("SELECT COUNT(*) FROM events WHERE state='BREAKOUT_CANDIDATE' AND observed_at_utc>=?", (since,)).fetchone()[0]
    confirmed = conn.execute("SELECT COUNT(*) FROM lifecycle_events WHERE state='BREAKOUT_CONFIRMED_PAPER' AND observed_at_utc>=?", (since,)).fetchone()[0]
    invalidated = conn.execute("SELECT COUNT(*) FROM lifecycle_events WHERE state='BREAKOUT_INVALIDATED' AND observed_at_utc>=?", (since,)).fetchone()[0]
    expired = conn.execute("SELECT COUNT(*) FROM lifecycle_events WHERE state='BREAKOUT_EXPIRED' AND observed_at_utc>=?", (since,)).fetchone()[0]
    errors = sum(1 for line in LOG.read_text(encoding='utf-8', errors='ignore').splitlines()[-5000:]
                 if '"type": "ERROR"' in line or '"type": "CYCLE_ABORTED"' in line)
    event = {'state': 'DAILY_SUMMARY', 'symbol': 'SYSTEM', 'candidates': candidates,
             'confirmed': confirmed, 'invalidated': invalidated, 'expired': expired, 'errors': errors}
    if telegram(event):
        meta_set(conn, 'daily_summary_last_sent_at', current)
        conn.commit()
        emit(type='DAILY_SUMMARY_SENT', candidates=candidates, confirmed=confirmed,
             invalidated=invalidated, expired=expired, errors=errors)


def flush_notifications(conn, limit=3):
    current = time.time()
    rows = conn.execute('SELECT event_key,payload_json FROM notification_outbox WHERE delivered_at IS NULL AND next_attempt_at <= ? ORDER BY rowid LIMIT 50', (current,)).fetchall()
    sent = 0
    for key, payload in rows:
        event = json.loads(payload)
        state = event.get('state')
        if state not in ('BREAKOUT_CANDIDATE', 'BREAKOUT_CONFIRMED_PAPER', 'BREAKOUT_INVALIDATED'):
            conn.execute('UPDATE notification_outbox SET delivered_at=? WHERE event_key=?', (now(), key))
            continue
        if sent >= limit:
            break
        if telegram(event):
            conn.execute('UPDATE notification_outbox SET delivered_at=? WHERE event_key=?', (now(), key))
        else:
            conn.execute('UPDATE notification_outbox SET next_attempt_at=? WHERE event_key=?', (time.time() + 300, key))
        sent += 1
    conn.commit()

def now():
    return datetime.now(timezone.utc).isoformat()


def fetch_raw(path, params=None, attempts=FAST_ATTEMPTS):
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    req = urllib.request.Request(url, headers={'User-Agent': 'WEEX-spot-radar/0.13-decoupled-mtf-paper'})
    last_exc = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=FAST_TIMEOUT) as response:
                result = json.load(response)
            return result
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
        if METRICS is not None:
            METRICS['retries'] += 1
        time.sleep(0.75 * (2 ** attempt))
    raise last_exc


def fetch(path, params=None, attempts=FAST_ATTEMPTS):
    global METRICS
    started = time.monotonic()
    endpoint = path.rsplit('/', 1)[-1]
    interval = params.get('interval') if params else None
    kind = f'{endpoint}:{interval}' if interval else endpoint
    if METRICS is not None:
        METRICS['api_calls'][kind] = METRICS['api_calls'].get(kind, 0) + 1
    try:
        return fetch_raw(path, params, attempts)
    finally:
        duration = time.monotonic() - started
        if METRICS is not None:
            METRICS['api_seconds'][kind] = round(METRICS['api_seconds'].get(kind, 0) + duration, 2)
            if duration >= 8:
                METRICS['slow_calls'] += 1
                emit(type='SLOW_API', symbol=CURRENT_SYMBOL, endpoint=kind,
                     seconds=round(duration, 2))


def universe():
    raw = fetch('/api/v3/exchangeInfo', {'symbolStatus': 'TRADING'})
    result = set()
    for x in raw.get('symbols', []):
        symbol = x.get('symbol', '')
        base = symbol[:-4] if symbol.endswith('USDT') else ''
        if (x.get('status') == 'TRADING' and x.get('quoteAsset') == 'USDT'
                and x.get('enableTrade') is not False and symbol.endswith('USDT')
                and base and base.isascii() and base.isalnum()):
            result.add(symbol)
    if not result:
        raise ValueError('No WEEX spot USDT symbols')
    return result


def snapshot():
    raw = fetch('/api/v3/market/ticker/24hr')
    if not isinstance(raw, list):
        raise ValueError('Unexpected all-tickers response')
    return {x['symbol']: x for x in raw if isinstance(x, dict) and 'symbol' in x}


def eligible(x):
    try:
        volume = float(x['quoteVolume'])
        bid, ask = float(x['bidPrice']), float(x['askPrice'])
        last, opening = float(x['lastPrice']), float(x['openPrice'])
        if min(bid, ask, last, opening) <= 0 or ask <= bid:
            return False
        spread = 100 * (ask - bid) / ((ask + bid) / 2)
        rise = 100 * (last / opening - 1)
        return volume >= 10000 and spread <= 0.5 and rise <= 20
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def candles_tf(symbol, interval, count, interval_ms):
    """Return exactly `count` closed, contiguous candles for one timeframe."""
    raw = fetch('/api/v3/market/klines', {'symbol': symbol, 'interval': interval, 'limit': max(100, count + 5)})
    if not isinstance(raw, list):
        raise ValueError(f'Invalid {interval} candles payload')
    current = int(time.time() * 1000)
    rows = []
    for r in raw:
        if not isinstance(r, list) or len(r) < 8:
            continue
        end = int(r[6])
        if end >= current:
            continue
        rows.append({'start': int(r[0]), 'end': end, 'high': float(r[2]),
                     'low': float(r[3]), 'close': float(r[4]), 'volume': float(r[7])})
    rows.sort(key=lambda x: x['start'])
    rows = rows[-count:]
    if len(rows) != count:
        raise ValueError(f'Insufficient {interval} candles')
    if current - rows[-1]['end'] > int(interval_ms * 2.5):
        raise ValueError(f'Stale {interval} candles')
    if any(abs((b['start'] - a['start']) - interval_ms) > 1000 for a, b in zip(rows, rows[1:])):
        raise ValueError(f'Missing {interval} candles')
    return rows


def candles(symbol):
    # Lifecycle confirmation remains on closed 15m bars.
    return candles_tf(symbol, '15m', 49, BAR_MS)


def cache_expiry(last_end_ms, interval_ms):
    return (last_end_ms + 1 + interval_ms) / 1000.0 + 5.0


def negative_cache_get(conn, symbol, timeframe):
    row = conn.execute(
        'SELECT reason,expires_at FROM mtf_negative_cache WHERE symbol=? AND timeframe=?',
        (symbol, timeframe)).fetchone()
    if not row:
        return None
    if float(row[1]) <= time.time():
        conn.execute('DELETE FROM mtf_negative_cache WHERE symbol=? AND timeframe=?',
                     (symbol, timeframe))
        return None
    return row[0]


def negative_cache_set(conn, symbol, timeframe, reason, ttl_seconds):
    conn.execute("""INSERT INTO mtf_negative_cache(symbol,timeframe,reason,expires_at)
                    VALUES (?,?,?,?) ON CONFLICT(symbol,timeframe) DO UPDATE SET
                    reason=excluded.reason,expires_at=excluded.expires_at""",
                 (symbol, timeframe, reason, time.time() + ttl_seconds))


def negative_cache_clear(conn, symbol, timeframe):
    conn.execute('DELETE FROM mtf_negative_cache WHERE symbol=? AND timeframe=?',
                 (symbol, timeframe))


def daily_context(conn, symbol):
    row = conn.execute("SELECT daily_direction,daily_close,daily_sma20,daily_expires_at FROM mtf_cache WHERE symbol=?", (symbol,)).fetchone()
    if row and row[3] and float(row[3]) > time.time():
        if METRICS is not None:
            METRICS['cache_1d_hit'] += 1
        return {'direction': row[0], 'daily_close': row[1], 'daily_sma20': row[2]}
    reason = negative_cache_get(conn, symbol, '1d')
    if reason:
        if METRICS is not None:
            METRICS['negative_1d_hit'] += 1
        raise ValueError(reason)
    if METRICS is not None:
        METRICS['cache_1d_miss'] += 1
    try:
        daily = candles_tf(symbol, '1d', 21, DAY_MS)
    except ValueError as exc:
        if str(exc).startswith('Insufficient 1d'):
            negative_cache_set(conn, symbol, '1d', str(exc), NEGATIVE_1D_TTL)
        raise
    negative_cache_clear(conn, symbol, '1d')
    daily_sma20 = statistics.mean(x['close'] for x in daily[-20:])
    daily_close = daily[-1]['close']
    direction = 'LONG' if daily_close > daily_sma20 else 'SHORT' if daily_close < daily_sma20 else 'NEUTRAL'
    expires = cache_expiry(daily[-1]['end'], DAY_MS)
    conn.execute("""INSERT INTO mtf_cache(symbol,daily_direction,daily_close,daily_sma20,daily_expires_at)
                    VALUES (?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET
                    daily_direction=excluded.daily_direction,daily_close=excluded.daily_close,
                    daily_sma20=excluded.daily_sma20,daily_expires_at=excluded.daily_expires_at""",
                 (symbol, direction, daily_close, daily_sma20, expires))
    return {'direction': direction, 'daily_close': daily_close, 'daily_sma20': daily_sma20}


def hourly_structure(conn, symbol):
    row = conn.execute("SELECT range_low,range_high,range_width_pct,hourly_upper_touches,hourly_lower_touches,hourly_expires_at FROM mtf_cache WHERE symbol=?", (symbol,)).fetchone()
    if row and row[5] and float(row[5]) > time.time():
        if METRICS is not None:
            METRICS['cache_1h_hit'] += 1
        return {'low': row[0], 'high': row[1], 'width': row[2], 'upper_touches': row[3], 'lower_touches': row[4]}
    reason = negative_cache_get(conn, symbol, '1h')
    if reason:
        if METRICS is not None:
            METRICS['negative_1h_hit'] += 1
        raise ValueError(reason)
    if METRICS is not None:
        METRICS['cache_1h_miss'] += 1
    try:
        hourly = candles_tf(symbol, '1h', 25, HOUR_MS)
    except ValueError as exc:
        if str(exc).startswith('Insufficient 1h'):
            negative_cache_set(conn, symbol, '1h', str(exc), NEGATIVE_1H_TTL)
        raise
    negative_cache_clear(conn, symbol, '1h')
    box = hourly[-25:-1]
    high, low = max(x['high'] for x in box), min(x['low'] for x in box)
    width = 200 * (high - low) / (high + low) if low > 0 else 999.0
    upper_touches = sum(x['high'] >= high * 0.995 for x in box)
    lower_touches = sum(x['low'] <= low * 1.005 for x in box)
    expires = cache_expiry(hourly[-1]['end'], HOUR_MS)
    conn.execute("""INSERT INTO mtf_cache(symbol,range_low,range_high,range_width_pct,hourly_upper_touches,hourly_lower_touches,hourly_expires_at)
                    VALUES (?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET
                    range_low=excluded.range_low,range_high=excluded.range_high,
                    range_width_pct=excluded.range_width_pct,hourly_upper_touches=excluded.hourly_upper_touches,
                    hourly_lower_touches=excluded.hourly_lower_touches,hourly_expires_at=excluded.hourly_expires_at""",
                 (symbol, low, high, width, upper_touches, lower_touches, expires))
    return {'low': low, 'high': high, 'width': width, 'upper_touches': upper_touches, 'lower_touches': lower_touches}


def analyze(conn, symbol, m15=None):
    """Cached MTF funnel. Rejected symbols are reconsidered when 1D/1H bars refresh."""
    daily = daily_context(conn, symbol)
    direction = daily['direction']
    if direction == 'NEUTRAL':
        return None
    structure = hourly_structure(conn, symbol)
    high, low, width = structure['high'], structure['low'], structure['width']
    upper_touches, lower_touches = structure['upper_touches'], structure['lower_touches']
    if low <= 0 or not 1.0 <= width <= 15.0:
        return None
    if direction == 'LONG' and upper_touches < 2:
        return None
    if direction == 'SHORT' and lower_touches < 2:
        return None
    m15 = m15 if m15 is not None else candles_tf(symbol, '15m', 49, BAR_MS)
    trigger = m15[-1]
    med = statistics.median(x['volume'] for x in m15[:-1])
    if med <= 0:
        return None
    close, ratio = trigger['close'], trigger['volume'] / med
    if direction == 'LONG':
        if high * 1.001 < close <= high * 1.012 and ratio >= 1.8:
            state = 'BREAKOUT_CANDIDATE'
        elif high * 0.985 <= close <= high and ratio >= 1.2:
            state = 'WATCH'
        else:
            return None
    else:
        if low * 0.988 <= close < low * 0.999 and ratio >= 1.8:
            state = 'BREAKOUT_CANDIDATE'
        elif low <= close <= low * 1.015 and ratio >= 1.2:
            state = 'WATCH'
        else:
            return None
    return {'symbol': symbol, 'state': state, 'direction': direction,
            'range_low': low, 'range_high': high, 'range_width_pct': round(width, 3),
            'trigger_close': close, 'volume_ratio': round(ratio, 2),
            'candle_close_ms': trigger['end'], 'daily_close': daily['daily_close'],
            'daily_sma20': round(daily['daily_sma20'], 10), 'hourly_upper_touches': upper_touches,
            'hourly_lower_touches': lower_touches,
            'timeframes': {'context': '1d', 'structure': '1h', 'trigger': '15m'},
            'observed_at_utc': now(), 'mode': 'PAPER_ONLY_NO_ORDERS',
            'rules_version': 'experimental_v0_13_decoupled_mtf_long_short_1d_1h_15m'}

def liquidity(symbol, direction='LONG'):
    book = fetch('/api/v3/market/depth', {'symbol': symbol, 'limit': 200})
    bids = [(float(p), float(q)) for p, q in book.get('bids', [])]
    asks = [(float(p), float(q)) for p, q in book.get('asks', [])]
    if not bids or not asks:
        raise ValueError('Empty order book')
    bid, ask = max(p for p, _ in bids), min(p for p, _ in asks)
    if bid <= 0 or ask <= bid:
        raise ValueError('Invalid spread')
    spread = 200 * (ask - bid) / (ask + bid)
    if direction == 'SHORT':
        depth = sum(p * q for p, q in bids if p >= bid * 0.995)
    else:
        depth = sum(p * q for p, q in asks if p <= ask * 1.005)
    return {'best_bid': bid, 'best_ask': ask, 'spread_pct': round(spread, 4),
            'near_side_depth_usdt': round(depth, 2), 'liquidity_side': 'bid' if direction == 'SHORT' else 'ask',
            'liquidity_ok': spread <= 0.35 and depth >= 1000}


WINDOW_MS = 4 * 60 * 60 * 1000


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS queue (symbol TEXT PRIMARY KEY, last_checked REAL NOT NULL DEFAULT 0, watch_until REAL NOT NULL DEFAULT 0)')
    conn.execute('CREATE TABLE IF NOT EXISTS events (symbol TEXT, candle_close_ms INTEGER, state TEXT, observed_at_utc TEXT, payload_json TEXT, PRIMARY KEY(symbol,candle_close_ms,state))')
    conn.execute('''CREATE TABLE IF NOT EXISTS active_breakouts (
        symbol TEXT PRIMARY KEY, signal_candle_ms INTEGER NOT NULL,
        range_high REAL NOT NULL, expires_ms INTEGER NOT NULL,
        status TEXT NOT NULL, resolved_candle_ms INTEGER, resolved_close REAL,
        direction TEXT NOT NULL DEFAULT 'LONG', range_low REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS lifecycle_events (
        symbol TEXT NOT NULL, signal_candle_ms INTEGER NOT NULL,
        state TEXT NOT NULL, candle_close_ms INTEGER NOT NULL,
        observed_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL,
        PRIMARY KEY(symbol, signal_candle_ms, state))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS notification_outbox (
        event_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, delivered_at TEXT, next_attempt_at REAL NOT NULL DEFAULT 0)''')
    conn.execute('CREATE TABLE IF NOT EXISTS agent_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute("""CREATE TABLE IF NOT EXISTS mtf_cache (
        symbol TEXT PRIMARY KEY, daily_direction TEXT, daily_close REAL, daily_sma20 REAL, daily_expires_at REAL,
        range_low REAL, range_high REAL, range_width_pct REAL, hourly_upper_touches INTEGER,
        hourly_lower_touches INTEGER, hourly_expires_at REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS mtf_negative_cache (
        symbol TEXT NOT NULL, timeframe TEXT NOT NULL, reason TEXT NOT NULL,
        expires_at REAL NOT NULL, PRIMARY KEY(symbol,timeframe))""")
    breakout_columns = {row[1] for row in conn.execute('PRAGMA table_info(active_breakouts)')}
    if 'direction' not in breakout_columns:
        conn.execute("ALTER TABLE active_breakouts ADD COLUMN direction TEXT NOT NULL DEFAULT 'LONG'")
    if 'range_low' not in breakout_columns:
        conn.execute('ALTER TABLE active_breakouts ADD COLUMN range_low REAL')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(notification_outbox)')}
    if 'next_attempt_at' not in columns:
        conn.execute('ALTER TABLE notification_outbox ADD COLUMN next_attempt_at REAL NOT NULL DEFAULT 0')
    conn.commit()


def register_breakout(conn, event):
    symbol = event['symbol']
    active = conn.execute('SELECT status FROM active_breakouts WHERE symbol=?',
                          (symbol,)).fetchone()
    if active and active[0] == 'ACTIVE':
        return False
    previous = conn.execute('SELECT signal_candle_ms FROM active_breakouts WHERE symbol=?',
                            (symbol,)).fetchone()
    if previous and event['candle_close_ms'] <= previous[0]:
        return False
    ms = event['candle_close_ms']
    conn.execute('''INSERT INTO active_breakouts
        (symbol,signal_candle_ms,range_high,expires_ms,status,direction,range_low)
        VALUES (?,?,?,?, 'ACTIVE',?,?)
        ON CONFLICT(symbol) DO UPDATE SET signal_candle_ms=excluded.signal_candle_ms,
        range_high=excluded.range_high,expires_ms=excluded.expires_ms,
        status="ACTIVE",direction=excluded.direction,range_low=excluded.range_low,
        resolved_candle_ms=NULL,resolved_close=NULL''',
        (symbol, ms, event['range_high'], ms + WINDOW_MS, event.get('direction', 'LONG'), event.get('range_low')))
    return True


def resolve_breakout(conn, symbol, bars, observed_ms):
    row = conn.execute("""SELECT signal_candle_ms,range_high,expires_ms,direction,range_low
                          FROM active_breakouts WHERE symbol=? AND status='ACTIVE'""",
                       (symbol,)).fetchone()
    if not row:
        return None
    signal_ms, range_high, expiry_ms, direction, range_low = row
    direction = direction or 'LONG'
    level = range_high if direction == 'LONG' else range_low
    if level is None:
        level = range_high
    by_end = {int(b['end']): float(b['close']) for b in bars if signal_ms < int(b['end']) <= observed_ms}
    last = min(observed_ms, expiry_ms)
    expected = range(signal_ms + BAR_MS, last + 1, BAR_MS)
    missing = [end for end in expected if end not in by_end]
    if missing and observed_ms < expiry_ms:
        return None
    first_end = signal_ms + BAR_MS
    first_close = by_end.get(first_end)
    holds = first_close is not None and ((direction == 'LONG' and first_close >= level) or
                                         (direction == 'SHORT' and first_close <= level))
    if holds:
        confirmed = conn.execute("SELECT 1 FROM lifecycle_events WHERE symbol=? AND signal_candle_ms=? AND state='BREAKOUT_CONFIRMED_PAPER'", (symbol, signal_ms)).fetchone()
        if not confirmed:
            confirm_event = {'symbol': symbol, 'state': 'BREAKOUT_CONFIRMED_PAPER', 'direction': direction,
                             'signal_candle_ms': signal_ms, 'range_high': range_high, 'range_low': range_low,
                             'breakout_level': level, 'candle_close_ms': first_end, 'trigger_close': first_close,
                             'observed_at_utc': now(), 'mode': 'PAPER_ONLY_NO_ORDERS',
                             'rules_version': 'experimental_v0_13_decoupled_mtf_long_short_1d_1h_15m'}
            conn.execute('INSERT OR IGNORE INTO lifecycle_events VALUES (?,?,?,?,?,?)',
                         (symbol, signal_ms, confirm_event['state'], first_end, confirm_event['observed_at_utc'], json.dumps(confirm_event, ensure_ascii=False)))
            queue_notification(conn, confirm_event)
            emit(type='LIFECYCLE', **confirm_event)
    invalid = None if missing else next(((end, by_end[end]) for end in expected
                    if (direction == 'LONG' and by_end[end] < level) or (direction == 'SHORT' and by_end[end] > level)), None)
    if invalid:
        end, close = invalid
        state = 'BREAKOUT_INVALIDATED'
    elif observed_ms >= expiry_ms:
        end, close = expiry_ms, by_end.get(expiry_ms)
        state = 'BREAKOUT_UNVERIFIED' if missing else 'BREAKOUT_EXPIRED'
    else:
        return None
    event = {'symbol': symbol, 'state': state, 'direction': direction, 'signal_candle_ms': signal_ms,
             'range_high': range_high, 'range_low': range_low, 'breakout_level': level,
             'candle_close_ms': end, 'trigger_close': close, 'observed_at_utc': now(),
             'mode': 'PAPER_ONLY_NO_ORDERS'}
    conn.execute('UPDATE active_breakouts SET status=?,resolved_candle_ms=?,resolved_close=? WHERE symbol=? AND status="ACTIVE"',
                 (state, end, close, symbol))
    conn.execute('INSERT OR IGNORE INTO lifecycle_events VALUES (?,?,?,?,?,?)',
                 (symbol, signal_ms, state, end, event['observed_at_utc'], json.dumps(event, ensure_ascii=False)))
    queue_notification(conn, event)
    emit(type='LIFECYCLE', **event)
    return event

def cycle(conn, limit):
    global METRICS, CURRENT_SYMBOL
    started = time.monotonic()
    METRICS = {'api_calls': {}, 'api_seconds': {}, 'retries': 0, 'slow_calls': 0,
               'cache_1d_hit': 0, 'cache_1d_miss': 0, 'cache_1h_hit': 0, 'cache_1h_miss': 0, 'negative_1d_hit': 0, 'negative_1h_hit': 0}
    symbols = universe()
    tickers = snapshot()
    matched = symbols & tickers.keys()
    eligible_symbols = {s for s in matched if eligible(tickers[s])}
    conn.executemany('INSERT OR IGNORE INTO queue(symbol) VALUES (?)', ((s,) for s in symbols))
    # Preserve unavailable symbols while their breakout lifecycle is unresolved.
    conn.execute('DELETE FROM queue WHERE symbol NOT IN (' + ','.join('?' for _ in symbols) + ') AND symbol NOT IN (SELECT symbol FROM active_breakouts WHERE status="ACTIVE")', tuple(symbols))
    conn.commit()
    flush_notifications(conn)
    # Prioritize fresh WATCH candidates, then least recently checked pairs.
    current = time.time()
    rows = conn.execute('SELECT symbol,last_checked,watch_until FROM queue').fetchall()
    active_symbols = {r[0] for r in conn.execute(
        "SELECT symbol FROM active_breakouts WHERE status='ACTIVE'")}
    pending = [(s, checked, watch) for s, checked, watch in rows
               if s in eligible_symbols or s in active_symbols]
    pending.sort(key=lambda x: (0 if x[0] in active_symbols else 1,
                                0 if x[2] > current else 1, x[1]))
    chosen = pending[:limit]
    emit(type='MARKET_FILTER', universe=len(symbols), tickers_received=len(tickers),
         matched=len(matched), eligible=len(eligible_symbols), unmatched=len(symbols - matched),
         queued=len(chosen), remaining_eligible=max(0, len(pending) - len(chosen)))
    counts = {'processed': 0, 'watch': 0, 'breakout_candidates': 0,
              'rejected_liquidity': 0, 'http_400': 0, 'other_errors': 0, 'insufficient_history': 0, 'new_events': 0}
    for symbol, _, _ in chosen:
        CURRENT_SYMBOL = symbol
        symbol_started = time.monotonic()
        checked_at = time.time()
        try:
            if symbol in active_symbols and symbol not in symbols:
                # A delisted pair cannot be verified; retire after the original window.
                row = conn.execute('SELECT signal_candle_ms,range_high,expires_ms,direction,range_low FROM active_breakouts WHERE symbol=? AND status="ACTIVE"', (symbol,)).fetchone()
                if row and int(time.time() * 1000) >= row[2]:
                    signal_ms, range_high, expiry_ms, direction, range_low = row
                    level = range_high if direction == 'LONG' else range_low
                    event = {'symbol': symbol, 'state': 'BREAKOUT_UNVERIFIED', 'direction': direction,
                             'signal_candle_ms': signal_ms, 'range_high': range_high, 'range_low': range_low, 'breakout_level': level,
                             'candle_close_ms': expiry_ms, 'trigger_close': None,
                             'observed_at_utc': now(), 'mode': 'ALERT_ONLY_NO_ORDERS'}
                    conn.execute('UPDATE active_breakouts SET status=? WHERE symbol=? AND status="ACTIVE"', ('BREAKOUT_UNVERIFIED', symbol))
                    conn.execute('INSERT OR IGNORE INTO lifecycle_events VALUES (?,?,?,?,?,?)',
                                 (symbol, signal_ms, event['state'], expiry_ms, event['observed_at_utc'], json.dumps(event, ensure_ascii=False)))
                    queue_notification(conn, event)
                    emit(type='LIFECYCLE', **event)
                conn.execute('UPDATE queue SET last_checked=? WHERE symbol=?', (checked_at, symbol))
                conn.commit()
                counts['processed'] += 1
                continue
            # Resolve from actual closed bars, independent of the current setup rules.
            m15 = None
            if symbol in active_symbols:
                m15 = candles(symbol)
                lifecycle = resolve_breakout(conn, symbol, m15, int(time.time() * 1000))
                if lifecycle:
                    conn.commit()
            event = analyze(conn, symbol, m15=m15)
            if event:
                if event['state'] == 'BREAKOUT_CANDIDATE':
                    event.update(liquidity(symbol, event.get('direction', 'LONG')))
                    if not event['liquidity_ok']:
                        event['state'] = 'REJECTED_LIQUIDITY'
                if event['state'] == 'BREAKOUT_CANDIDATE':
                    # A signal already present in the v0.6 history must not be rebroadcast.
                    existing = conn.execute('SELECT 1 FROM events WHERE symbol=? AND candle_close_ms=? AND state=?',
                                            (symbol, event['candle_close_ms'], 'BREAKOUT_CANDIDATE')).fetchone()
                    if existing or not register_breakout(conn, event):
                        event = None
                if event is None:
                    watch_until = 0
                    conn.execute('UPDATE queue SET last_checked=?,watch_until=? WHERE symbol=?',
                                 (checked_at, watch_until, symbol))
                    conn.commit()
                    counts['processed'] += 1
                    continue
                if event['state'] == 'WATCH':
                    counts['watch'] += 1
                    watch_until = checked_at + 3600
                else:
                    watch_until = 0
                    if event['state'] == 'BREAKOUT_CANDIDATE':
                        counts['breakout_candidates'] += 1
                    else:
                        counts['rejected_liquidity'] += 1
                before = conn.total_changes
                conn.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',
                             (symbol, event['candle_close_ms'], event['state'],
                              event['observed_at_utc'], json.dumps(event)))
                if conn.total_changes > before:
                    counts['new_events'] += 1
                    if event['state'] == 'BREAKOUT_CANDIDATE':
                        emit(type='SIGNAL', **event)
                    queue_notification(conn, event)
            else:
                watch_until = 0
            conn.execute('UPDATE queue SET last_checked=?,watch_until=? WHERE symbol=?',
                         (checked_at, watch_until, symbol))
        except urllib.error.HTTPError as exc:
            counts['http_400' if exc.code == 400 else 'other_errors'] += 1
            conn.execute('UPDATE queue SET last_checked=? WHERE symbol=?', (checked_at, symbol))
        except Exception as exc:
            message = str(exc)
            if message.startswith('Insufficient ') or message.startswith('Stale ') or message.startswith('Missing '):
                counts['insufficient_history'] += 1
                emit(type='SKIP_INSUFFICIENT_HISTORY', symbol=symbol, reason=message)
            else:
                counts['other_errors'] += 1
                emit(type='ERROR', symbol=symbol, error=message)
            conn.execute('UPDATE queue SET last_checked=? WHERE symbol=?', (checked_at, symbol))
        counts['processed'] += 1
        conn.commit()
        symbol_seconds = time.monotonic() - symbol_started
        if symbol_seconds >= 15:
            emit(type='SLOW_SYMBOL', symbol=symbol, seconds=round(symbol_seconds, 2))
        if counts['processed'] % 10 == 0:
            emit(type='PROGRESS', processed=counts['processed'], total=len(chosen),
                 elapsed_seconds=round(time.monotonic() - started, 1))
    recent = conn.execute('SELECT COUNT(*) FROM queue WHERE last_checked >= ?', (time.time() - 3600,)).fetchone()[0]
    CURRENT_SYMBOL = None
    emit(type='CYCLE_DIAGNOSTICS', **METRICS)
    METRICS = None
    emit(type='CYCLE_END', **counts, eligible=len(eligible_symbols),
         unique_checked_last_hour=recent, elapsed_seconds=round(time.monotonic() - started, 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--batch', type=int, default=120)
    args = parser.parse_args()
    if args.batch < 1 or args.batch > 500:
        parser.error('--batch must be 1..500')
    if PID.exists():
        parser.error('agent.pid already exists; verify whether another agent is running')
    PID.write_text(str(os.getpid()), encoding='ascii')
    try:
        run_agent(args)
    finally:
        PID.unlink(missing_ok=True)


def run_agent(args):
    with sqlite3.connect(DB) as conn:
        init(conn)
        migrate_outbox_once(conn)
        try:
            consecutive_aborts = 0
            last_system_alert = 0.0
            while True:
                emit(type='CYCLE_START', time_utc=now())
                try:
                    cycle(conn, args.batch)
                    consecutive_aborts = 0
                except Exception as exc:
                    consecutive_aborts += 1
                    emit(type='CYCLE_ABORTED', error=str(exc), consecutive=consecutive_aborts)
                    current = time.time()
                    if consecutive_aborts >= 3 and current - last_system_alert >= 3600:
                        alert = {'state': 'SYSTEM_ERROR', 'symbol': 'SYSTEM',
                                 'message': f'{consecutive_aborts} цикли поспіль завершилися помилкою.'}
                        if telegram(alert):
                            last_system_alert = current
                try:
                    maybe_daily_summary(conn)
                except Exception as exc:
                    emit(type='DAILY_SUMMARY_ERROR', error_type=type(exc).__name__, error=str(exc))
                if args.once:
                    break
                time.sleep(30)
        except KeyboardInterrupt:
            emit(type='STOPPED', time_utc=now())


if __name__ == '__main__':
    main()
