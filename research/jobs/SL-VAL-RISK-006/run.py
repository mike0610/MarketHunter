import json, math, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-RISK-006"
START_MS = 1546300800000  # 2019-01-01 UTC
END_MS = 1767225600000    # 2026-01-01 UTC exclusive
ENTER_DD = 0.20
RELEASE_DD = 0.10
REDUCED_M = 0.5
STATIC_M = 0.67260  # pre-authorized discovery-only mean exposure

def emit(outdir, state, payload):
    p = Path(outdir); p.mkdir(parents=True, exist_ok=True)
    result = {"object_id": OBJECT_ID, "terminal_state": state, "generated_at_utc": datetime.now(timezone.utc).isoformat(), **payload}
    (p / "terminal_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

def fetch_klines():
    rows=[]; cur=START_MS
    while cur < END_MS:
        q=urllib.parse.urlencode({"symbol":"BTCUSDT","interval":"1d","startTime":cur,"endTime":END_MS-1,"limit":1000})
        url="https://data-api.binance.vision/api/v3/klines?"+q
        with urllib.request.urlopen(url, timeout=20) as r:
            batch=json.loads(r.read().decode())
        if not batch: break
        rows.extend(batch)
        nxt=int(batch[-1][0])+86400000
        if nxt<=cur: raise RuntimeError("non-advancing provider cursor")
        cur=nxt
    return rows

def maxdd(eq):
    peak=eq[0]; m=0.0
    for x in eq:
        peak=max(peak,x); m=min(m,x/peak-1.0)
    return m

def recovery_date(dates, eq):
    peak=eq[0]; peak_i=0; worst=0.0; worst_peak_i=0
    for i,x in enumerate(eq):
        if x>peak: peak=x; peak_i=i
        dd=x/peak-1
        if dd<worst: worst=dd; worst_peak_i=peak_i
    target=eq[worst_peak_i]
    for i in range(worst_peak_i+1,len(eq)):
        if eq[i]>=target: return dates[i]
    return None

def main(outdir):
    try: rows=fetch_klines()
    except Exception as e:
        emit(outdir,"BLOCKED-PROVIDER",{"reason":repr(e)}); return
    opens=[int(r[0]) for r in rows]
    if len(rows)!=2557 or len(set(opens))!=len(opens) or any(b-a!=86400000 for a,b in zip(opens,opens[1:])):
        emit(outdir,"DATA-INTEGRITY-FAIL",{"row_count":len(rows),"first_open":opens[0] if opens else None,"last_open":opens[-1] if opens else None}); return
    closes=[float(r[4]) for r in rows]
    dates=[datetime.fromtimestamp(t/1000,timezone.utc).date().isoformat() for t in opens]
    # Controller state for return on day i uses equity known through i-1.
    eq_b=[1.0]; states=[]; state="NORMAL"; peak=1.0
    logrets=[None]+[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    for i in range(1,len(closes)):
        prior_eq=eq_b[-1]; peak=max(peak,prior_eq); dd=1-prior_eq/peak
        if state=="NORMAL" and dd>=ENTER_DD: state="REDUCED"
        elif state=="REDUCED" and dd<=RELEASE_DD: state="NORMAL"
        m=REDUCED_M if state=="REDUCED" else 1.0
        states.append(state); eq_b.append(prior_eq*math.exp(m*logrets[i]))
    # locked slice begins 2022-01-01; normalize all arms there.
    s=dates.index("2022-01-01")
    ld=dates[s:]
    raw_lr=logrets[s+1:]
    locked_states=states[s:]  # state attached to return from date s to s+1 onward
    def path(mult_fn):
        e=[1.0]
        for j,lr in enumerate(raw_lr): e.append(e[-1]*math.exp(mult_fn(j)*lr))
        return e
    a=path(lambda j:1.0)
    b=path(lambda j: REDUCED_M if locked_states[j]=="REDUCED" else 1.0)
    c=path(lambda j:STATIC_M)
    metrics={}
    for name,e in (("A",a),("B",b),("C",c)):
        metrics[name]={"terminal_return":e[-1]-1,"max_drawdown":maxdd(e),"recovery_date":recovery_date(ld,e)}
    # Timing value requires B to dominate static C on drawdown at comparable exposure without worse terminal return.
    timing_pass = metrics["B"]["max_drawdown"] > metrics["C"]["max_drawdown"] and metrics["B"]["terminal_return"] >= metrics["C"]["terminal_return"]
    state="EXPOSURE-MATCHED-TIMING-VALUE-PASS" if timing_pass else "EXPOSURE-MATCHED-TIMING-VALUE-FAIL"
    emit(outdir,state,{"contract":{"enter_dd":ENTER_DD,"release_dd":RELEASE_DD,"reduced_m":REDUCED_M,"static_m":STATIC_M,"locked":"2022-01-01..2025-12-31"},"row_count":len(rows),"metrics":metrics,"decision_rule":"PASS only if dynamic B has shallower max DD than static C and terminal return >= C; otherwise FAIL"})

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else ".")
