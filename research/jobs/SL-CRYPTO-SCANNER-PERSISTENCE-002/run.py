"""SL-CRYPTO-SCANNER-PERSISTENCE-002
Restart/idempotency proof for the bounded crypto scanner/paper E2E lane.
Research only, public data only, virtual capital only, no real orders.
"""
import argparse, hashlib, json, math, sqlite3, time, urllib.request
from pathlib import Path

OBJECT_ID="SL-CRYPTO-SCANNER-PERSISTENCE-002"
ASSETS=["BTCUSDT","ETHUSDT","BNBUSDT","ADAUSDT","XRPUSDT","DOGEUSDT","LINKUSDT","LTCUSDT"]
VOL_WIN,VOL_LOOK,VOL_Q=42,540,.30
DEV_WIN,DEV_LOOK,DEV_Q=42,540,.90
HOLD,DECLUSTER=6,6
COST=.001
CAPITAL=1000.0
NOTIONAL=100.0

def get_json(url,timeout=20):
    req=urllib.request.Request(url,headers={"User-Agent":"MarketHunter-Research/1.0"})
    return json.loads(urllib.request.urlopen(req,timeout=timeout).read())

def emit(out,state,**extra):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/"terminal_result.json").write_text(json.dumps({"object_id":OBJECT_ID,"terminal_state":state,**extra},indent=2,sort_keys=True,default=str))

def qtl(v,q):
    s=sorted(v); x=(len(s)-1)*q; lo,hi=int(math.floor(x)),int(math.ceil(x))
    return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def sd(v):
    m=sum(v)/len(v); return math.sqrt(sum((x-m)**2 for x in v)/len(v))

def spot_universe():
    p=get_json("https://api.binance.com/api/v3/exchangeInfo")
    return sorted({x["symbol"] for x in p.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("isSpotTradingAllowed",True)})

def futures_universe():
    p=get_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
    return sorted({x["symbol"] for x in p.get("symbols",[]) if x.get("status")=="TRADING" and x.get("quoteAsset")=="USDT" and x.get("contractType")=="PERPETUAL"})

def klines(symbol):
    rows=get_json(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=1000")
    now=int(time.time()*1000); out={}
    for r in rows:
        if int(r[6])>=now: continue
        out[int(r[0])//1000]=(float(r[1]),float(r[4]))
    return out

def events(ts,data):
    n=len(ts); close={s:[data[s][t][1] for t in ts] for s in ASSETS}
    ret={s:[None]+[math.log(close[s][i]/close[s][i-1]) for i in range(1,n)] for s in ASSETS}
    market=[None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,n)]
    rv=[None]*n; dev={s:[None]*n for s in ASSETS}
    for i in range(VOL_WIN+1,n):
        rv[i]=sd(market[i-VOL_WIN+1:i+1])
        for s in ASSETS: dev[s][i]=sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
    out=[]; last=-10**9; floor=max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1
    for i in range(floor,n-1):
        if i-last<DECLUSTER: continue
        vh=[x for x in rv[i-VOL_LOOK:i] if x is not None]
        if not vh or rv[i]>qtl(vh,VOL_Q): continue
        dh=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None]
        if not dh: continue
        th=qtl(dh,DEV_Q); a=max(ASSETS,key=lambda s:abs(dev[s][i]))
        if abs(dev[a][i])<=th: continue
        side="SHORT" if dev[a][i]>0 else "LONG"
        e={"signal_ts":ts[i],"asset":a,"side":side}
        if i+1<n: e.update(entry_ts=ts[i+1],entry=data[a][ts[i+1]][0])
        if i+HOLD<n:
            e.update(exit_ts=ts[i+HOLD],exit=data[a][ts[i+HOLD]][0])
            gross=e["exit"]/e["entry"]-1 if side=="LONG" else e["entry"]/e["exit"]-1
            e["net10"]=gross-COST
        out.append(e); last=i
    return out

def schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS scan_cycles(
      cycle_id TEXT PRIMARY KEY, latest_bar_ts INTEGER NOT NULL,
      spot_count INTEGER NOT NULL, futures_count INTEGER NOT NULL,
      spot_hash TEXT NOT NULL, futures_hash TEXT NOT NULL,
      strategy_state TEXT NOT NULL, created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS material_states(
      event_key TEXT PRIMARY KEY, cycle_id TEXT NOT NULL,
      state TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS replay_trades(
      trade_key TEXT PRIMARY KEY, signal_ts INTEGER NOT NULL,
      asset TEXT NOT NULL, side TEXT NOT NULL, entry_ts INTEGER NOT NULL,
      entry REAL NOT NULL, exit_ts INTEGER NOT NULL, exit REAL NOT NULL,
      notional REAL NOT NULL, net10 REAL NOT NULL, pnl REAL NOT NULL,
      classification TEXT NOT NULL
    );
    """)

def apply_cycle(db,cycle_id,latest_ts,spot_count,fut_count,spot_hash,fut_hash,state,reason,payload,replay):
    with sqlite3.connect(db) as c:
        schema(c)
        c.execute("INSERT OR IGNORE INTO scan_cycles VALUES(?,?,?,?,?,?,?,?)",(cycle_id,latest_ts,spot_count,fut_count,spot_hash,fut_hash,state,int(time.time())))
        key=hashlib.sha256((cycle_id+"|"+state+"|Quiet-RV-v1").encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO material_states VALUES(?,?,?,?,?)",(key,cycle_id,state,reason,json.dumps(payload,sort_keys=True)))
        if replay:
            tkey=hashlib.sha256(("Quiet-RV-v1|%s|%s|%s"%(replay["signal_ts"],replay["asset"],replay["side"])).encode()).hexdigest()
            c.execute("INSERT OR IGNORE INTO replay_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(tkey,replay["signal_ts"],replay["asset"],replay["side"],replay["entry_ts"],replay["entry"],replay["exit_ts"],replay["exit"],NOTIONAL,replay["net10"],NOTIONAL*replay["net10"],"HISTORICAL-LIFECYCLE-REPLAY/NOT-CURRENT-TRADE"))
        return tuple(c.execute("SELECT (SELECT count(*) FROM scan_cycles),(SELECT count(*) FROM material_states),(SELECT count(*) FROM replay_trades)").fetchone())

def main(out,job_path):
    try:
        if json.loads(Path(job_path).read_text()).get("object_id")!=OBJECT_ID: raise ValueError("object id mismatch")
    except Exception as e: emit(out,"BLOCKED-TOOLING",reason=repr(e)); return
    try:
        spot=spot_universe(); fut=futures_universe(); data={s:klines(s) for s in ASSETS}
    except Exception as e: emit(out,"PROVIDER-BLOCKED",reason=repr(e),real_orders=False); return
    missing=[s for s in ASSETS if s not in spot]
    if missing: emit(out,"EVIDENCE-BLOCKED",reason="missing frozen basket assets",missing=missing); return
    common=sorted(set.intersection(*[set(data[s]) for s in ASSETS])); required=max(VOL_LOOK,DEV_LOOK)+VOL_WIN+HOLD+2
    if len(common)<required: emit(out,"EVIDENCE-BLOCKED",reason="insufficient common bars",common_bars=len(common),required=required); return
    ev=events(common,data); latest=common[-1]; cur=[e for e in ev if e["signal_ts"]==latest]
    if cur:
        e=cur[-1]; state="PAPER-ENTRY-QUEUED"; reason="frozen signal on latest completed bar; next open unobserved"; payload={"asset":e["asset"],"side":e["side"],"signal_ts":e["signal_ts"],"max_notional_usdt":NOTIONAL,"real_order":False}
    else:
        state="NO-SIGNAL"; reason="latest completed common 4h bar does not satisfy frozen Quiet-RV"; payload={"evaluated_ts":latest,"real_order":False}
    done=[e for e in ev if "net10" in e]; replay=done[-1] if done else None
    sh=hashlib.sha256("\n".join(spot).encode()).hexdigest(); fh=hashlib.sha256("\n".join(fut).encode()).hexdigest()
    cycle_id=hashlib.sha256(("BINANCE|SPOT|USD-M-PERP|Quiet-RV-v1|%s|%s|%s"%(latest,sh,fh)).encode()).hexdigest()
    p=Path(out); p.mkdir(parents=True,exist_ok=True); db=p/"scanner_persistence.sqlite"
    first=apply_cycle(db,cycle_id,latest,len(spot),len(fut),sh,fh,state,reason,payload,replay)
    # Simulated restart: independent connection, exact same deterministic cycle.
    second=apply_cycle(db,cycle_id,latest,len(spot),len(fut),sh,fh,state,reason,payload,replay)
    with sqlite3.connect(db) as c:
        schema(c); persisted=c.execute("SELECT cycle_id,strategy_state FROM scan_cycles").fetchall(); m=c.execute("SELECT state,reason FROM material_states").fetchall(); trades=c.execute("SELECT asset,side,pnl,classification FROM replay_trades").fetchall()
    ok=first==second and len(persisted)==1 and len(m)==1 and len(trades)<=1
    emit(out,"PERSISTENCE-PASS" if ok else "PERSISTENCE-FAIL",
         restart_idempotent=first==second,counts_after_first={"scan_cycles":first[0],"material_states":first[1],"replay_trades":first[2]},counts_after_restart={"scan_cycles":second[0],"material_states":second[1],"replay_trades":second[2]},
         current_state={"state":state,"reason":reason,"payload":payload},universe={"spot_trading_usdt":len(spot),"futures_trading_usdt_perpetual":len(fut),"spot_hash":sh,"futures_hash":fh},common_closed_4h_bars=len(common),
         historical_replay=None if replay is None else {"asset":replay["asset"],"side":replay["side"],"signal_ts":replay["signal_ts"],"entry_ts":replay["entry_ts"],"exit_ts":replay["exit_ts"],"net10":replay["net10"],"pnl_usdt":NOTIONAL*replay["net10"],"classification":"HISTORICAL-LIFECYCLE-REPLAY/NOT-CURRENT-TRADE"},
         sqlite_artifact="scanner_persistence.sqlite",compaction={"per_symbol_unchanged_no_signal_rows":0,"strategy_level_material_state_rows":len(m)},real_orders=False,live_capital=False,paid_services=False,parameter_tuning=False,
         limitations=["research harness persistence proof, not deployed scheduler","current signal is never retro-filled","Futures universe is persisted separately but no Spot strategy semantics are silently reused for Futures"])

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--job",required=True); p.add_argument("--output",required=True); a=p.parse_args(); main(a.output,a.job)
