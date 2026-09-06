import argparse,csv,hashlib,io,json,os,tempfile,urllib.request,zipfile
from pathlib import Path
OBJECT_ID='SL-DATA-BTC-AGGFLOW-4H-CACHE-001'
CACHE=Path('/tmp/mh-sl-btc-aggflow-4h-cache-v1')
MONTHS=[(y,m) for y in (2025,2026) for m in range(1,13) if (y<2026 or m<=7)]
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def build(y,m):
 CACHE.mkdir(parents=True,exist_ok=True);dest=CACHE/f'{y}-{m:02d}.csv'
 if dest.exists():return 'cached'
 n=f'BTCUSDT-aggTrades-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/{n}'
 expected=get(u+'.CHECKSUM').decode().split()[0].lower();h=hashlib.sha256()
 with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as t:
  tmp=t.name
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30) as r:
   while True:
    z=r.read(1024*1024)
    if not z:break
    h.update(z);t.write(z)
 if h.hexdigest()!=expected:os.unlink(tmp);raise ValueError('checksum '+n)
 b={}
 try:
  with zipfile.ZipFile(tmp) as q:
   rd=csv.DictReader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0])))
   for x in rd:
    try:ts=int(x.get('transact_time') or x.get('T') or x.get('timestamp'));qty=float(x.get('quantity') or x.get('q'));maker=str(x.get('is_buyer_maker') or x.get('m')).lower()=='true'
    except:continue
    sec=ts/1e6 if ts>10**14 else ts/1e3;k=int(sec//14400*14400);a=b.setdefault(k,[0.,0.])
    if maker:a[1]+=qty
    else:a[0]+=qty
 finally:os.unlink(tmp)
 tmpout=dest.with_suffix('.tmp')
 with tmpout.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['bucket_ts','aggressive_buy_base','aggressive_sell_base'])
  for k,(buy,sell) in sorted(b.items()):w.writerow([k,buy,sell])
 os.replace(tmpout,dest);return expected
def main(out,job):
 if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
 try:
  for y,m in MONTHS:build(y,m)
  files=[CACHE/f'{y}-{m:02d}.csv' for y,m in MONTHS]
  if not all(x.exists() for x in files):raise ValueError('incomplete cache')
  merged=Path(out)/'btc_usdm_aggflow_4h_2025-01_2026-07.csv';Path(out).mkdir(parents=True,exist_ok=True)
  h=hashlib.sha256();rows=0
  with merged.open('wb') as w:
   header=b'bucket_ts,aggressive_buy_base,aggressive_sell_base\n';w.write(header);h.update(header)
   for f in files:
    with f.open('rb') as r:
     r.readline()
     for line in r:w.write(line);h.update(line);rows+=1
  emit(out,'EVIDENCE_READY',months=len(files),rows=rows,dataset=merged.name,dataset_sha256=h.hexdigest(),cache=str(CACHE),parameter_tuning=False)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
