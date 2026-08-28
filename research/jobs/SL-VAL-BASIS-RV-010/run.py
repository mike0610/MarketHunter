import argparse, csv, hashlib, io, json, math, statistics, urllib.request, zipfile, datetime
from pathlib import Path

OBJECT_ID='SL-VAL-BASIS-RV-010'
MONTHS=('2024-04','2024-05','2024-06')
EXPECTED_ROWS=2184
SPOT_BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h'
FUT_BASE='https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h'
LOOKBACK=168
HORIZON=24
Q=0.95


def emit(outdir,state,**extra):
    Path(outdir).mkdir(parents=True,exist_ok=True)
    payload={'object_id':OBJECT_ID,'terminal_state':state,**extra}
    (Path(outdir)/'terminal_result.json').write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def checked_zip(url):
    data=fetch(url)
    provider=fetch(url+'.CHECKSUM').decode('utf-8','replace').strip().split()[0].lower()
    actual=hashlib.sha256(data).hexdigest()
    if provider!=actual: raise ValueError(f'checksum mismatch {url}: provider={provider} actual={actual}')
    return data,actual

def parse_zip(data):
    rows={}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names=[n for n in zf.namelist() if not n.endswith('/')]
        if len(names)!=1: raise ValueError(f'unexpected zip members {names}')
        text=io.TextIOWrapper(zf.open(names[0]),encoding='utf-8')
        for row in csv.reader(text):
            if not row: continue
            try: raw=int(row[0]); close=float(row[4])
            except (ValueError,IndexError): continue
            ts=int(raw/1_000_000 if raw>10**14 else raw/1_000)
            if not math.isfinite(close) or close<=0 or ts in rows: raise ValueError(f'invalid/duplicate row {raw}')
            rows[ts]=close
    return rows

def quantile(xs,q):
    ys=sorted(xs); pos=(len(ys)-1)*q; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)

def validate_job(path):
    j=json.loads(Path(path).read_text(encoding='utf-8'))
    if j.get('object_id')!=OBJECT_ID: raise ValueError('job object_id mismatch')

def main(outdir):
    spot={}; perp={}; files=[]
    try:
        for month in MONTHS:
            name=f'BTCUSDT-1h-{month}.zip'
            for leg,base,target in (('spot',SPOT_BASE,spot),('perp',FUT_BASE,perp)):
                url=f'{base}/{name}'; data,sha=checked_zip(url); part=parse_zip(data)
                if set(target)&set(part): raise ValueError(f'cross-file duplicate {leg}')
                target.update(part); files.append({'leg':leg,'month':month,'url':url,'sha256':sha,'rows':len(part)})
    except Exception as e:
        emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),outcomes_opened=False,files=files); return
    ts=sorted(set(spot)&set(perp))
    aligned=[[t,format(spot[t],'.12g'),format(perp[t],'.12g')] for t in ts]
    aligned_sha=hashlib.sha256('\n'.join(','.join(map(str,r)) for r in aligned).encode()).hexdigest()
    gaps=[(ts[i],ts[i+1]) for i in range(len(ts)-1) if ts[i+1]-ts[i]!=3600]
    if len(spot)!=EXPECTED_ROWS or len(perp)!=EXPECTED_ROWS or len(ts)!=EXPECTED_ROWS or gaps:
        emit(outdir,'BLOCKED-EVIDENCE',reason='q2-alignment-integrity-failed',spot_rows=len(spot),perp_rows=len(perp),aligned_rows=len(ts),gaps=gaps,aligned_price_table_sha256=aligned_sha,outcomes_opened=False,files=files); return
    basis=[perp[t]/spot[t]-1.0 for t in ts]; absb=[abs(x) for x in basis]
    thresholds=[None]*len(ts)
    for i in range(LOOKBACK,len(ts)): thresholds[i]=quantile(absb[i-LOOKBACK:i],Q)
    raw=[]
    for i in range(LOOKBACK+1,len(ts)-HORIZON):
        if absb[i]>thresholds[i] and not (absb[i-1]>thresholds[i-1]): raw.append(i)
    events=[]; last=-10**9
    for i in raw:
        if i-last>HORIZON: events.append(i); last=i
    event_set=set(events); used=set(); paired=[]
    for i in events:
        sign=1 if basis[i]>=0 else -1
        dt=datetime.datetime.fromtimestamp(ts[i],datetime.timezone.utc)
        trend=1 if spot[ts[i]]>=spot[ts[i-24]] else -1
        cands=[]
        for j in range(LOOKBACK+24,len(ts)-HORIZON):
            if j in event_set or j in used: continue
            dj=datetime.datetime.fromtimestamp(ts[j],datetime.timezone.utc)
            if dj.year!=dt.year or dj.month!=dt.month: continue
            if (1 if basis[j]>=0 else -1)!=sign: continue
            if (1 if spot[ts[j]]>=spot[ts[j-24]] else -1)!=trend: continue
            if absb[j]>thresholds[j]: continue
            cands.append((abs(absb[j]-absb[i]),ts[j],j))
        if not cands: continue
        _,_,j=min(cands); used.add(j)
        ce=absb[i]-absb[i+HORIZON]; cc=absb[j]-absb[j+HORIZON]
        paired.append((i,j,ce,cc,ce-cc,sign))
    if len(paired)<10:
        emit(outdir,'BLOCKED-EVIDENCE',reason='insufficient-q2-matched-events',raw_crossings=len(raw),declustered_events=len(events),matched_pairs=len(paired),aligned_price_table_sha256=aligned_sha,outcomes_opened=True,files=files); return
    ev=[x[2] for x in paired]; ct=[x[3] for x in paired]; diffs=[x[4] for x in paired]
    ev_win=sum(x>0 for x in ev)/len(ev); ct_win=sum(x>0 for x in ct)/len(ct)
    med_ev=statistics.median(ev); med_ct=statistics.median(ct); med_diff=statistics.median(diffs)
    sign_stats={}
    sign_ok=True
    for sign,label in ((1,'positive_basis'),(-1,'negative_basis')):
        xs=[x[4] for x in paired if x[5]==sign]
        sign_stats[label]={'n':len(xs),'paired_median_difference':statistics.median(xs) if xs else None}
        if len(xs)>=3 and statistics.median(xs)<0: sign_ok=False
    support=med_ev>0 and med_diff>0 and ev_win>ct_win and sign_ok
    state='BASIS-ROBUSTNESS-SUPPORT' if support else 'BASIS-ROBUSTNESS-FAIL'
    rows=[{'event_ts':ts[i],'control_ts':ts[j],'event_basis':basis[i],'control_basis':basis[j],'event_24h_compression':ce,'control_24h_compression':cc,'paired_diff':d,'basis_sign':sign} for i,j,ce,cc,d,sign in paired]
    rows_sha=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    emit(outdir,state,scope='BTCUSDT Spot/USD-M perp 1h Q2-2024 independent temporal robustness',aligned_price_table_sha256=aligned_sha,source_files=files,rule={'tail_threshold':'strictly-prior 168h 95th percentile of |basis|','event':'first crossing above threshold','decluster_hours':24,'primary_horizon_hours':24,'control':'same calendar month, basis sign, prior-24h spot trend sign; non-tail; nearest |basis|; earliest tie; unused','robustness_support':'Q2 median event compression >0 AND paired median event-control compression >0 AND event convergence fraction > control AND no basis-sign family with n>=3 has negative paired median'},raw_crossings=len(raw),declustered_events=len(events),matched_pairs=len(paired),event_median_24h_compression=med_ev,control_median_24h_compression=med_ct,paired_median_difference=med_diff,event_convergence_fraction=ev_win,control_convergence_fraction=ct_win,sign_stats=sign_stats,paired_rows_sha256=rows_sha,parameter_tuning=False,funding_opened=False,fees_slippage_modeled=False,execution_pnl_claimed=False,execution_feasibility='UNRESOLVED_WITHOUT_FUNDING_SPREAD_FEES_SLIPPAGE_LATENCY_AND_FILL_MODEL',outcomes_opened=True,limitations=['independent Q2-2024 temporal slice but same venue and underlying','price convergence is not executable arbitrage PnL','funding, spreads, fees, slippage, latency, fills and legging risk are unresolved','no parameter rescue after Q1 support'])

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--job',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    try: validate_job(a.job)
    except Exception as e: emit(a.output,'BLOCKED-EVIDENCE',reason=f'job-contract-validation:{e!r}',outcomes_opened=False)
    else: main(a.output)
