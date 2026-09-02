import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-QUIET-RV-DRAWDOWN-ANATOMY-001';PARENT='SL-VAL-QUIET-RV-FUTURES-REALISM-001';ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];TF='4h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);VOL_WIN=42;VOL_LOOK=540;VOL_Q=.30;DEV_WIN=42;DEV_LOOK=540;DEV_Q=.90;HOLD=6;DECLUSTER=6;COST=.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
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
 return dict(rows)
def mon(sym,y,m):
 n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{TF}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r
def qtl(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def sd(a):m=sum(a)/len(a);return math.sqrt(sum((x-m)**2 for x in a)/len(a))
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);n=len(a);med=s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':n,'mean':sum(a)/n,'median':med,'hit':sum(x>0 for x in a)/n,'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def iso(ts):return datetime.fromtimestamp(ts,timezone.utc).isoformat()
def pctshares(vals,negative=True):
 xs=sorted(((-v if negative else v) for v in vals if (v<0 if negative else v>0)),reverse=True);tot=sum(xs)
 return {str(k): (sum(xs[:k])/tot if tot else 0.0) for k in (1,3,5,10)}
def streaks(vals):
 out=[];cur=0
 for v in vals:
  if v<0:cur+=1
  elif cur:out.append(cur);cur=0
 if cur:out.append(cur)
 return {'count':len(out),'max':max(out) if out else 0,'mean':sum(out)/len(out) if out else 0.0,'distribution':{str(k):out.count(k) for k in sorted(set(out))}}
def dd_anatomy(events):
 eq=1.;pk=1.;pk_i=-1;worst=0.;start=trough=-1
 for i,e in enumerate(events):
  eq*=1+e['net10']
  if eq>pk:pk=eq;pk_i=i
  d=eq/pk-1
  if d<worst:worst=d;start=pk_i+1;trough=i
 rec=None
 if trough>=0:
  base=1.
  for e in events[:start]:base*=1+e['net10']
  eq2=base
  for j in range(start,len(events)):
   eq2*=1+events[j]['net10']
   if eq2>=base:rec=j;break
 return {'max_dd':worst,'start_ts':iso(events[start]['ts']) if start>=0 else None,'trough_ts':iso(events[trough]['ts']) if trough>=0 else None,'recovery_ts':iso(events[rec]['ts']) if rec is not None else None,'trade_count_to_trough':(trough-start+1 if start>=0 else 0),'trade_count_to_recovery':(rec-start+1 if rec is not None and start>=0 else None),'slice':[start,trough,rec]}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};F={}
  for sym in ASSETS:
   F[sym]=funding(sym);rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     rows+=mon(sym,y,m)
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
  vh=[x for x in rv[i-VOL_LOOK:i] if x is not None];vth=qtl(vh,VOL_Q)
  if rv[i]>vth:continue
  vals=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None];dth=qtl(vals,DEV_Q);cand=max(ASSETS,key=lambda s:abs(dev[s][i]))
  if abs(dev[cand][i])<=dth:continue
  side='SHORT' if dev[cand][i]>0 else 'LONG';entry_t=common[i+1];exit_t=common[i+HOLD];entry=data[cand][entry_t][0];exitp=data[cand][exit_t][0];price=exitp/entry-1 if side=='LONG' else entry/exitp-1
  fr=sum(rate for t,rate in F[cand].items() if entry_t<t<=exit_t);fund=-fr if side=='LONG' else fr;gross=price+fund
  pre_ret=sum(market[max(1,i-42+1):i+1]);disp=sd([dev[s][i] for s in ASSETS]);events.append({'ts':ts,'asset':cand,'side':side,'price':price,'funding':fund,'gross':gross,'net10':gross-COST,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS','rv_ratio':rv[i]/vth if vth else None,'dev_ratio':abs(dev[cand][i])/dth if dth else None,'basket_ret42':pre_ret,'dispersion':disp});last=i
 o=[x for x in events if x['period']=='OOS'];baseline=st([x['net10'] for x in o]);ok=baseline['n']==101 and abs(baseline['mean']-0.00335499)<5e-6 and abs((baseline['pf'] or 0)-1.321827)<5e-4
 if not ok:emit(out,'EVIDENCE-FAIL',reason='parent aggregate reproduction mismatch',reproduced_10bps=baseline,parameter_tuning=False);return
 per_asset={a:st([x['net10'] for x in o if x['asset']==a]) for a in ASSETS};per_side_asset={s:{a:st([x['net10'] for x in o if x['side']==s and x['asset']==a]) for a in ASSETS} for s in ['LONG','SHORT']}
 months=defaultdict(list);quarters=defaultdict(list)
 for x in o:
  d=datetime.fromtimestamp(x['ts'],timezone.utc);months[d.strftime('%Y-%m')].append(x['net10']);quarters[f'{d.year}-Q{(d.month-1)//3+1}'].append(x['net10'])
 dd=dd_anatomy(o);a,b,c=dd['slice'];worst=o[a:(c+1 if c is not None else b+1)] if a>=0 else []
 loss_share=pctshares([x['net10'] for x in o],True);win_share=pctshares([x['net10'] for x in o],False);loss_by_asset=defaultdict(float);loss_by_side=defaultdict(float);all_loss=-sum(min(0,x['net10']) for x in o)
 for x in o:
  if x['net10']<0:loss_by_asset[x['asset']]+=-x['net10'];loss_by_side[x['side']]+=-x['net10']
 loss_conc={'asset_share':{k:v/all_loss for k,v in sorted(loss_by_asset.items(),key=lambda z:z[1],reverse=True)},'side_share':{k:v/all_loss for k,v in loss_by_side.items()},'top_loss_trade_share':loss_share,'top_win_trade_share':win_share}
 funding_dd=sum(x['funding'] for x in worst);price_dd=sum(x['price'] for x in worst);net_dd=sum(x['net10'] for x in worst)
 cov={}
 for k in ['rv_ratio','dev_ratio','basket_ret42','dispersion']:
  los=[x[k] for x in o if x['net10']<0 and x[k] is not None];win=[x[k] for x in o if x['net10']>0 and x[k] is not None];cov[k]={'loss_mean':sum(los)/len(los) if los else None,'win_mean':sum(win)/len(win) if win else None}
 max_asset=max(loss_conc['asset_share'].values()) if loss_conc['asset_share'] else 0;max_month=max((-sum(min(0,v) for v in vals) for vals in months.values()),default=0);month_loss_share=max_month/all_loss if all_loss else 0
 labels=[]
 if max_asset>=0.40 or month_loss_share>=0.40:labels.append('DRAWDOWN-CONCENTRATED')
 else:labels.append('DRAWDOWN-DIVERSIFIED')
 if cov['rv_ratio']['loss_mean'] is not None and cov['rv_ratio']['win_mean'] is not None and cov['rv_ratio']['loss_mean']>cov['rv_ratio']['win_mean']*1.15:labels.append('STRUCTURAL-STRESS-SENSITIVITY')
 strongest=[f'Largest asset share of OOS losses: {max_asset*100:.1f}%; largest single-month share of losses: {month_loss_share*100:.1f}%.',f'Top-5 losing trades account for {loss_share["5"]*100:.1f}% of losses vs top-5 winners {win_share["5"]*100:.1f}% of gains.',f'Worst drawdown window price contribution sum {price_dd*100:.2f}% vs funding {funding_dd*100:.2f}% across {len(worst)} trades; funding is not treated as causal unless material.']
 emit(out,'OUTCOME-COMPLETE',parent=PARENT,parent_reproduction_10bps=baseline,event_count=len(events),oos_event_count=len(o),diagnostic_labels=labels,per_asset=per_asset,per_side_asset=per_side_asset,monthly={k:st(v) for k,v in sorted(months.items())},quarterly={k:st(v) for k,v in sorted(quarters.items())},drawdown=dd,loss_concentration=loss_conc,loss_streaks=streaks([x['net10'] for x in o]),worst_drawdown_components={'price_sum':price_dd,'funding_sum':funding_dd,'net10_sum':net_dd,'trades':len(worst)},signal_state_covariates=cov,strongest_observations=strongest,next_empirical_object='SL-VAL-TREND-PULLBACK-CONTEXT-ANATOMY-001',parameter_tuning=False,limitations=['descriptive OOS anatomy only','same sample cannot validate discovered filters','stress dates not externally narrative-fit','fixed Binance USD-M 8-asset basket'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
