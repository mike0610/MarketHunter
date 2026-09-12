import argparse, csv, hashlib, io, json, math, urllib.request, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

OBJECT_ID='SL-VAL-MOM-003M-OOS-EXEC-001'
SYMBOL='BTCUSDT'; INTERVAL='1d'
START=datetime(2026,1,5,tzinfo=timezone.utc)
END=datetime(2026,8,24,tzinfo=timezone.utc)
FORMATION_DAYS=84
COST_MULT=0.998
MONTHS=[(2025,10),(2025,11),(2025,12),(2026,1),(2026,2),(2026,3),(2026,4),(2026,5),(2026,6),(2026,7),(2026,8)]
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/'

def emit(out,state,**payload):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))

def fetch_zip(y,m):
    name=f'{SYMBOL}-{INTERVAL}-{y:04d}-{m:02d}.zip'
    req=urllib.request.Request(BASE+name,headers={'User-Agent':'MarketHunter-Research/1.0'})
    with urllib.request.urlopen(req,timeout=25) as r:
        raw=r.read()
    return name,raw

def parse_zip(raw):
    rows=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=1: raise ValueError('unexpected archive members')
        text=z.read(names[0]).decode('utf-8')
    for row in csv.reader(io.StringIO(text)):
        if not row: continue
        ts=int(row[0]);
        # Binance historical archives may encode open time in ms or us depending on era.
        if ts>10**14: ts//=1000
        dt=datetime.fromtimestamp(ts/1000,tz=timezone.utc)
        rows.append((dt,float(row[1])))
    return rows

def compound(rs):
    x=1.0
    for r in rs: x*=1.0+r
    return x-1.0

def max_dd(equity):
    peak=equity[0]; m=0.0
    for x in equity:
        peak=max(peak,x); m=min(m,x/peak-1.0)
    return m

def main(out,job):
    try:
        cfg=json.loads(Path(job).read_text())
        assert cfg['object_id']==OBJECT_ID and cfg['executor']=='vps'
        opens={}; archives=[]
        for y,m in MONTHS:
            name,raw=fetch_zip(y,m)
            sha=hashlib.sha256(raw).hexdigest(); parsed=parse_zip(raw)
            archives.append({'file':name,'sha256':sha,'rows':len(parsed)})
            for dt,op in parsed:
                if dt in opens: raise ValueError(f'duplicate open time {dt.isoformat()}')
                opens[dt]=op
        dates=sorted(opens)
        if not dates: return emit(out,'BLOCKED-EVIDENCE',reason='no Binance rows acquired')
        # Integrity over the exact required calendar span: daily UTC rows, unique and monotonic.
        need_start=datetime(2025,10,1,tzinfo=timezone.utc); need_end=datetime(2026,8,31,tzinfo=timezone.utc)
        d=need_start; missing=[]
        while d<=need_end:
            if d not in opens: missing.append(d.isoformat())
            d+=timedelta(days=1)
        if missing:
            return emit(out,'BLOCKED-EVIDENCE',reason='missing daily Binance rows in required span',missing=missing[:20],missing_count=len(missing),archives=archives)
        mondays=[]; t=START
        while t<=END:
            mondays.append(t); t+=timedelta(days=7)
        if len(mondays)!=34:
            return emit(out,'BLOCKED-EVIDENCE',reason='unexpected Monday boundary count',count=len(mondays))
        weekly=[]
        for a,b in zip(mondays[:-1],mondays[1:]):
            lag=a-timedelta(days=FORMATION_DAYS)
            if a not in opens or b not in opens or lag not in opens:
                return emit(out,'BLOCKED-EVIDENCE',reason='required boundary missing',a=a.isoformat(),b=b.isoformat(),lag=lag.isoformat())
            formation=opens[a]/opens[lag]-1.0
            is_long=formation>0
            ret=(opens[b]/opens[a]-1.0) if is_long else 0.0
            weekly.append({'start':a.isoformat(),'end':b.isoformat(),'formation_return':formation,'long':is_long,'gross_return':ret})
        # Group contiguous LONG intervals into completed episodes and apply one frozen 20bp round-trip cost per episode.
        episodes=[]; cur=[]
        for w in weekly:
            if w['long']:
                cur.append(w)
            elif cur:
                gross=compound([x['gross_return'] for x in cur]); net=(1.0+gross)*COST_MULT-1.0
                episodes.append({'start':cur[0]['start'],'end':cur[-1]['end'],'weeks':len(cur),'gross_return':gross,'stressed_return':net}); cur=[]
        if cur:
            gross=compound([x['gross_return'] for x in cur]); net=(1.0+gross)*COST_MULT-1.0
            episodes.append({'start':cur[0]['start'],'end':cur[-1]['end'],'weeks':len(cur),'gross_return':gross,'stressed_return':net})
        stressed=[e['stressed_return'] for e in episodes]
        aggregate=compound(stressed) if stressed else 0.0
        positive=sum(r>0 for r in stressed)
        leave_best=None
        if len(stressed)>=2:
            best=max(range(len(stressed)),key=lambda i:stressed[i]); leave_best=compound([r for i,r in enumerate(stressed) if i!=best])
        # Predeclared breadth criterion targets the earlier single-episode concentration failure.
        if len(stressed)<3:
            state='INSUFFICIENT-EPISODES'
        elif positive>=2 and leave_best is not None and leave_best>0 and aggregate>0:
            state='OOS-BREADTH-SUPPORT'
        else:
            state='OOS-BREADTH-NOT-SUPPORT'
        eq=[1.0]; i=0
        while i<len(weekly):
            if not weekly[i]['long']:
                eq.append(eq[-1]); i+=1; continue
            j=i; rs=[]
            while j<len(weekly) and weekly[j]['long']:
                rs.append(weekly[j]['gross_return']); j+=1
            ep=(1.0+compound(rs))*COST_MULT
            eq.append(eq[-1]*ep)
            for _ in range(i+1,j): eq.append(eq[-1])
            i=j
        passive=opens[END]/opens[START]-1.0
        evidence={'contract':{'oos_scored_window':'2026-01-05T00:00:00Z to 2026-08-24T00:00:00Z','completed_weekly_intervals':33,'signal':'LONG iff prior 84-calendar-day / 12-complete-week formation return > 0, else FLAT','execution':'Monday 00:00 UTC daily open','cost':'0.998 multiplier once per completed contiguous LONG episode','no_short':True,'no_parameter_tuning':True,'breadth_gate':'support only if >=3 completed LONG episodes, >=2 positive stressed episodes, stressed aggregate >0, and leave-best-episode-out compound >0'},'provider':'Binance official data archive data.binance.vision','archives':archives,'daily_first':dates[0].isoformat(),'daily_last':dates[-1].isoformat(),'weekly':weekly,'episodes':episodes,'completed_long_episodes':len(episodes),'positive_stressed_episodes':positive,'stressed_aggregate_return':aggregate,'leave_best_episode_out_return':leave_best,'strategy_max_drawdown_episode_path':max_dd(eq),'passive_btc_return_same_window':passive}
        p=Path(out); p.mkdir(parents=True,exist_ok=True); eraw=json.dumps(evidence,indent=2,sort_keys=True); (p/'oos_evidence.json').write_text(eraw)
        emit(out,state,reason='frozen untouched post-2025 BTCUSDT OOS executed from official Binance archives',evidence_file='oos_evidence.json',evidence_sha256=hashlib.sha256(eraw.encode()).hexdigest(),**evidence)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'provider/data/execution failure: {e!r}',contract_frozen=True,no_parameter_tuning=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
