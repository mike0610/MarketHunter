import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-QUIET-RV-FUTURES-REALISM-001';ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];TF='4h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);VOL_WIN=42;VOL_LOOK=540;VOL_Q=.30;DEV_WIN=42;DEV_LOOK=540;DEV_Q=.90;HOLD=6;DECLUSTER=6;BASE=.001;STRESS=.002

def emit(o,s,**x):p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def funding(sym):
 rows=[];cur=int(WARM.timestamp()*1000);end=int(END.timestamp()*1000)
 while cur<end:
  q=urllib.parse.urlencode({'symbol':sym,'startTime':cur,'endTime':end,'limit':1000});a=json.loads(get('https://fapi.binance.com/fapi/v1/fundingRate?'+q).decode())
  if not a:break
  for x in a:
   t=int(x['fundingTime'])//1000
   if int(WARM.timestamp())<=t<int(END.timestamp()):rows.append((t,float(x['fundingRate'])))
  nxt=max(int(x['fundingTime']) for x in a)+1
  if nxt<=cur:break
  cur=nxt
 return dict(rows),{'symbol':sym,'kind':'funding','rows':len(rows)}
def mon(sym,y,m):
 n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{TF}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r,{'symbol':sym,'kind':'kline','url':u,'sha256':a,'rows':len(r)}
def qtl(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def sd(a):m=sum(a)/len(a);return math.sqrt(sum((x-m)**2 for x in a)/len(a))
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);n=len(a);med=s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':n,'mean':sum(a)/n,'median':med,'hit':sum(x>0 for x in a)/n,'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};F={};src=[]
  for sym in ASSETS:
   F[sym],meta=funding(sym);src.append(meta);rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=mon(sym,y,m);rows+=a;src.append(b)
   data[sym]={t:(o,c) for t,o,c in rows}
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[s]) for s in ASSETS]));ret={}
 for s in ASSETS:
  c=[data[s][t][1] for t in common];ret[s]=[None]+[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
 market=[None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,len(common))];rv=[None]*len(common);dev={s:[None]*len(common) for s in ASSETS}
 for i in range(VOL_WIN+1,len(common)):
  rv[i]=sd(market[i-VOL_WIN+1:i+1])
  for s in ASSETS:dev[s][i]=sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
 events=[];last=-10**9
 for i in range(max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1,len(common)-HOLD-1):
  ts=common[i]
  if ts<int(START.timestamp()) or ts>=int(END.timestamp()) or i-last<DECLUSTER:continue
  vh=[x for x in rv[i-VOL_LOOK:i] if x is not None]
  if rv[i]>qtl(vh,VOL_Q):continue
  vals=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None];th=qtl(vals,DEV_Q);cand=max(ASSETS,key=lambda s:abs(dev[s][i]))
  if abs(dev[cand][i])<=th:continue
  side='SHORT' if dev[cand][i]>0 else 'LONG';entry_t=common[i+1];exit_t=common[i+HOLD];entry=data[cand][entry_t][0];exitp=data[cand][exit_t][0];price=exitp/entry-1 if side=='LONG' else entry/exitp-1
  fr=sum(rate for t,rate in F[cand].items() if entry_t<t<=exit_t);fund=-fr if side=='LONG' else fr;gross=price+fund
  events.append({'ts':ts,'asset':cand,'side':side,'price':price,'funding':fund,'net10':gross-BASE,'net20':gross-STRESS,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'});last=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net10'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 supported=s['n']>=30 and s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5);v='ROBUSTNESS-SUPPORTED' if supported else ('BLOCKED-EVIDENCE' if s['n']<30 else 'ROBUSTNESS-FAILED')
 emit(out,'OUTCOME-COMPLETE',terminal_verdict=v,parent='SL-VAL-QUIET-RV-001',contract={'assets':ASSETS,'market':'Binance USD-M perpetual futures','tf':TF,'quiet_regime':'same frozen parent rule','relative_deviation':'same frozen parent rule','direction':'same frozen parent fade','entry':'next_bar_open','exit':'parent i+6 open, preserving 20h elapsed timing','decluster_bars':6,'funding':'realized strictly after entry through exit, signed by side','base_cost':BASE,'stress_cost':STRESS,'split':'2025-01-01','leverage':'1x','parameter_tuning':False},event_count=len(events),is_stats=st([x['net10'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_long=st([x['net10'] for x in o if x['side']=='LONG']),oos_short=st([x['net10'] for x in o if x['side']=='SHORT']),oos_mean_price_component=sum(x['price'] for x in o)/len(o) if o else None,oos_mean_funding_component=sum(x['funding'] for x in o)/len(o) if o else None,oos_top_positive_trade_share=top,source_files=src,parameter_tuning=False,limitations=['fixed liquid 8-asset basket','Binance USD-M only','fixed cost proxy; no order-book slippage','no leverage or liquidation modeling','exact parent signal and timing preserved; no post-result tuning'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
