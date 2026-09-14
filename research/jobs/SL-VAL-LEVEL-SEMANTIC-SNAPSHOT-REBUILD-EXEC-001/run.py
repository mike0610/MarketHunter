import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from decimal import Decimal, InvalidOperation
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-LEVEL-SEMANTIC-SNAPSHOT-REBUILD-EXEC-001'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
START=datetime(2019,1,1,tzinfo=timezone.utc)
END=datetime(2022,1,1,tzinfo=timezone.utc)
LEGACY_PARENT_SHA='9d767934ec1142b1c2b88920098a951bb11bac448ccd0baeacc6ea4545039c8b'
EXPECTED_EVENT_COUNT=1391
EXPECTED_UNKNOWN_COUNT=4
EXPECTED_SUPPRESSIONS=435

def emit(outdir,state,**x):
    p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
    payload={'object_id':OBJECT_ID,'terminal_state':state,**x}
    (p/'terminal_result.json').write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')

def stable_sha(obj):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def canon_decimal(s):
    try:
        d=Decimal(s)
    except InvalidOperation:
        raise ValueError(f'invalid_decimal:{s!r}')
    if not d.is_finite():
        raise ValueError(f'nonfinite_decimal:{s!r}')
    if d == 0:
        return '0'
    out=format(d,'f')
    if '.' in out:
        out=out.rstrip('0').rstrip('.')
    return out

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read()

def load_month(y,m):
    name=f'BTCUSDT-1d-{y}-{m:02d}.zip'
    url=f'{BASE}/{name}'
    z=get(url)
    expected=get(url+'.CHECKSUM').decode().split()[0].lower()
    actual=hashlib.sha256(z).hexdigest()
    if expected!=actual:
        raise ValueError(f'checksum mismatch {name}')
    legacy_rows=[]
    semantic_rows=[]
    with zipfile.ZipFile(io.BytesIO(z)) as q:
        names=[n for n in q.namelist() if not n.endswith('/')]
        if len(names)!=1:
            raise ValueError(f'zip members {name}: {names}')
        text=io.TextIOWrapper(q.open(names[0]),encoding='utf-8')
        for r in csv.reader(text):
            if not r:
                continue
            try:
                raw=int(r[0])
                o,h,l,c=map(float,r[1:5])
                ds=[canon_decimal(x) for x in r[1:5]]
            except Exception:
                continue
            ts=raw/1_000_000 if raw>10**14 else raw/1_000
            tsi=int(ts)
            legacy_rows.append({'ts':tsi,'o':o,'h':h,'l':l,'c':c})
            semantic_rows.append({'ts':tsi,'open':ds[0],'high':ds[1],'low':ds[2],'close':ds[3]})
    return legacy_rows,semantic_rows,{'url':url,'sha256':actual,'rows':len(legacy_rows)}

def nearest_level(p,step):
    lo=math.floor(p/step)*step
    hi=lo+step
    return lo if (p-lo)<= (hi-p) else hi

def raw_event(prev,bar,factor):
    p=prev['c']
    g=10**(math.floor(math.log10(p))-1)
    step=g*factor
    L=nearest_level(p,step)
    if abs(p-L)<1e-12:
        return None,'PREV_CLOSE_AT_LEVEL'
    if p<L:
        direction='UP'
        if bar['h']<L:
            return None,None
        if bar['c']>L:
            label='POST_CROSS_CONTINUATION'
        elif bar['c']<L:
            label='AT_LEVEL_REFLECTION'
        else:
            return None,'CLOSE_AT_LEVEL'
    else:
        direction='DOWN'
        if bar['l']>L:
            return None,None
        if bar['c']<L:
            label='POST_CROSS_CONTINUATION'
        elif bar['c']>L:
            label='AT_LEVEL_REFLECTION'
        else:
            return None,'CLOSE_AT_LEVEL'
    return {'ts':bar['ts'],'level':round(L,12),'direction':direction,'label':label,
            'grid':'PRIMARY' if factor==1 else 'HALF'},None

def census(rows):
    out=[]; unknown=[]; suppressed=0; last={}
    for i in range(1,len(rows)):
        if not (int(START.timestamp())<=rows[i]['ts']<int(END.timestamp())):
            continue
        for factor in (1.0,0.5):
            e,u=raw_event(rows[i-1],rows[i],factor)
            if u:
                unknown.append((rows[i]['ts'],factor,u))
            if not e:
                continue
            key=(e['grid'],e['level'],e['direction'])
            prev_idx=last.get(key)
            if prev_idx is not None and i-prev_idx<=5:
                suppressed+=1
                continue
            last[key]=i
            out.append(e)
    return out,unknown,suppressed

def main(outdir,job_path):
    try:
        spec=json.loads(Path(job_path).read_text())
        required={
            'object_id':OBJECT_ID,
            'legacy_parent_census_sha256':LEGACY_PARENT_SHA,
            'expected_event_count':EXPECTED_EVENT_COUNT,
            'expected_unknown_count':EXPECTED_UNKNOWN_COUNT,
            'expected_decluster_suppressions':EXPECTED_SUPPRESSIONS,
        }
        if any(spec.get(k)!=v for k,v in required.items()):
            raise ValueError('job contract mismatch')
        legacy_rows=[]; semantic_rows=[]; files=[]
        months=[(2018,12)]+[(y,m) for y in (2019,2020,2021) for m in range(1,13)]
        for y,m in months:
            lr,sr,meta=load_month(y,m)
            legacy_rows.extend(lr); semantic_rows.extend(sr); files.append(meta)
    except Exception as e:
        emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),outcomes_opened=False)
        return

    pairs=sorted(zip(legacy_rows,semantic_rows),key=lambda x:x[0]['ts'])
    legacy_rows=[x[0] for x in pairs]; semantic_rows=[x[1] for x in pairs]
    ts=[r['ts'] for r in legacy_rows]
    if len(ts)!=len(set(ts)) or any(ts[i+1]<=ts[i] for i in range(len(ts)-1)):
        emit(outdir,'REFERENCE-PARENT-MISMATCH',reason='duplicate_or_nonmonotonic_source',
             parent_census_sha256=None,outcomes_opened=False)
        return

    events,unknown,suppressed=census(legacy_rows)
    legacy_parent={
        'contract_version':'LEVEL-007-new-census-v1',
        'scope':'BTCUSDT Spot 1d 2019-01-01..2021-12-31; 2018-12 warmup only',
        'events':events,
        'unknown':unknown,
        'decluster_suppressions':suppressed,
        'files':files,
        'outcomes_opened':False
    }
    parent_sha=stable_sha(legacy_parent)
    guards_ok=(parent_sha==LEGACY_PARENT_SHA and len(events)==EXPECTED_EVENT_COUNT
               and len(unknown)==EXPECTED_UNKNOWN_COUNT and suppressed==EXPECTED_SUPPRESSIONS)
    if not guards_ok:
        emit(outdir,'REFERENCE-PARENT-MISMATCH',
             reason='legacy_parent_reproduction_mismatch',
             expected_parent_census_sha256=LEGACY_PARENT_SHA,
             observed_parent_census_sha256=parent_sha,
             event_count=len(events),unknown_count=len(unknown),
             decluster_suppressions=suppressed,file_count=len(files),outcomes_opened=False)
        return

    market_payload={
        'contract_version':'LEVEL-market-data-semantic-v1',
        'scope':'BTCUSDT Spot 1d 2018-12 warmup + 2019-01-01..2021-12-31 parent window',
        'normalization':'timestamp integer seconds; OHLC exact decimal strings with insignificant trailing zeros removed',
        'rows':semantic_rows
    }
    event_payload={
        'contract_version':'LEVEL-event-population-v1',
        'scope':'BTCUSDT Spot 1d 2019-01-01..2021-12-31',
        'events':events,
        'unknown':unknown,
        'decluster_suppressions':suppressed
    }
    provenance_payload={
        'contract_version':'LEVEL-provider-provenance-v1',
        'provider':'Binance public data archive',
        'files':files
    }
    identity={
        'object_id':OBJECT_ID,
        'legacy_parent_census_sha256':parent_sha,
        'market_data_semantic_sha256':stable_sha(market_payload),
        'event_population_sha256':stable_sha(event_payload),
        'provider_provenance_sha256':stable_sha(provenance_payload),
        'event_count':len(events),
        'unknown_count':len(unknown),
        'decluster_suppressions':suppressed,
        'file_count':len(files),
        'row_count':len(semantic_rows),
        'outcomes_opened':False
    }
    p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
    (p/'snapshot_identity.json').write_text(json.dumps(identity,indent=2,sort_keys=True),encoding='utf-8')
    emit(outdir,'SEMANTIC-SNAPSHOT-REBUILT',**identity)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--job',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    main(args.output,args.job)
