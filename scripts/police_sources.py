"""Police open data scoped to the published constituency geometry."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from shapely.geometry import shape,Polygon,Point
API='https://data.police.uk/api'
GEOMETRY='https://members-api.parliament.uk/api/Location/Constituency/4019/Geometry'
def geometry(c):
 import json
 v=c['get'](GEOMETRY).json()['value'];g=json.loads(v) if isinstance(v,str) else v
 if not shape(g).is_valid:raise ValueError('Invalid constituency geometry')
 return {'items':[],'geometry':g,'note':'Approximate Dudley constituency boundary supplied by Parliament. This is not a survey boundary.'}
def getgeometry(c):return geometry(c)['geometry']
def crime(c):
 g=getgeometry(c);boundary=shape(g);xmin,ymin,xmax,ymax=boundary.bounds
 month=c['get'](API+'/crime-last-updated').json()['date'][:7]
 poly=f'{ymin},{xmin}:{ymin},{xmax}:{ymax},{xmax}:{ymax},{xmin}'
 raw=c['get'](API+'/crimes-street/all-crime',params={'poly':poly,'date':month},timeout=75).json()
 if not isinstance(raw,list):raise ValueError('Unexpected crime schema')
 counts=Counter();points=[];seen=set()
 for x in raw:
  loc=x.get('location')
  if not loc:continue
  lat=float(loc['latitude']);lon=float(loc['longitude'])
  if not boundary.covers(Point(lon,lat)):continue
  identity=x.get('persistent_id') or f"{x.get('id')}:{x.get('category')}:{lat}:{lon}"
  if identity in seen:continue
  seen.add(identity);counts[x['category']]+=1
  points.append({'lat':lat,'lon':lon,'category':x['category'],'street':loc.get('street',{}).get('name',''),'month':x['month']})
 return {'items':[{'title':k.replace('-',' ').capitalize(),'count':v,'summary':f'{v:,} recorded reports','url':'https://www.police.uk/pu/your-area/west-midlands-police/'} for k,v in counts.most_common()], 'points':points,'geometry':g,'month':month,'total':sum(counts.values()),'note':'Monthly police street-level records, filtered using Parliament’s approximate constituency boundary. Locations are anonymised approximate points, not exact addresses. Counts are reports published in this dataset, not all crime or a measure of individual risk; boundary anonymisation can move points across the edge. British Transport Police records may be included. Reporting has a publication delay.'}
def teams(c):
 boundary=shape(getgeometry(c));neighbourhoods=c['get'](API+'/west-midlands/neighbourhoods').json()
 candidates=[x for x in neighbourhoods if x['id'].startswith('DY')]
 def getteam(x):
  base=API+'/west-midlands/'+x['id'];coords=c['get'](base+'/boundary').json()
  p=Polygon([(float(t['longitude']),float(t['latitude'])) for t in coords])
  if not p.is_valid:p=p.buffer(0)
  if p.intersection(boundary).area<0.000001:return None
  people=c['get'](base+'/people').json();priorities=c['get'](base+'/priorities').json()
  clean=lambda s:BeautifulSoup(s or '', 'html.parser').get_text(' ',strip=True)
  return {'title':x['name'],'url':'https://www.police.uk/pu/your-area/west-midlands-police/','summary':'Neighbourhood overlaps the constituency; coverage is not identical to the parliamentary boundary.','people':[{'name':t['name'],'rank':t.get('rank','')} for t in people],'priorities':[{'issue':clean(t.get('issue')),'action':clean(t.get('action')),'date':t.get('issue-date'),'action_date':t.get('action-date')} for t in priorities]}
 with ThreadPoolExecutor(max_workers=3) as ex:rows=[x for x in ex.map(getteam,candidates) if x]
 if not rows:raise ValueError('No overlapping neighbourhoods found')
 return {'items':rows,'note':'West Midlands Police neighbourhoods intersecting the published approximate Dudley constituency. Priorities and officer lists are supplied by the force; their dates may be older than today’s retrieval.'}
def news(c):
 import feedparser
 u='https://www.westmidlands.police.uk/news/west-midlands/news/GetNewsRss/'
 f=feedparser.parse(c['get'](u).content)
 if not f.get('version'):raise ValueError('Police RSS did not return a valid feed')
 return {'items':[{'title':x.title,'url':x.link,'date':x.get('published',''),'summary':''} for x in f.entries if any(w in (x.get('title','')+' '+x.get('summary','')).lower() for w in ['dudley','sedgley','gornal','pensnett','woodsetton'])][:12],'note':'Police press releases mentioning places in or near Dudley; the news area can extend beyond the constituency.'}
SOURCES={'boundary':(GEOMETRY,geometry),'crime':('https://data.police.uk/',crime),'police_teams':('https://data.police.uk/docs/method/neighbourhoods/',teams),'police_news':('https://www.westmidlands.police.uk/news/',news)}
