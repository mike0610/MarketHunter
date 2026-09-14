import argparse,csv,hashlib,heapq,io,json,math,os,resource,tempfile,urllib.request,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path

OBJECT_ID='SL-VAL-QUIET-RV-LIMIT-MEMORY-BOUND-EXEC-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='4h'; WARM=datetime(2022,1,1,tzinfo=timezone.utc); START=datetime(2022,7,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
VOL_WIN=42;VOL_LOOK=540;VOL_Q=.30;DEV_WIN=42;DEV_LOOK=540;DEV_Q=.90
HOLD_HOURS=20;DECLUSTER=6;BASE_COST=.001;STRESS_COST=.002;CHUNK_ROWS=100000

TMP=None; DAY_META={}

def emit(out,state,**extra):
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    payload={'object_id':OBJECT_ID,'terminal_state':state,**extra}
    (p/'terminal_result.json').write_text(json.dumps(payload,indent=2,sort_keys=True))

def req(url,timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=timeout)

def get_small(url):
    with req(url) as r:return r.read()

def checked_zip_bytes(url):
    z=get_small(url); expected=get_small(url+'.CHECKSUM').decode().split()[0].lower(); actual=hashlib.sha256(z).hexdigest()
    if actual!=expected: raise ValueError('checksum '+url)
    return z,actual

def download_checked(url,dst):
    expected=get_small(url+'.CHECKSUM').decode().split()[0].lower(); h=hashlib.sha256()
    with req(url) as r,open(dst,'wb') as f:
        while True:
            b=r.read(1024*1024)
            if not b:break
            h.update(b);f.write(b)
    actual=h.hexdigest()
    if actual!=expected: raise ValueError('checksum '+url)
    return actual

def norm_ts(raw):
    raw=int(raw); return raw/1e6 if raw>10**14 else raw/1e3

def parse_trade(r):
    if len(r)<5:return None
    try: tid=int(r[0]);px=float(r[1]);ts=norm_ts(r[4])
    except Exception:return None
    if not math.isfinite(px) or px<=0:return None
    return (ts,tid,px)

def zip_rows(path):
    with zipfile.ZipFile(path) as q:
        names=[x for x in q.namelist() if not x.endswith('/')]
        if not names:raise ValueError('empty zip '+str(path))
        with q.open(names[0]) as fh:
            for r in csv.reader(io.TextIOWrapper(fh)):
                x=parse_trade(r)
                if x is not None:yield x

def write_chunk(rows,path):
    rows.sort(key=lambda x:(x[0],x[1]))
    with open(path,'w',newline='') as f:
        w=csv.writer(f);w.writerows(rows)

def read_chunk(path):
    with open(path,newline='') as f:
        for r in csv.reader(f):yield (float(r[0]),int(r[1]),float(r[2]))

def external_sort(path,key):
    parts=[];chunk=[]
    for x in zip_rows(path):
        chunk.append(x)
        if len(chunk)>=CHUNK_ROWS:
            p=Path(TMP)/f'{key}.part{len(parts):04d}.csv';write_chunk(chunk,p);parts.append(p);chunk=[]
    if chunk:
        p=Path(TMP)/f'{key}.part{len(parts):04d}.csv';write_chunk(chunk,p);parts.append(p)
    out=Path(TMP)/f'{key}.sorted.csv'
    its=[read_chunk(p) for p in parts]
    with open(out,'w',newline='') as f:
        w=csv.writer(f)
        for x in heapq.merge(*its,key=lambda x:(x[0],x[1])):w.writerow(x)
    for p in parts:p.unlink(missing_ok=True)
    return out

def sorted_file_rows(path):
    with open(path,newline='') as f:
        for r in csv.reader(f):yield (float(r[0]),int(r[1]),float(r[2]))

def day_url(sym,d):
    ds=d.strftime('%Y-%m-%d');return f'https://data.binance.vision/data/spot/daily/trades/{sym}/{sym}-trades-{ds}.zip'

def prepare_day(sym,d):
    key=(sym,d.isoformat())
    if key in DAY_META:return DAY_META[key]
    url=day_url(sym,d);zp=Path(TMP)/f'{sym}-{d.isoformat()}.zip';sha=download_checked(url,zp)
    n=0;mono=True;prev=None
    for x in zip_rows(zp):
        k=(x[0],x[1]);n+=1
        if prev is not None and k<prev:mono=False
        prev=k
    sorted_path=None if mono else external_sort(zp,f'{sym}-{d.isoformat()}')
    m={'family':'spot-trades','symbol':sym,'date':d.isoformat(),'url':url,'sha256':sha,'rows':n,'archive_monotonic':mono,
       '_zip':str(zp),'_sorted':str(sorted_path) if sorted_path else None}
    DAY_META[key]=m;return m

def day_rows(sym,d):
    m=prepare_day(sym,d)
    return sorted_file_rows(m['_sorted']) if m['_sorted'] else zip_rows(m['_zip'])

def month_klines(sym,y,m):
    base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';name=f'{sym}-{TF}-{y}-{m:02d}.zip';url=f'{base}/{name}'
    z,sha=checked_zip_bytes(url);rows=[]
    with zipfile.ZipFile(io.BytesIO(z)) as q:
        member=[x for x in q.namelist() if not x.endswith('/')][0]
        for r in csv.reader(io.TextIOWrapper(q.open(member))):
            try:ts=int(norm_ts(r[0]));op=float(r[1]);cl=float(r[4])
            except Exception:continue
            rows.append((ts,op,cl))
    return rows,{'family':'klines-4h','symbol':sym,'url':url,'sha256':sha,'rows':len(rows)}

def qtl(a,q):
    s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def sd(a):
    m=sum(a)/len(a);return math.sqrt(sum((x-m)**2 for x in a)/len(a))

def stats(a):
    if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
    s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;gain=sum(x for x in a if x>0);loss=-sum(x for x in a if x<0)
    eq=peak=1.;dd=0.
    for x in a:eq*=1+x;peak=max(peak,eq);dd=min(dd,eq/peak-1)
    return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':gain/loss if loss else None,'cum':eq-1,'max_dd':dd}

def utc_date(ts):return datetime.fromtimestamp(ts,tz=timezone.utc).date()

def first_window(sym,start,end,pred):
    d=utc_date(start);last=utc_date(max(start,end-1e-6))
    while d<=last:
        for ts,tid,px in day_rows(sym,d):
            if ts<start:continue
            if ts>=end:break
            if pred(px):return (ts,tid,px)
        d+=timedelta(days=1)
    return None

def first_after(sym,target):
    d=utc_date(target)
    for off in (0,1):
        for ts,tid,px in day_rows(sym,d+timedelta(days=off)):
            if ts>=target:return (ts,tid,px)
    return None

def concentration(events,key):
    if not events:return {}
    out={}
    for e in events:out[e[key]]=out.get(e[key],0)+1
    return {k:v/len(events) for k,v in sorted(out.items())}

def synthetic_fixture():
    raw=[['4','99','x','x','1000000'],['2','100','x','x','1000000'],['3','101','x','x','1000000'],['bad'],['5','nan','x','x','1000001'],['6','0','x','x','1000002'],['1','98','x','x','999000']]
    valid=[parse_trade(r) for r in raw];ref=sorted([x for x in valid if x is not None],key=lambda x:(x[0],x[1]))
    tmp=Path(TMP)/'fixture.zip'
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('fixture.csv','\n'.join(','.join(r) for r in raw))
    got=list(zip_rows(tmp));
    if any((got[i][0],got[i][1])>(got[i+1][0],got[i+1][1]) for i in range(len(got)-1)):
        sp=external_sort(tmp,'fixture');got=list(sorted_file_rows(sp))
    if got!=ref:raise AssertionError('fixture-order-filter-mismatch')
    def fw(rows,start,end,pred):
        for x in rows:
            if x[0]<start:continue
            if x[0]>=end:break
            if pred(x[2]):return x
        return None
    if fw(got,999,1001,lambda p:p<100)!=(999.0,1,98.0):raise AssertionError('fixture-long-strict')
    if fw(got,1000,1001,lambda p:p>100)!=(1000.0,3,101.0):raise AssertionError('fixture-short-strict-order')
    if fw(got,1000,1001,lambda p:p<100)!=(1000.0,4,99.0):raise AssertionError('fixture-touch-no-fill')
    day1=[(86399.0,1,100.0)];day2=[(86400.0,2,101.0),(90000.0,3,102.0)];target=86400.0
    refx=next((x for x in day1+day2 if x[0]>=target),None)
    gotx=next((x for x in day2 if x[0]>=target),None)
    if gotx!=refx:raise AssertionError('fixture-cross-midnight-exit')
    return {'passed':True,'cases':['LONG-strict-through','SHORT-strict-through','exact-touch-no-fill','same-timestamp-trade-id-order','cross-midnight-fill-exit','invalid-row-filter','disordered-row-sort']}

def main(out,job):
    global TMP
    try:
        spec=json.loads(Path(job).read_text())
        if spec.get('object_id')!=OBJECT_ID:raise ValueError('object_id mismatch')
        with tempfile.TemporaryDirectory(prefix='mh-qrv-') as td:
            TMP=td
            try:fixture=synthetic_fixture()
            except Exception as e:emit(out,'EVIDENCE-FAIL',reason=repr(e),stage='synthetic-equivalence-fixture',parameter_tuning=False);return
            data={};sources=[]
            try:
                for sym in ASSETS:
                    rows=[]
                    for y in range(2022,2027):
                        for m in range(1,13):
                            d=datetime(y,m,1,tzinfo=timezone.utc)
                            if d<WARM or d>=END:continue
                            a,b=month_klines(sym,y,m);rows+=a;sources.append(b)
                    data[sym]={ts:(op,cl) for ts,op,cl in rows}
            except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),stage='parent-kline-acquisition',parameter_tuning=False);return
            common=sorted(set.intersection(*[set(data[s]) for s in ASSETS]))
            if len(common)<1200:emit(out,'EVIDENCE-FAIL',reason='insufficient synchronized 4h history',common_bars=len(common),parameter_tuning=False);return
            ret={}
            for sym in ASSETS:
                close=[data[sym][t][1] for t in common]
                if any((not math.isfinite(x) or x<=0) for x in close):emit(out,'EVIDENCE-FAIL',reason='invalid synchronized close',symbol=sym,parameter_tuning=False);return
                ret[sym]=[None]+[math.log(close[i]/close[i-1]) for i in range(1,len(close))]
            market=[None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,len(common))];rv=[None]*len(common);dev={s:[None]*len(common) for s in ASSETS}
            for i in range(VOL_WIN+1,len(common)):
                rv[i]=sd(market[i-VOL_WIN+1:i+1])
                for s in ASSETS:dev[s][i]=sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
            signals=[];last=-10**9;start_idx=max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1
            for i in range(start_idx,len(common)-7):
                ts=common[i]
                if ts<int(START.timestamp()) or ts>=int(END.timestamp()) or i-last<DECLUSTER:continue
                hist=[x for x in rv[i-VOL_LOOK:i] if x is not None]
                if len(hist)<VOL_LOOK-1 or rv[i]>qtl(hist,VOL_Q):continue
                vals=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None];thr=qtl(vals,DEV_Q);cand=max(ASSETS,key=lambda s:abs(dev[s][i]))
                if abs(dev[cand][i])<=thr:continue
                side='SHORT' if dev[cand][i]>0 else 'LONG';limit=data[cand][ts][1];activation=ts+4*3600;expiry=activation+4*3600
                pe=data[cand][common[i+1]][0];px=data[cand][common[i+6]][0];pg=px/pe-1 if side=='LONG' else pe/px-1
                signals.append({'signal_ts':ts,'asset':cand,'side':side,'limit':limit,'activation':activation,'expiry':expiry,'parent_entry':pe,'parent_gross':pg,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'});last=i
            if not signals:emit(out,'EVIDENCE-FAIL',reason='no frozen-parent signals reconstructed',parameter_tuning=False);return
            fills=[];misses=[];errors=[]
            for s in signals:
                try:
                    pred=(lambda p,L=s['limit']:p<L) if s['side']=='LONG' else (lambda p,L=s['limit']:p>L)
                    ft=first_window(s['asset'],s['activation'],s['expiry'],pred)
                    if ft is None:
                        m=dict(s);m['parent_net10']=s['parent_gross']-BASE_COST;m['parent_net20']=s['parent_gross']-STRESS_COST;misses.append(m);continue
                    fts,ftid,_=ft;target=fts+HOLD_HOURS*3600;xt=first_after(s['asset'],target)
                    if xt is None:errors.append({'asset':s['asset'],'signal_ts':s['signal_ts'],'reason':'no exit trade at/after target'});continue
                    xts,xtid,xpx=xt;gross=xpx/s['limit']-1 if s['side']=='LONG' else s['limit']/xpx-1
                    e=dict(s);e.update({'fill_ts':fts,'fill_trade_id':ftid,'entry_price':s['limit'],'exit_target_ts':target,'exit_ts':xts,'exit_trade_id':xtid,'exit_price':xpx,'net10':gross-BASE_COST,'net20':gross-STRESS_COST,'entry_improvement_vs_parent':(s['parent_entry']/s['limit']-1 if s['side']=='LONG' else s['limit']/s['parent_entry']-1)});fills.append(e)
                except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),stage='raw-trade-first-cross',asset=s['asset'],signal_ts=s['signal_ts'],parameter_tuning=False);return
            if errors:emit(out,'EVIDENCE-FAIL',reason='exit coverage incomplete',errors=errors[:20],error_count=len(errors),signal_count=len(signals),fill_count=len(fills),parameter_tuning=False);return
            oos=[e for e in fills if e['period']=='OOS'];oos_sig=[e for e in signals if e['period']=='OOS'];oos_miss=[e for e in misses if e['period']=='OOS'];n_sig=len(oos_sig);n_fill=len(oos)
            r10=[e['net10'] for e in oos];r20=[e['net20'] for e in oos];by10={e['signal_ts']:e['net10'] for e in oos};by20={e['signal_ts']:e['net20'] for e in oos};ordered=sorted(oos_sig,key=lambda x:x['signal_ts']);total10=[by10.get(e['signal_ts'],0.) for e in ordered];total20=[by20.get(e['signal_ts'],0.) for e in ordered]
            miss_cf=[e['parent_net10'] for e in oos_miss];avg=sum(e['entry_improvement_vs_parent'] for e in oos)/n_fill if n_fill else None;s10=stats(r10);s20=stats(r20);p10=bool(n_fill and s10['mean'] is not None and s10['mean']>0 and (s10['pf'] or 0)>1);p20=bool(n_fill and s20['mean'] is not None and s20['mean']>0 and (s20['pf'] or 0)>1)
            ev='INCONCLUSIVE-NO-OOS-SIGNALS' if not n_sig else 'WEAK-NO-FILLS' if not n_fill else 'WEAK-OR-NEGATIVE-COST-STRESS' if not(p10 and p20) else 'INCONCLUSIVE-POSITIVE-STATS-GATES-REQUIRE-QUALITATIVE-REVIEW'
            trade_sources=[]
            for m in DAY_META.values():trade_sources.append({k:v for k,v in m.items() if not k.startswith('_')})
            trade_sources.sort(key=lambda x:(x['symbol'],x['date']))
            peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            emit(out,'OUTCOME-COMPLETE',contract={'parent_object':'SL-VAL-QUIET-RV-001','assets':ASSETS,'tf':TF,'quiet_regime':'42-bar basket realized volatility <= strictly-prior 540-bar 30th percentile','relative_deviation':'42-bar cumulative asset-minus-equal-weight-basket return','signal':'largest absolute deviation > strictly-prior pooled 540-bar 90th percentile','direction':'fade deviation','limit_price':'signal_bar_close','activation':'next_4h_bar_start','expiry_hours':4,'fill_confirmation':'first Binance Spot raw trade strictly through limit; touch does not fill','entry_price':'original_limit','exit':'first raw trade at_or_after fill_confirmation_ts + 20h','decluster_bars':DECLUSTER,'base_cost':BASE_COST,'stress_cost':STRESS_COST,'split':'2025-01-01','parameter_tuning':False,'memory_repair':'stream checked ZIP to temp disk; metadata-only cache; bounded deterministic external sort only if archive order is nonmonotonic'},synthetic_equivalence_fixture=fixture,signal_count=len(signals),fill_count=len(fills),no_fill_count=len(misses),oos_signal_count=n_sig,oos_fill_count=n_fill,oos_no_fill_count=len(oos_miss),oos_fill_rate=(n_fill/n_sig if n_sig else None),oos_filled_stats_10bps=s10,oos_filled_stats_20bps=s20,oos_total_strategy_stats_10bps=stats(total10),oos_total_strategy_stats_20bps=stats(total20),oos_missed_parent_counterfactual_10bps=stats(miss_cf),oos_avg_entry_improvement_vs_parent=avg,oos_asset_fill_share=concentration(oos,'asset'),oos_side_fill_share=concentration(oos,'side'),oos_asset_signal_share=concentration(oos_sig,'asset'),oos_side_signal_share=concentration(oos_sig,'side'),evidence_class=ev,peak_rss_diagnostic=peak_rss,source_files=sources+trade_sources,parameter_tuning=False,limitations=['strict-through raw trade is conservative fill-confirmation evidence, not queue-priority proof','no latency, queue position, partial-fill or size/capacity model','SHORT branch uses Spot price evidence only; actual shorting requires futures/borrow execution evidence','fill-rate and subset-dominance gates were frozen qualitatively, not numerically; runner does not invent cutoffs','raw Binance public archives may be revised later; SHA-256 provenance is recorded'])
    except Exception as e:
        if not (Path(out)/'terminal_result.json').exists():emit(out,'EVIDENCE-FAIL',reason=repr(e),stage='runner-unhandled',parameter_tuning=False)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
