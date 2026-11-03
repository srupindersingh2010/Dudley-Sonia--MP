"""Official parliamentary records. No inferred political positions or attendance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from bs4 import BeautifulSoup

MEM='https://members-api.parliament.uk/api/Members/5274'
VOTES='https://commonsvotes-api.parliament.uk/data'
def clean(value):return BeautifulSoup(value or '', 'html.parser').get_text(' ',strip=True)
def member(c):
 v=c['get'](MEM).json()['value']
 assert v['id']==5274
 h=v['latestHouseMembership'];p=v['latestParty']
 return {'items':[], 'name':v['nameDisplayAs'],'party':p['name'],'constituency':h['membershipFrom'],'elected':h['membershipStartDate'][:10], 'portrait':'https://members-api.parliament.uk/api/Members/5274/Portrait?cropType=ThreeFour','note':'Official Parliament member record. Portrait: UK Parliament, licensed under the Parliamentary Copyright Licence.'}
def portrait(c):
 r=c['get'](MEM+'/Portrait',params={'cropType':'ThreeFour'})
 if 'image/' not in r.headers.get('Content-Type','') or len(r.content)<1000:raise ValueError('Portrait response invalid')
 p=c['root']/'assets'/'sonia-kumar.jpg';tmp=p.with_suffix('.tmp');tmp.write_bytes(r.content);tmp.replace(p)
 return {'items':[],'note':'Official UK Parliament portrait; Parliamentary Copyright Licence applies.'}
def biography(c):
 v=c['get'](MEM+'/Biography').json()['value'];rows=[]
 for key in ['governmentPosts','oppositionPosts','otherPosts','committeeMemberships']:
  for x in v[key]:
   if not x.get('endDate'):rows.append({'title':x['name'],'date':x['startDate'][:10],'url':'https://members.parliament.uk/member/5274/career','summary':key})
 return {'items':rows,'note':'Current roles published by Parliament. An empty list means no current posts in these API categories. PPS posts and APPGs may not be fully covered; see the separate role sources.'}
def election(c):
 v=c['get'](MEM+'/LatestElectionResult').json()['value']
 return {'items':[{'title':v['electionTitle'],'date':v['electionDate'][:10],'url':'https://members.parliament.uk/member/5274/electionresult','summary':f"Majority: {v['majority']:,}. Electorate: {v['electorate']:,}. Ballots cast: {v['turnout']:,}."}], 'majority':v['majority'],'election_date':v['electionDate'][:10]}
def contact(c):
 v=c['get'](MEM+'/Contact').json()['value'];rows=[]
 for x in v:
  if x['isWebAddress']:
   rows.append({'title':x['type'],'url':x.get('website') or x['line1'],'summary':'Account linked from Parliament.'});continue
  address=', '.join(x[k] for k in ['line1','line2','line3','line4','line5','postcode'] if x.get(k))
  rows.append({'title':x['type'],'url':'https://members.parliament.uk/member/5274/contact','summary':address,'email':x.get('email'),'phone':x.get('phone')})
 return {'items':rows,'note':'For a surgery appointment contact the MP’s office through its official email or telephone. Confirm the location before visiting. Casework is for constituents; this site collects no casework.'}
def votes(c):
 start=(c['now'].date()-timedelta(days=90)).isoformat();end=c['now'].date().isoformat();allrows=[];skip=0
 while True:
  v=c['get'](VOTES+'/divisions.json/search',params={'queryParameters.startDate':start,'queryParameters.endDate':end,'queryParameters.take':100,'queryParameters.skip':skip}).json()
  if not isinstance(v,list):raise ValueError('Unexpected divisions schema')
  allrows.extend(v)
  if len(v)<100:break
  skip+=100
  if skip>5000:raise ValueError('Division pagination exceeded safe limit')
 previous={x.get('division_id'):x for x in c.get('previous',{}).get('items',[])}
 def detail(x):
  old=previous.get(x['DivisionId'])
  if old and old.get('publication_updated')==x.get('PublicationUpdated'):return old
  d=c['get'](VOTES+f"/division/{x['DivisionId']}.json").json();vote='No recorded vote'
  for k,label in [('Ayes','Aye'),('Noes','No'),('AyeTellers','Aye (teller)'),('NoTellers','No (teller)')]:
   if any(m['MemberId']==5274 for m in (d[k] or [])):vote=label
  return {'title':d['Title'],'date':d['Date'],'url':f"https://votes.parliament.uk/votes/commons/division/{d['DivisionId']}",'summary':vote,'vote':vote,'division_id':d['DivisionId'],'publication_updated':d.get('PublicationUpdated')}
 with ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(detail,allrows))
 rows.sort(key=lambda x:x['date'],reverse=True);participated=sum(x['vote']!='No recorded vote' for x in rows)
 return {'items':rows,'period_start':start,'period_end':end,'total_divisions':len(rows),'recorded_votes':participated,'participation_percent':round(100*participated/len(rows),1) if rows else None,'note':'Recorded voting participation over the last 90 days: recorded votes (including tellers) divided by all published Commons divisions in that period. This is not a measure of attendance in Parliament. No recorded vote does not establish absence or the reason, and is not automatically an abstention. Read the exact division motion before interpreting a vote.'}
def questions(c):
 v=c['get']('https://questions-statements-api.parliament.uk/api/writtenquestions/questions',params={'askingMemberId':5274,'take':20}).json();rows=[]
 for r in v['results']:
  x=r['value'];assert x['askingMemberId']==5274
  rows.append({'title':x.get('heading') or x['questionText'],'date':x['dateTabled'],'url':f"https://questions-statements.parliament.uk/written-questions/detail/{x['dateTabled'][:10]}/{x['uin']}",'summary':clean(x['questionText']),'answer':clean(x.get('answerText')),'answered':x.get('dateAnswered'),'department':x.get('answeringBodyName')})
 return {'items':rows,'note':'Latest 20 written questions. Answers in the search feed may be shortened; follow the original record for the full answer.'}
def interests(c):
 base='https://interests-api.parliament.uk/api/v1/Interests';v=c['get'](base,params={'MemberId':5274,'Take':100,'ExpandChildInterests':'true'}).json()
 if v['totalResults']>100:raise ValueError('Interests pagination required')
 return {'items':[{'title':x['summary'],'date':x.get('publishedDate'),'summary':x['category']['name'],'url':'https://members.parliament.uk/member/5274/registeredinterests'} for x in v['items']], 'note':'Published register entries, not allegations of wrongdoing. Read the official register for full amounts, donors, amendments and historical entries.'}
def whatson(c):
 today=c['now'].date();mon=today-timedelta(days=today.weekday());sun=mon+timedelta(days=6)
 v=c['get']('https://whatson-api.parliament.uk/calendar/events/list.json',params={'startdate':mon.isoformat(),'enddate':sun.isoformat()}).json()
 if not isinstance(v,list):raise ValueError('Unexpected calendar schema')
 rows=[]
 for x in v:
  if x.get('House')!='Commons':continue
  title=x.get('Description') or (x.get('Committee') or {}).get('Description') or x.get('Type') or 'Commons business'
  inquiries='; '.join(t.get('Description','') for t in (x.get('Committee') or {}).get('Inquiries',[]))
  rows.append({'title':title,'date':x['StartDate'][:10]+('T'+x['StartTime'] if x.get('StartTime') else ''),'url':(f"https://committees.parliament.uk/event/{x['Id']}" if x.get('Committee') else f"https://whatson.parliament.uk/event/cal{x['Id']}"),'summary':'; '.join(filter(None,[x.get('Type'),x.get('Location'),inquiries])),'cancelled':bool(x.get('CancelledDate'))})
 return {'items':sorted(rows,key=lambda x:x['date']),'note':f'Commons business for {mon.isoformat()} to {sun.isoformat()}. This is the House’s schedule, not Sonia Kumar’s diary or evidence of her attendance.'}
SOURCES={
'member':(MEM,member),'portrait':(MEM+'/Portrait',portrait),'biography':(MEM+'/Biography',biography),'election':(MEM+'/LatestElectionResult',election),'contact':(MEM+'/Contact',contact),
'votes':('https://votes.parliament.uk/votes/commons',votes),'questions':('https://questions-statements.parliament.uk/written-questions',questions),
'interests':('https://members.parliament.uk/member/5274/registeredinterests',interests),'whatson':('https://whatson.parliament.uk/',whatson)}
