#!/usr/bin/env python3
"""Render a complete static site: content works without JavaScript."""
import json,shutil,re
from pathlib import Path
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from jinja2 import Environment,FileSystemLoader,select_autoescape
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist'

def safeurl(value):
 if not isinstance(value,str):return '#'
 p=urlparse(value)
 return value if p.scheme in ('http','https','mailto','tel') and (p.scheme in ('mailto','tel') or p.netloc) else '#'
def fmt(value,with_time=False):
 if not value:return 'Not yet retrieved'
 try:
  dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
  if dt.tzinfo:dt=dt.astimezone(ZoneInfo('Europe/London'))
  return dt.strftime('%d %b %Y'+(' at %H:%M %Z' if with_time else ''))
 except (ValueError,TypeError):return str(value)
def read(name):
 try:return json.loads((ROOT/'data'/f'{name}.json').read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {'key':name,'source':'https://github.com/srupindersingh2010/Dudley-Sonia--MP','status':'unavailable','data':{'items':[],'note':'This source has not been retrieved yet.'}}
def map_svg(crime):
 g=crime.get('geometry');points=crime.get('points',[])
 if not g:return None
 polygons=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
 coords=[p for poly in polygons for ring in poly for p in ring];xs=[p[0] for p in coords];ys=[p[1] for p in coords]
 xmin,xmax=min(xs),max(xs);ymin,ymax=min(ys),max(ys)
 # Equirectangular projection corrected for latitude; equal scales in km.
 import math
 factor=math.cos(math.radians((ymin+ymax)/2));scale=min(560/((xmax-xmin)*factor),360/(ymax-ymin))
 def xy(lon,lat):return (20+(lon-xmin)*factor*scale,20+(ymax-lat)*scale)
 paths=[]
 for poly in polygons:
  for ring in poly:
   paths.append('M'+' L'.join(f'{xy(*p)[0]:.1f},{xy(*p)[1]:.1f}' for p in ring)+' Z')
 dots=[{'x':round(xy(p['lon'],p['lat'])[0],1),'y':round(xy(p['lon'],p['lat'])[1],1)} for p in points]
 return {'path':' '.join(paths),'points':dots}
def main():
 OUT.mkdir(exist_ok=True)
 for p in OUT.iterdir():
  if p.is_file():p.unlink()
 shutil.copytree(ROOT/'assets',OUT/'assets',dirs_exist_ok=True);shutil.copytree(ROOT/'data',OUT/'data',dirs_exist_ok=True)
 (OUT/'.nojekyll').write_text('')
 config=json.loads((ROOT/'config.json').read_text());data={p.stem:read(p.stem) for p in (ROOT/'data').glob('*.json')};data.pop('meta',None)
 env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=select_autoescape(['html']))
 env.filters.update(url=safeurl,date=fmt)
 pages=[('index','Overview'),('parliament','In Parliament'),('community','Dudley & events'),('safety','Policing & safety'),('help','Get help'),('sources','Sources & status'),('privacy','Privacy')]
 today=datetime.now(ZoneInfo('Europe/London')).date()
 meetings=[]
 for key in ['council_meetings','wmca_meetings']:
  for item in data.get(key,{}).get('data',{}).get('items',[]):
   if today.isoformat()<=item.get('date','')[:10]<=(today+timedelta(days=30)).isoformat():meetings.append({**item,'authority':'Dudley Council' if key=='council_meetings' else 'WMCA'})
 meetings.sort(key=lambda x:x.get('date',''))
 context={'config':config,'data':data,'pages':pages,'today':today.isoformat(),'meetings':meetings,'crime_map':map_svg(data.get('crime',{}).get('data',{})),'checked':read('meta').get('checked_at'),'statuses':{s:sum(v.get('status')==s for v in data.values()) for s in ['ok','stale','unavailable']}}
 for slug,title in pages:
  (OUT/(slug+'.html')).write_text(env.get_template('page.html').render(**context,page=slug,page_title=title))
 print(f'Built {len(pages)} static pages in {OUT}')
if __name__=='__main__':main()
