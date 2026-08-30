import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-CROSS-SECTIONAL-MOMENTUM-001';ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];TF='4h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);LOOK=42;HOLD=42;COST=.001

def emit(o,s,**x):p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(sym,y,m):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{base}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r,{'symbol':sym,'url':u,'sha256':a,'rows':len(r)}
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};files=[]
  for sym in ASSETS:
   rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=mon(sym,y,m);rows+=a;files.append(b)
   data[sym]={ts:(o,c) for ts,o,c in rows}
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[x]) for x in ASSETS]));events=[]
 for i in range(LOOK,len(common)-HOLD-1,HOLD):
  ts=common[i]
  if ts<int(START.timestamp()) or ts>=int(END.timestamp()):continue
  ranks=sorted([(data[s][common[i]][1]/data[s][common[i-LOOK]][1]-1,s) for s in ASSETS],reverse=True);longs=[x[1] for x in ranks[:2]];shorts=[x[1] for x in ranks[-2:]]
  lg=sum(data[s][common[i+HOLD]][0]/data[s][common[i+1]][0]-1 for s in longs)/2;sh=sum(1-data[s][common[i+HOLD]][0]/data[s][common[i+1]][0] for s in shorts)/2;gross=.5*lg+.5*sh
  events.append({'ts':ts,'longs':longs,'shorts':shorts,'net':gross-COST,'net20':gross-.002,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'})
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 if s['n']<30:v='BLOCKED-EVIDENCE'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'book':'FUTURES-DIAGNOSTIC','capital_usdt':1000,'assets':ASSETS,'universe_policy':'fixed predeclared long-lived liquid basket; NOT survivorship-aware full-market evidence','tf':TF,'ranking_lookback_bars':LOOK,'rebalance_hold_bars':HOLD,'long':'top 2 trailing-return assets','short':'bottom 2 trailing-return assets','portfolio':'50% equal-weight long sleeve + 50% equal-weight short sleeve','entry':'next_bar_open','base_cost':.001,'stress_cost':.002,'split':'2025-01-01','edge_gate_notional':'1x','parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_top_positive_period_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['this bounded fixed basket cannot establish survivorship-aware broad-market cross-sectional momentum','all assets are predeclared before outcomes and no replacements are allowed','short sleeve requires futures; spot archives are synchronized price evidence','funding/leverage excluded from base edge gate','fixed round-trip cost proxy; no order-book slippage','positive result requires separate dynamic-universe survivorship-aware validation before promotion'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
