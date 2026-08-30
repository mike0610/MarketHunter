import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-VOLUME-SURPRISE-001';ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];TF='1h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);LOOK=720;VOL_Q=.95;RET_Q=.75;HOLD=3;DECLUSTER=6;COST=.001

def emit(o,s,**x):p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(sym,y,m):
 b=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{b}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4]);qv=float(x[7])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c,qv))
 return r,{'symbol':sym,'url':u,'sha256':a,'rows':len(r)}
def qtl(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};files=[]
  for s in ASSETS:
   rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=mon(s,y,m);rows+=a;files.append(b)
   data[s]={ts:(o,c,qv) for ts,o,c,qv in rows}
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 events=[]
 for s in ASSETS:
  ts=sorted(data[s]);last=-10**9
  ret=[None]+[math.log(data[s][ts[i]][1]/data[s][ts[i-1]][1]) for i in range(1,len(ts))]
  qv=[data[s][t][2] for t in ts]
  for i in range(LOOK+1,len(ts)-HOLD-1):
   t=ts[i]
   if t<int(START.timestamp()) or t>=int(END.timestamp()) or i-last<DECLUSTER:continue
   vth=qtl(qv[i-LOOK:i],VOL_Q);rth=qtl([abs(x) for x in ret[i-LOOK:i] if x is not None],RET_Q)
   if qv[i]<=vth or abs(ret[i])>rth or ret[i]==0:continue
   side='LONG' if ret[i]>0 else 'SHORT';entry=data[s][ts[i+1]][0];exitp=data[s][ts[i+HOLD]][0];gross=exitp/entry-1 if side=='LONG' else 1-exitp/entry
   events.append({'ts':t,'asset':s,'side':side,'net':gross-COST,'net20':gross-.002,'period':'IS' if t<int(SPLIT.timestamp()) else 'OOS'});last=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s10=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 if s10['n']<30:v='BLOCKED-EVIDENCE'
 elif s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'book':'FUTURES-DIAGNOSTIC','capital_usdt':1000,'assets':ASSETS,'tf':TF,'participation_signal':'quote volume > strictly-prior 720h 95th percentile','price_filter':'absolute current 1h return <= strictly-prior 720h 75th percentile to exclude price-shock events','direction':'follow current return sign','entry':'next_bar_open','hold_bars':3,'decluster_bars_per_asset':6,'base_cost':.001,'stress_cost':.002,'split':'2025-01-01','edge_gate_notional':'1x','parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s10,oos_stats_20bps=s20,oos_long=st([x['net'] for x in o if x['side']=='LONG']),oos_short=st([x['net'] for x in o if x['side']=='SHORT']),oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['fixed liquid basket is bounded probe, not dynamic universe','volume-growth effects handled only through rolling quantiles','short signals require futures; spot archives are price/volume evidence','funding/leverage and order-book slippage excluded','post-result direction/asset/regime filters require new untouched hypothesis'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
