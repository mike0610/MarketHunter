import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-MTF-ALIGNMENT-001'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h'
WARM=datetime(2021,1,1,tzinfo=timezone.utc); START=datetime(2022,2,1,tzinfo=timezone.utc); SPLIT=datetime(2025,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
FAST=6; MID=42; SLOW=180; COST=.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u): return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(y,m):
 n=f'BTCUSDT-4h-{y}-{m:02d}.zip';u=f'{BASE}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a: raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try: raw=int(x[0]);o,c=float(x[1]),float(x[4])
   except: continue
   ts=raw/1e6 if raw>10**14 else raw/1e3;r.append({'ts':int(ts),'o':o,'c':c})
 return r,{'url':u,'sha256':a,'rows':len(r)}
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  rows=[];files=[]
  for y in range(2021,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    a,b=mon(y,m);rows+=a;files.append(b)
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts']);events=[];comp=[]
 for i in range(SLOW+1,len(rows)-7):
  t=datetime.fromtimestamp(rows[i]['ts'],timezone.utc)
  if t<START or t>=END or t.hour!=0:continue
  r6=rows[i-1]['c']/rows[i-1-FAST]['c']-1;r42=rows[i-1]['c']/rows[i-1-MID]['c']-1;r180=rows[i-1]['c']/rows[i-1-SLOW]['c']-1
  side='LONG' if r6>0 and r42>0 and r180>0 else ('SHORT' if r6<0 and r42<0 and r180<0 else None)
  cside='LONG' if r180>0 else ('SHORT' if r180<0 else None)
  entry=rows[i]['o'];exitp=rows[i+6]['o']
  if cside:
   g=exitp/entry-1 if cside=='LONG' else entry/exitp-1;comp.append({'ts':rows[i]['ts'],'net':g-COST,'net20':g-.002,'period':'IS' if t<SPLIT else 'OOS'})
  if side:
   g=exitp/entry-1 if side=='LONG' else entry/exitp-1;events.append({'ts':rows[i]['ts'],'side':side,'net':g-COST,'net20':g-.002,'period':'IS' if t<SPLIT else 'OOS'})
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 co=[x for x in comp if x['period']=='OOS'];cs=st([x['net'] for x in co]);cs20=st([x['net20'] for x in co])
 if s['n']<30:v='WAIT-LIVE-SAMPLE-ACCUMULATION'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'market':'BTCUSDT','source':'Spot 4h','decision':'daily 00:00 UTC','alignment':'strictly-prior 24h/7d/30d return signs all agree','entry':'current 00:00 open using only prior closed bars','exit':'next day 00:00 open exact 24h','cost':.001,'cost_stress':.002,'split':'2025-01-01','book':'FUTURES-DIAGNOSTIC 1x','parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_long=st([x['net'] for x in o if x['side']=='LONG']),oos_short=st([x['net'] for x in o if x['side']=='SHORT']),oos_top_positive_trade_share=top,comparator_30d_oos_10bps=cs,comparator_30d_oos_20bps=cs20,alignment_coverage_oos=(len(o)/len(co) if co else None),terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['single BTC first-pass','alignment may only reduce exposure rather than add edge','30d comparator has different exposure frequency','fixed costs only','candidate requires independent robustness'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
