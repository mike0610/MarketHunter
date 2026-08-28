import argparse, csv, hashlib, io, json, math, statistics, urllib.request, zipfile
from pathlib import Path

OBJECT_ID='SL-VAL-BASIS-RV-009'
MONTHS=('2024-01','2024-02','2024-03')
EXPECTED_ROWS=2184
EXPECTED_ALIGNED_SHA='c56883fa67ed2c75d9b441791d08ca26a6c2dd91f3b79ea36100343764fe4585'
EXPECTED_FILES={
('spot','2024-01'):'cf873a185bd5b24b8e00034e49583fcb49928e0c3a45c6fc27a632a683655417',
('perp','2024-01'):'bf673f3d10804a951e8bac56dd2473486f113025971d43ebe5258ec40f9bfeb3',
('spot','2024-02'):'b83aa7319ef1d4baa7b923c0fe802b88dfaf241c7456af295f1f656a24379b33',
('perp','2024-02'):'655ff5ac0fc570956756944c7afef4895c9bd149342f1e437de97292cbd1fe22',
('spot','2024-03'):'b0851daf609d6ab82fdf8f1d1c4fbd974bc1b4e6530a832067516ac1c2be63a6',
('perp','2024-03'):'8138642b757ddf5a42207130277be4569afb4c581a0a1817be9f5f35a4415498'}
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

def checked_zip(url,expected):
    data=fetch(url); chk=fetch(url+'.CHECKSUM').decode('utf-8','replace').strip().split()[0].lower(); actual=hashlib.sha256(data).hexdigest()
    if chk!=actual or actual!=expected: raise ValueError(f'checksum/hash mismatch {url}: provider={chk} actual={actual} expected={expected}')
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
                url=f'{base}/{name}'; data,sha=checked_zip(url,EXPECTED_FILES[(leg,month)]); part=parse_zip(data)
                if set(target)&set(part): raise ValueError(f'cross-file duplicate {leg}')
                target.update(part); files.append({'leg':leg,'month':month,'url':url,'sha256':sha,'rows':len(part)})
    except Exception as e:
        emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),outcomes_opened=False,files=files); return
    ts=sorted(set(spot)&set(perp))
    aligned=[[t,format(spot[t],'.12g'),format(perp[t],'.12g')] for t in ts]
    aligned_sha=hashlib.sha256('\n'.join(','.join(map(str,r)) for r in aligned).encode()).hexdigest()
    gaps=[(ts[i],ts[i+1]) for i in range(len(ts)-1) if ts[i+1]-ts[i]!=3600]
    if len(spot)!=EXPECTED_ROWS or len(perp)!=EXPECTED_ROWS or len(ts)!=EXPECTED_ROWS or gaps or aligned_sha!=EXPECTED_ALIGNED_SHA:
        emit(outdir,'BLOCKED-EVIDENCE',reason='parent-alignment-identity-failed',spot_rows=len(spot),perp_rows=len(perp),aligned_rows=len(ts),gaps=gaps,aligned_price_table_sha256=aligned_sha,expected_aligned_sha256=EXPECTED_ALIGNED_SHA,outcomes_opened=False); return
    basis=[perp[t]/spot[t]-1.0 for t in ts]
    absb=[abs(x) for x in basis]
    thresholds=[None]*len(ts)
    for i in range(LOOKBACK,len(ts)): thresholds[i]=quantile(absb[i-LOOKBACK:i],Q)
    raw=[]
    for i in range(LOOKBACK+1,len(ts)-HORIZON):
        if absb[i]>thresholds[i] and not (absb[i-1]>thresholds[i-1]): raw.append(i)
    events=[]; last=-10**9
    for i in raw:
        if i-last>HORIZON: events.append(i); last=i
    event_set=set(events)
    controls=[]; used=set(); paired=[]
    for i in events:
        sign=1 if basis[i]>=0 else -1; month=ts[i]//(31*24*3600)  # only a coarse pre-outcome partition key; exact calendar month below
        import datetime
        dt=datetime.datetime.fromtimestamp(ts[i],datetime.timezone.utc); trend=1 if spot[ts[i]]>=spot[ts[i-24]] else -1
        cands=[]
        for j in range(LOOKBACK+24,len(ts)-HORIZON):
            if j in event_set or j in used: continue
            dj=datetime.datetime.fromtimestamp(ts[j],datetime.timezone.utc)
            if dj.year!=dt.year or dj.month!=dt.month: continue
            if (1 if basis[j]>=0 else -1)!=sign: continue
            trj=1 if spot[ts[j]]>=spot[ts[j-24]] else -1
            if trj!=trend: continue
            if absb[j]>thresholds[j]: continue
            cands.append((abs(absb[j]-absb[i]),ts[j],j))
        if not cands: continue
        _,_,j=min(cands); used.add(j); controls.append(j)
        ce=absb[i]-absb[i+HORIZON]; cc=absb[j]-absb[j+HORIZON]
        paired.append((i,j,ce,cc,ce-cc))
    if len(paired)<10:
        emit(outdir,'BLOCKED-EVIDENCE',reason='insufficient-deterministic-matched-events',raw_crossings=len(raw),declustered_events=len(events),matched_pairs=len(paired),aligned_price_table_sha256=aligned_sha,outcomes_opened=True); return
    ev_comp=[x[2] for x in paired]; ct_comp=[x[3] for x in paired]; diffs=[x[4] for x in paired]
    ev_win=sum(x>0 for x in ev_comp)/len(ev_comp); ct_win=sum(x>0 for x in ct_comp)/len(ct_comp)
    med_ev=statistics.median(ev_comp); med_ct=statistics.median(ct_comp); med_diff=statistics.median(diffs)
    support=med_ev>0 and med_diff>0 and ev_win>ct_win
    state='BASIS-CONVERGENCE-SUPPORT' if support else 'BASIS-CONVERGENCE-NO-SUPPORT'
    rows=[{'event_ts':ts[i],'control_ts':ts[j],'event_basis':basis[i],'control_basis':basis[j],'event_24h_compression':ce,'control_24h_compression':cc,'paired_diff':d} for i,j,ce,cc,d in paired]
    rows_sha=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    emit(outdir,state,scope='BTCUSDT Spot/USD-M perp 1h Q1-2024 exact BASIS-RV-008 parent',aligned_price_table_sha256=aligned_sha,rule={'tail_threshold':'strictly-prior 168h 95th percentile of |basis|','event':'first crossing above threshold','decluster_hours':24,'primary_horizon_hours':24,'control':'same calendar month, basis sign, prior-24h spot trend sign; non-tail; nearest |basis|; earliest tie; unused','support':'median event compression >0 AND median paired event-control compression >0 AND event convergence fraction > control'},raw_crossings=len(raw),declustered_events=len(events),matched_pairs=len(paired),event_median_24h_compression=med_ev,control_median_24h_compression=med_ct,paired_median_difference=med_diff,event_convergence_fraction=ev_win,control_convergence_fraction=ct_win,paired_rows_sha256=rows_sha,parameter_tuning=False,funding_opened=False,fees_slippage_modeled=False,execution_pnl_claimed=False,outcomes_opened=True,limitations=['price convergence only; not executable arbitrage PnL','no funding, borrow, fees, spread, slippage, latency, or fill model','Q1-2024 single venue/underlying window','tail threshold fixed before outcomes'])

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--job',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    try: validate_job(a.job)
    except Exception as e: emit(a.output,'BLOCKED-EVIDENCE',reason=f'job-contract-validation:{e!r}',outcomes_opened=False)
    else: main(a.output)
