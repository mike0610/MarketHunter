import argparse, csv, hashlib, io, json, math, urllib.error, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-BREAKER-ZONE-SL-001"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TF = "1d"
WARM = datetime(2020, 1, 1, tzinfo=timezone.utc)
START = datetime(2021, 1, 1, tzinfo=timezone.utc)
SPLIT = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 1, tzinfo=timezone.utc)
BUFFERS = [0.0, 0.25, 0.5]
HOLD = 12
COST = 0.001
SWING = 3
LOOKBACK = 180


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "terminal_result.json").write_text(json.dumps({"object_id": OBJECT_ID, "terminal_state": state, **payload}, indent=2, sort_keys=True))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MarketHunter-Research/1.0"})
    return urllib.request.urlopen(req, timeout=30).read()


def month(symbol, year, month_num):
    name = f"{symbol}-{TF}-{year}-{month_num:02d}.zip"
    url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{TF}/{name}"
    raw = get(url)
    expected = get(url + ".CHECKSUM").decode().split()[0].lower()
    actual = hashlib.sha256(raw).hexdigest()
    if expected != actual:
        raise ValueError("checksum " + name)
    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        fn = [x for x in z.namelist() if not x.endswith("/")][0]
        for x in csv.reader(io.TextIOWrapper(z.open(fn))):
            try:
                t = int(x[0]); o, h, l, c = map(float, x[1:5])
            except Exception:
                continue
            sec = t / 1e6 if t > 10**14 else t / 1e3
            rows.append({"ts": int(sec), "o": o, "h": h, "l": l, "c": c})
    return rows, {"url": url, "sha256": actual, "rows": len(rows)}


def atr14(rows, i):
    if i < 14:
        return None
    vals = []
    for j in range(i - 13, i + 1):
        prev = rows[j - 1]["c"]
        vals.append(max(rows[j]["h"] - rows[j]["l"], abs(rows[j]["h"] - prev), abs(rows[j]["l"] - prev)))
    return sum(vals) / len(vals)


def swing_low(rows, i):
    if i < SWING or i + SWING >= len(rows): return False
    v = rows[i]["l"]
    return all(v < rows[j]["l"] for j in range(i-SWING, i)) and all(v <= rows[j]["l"] for j in range(i+1, i+SWING+1))


def swing_high(rows, i):
    if i < SWING or i + SWING >= len(rows): return False
    v = rows[i]["h"]
    return all(v > rows[j]["h"] for j in range(i-SWING, i)) and all(v >= rows[j]["h"] for j in range(i+1, i+SWING+1))


def zones(rows, i):
    lo = max(SWING, i - LOOKBACK)
    confirmed_end = i - SWING
    lows = [rows[j]["l"] for j in range(lo, confirmed_end + 1) if swing_low(rows, j)]
    highs = [rows[j]["h"] for j in range(lo, confirmed_end + 1) if swing_high(rows, j)]
    return (lows[-1] if lows else None, highs[-1] if highs else None)


def max_dd(returns):
    eq = peak = 1.0; dd = 0.0
    for r in returns:
        eq *= 1 + r; peak = max(peak, eq); dd = min(dd, eq / peak - 1)
    return dd


def stats(events, buffer):
    x = [e[buffer] for e in events]
    if not x: return {"n": 0}
    rets = [e["ret"] for e in x]
    losses = [r for r in rets if r < 0]
    stopped = [e for e in x if e["exit"] == "STOP"]
    recovered = [e for e in stopped if e["recovered"]]
    eq = 1.0
    for r in rets: eq *= 1 + r
    return {
        "n": len(x),
        "stop_out_rate": len(stopped) / len(x),
        "mean_loss": sum(losses) / len(losses) if losses else None,
        "stopped_then_recovered_rate": len(recovered) / len(stopped) if stopped else None,
        "max_drawdown": max_dd(rets),
        "final_return": eq - 1,
        "mean_return": sum(rets) / len(rets),
    }


def evaluate(symbol):
    rows=[]; sources=[]
    for y in range(2020, 2027):
        for m in range(1, 13):
            d=datetime(y,m,1,tzinfo=timezone.utc)
            if d < WARM or d >= END: continue
            try: a,b=month(symbol,y,m)
            except urllib.error.HTTPError as e:
                if e.code == 404: continue
                raise
            rows += a; sources.append(b)
    rows.sort(key=lambda r:r["ts"])
    events=[]
    for i in range(max(LOOKBACK,15), len(rows)-HOLD-1):
        if rows[i]["ts"] < int(START.timestamp()) or rows[i]["ts"] >= int(END.timestamp()): continue
        a=atr14(rows,i)
        if not a: continue
        support,resistance=zones(rows,i)
        side=None; low=high=None
        # Frozen causal proxy for a breaker-zone retest: current close sits within one ATR-wide zone around the latest confirmed swing boundary.
        if support is not None and support <= rows[i]["c"] <= support+a:
            side="LONG"; low=support; high=support+a
        elif resistance is not None and resistance-a <= rows[i]["c"] <= resistance:
            side="SHORT"; low=resistance-a; high=resistance
        if side is None: continue
        entry=rows[i+1]["o"]
        variants={}
        for b in BUFFERS:
            stop=(low-b*a) if side=="LONG" else (high+b*a)
            exitp=rows[i+HOLD]["c"]; reason="HOLD"; stop_idx=None
            for j in range(i+1,i+HOLD+1):
                hit=rows[j]["l"] <= stop if side=="LONG" else rows[j]["h"] >= stop
                if hit:
                    exitp=stop; reason="STOP"; stop_idx=j; break
            gross=exitp/entry-1 if side=="LONG" else entry/exitp-1
            recovered=False
            if stop_idx is not None:
                future=rows[stop_idx+1:i+HOLD+1]
                recovered=any((r["h"] > entry if side=="LONG" else r["l"] < entry) for r in future)
            variants[str(b)]={"ret":gross-COST,"exit":reason,"recovered":recovered}
        events.append({"ts":rows[i]["ts"],"side":side,"period":"IS" if rows[i]["ts"] < int(SPLIT.timestamp()) else "OOS",**variants})
    oos=[e for e in events if e["period"]=="OOS"]
    return {"symbol":symbol,"event_count":len(events),"oos_event_count":len(oos),"oos":{str(b):stats(oos,str(b)) for b in BUFFERS},"source_files":sources}


def main(out, job):
    try:
        cfg=json.loads(Path(job).read_text())
        if cfg.get("object_id") != OBJECT_ID: raise ValueError("object")
        results=[evaluate(s) for s in SYMBOLS]
    except Exception as e:
        emit(out,"PROVIDER-BLOCKED",reason=repr(e),parameter_tuning=False); return
    total=sum(r["oos_event_count"] for r in results)
    emit(out,"OUTCOME-COMPLETE",contract={"symbols":SYMBOLS,"tf":TF,"buffers_atr":BUFFERS,"hold_bars":HOLD,"cost":COST,"split":"2025-01-01","same_entries_across_variants":True,"parameter_tuning":False},per_symbol=results,evidence_gate={"oos_events":total,"sufficient_for_comparison":total>=30},terminal_verdict="COMPARISON-AVAILABLE" if total>=30 else "BLOCKED-EVIDENCE",limitations=["research runner uses a frozen causal swing-zone proxy rather than importing production BreakerDetector","spot daily history only","no partial exits","no parameter tuning"],parameter_tuning=False)

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--job",required=True); p.add_argument("--output",required=True); q=p.parse_args(); main(q.output,q.job)
