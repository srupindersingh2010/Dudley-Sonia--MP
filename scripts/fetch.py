#!/usr/bin/env python3
"""Fetch each source independently; preserve last successful payload on error."""
import argparse,json,os,sys,time,threading
from urllib.parse import urlsplit
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from core_sources import SOURCES as CORE
from police_sources import SOURCES as POLICE

_police_lock=threading.Lock()
_police_last=0.0
def get(url,**kwargs):
 kwargs.setdefault('timeout',30)
 kwargs.setdefault('headers',{'User-Agent':'DudleyPublicInformation/1.0 (+https://github.com/srupindersingh2010/Dudley-Sonia--MP)'})
 # No automatic retry storm. Per-source failure preserves last good data.
 global _police_last
 for attempt in range(3):
  if urlsplit(url).hostname=='data.police.uk':
   with _police_lock:
    time.sleep(max(0,1.1-(time.monotonic()-_police_last)))
    _police_last=time.monotonic()
  r=requests.get(url,**kwargs)
  if r.status_code!=429 or attempt==2:break
  try:delay=min(25,max(3,float(r.headers.get('Retry-After',6))))
  except ValueError:delay=6
  time.sleep(delay)
 r.raise_for_status();return r

def load(path,default):
 try:return json.loads(path.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default

def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def refresh(key,url,fn,ctx,data_dir):
 path=data_dir/(key+'.json');old=load(path,{})
 stamp=ctx['now'].astimezone(timezone.utc).isoformat(timespec='seconds')
 try:
  result=fn({**ctx,'previous':old.get('data',{})})
  if not isinstance(result,dict) or not isinstance(result.get('items'),list):raise ValueError('Invalid source payload')
  out={'key':key,'source':url,'retrieved_at':stamp,'checked_at':stamp,'status':'ok','error':None,'data':result}
 except Exception as e:
  # Only publish safe error class/status, never server bodies or secret calendar URLs.
  response=getattr(e,'response',None)
  reason=f'HTTP {response.status_code}' if response is not None else type(e).__name__
  out={**old,'key':key,'source':url,'retrieved_at':old.get('retrieved_at'),'checked_at':stamp,'status':'stale' if old.get('retrieved_at') else 'unavailable','error':reason,'data':old.get('data',{'items':[],'note':'Automatic retrieval is currently unavailable. Use the original source below.'})}
 atomic(path,out);return key,out['status'],len(out['data']['items'])

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--only',nargs='*');args=ap.parse_args()
 config=load(ROOT/'config.json',{});now=datetime.now(ZoneInfo('Europe/London'))
 sources={**CORE,**POLICE}
 from parliament_sources import SOURCES as PARLIAMENT
 from local_sources import SOURCES as LOCAL
 from petition_sources import SOURCES as PETITIONS
 sources.update(PARLIAMENT);sources.update(LOCAL);sources.update(PETITIONS)
 if args.only:sources={k:v for k,v in sources.items() if k in args.only}
 ctx={'get':get,'now':now,'config':config,'root':ROOT}
 statuses=[]
 with ThreadPoolExecutor(max_workers=5) as ex:
  futures=[ex.submit(refresh,k,u,fn,ctx,ROOT/'data') for k,(u,fn) in sources.items()]
  for f in as_completed(futures):
   v=f.result();statuses.append(v);print(*v,flush=True)
 atomic(ROOT/'data'/'meta.json',{'checked_at':now.isoformat(),'timezone':'Europe/London','sources':{p.stem:load(p,{}).get('status') for p in sorted((ROOT/'data').glob('*.json')) if p.stem!='meta'}})
 return 0
if __name__=='__main__':raise SystemExit(main())
