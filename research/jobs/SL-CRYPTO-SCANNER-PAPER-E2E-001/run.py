"""SL-CRYPTO-SCANNER-PAPER-E2E-001
Research-only proof: public venue universe -> compatibility -> frozen Quiet-RV
-> risk/evidence gate -> honest current paper action/no-trade -> historical
lifecycle replay -> statistics. No real orders, private endpoints, paid data,
or tuning.
"""
import argparse, hashlib, json, math, time, urllib.request
from pathlib import Path

OBJECT_ID = "SL-CRYPTO-SCANNER-PAPER-E2E-001"
ASSETS = ["BTCUSDT","ETHUSDT","BNBUSDT","ADAUSDT","XRPUSDT","DOGEUSDT","LINKUSDT","LTCUSDT"]
INTERVAL = "4h"
VOL_WIN, VOL_LOOK, VOL_Q = 42, 540, .30
DEV_WIN, DEV_LOOK, DEV_Q = 42, 540, .90
HOLD, DECLUSTER = 6, 6
COST = .001
CAPITAL = 1000.0
MAX_NOTIONAL_FRAC = .10
SOFT_DEADLINE = 18 * 60

def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent":"MarketHunter-Research/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def emit(out, state, **extra):
    p = Path(out); p.mkdir(parents=True, exist_ok=True)
    (p / "terminal_result.json").write_text(json.dumps({"object_id":OBJECT_ID,"terminal_state":state,**extra}, indent=2, sort_keys=True, default=str))

def qtl(values, q):
    s = sorted(values); x = (len(s)-1)*q
    lo, hi = int(math.floor(x)), int(math.ceil(x))
    return s[lo] if lo == hi else s[lo]*(hi-x) + s[hi]*(x-lo)

def stdev(values):
    m = sum(values)/len(values)
    return math.sqrt(sum((x-m)**2 for x in values)/len(values))

def fetch_spot_universe():
    p = get_json("https://api.binance.com/api/v3/exchangeInfo")
    return sorted({x["symbol"] for x in p.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("isSpotTradingAllowed", True)})

def fetch_futures_universe():
    p = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
    return sorted({x["symbol"] for x in p.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("contractType")=="PERPETUAL"})

def fetch_klines(symbol, limit=1000):
    rows = get_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={INTERVAL}&limit={limit}")
    now_ms = int(time.time()*1000); out = {}
    for r in rows:
        if int(r[6]) >= now_ms: continue
        out[int(r[0])//1000] = (float(r[1]), float(r[4]), int(r[6])//1000)
    return out

def frozen_events(common_ts, data):
    n = len(common_ts)
    close = {s:[data[s][t][1] for t in common_ts] for s in ASSETS}
    ret = {s:[None]+[math.log(close[s][i]/close[s][i-1]) for i in range(1,n)] for s in ASSETS}
    market = [None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,n)]
    rv = [None]*n; dev = {s:[None]*n for s in ASSETS}
    for i in range(VOL_WIN+1,n):
        rv[i] = stdev(market[i-VOL_WIN+1:i+1])
        for s in ASSETS:
            dev[s][i] = sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
    events = []; last = -10**9; floor = max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1
    for i in range(floor,n-1):
        if i-last < DECLUSTER: continue
        vh = [x for x in rv[i-VOL_LOOK:i] if x is not None]
        if not vh or rv[i] > qtl(vh,VOL_Q): continue
        dh = [abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None]
        if not dh: continue
        threshold = qtl(dh,DEV_Q); cand = max(ASSETS,key=lambda s:abs(dev[s][i]))
        if abs(dev[cand][i]) <= threshold: continue
        side = "SHORT" if dev[cand][i] > 0 else "LONG"
        e = {"signal_ts":common_ts[i],"asset":cand,"side":side,"signal_index":i}
        if i+1 < n:
            e["entry_ts"] = common_ts[i+1]; e["entry"] = data[cand][common_ts[i+1]][0]
        if i+HOLD < n:
            e["exit_ts"] = common_ts[i+HOLD]; e["exit"] = data[cand][common_ts[i+HOLD]][0]
            gross = e["exit"]/e["entry"]-1 if side=="LONG" else e["entry"]/e["exit"]-1
            e["gross_return"] = gross; e["net_return_10bps"] = gross-COST
        events.append(e); last = i
    return events

def max_drawdown(returns):
    eq = peak = 1.0; dd = 0.0
    for r in returns:
        eq *= 1+r; peak = max(peak,eq); dd = min(dd,eq/peak-1)
    return dd

def main(out, job_path):
    started = time.monotonic()
    try:
        job = json.loads(Path(job_path).read_text())
        if job.get("object_id") != OBJECT_ID: raise ValueError("object id mismatch")
    except Exception as e:
        emit(out,"BLOCKED-TOOLING",reason=f"job-contract:{e!r}"); return
    try:
        spot = fetch_spot_universe(); fut = fetch_futures_universe()
    except Exception as e:
        emit(out,"PROVIDER-BLOCKED",reason=f"universe-discovery:{e!r}",real_orders=False,paid_services=False); return
    coverage = {
        "spot":{"venue":"BINANCE","market":"SPOT","quote":"USDT","tradable_count":len(spot),"symbols_sha256":hashlib.sha256("\n".join(spot).encode()).hexdigest()},
        "futures":{"venue":"BINANCE","market":"USD-M-PERP","quote":"USDT","tradable_count":len(fut),"symbols_sha256":hashlib.sha256("\n".join(fut).encode()).hexdigest()}
    }
    missing_spot = [s for s in ASSETS if s not in spot]; missing_fut = [s for s in ASSETS if s not in fut]
    compatibility = {"Quiet-RV-v1":{"strategy_status":"PAPER-ELIGIBLE/HIGH-DRAWDOWN","spot":{"compatible":not missing_spot,"missing_assets":missing_spot,"reason":"exact frozen 8-asset basket required"},"futures":{"compatible":False,"missing_assets":missing_fut,"reason":"no separate frozen Binance USD-M paper strategy version authorized; price portability does not silently change execution semantics"}}}
    if missing_spot:
        emit(out,"E2E-BLOCKED-EVIDENCE",scan_cycle=coverage,compatibility=compatibility,material_states=[{"state":"INELIGIBLE","book":"SPOT","strategy":"Quiet-RV-v1","reason":"missing frozen basket assets"}],real_orders=False,paid_services=False,parameter_tuning=False); return
    data = {}; errors = {}
    for s in ASSETS:
        if time.monotonic()-started > SOFT_DEADLINE:
            emit(out,"BLOCKED-TOOLING",reason="soft deadline during candle acquisition",scan_cycle=coverage,compatibility=compatibility); return
        try: data[s] = fetch_klines(s)
        except Exception as e: errors[s] = repr(e)
    if errors:
        emit(out,"PROVIDER-BLOCKED",reason="candle-acquisition",errors=errors,scan_cycle=coverage,compatibility=compatibility,real_orders=False,paid_services=False); return
    common = sorted(set.intersection(*[set(data[s]) for s in ASSETS])); required = max(VOL_LOOK,DEV_LOOK)+VOL_WIN+HOLD+2
    evidence = {"common_closed_4h_bars":len(common),"required_minimum":required,"first_ts":common[0] if common else None,"last_ts":common[-1] if common else None,"freshness_seconds":int(time.time())-(common[-1]+4*3600) if common else None,"all_assets_positive":all(all(o>0 and c>0 for o,c,_ in data[s].values()) for s in ASSETS),"source":"Binance public REST exchangeInfo + klines"}
    if len(common) < required or evidence["freshness_seconds"] > 8*3600:
        emit(out,"E2E-BLOCKED-EVIDENCE",scan_cycle=coverage,compatibility=compatibility,evidence=evidence,material_states=[{"state":"DATA-FAIL","book":"SPOT","strategy":"Quiet-RV-v1","reason":"insufficient/stale common closed-bar evidence"}],real_orders=False,paid_services=False,parameter_tuning=False); return
    events = frozen_events(common,data); latest_ts = common[-1]; current = [e for e in events if e["signal_ts"]==latest_ts]
    if current:
        e=current[-1]; paper={"state":"PAPER-ENTRY-QUEUED","reason":"frozen signal present; next-bar-open not yet observed","asset":e["asset"],"side":e["side"],"signal_ts":e["signal_ts"],"max_notional_usdt":round(CAPITAL*MAX_NOTIONAL_FRAC,2),"real_order":False}
    else:
        paper={"state":"NO-SIGNAL","reason":"latest completed common 4h bar does not satisfy frozen Quiet-RV trigger","evaluated_ts":latest_ts,"real_order":False}
    completed = [e for e in events if "net_return_10bps" in e]; replay = None
    if completed:
        e=completed[-1]; notional=CAPITAL*MAX_NOTIONAL_FRAC
        replay={"state":"HISTORICAL-LIFECYCLE-REPLAY","not_current_trade":True,"asset":e["asset"],"side":e["side"],"signal_ts":e["signal_ts"],"entry_ts":e["entry_ts"],"entry":e["entry"],"exit_ts":e["exit_ts"],"exit":e["exit"],"notional_usdt":notional,"net_return_10bps":e["net_return_10bps"],"paper_pnl_usdt":notional*e["net_return_10bps"],"purpose":"prove signal->risk cap->paper entry->exit->statistics plumbing without fabricating a current fill"}
    recent = completed[-50:]
    stats = {"completed_replay_events_in_window":len(completed),"recent_50_or_less_mean_net_10bps":sum(e["net_return_10bps"] for e in recent)/len(recent) if recent else None,"recent_50_or_less_max_drawdown":max_drawdown([e["net_return_10bps"] for e in recent]) if recent else None}
    terminal = "E2E-PASS-CURRENT-PAPER-QUEUED" if current else "E2E-PASS-NO-CURRENT-TRADE"
    emit(out,terminal,scope={"research_only":True,"virtual_capital_usdt":CAPITAL,"real_orders":False,"live_capital":False,"paid_services":False},scan_cycle=coverage,compatibility=compatibility,evidence=evidence,current_market_decision=paper,historical_lifecycle_replay=replay,statistics=stats,state_compaction={"full_universe_coverage_proven_by_counts_and_symbol_hashes":True,"unchanged_per_symbol_NO_SIGNAL_rows_persisted":False,"material_states_persisted_in_terminal_artifact":True},futures_book={"scanned":True,"paper_strategy_evaluated":False,"reason":"no separately frozen compatible strategy version; fail closed rather than reuse Spot semantics"},parameter_tuning=False,limitations=["first bounded E2E proof, not production persistent scanner","Quiet-RV current decision uses latest completed common 4h bar","historical lifecycle replay is explicitly not a current paper position","funding/OI/execution portability not inferred"])

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--job",required=True); p.add_argument("--output",required=True); a=p.parse_args(); main(a.output,a.job)
