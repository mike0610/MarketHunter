import argparse,csv,hashlib,io,json,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-CROSS-SECTIONAL-FUNDING-CARRY-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='1h'
START=datetime(2022,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
BASE_COST=.001
STRESS_COST=.002

def emit(out,state,**extra):
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**extra},indent=2,sort_keys=True))

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def funding(sym):
    rows=[];cur=int(START.timestamp()*1000);end=int(END.timestamp()*1000)
    while cur<end:
        q=urllib.parse.urlencode({'symbol':sym,'startTime':cur,'endTime':end,'limit':1000})
        a=json.loads(get('https://fapi.binance.com/fapi/v1/fundingRate?'+q).decode())
        if not a:break
        for x in a:
            t=int(x['fundingTime'])//1000
            if t<int(START.timestamp()) or t>=int(END.timestamp()):continue
            rows.append((t,float(x['fundingRate'])))
        nxt=max(int(x['fundingTime']) for x in a)+1
        if nxt<=cur:break
        cur=nxt
    return dict(rows),{'symbol':sym,'kind':'funding','rows':len(rows)}

def month(sym,y,m):
    n=f'{sym}-{TF}-{y}-{m:02d}.zip'
    u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{TF}/{n}'
    z=get(u)
    expected=get(u+'.CHECKSUM').decode().split()[0].lower()
    actual=hashlib.sha256(z).hexdigest()
    if expected!=actual:raise ValueError('checksum '+n)
    out=[]
    with zipfile.ZipFile(io.BytesIO(z)) as q:
        names=[v for v in q.namelist() if not v.endswith('/')]
        if not names:raise ValueError('empty zip '+n)
        for x in csv.reader(io.TextIOWrapper(q.open(names[0]))):
            try:
                raw=int(x[0]);op=float(x[1])
            except:continue
            ts=int(raw/1e6 if raw>10**14 else raw/1e3)
            if ts<int(START.timestamp()) or ts>=int(END.timestamp()):continue
            out.append((ts,op))
    return out,{'symbol':sym,'kind':'kline','url':u,'sha256':actual,'rows':len(out)}

def stats(vals):
    if not vals:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
    s=sorted(vals);n=len(s);med=s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2
    g=sum(x for x in vals if x>0);l=-sum(x for x in vals if x<0)
    eq=pk=1.;dd=0.
    for x in vals:
        eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
    return {'n':n,'mean':sum(vals)/n,'median':med,'hit':sum(x>0 for x in vals)/n,'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}

def main(out,job):
    try:
        cfg=json.loads(Path(job).read_text())
        if cfg.get('object_id')!=OBJECT_ID:raise ValueError('object_id mismatch')
        F={};P={};src=[]
        for sym in ASSETS:
            F[sym],meta=funding(sym);src.append(meta)
            rows=[]
            for y in range(2022,2027):
                for m in range(1,13):
                    d=datetime(y,m,1,tzinfo=timezone.utc)
                    if d<START or d>=END:continue
                    a,b=month(sym,y,m);rows+=a;src.append(b)
            P[sym]=dict(rows)
    except Exception as e:
        emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return

    common_f=set.intersection(*[set(F[s]) for s in ASSETS])
    signals=sorted(t for t in common_f if datetime.fromtimestamp(t,timezone.utc).hour==0)
    events=[]
    for ts in signals:
        if ts<int(START.timestamp()) or ts>=int(END.timestamp()):continue
        ranks=sorted((F[s][ts],s) for s in ASSETS)
        longs=[s for _,s in ranks[:2]]
        shorts=[s for _,s in ranks[-2:]]
        entry=ts+3600
        exit_=entry+24*3600
        if exit_>=int(END.timestamp()):continue
        if any(entry not in P[s] or exit_ not in P[s] for s in longs+shorts):continue
        leg_returns=[];price_component=0.0;funding_component=0.0
        for s in longs:
            pr=P[s][exit_]/P[s][entry]-1
            fr=-sum(rate for t,rate in F[s].items() if entry<t<=exit_)
            leg_returns.append(pr+fr);price_component+=0.25*pr;funding_component+=0.25*fr
        for s in shorts:
            pr=1-P[s][exit_]/P[s][entry]
            fr=sum(rate for t,rate in F[s].items() if entry<t<=exit_)
            leg_returns.append(pr+fr);price_component+=0.25*pr;funding_component+=0.25*fr
        gross=sum(leg_returns)/4
        events.append({'ts':ts,'longs':longs,'shorts':shorts,'gross':gross,'net10':gross-BASE_COST,'net20':gross-STRESS_COST,'price':price_component,'funding':funding_component,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'})

    o=[e for e in events if e['period']=='OOS']
    r10=[e['net10'] for e in o];r20=[e['net20'] for e in o]
    s10=stats(r10);s20=stats(r20)
    wins=sorted([x for x in r10 if x>0],reverse=True)
    top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
    if s10['n']<30:verdict='BLOCKED-EVIDENCE'
    elif s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):verdict='CANDIDATE'
    else:verdict='REJECTED'
    emit(out,'OUTCOME-COMPLETE',terminal_verdict=verdict,contract={'book':'FUTURES-DIAGNOSTIC','capital_usdt':1000,'assets':ASSETS,'signal':'daily 00:00 UTC current funding cross-sectional rank','long':'2 lowest funding rates','short':'2 highest funding rates','entry':'next hourly open','holding_hours':24,'portfolio':'25% each across 4 legs, gross 1x, near dollar-neutral','funding_accounting':'actual payments strictly after entry and through exit','base_cost':BASE_COST,'stress_cost':STRESS_COST,'split':'2025-01-01','parameter_tuning':False},event_count=len(events),is_stats_10bps=stats([e['net10'] for e in events if e['period']=='IS']),oos_stats_10bps=s10,oos_stats_20bps=s20,oos_mean_price_component=sum(e['price'] for e in o)/len(o) if o else None,oos_mean_funding_component=sum(e['funding'] for e in o)/len(o) if o else None,oos_top_positive_period_share=top,source_files=src,parameter_tuning=False,limitations=['fixed 8-asset liquid basket, not dynamic survivorship-aware universe','Binance USDT-margined perpetuals only','current funding rank may not persist into subsequent funding windows','fixed round-trip cost proxy; no order-book slippage','no leverage beyond gross 1x and no liquidation modeling','candidate status would require cross-venue and dynamic-universe robustness before promotion'])
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
