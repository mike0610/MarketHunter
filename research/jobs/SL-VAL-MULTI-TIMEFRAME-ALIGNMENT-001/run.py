import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-MULTI-TIMEFRAME-ALIGNMENT-001';SYM='BTCUSDT';TF='4h';WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,4,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);DAYS=90;FAST=30;HOLD=12;COST=.001

def emit(o,s,**x):p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(tf,y,m):
 b=f'https://data.binance.vision/data/spot/monthly/klines/{SYM}/{tf}';n=f'{SYM}-{tf}-{y}-{m:02d}.zip';u=f'{b}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if a!=e:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);op=float(x[1]);cl=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,op,cl))
 return r,{'url':u,'sha256':a,'rows':len(r)}
def st(a):
 if not a:return {'n':0,'mean':None,'pf':None,'cum':None,'max_dd':None}
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  four=[];day=[];files=[]
  for y in range(2022,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    a,b=mon('4h',y,m);four+=a;files.append(b);a,b=mon('1d',y,m);day+=a;files.append(b)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 f={t:(o,c) for t,o,c in four};ds=sorted(day);dc={t:c for t,o,c in day};ts=sorted(f);events=[]
 for i in range(FAST,len(ts)-HOLD-1):
  t=ts[i];dt=datetime.fromtimestamp(t,timezone.utc)
  if dt.hour!=0 or t<int(START.timestamp()) or t>=int(END.timestamp()):continue
  prior=[x for x in ds if x<t]
  if len(prior)<DAYS:continue
  ddir=dc[prior[-1]]/dc[prior[-DAYS]]-1;fdir=f[t][1]/f[ts[i-FAST]][1]-1
  side='LONG' if ddir>0 and fdir>0 else ('SHORT' if ddir<0 and fdir<0 else None)
  if not side:continue
  entry=f[ts[i+1]][0];exitp=f[ts[i+HOLD+1]][0];gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':t,'side':side,'net':gross-COST,'net20':gross-.002,'period':'IS' if t<int(SPLIT.timestamp()) else 'OOS'})
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 if s['n']<30:v='BLOCKED-EVIDENCE'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'asset':SYM,'book':'FUTURES-DIAGNOSTIC','price_evidence':'spot','execution_tf':'4h','htf':'1d','daily_direction_days':DAYS,'four_hour_direction_bars':FAST,'signal':'LONG if both completed-direction measures positive; SHORT if both negative; otherwise FLAT','signal_time':'00:00 UTC using completed prior daily bar and current completed 4h bar','entry':'next 4h open','hold_hours':48,'base_cost':.001,'stress_cost':.002,'split':'2025-01-01','parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['single-asset bounded probe','shorts require futures while spot archives provide synchronized price evidence','funding excluded','fixed cost proxy; no order-book slippage','no parameter tuning after outcomes'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
