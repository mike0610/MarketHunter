import argparse,csv,hashlib,io,json,math,urllib.error,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-AGGFLOW-STRUCTURE-001'
SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT']
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180;PULL=3;ROLL=1080;Q=.90;HOLD=12;DECLUSTER=18;COST=.001
SWING_LEFT=3;SWING_RIGHT=3

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))

def get(u):
 return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def archive(symbol,market,y,m):
 root='spot' if market=='spot' else 'futures/um'
 n=f'{symbol}-4h-{y}-{m:02d}.zip'
 u=f'https://data.binance.vision/data/{root}/monthly/klines/{symbol}/4h/{n}'
 try:z=get(u)
 except urllib.error.HTTPError as e:
  if e.code==404:return None,None
  raise
 e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 out=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  rd=csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0])))
  for x in rd:
   try:
    raw=int(x[0]);o,h,l,c=map(float,x[1:5]);vol=float(x[5]);tb=float(x[9])
   except:continue
   ts=raw/1e6 if raw>10**14 else raw/1e3
   out.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c,'vol':vol,'tb':tb})
 return out,{'url':u,'sha256':a,'rows':len(out)}

def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}

def structure(prefix):
 # Exact SwingDetector(3,3) semantics, evaluated only on information available by the signal bar.
 highs=[];lows=[];n=len(prefix)
 for i in range(SWING_LEFT,n-SWING_RIGHT):
  ch=prefix[i]['h'];cl=prefix[i]['l']
  if all(prefix[j]['h']<ch for j in range(i-SWING_LEFT,i)) and all(prefix[j]['h']<=ch for j in range(i+1,i+SWING_RIGHT+1)):
   highs.append((i,ch))
  if all(prefix[j]['l']>cl for j in range(i-SWING_LEFT,i)) and all(prefix[j]['l']>=cl for j in range(i+1,i+SWING_RIGHT+1)):
   lows.append((i,cl))
 if len(highs)<2 or len(lows)<2:
  return {'trend':'sideways','bos':False,'choch':False}
 lh,ph=highs[-1],highs[-2];ll,pl=lows[-1],lows[-2]
 hh=lh[1]>ph[1];lower_h=lh[1]<ph[1];hl=ll[1]>pl[1];lower_l=ll[1]<pl[1]
 trend='bullish' if hh and hl else ('bearish' if lower_h and lower_l else 'sideways')
 close=prefix[-1]['c'];bos=False;choch=False
 if trend=='bullish':
  bos=close>lh[1];choch=close<ll[1]
 elif trend=='bearish':
  bos=close<ll[1];choch=close>lh[1]
 return {'trend':trend,'bos':bos,'choch':choch}

def evaluate(symbol):
 rows=[];flow={};files=[]
 for y in range(2020,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d<WARM or d>=END:continue
   a,meta=archive(symbol,'spot',y,m)
   if a:rows+=a;files.append(meta)
 for y in range(2025,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d<SPLIT or d>=END:continue
   a,meta=archive(symbol,'futures',y,m)
   if not a:continue
   files.append(meta)
   for x in a:
    if x['vol']>0:flow[x['ts']]=[x['tb'],max(0.,x['vol']-x['tb'])]
 if not rows:raise ValueError('no spot history '+symbol)
 rows.sort(key=lambda x:x['ts'])
 events=[];last=-10**9
 for i in range(max(TREND,PULL,ROLL)+1,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c'])
  pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
  hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i) if j>=PULL]
  if len(hist)<ROLL:continue
  th=quantile(hist,Q);side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>th:side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>th:side='SHORT'
  if not side:continue
  vals=[]
  for k in range(1,4):
   d=flow.get(b['ts']-k*14400)
   if d and d[0]+d[1]>0:vals.append((d[0]-d[1])/(d[0]+d[1]))
  if len(vals)<3:continue
  imbalance=sum(vals)/3
  flow_state='BUY-PRESSURE' if imbalance>0 else ('SELL-PRESSURE' if imbalance<0 else 'NEUTRAL')
  align='WITH-FLOW' if (side=='LONG' and flow_state=='BUY-PRESSURE') or (side=='SHORT' and flow_state=='SELL-PRESSURE') else 'COUNTER-FLOW'
  ctx=structure(rows[:i+1])
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o'];gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':b['ts'],'symbol':symbol,'side':side,'alignment':align,'structure':ctx['trend'],'bos':ctx['bos'],'choch':ctx['choch'],'net':gross-COST,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i
 o=[x for x in events if x['period']=='OOS']
 cells={}
 for regime in ['bullish','bearish','sideways']:
  z=[x for x in o if x['structure']==regime]
  cells[regime]={'all':st([x['net'] for x in z]),'with_flow':st([x['net'] for x in z if x['alignment']=='WITH-FLOW']),'counter_flow':st([x['net'] for x in z if x['alignment']=='COUNTER-FLOW']),'bos_n':sum(x['bos'] for x in z),'choch_n':sum(x['choch'] for x in z)}
 return {'symbol':symbol,'event_count':len(events),'oos_n':len(o),'cells':cells,'source_files':files}

def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  per=[evaluate(s) for s in SYMBOLS]
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 pooled={}
 deltas={}
 for regime in ['bullish','bearish','sideways']:
  wf=[];cf=[]
  for r in per:
   # Reconstruct pooled summary from per-symbol stats is impossible; keep cell evidence and use weighted means from cells.
   a=r['cells'][regime]['with_flow'];b=r['cells'][regime]['counter_flow']
   pooled[regime]=pooled.get(regime,{'with_n':0,'counter_n':0,'with_sum':0.0,'counter_sum':0.0})
   if a['n'] and a['mean'] is not None:pooled[regime]['with_n']+=a['n'];pooled[regime]['with_sum']+=a['n']*a['mean']
   if b['n'] and b['mean'] is not None:pooled[regime]['counter_n']+=b['n'];pooled[regime]['counter_sum']+=b['n']*b['mean']
 for regime,p in pooled.items():
  wm=p['with_sum']/p['with_n'] if p['with_n'] else None;cm=p['counter_sum']/p['counter_n'] if p['counter_n'] else None
  p['with_mean']=wm;p['counter_mean']=cm;p['delta_with_minus_counter']=(wm-cm) if wm is not None and cm is not None else None
  if p['with_n']>=8 and p['counter_n']>=8 and p['delta_with_minus_counter'] is not None:deltas[regime]=p['delta_with_minus_counter']
 supported=False
 if len(deltas)>=2:
  vals=list(deltas.values())
  supported=(max(vals)-min(vals)>=0.0025 and min(vals)<0<max(vals))
 verdict='STRUCTURE-CONTEXT-SUPPORTED' if supported else ('BLOCKED-EVIDENCE' if len(deltas)<2 else 'STRUCTURE-CONTEXT-NOT-SUPPORTED')
 emit(out,'OUTCOME-COMPLETE',contract={'symbols':SYMBOLS,'tf':'4h','parent_parameters':'identical to AGGFLOW portability object','structure':'MarketHunter SwingDetector left=3 right=3 + TrendEngine HH/HL/LH/LL semantics, prior-only prefix','split':'2025-01-01','parameter_tuning':False,'support_rule':'at least two comparable regimes, >=8 WITH and >=8 COUNTER each; cross-regime delta spread >=25bps and opposite signs'},per_symbol=per,pooled_regime=pooled,terminal_verdict=verdict,parameter_tuning=False,limitations=['three large Binance assets','4h only','fixed hold and fixed costs','structure is descriptive context, not standalone entry rule'])

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
