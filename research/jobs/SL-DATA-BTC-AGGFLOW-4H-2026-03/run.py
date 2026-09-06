import argparse,csv,hashlib,io,json,os,tempfile,urllib.request,zipfile
from pathlib import Path
OBJECT_ID='SL-DATA-BTC-AGGFLOW-4H-2026-03'
Y=2026;M=3
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def main(out,job):
 if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
 p=Path(out);p.mkdir(parents=True,exist_ok=True);n=f'BTCUSDT-aggTrades-{Y}-{M:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/{n}'
 try:
  expected=get(u+'.CHECKSUM').decode().split()[0].lower();h=hashlib.sha256()
  with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as t:
   tmp=t.name
   with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30) as r:
    while True:
     z=r.read(1024*1024)
     if not z:break
     h.update(z);t.write(z)
  actual=h.hexdigest()
  if actual!=expected:os.unlink(tmp);raise ValueError('checksum')
  buckets={}
  try:
   with zipfile.ZipFile(tmp) as q:
    rd=csv.DictReader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0])))
    for x in rd:
     try:ts=int(x.get('transact_time') or x.get('T') or x.get('timestamp'));qty=float(x.get('quantity') or x.get('q'));maker=str(x.get('is_buyer_maker') or x.get('m')).lower()=='true'
     except:continue
     sec=ts/1e6 if ts>10**14 else ts/1e3;b=int(sec//14400*14400);a=buckets.setdefault(b,[0.,0.])
     if maker:a[1]+=qty
     else:a[0]+=qty
  finally:os.unlink(tmp)
  dest=p/f'btc_usdm_aggflow_4h_{Y}_{M:02d}.csv'
  with dest.open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['bucket_ts','aggressive_buy_base','aggressive_sell_base','imbalance'])
   for b,(buy,sell) in sorted(buckets.items()):w.writerow([b,buy,sell,(buy-sell)/(buy+sell) if buy+sell else 0.])
  emit(out,'EVIDENCE_READY',month=f'{Y}-{M:02d}',rows=len(buckets),dataset=dest.name,dataset_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),source_url=u,source_sha256=actual,parameter_tuning=False)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
