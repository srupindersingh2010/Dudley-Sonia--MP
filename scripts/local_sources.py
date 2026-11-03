"""Public Dudley sources. No diary or private calendar access."""
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import csv
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from bs4 import BeautifulSoup

COUNCIL = 'https://dudley.cmis.uk.com/Meetings.aspx'
WMCA = 'https://governance.wmca.org.uk/mgCalendarAgendaView.aspx?MR=0'
PROFILE = 'https://www.nomisweb.co.uk/reports/lmp/wpca24/721420430/report.aspx'
LIBRARY = 'https://commonslibrary.parliament.uk/constituency-dashboard/'
EVENTS = 'https://www.dudley.gov.uk/things-to-do/events/'
OWN_RSS = 'https://sonia-kumar.co.uk/feed/'
BBC_RSS = 'https://feeds.bbci.co.uk/news/england/birmingham_and_black_country/rss.xml'
GOOGLE_RSS = 'https://news.google.com/rss/search?q=%22Sonia+Kumar%22&hl=en-GB&gl=GB&ceid=GB:en'


def clean(s):
    return BeautifulSoup(str(s or ''), 'html.parser').get_text(' ', strip=True)


def cmis_appointments(html):
    """Decode the JSON string used by Telerik; never execute remote scripts."""
    match = re.search(r'"appointments"\s*:\s*("(?:\\.|[^"\\])*")', html)
    if not match:
        raise ValueError('CMIS calendar appointment schema not found')
    data = json.loads(json.loads(match.group(1)))
    if not isinstance(data, list):
        raise ValueError('CMIS appointments is not a list')
    return data


def council_meetings(ctx):
    html = ctx['get'](COUNCIL).text
    data = cmis_appointments(html)
    committee_html = ctx['get']('https://dudley.cmis.uk.com/Committees/2015Onwards.aspx').text
    committees = {}
    committee_urls = {}
    for a in BeautifulSoup(committee_html, 'html.parser').select('a[href*="CommitteeDetails"]'):
        match = re.search(r'/id/(\d+)/', a.get('href',''))
        if match:
            name = a.get_text(' ',strip=True)
            committees[name] = match[1]
            committee_urls[name] = a['href'].replace('http://','https://',1)
    if not committees:
        raise ValueError('CMIS committee identifiers could not be resolved')
    today = ctx['now'].date()
    cutoff = today + timedelta(days=30)
    items = []
    for row in data:
        dt = datetime.strptime(row['start'], '%Y/%m/%d %H:%M')
        if not today <= dt.date() <= cutoff:
            continue
        title = re.sub(r'^\d{1,2}:\d{2}\s+', '', row['subject'])
        parts = title.rsplit(' : ', 1)
        mid = int(row['id'])
        cid = committees.get(parts[0])
        meeting_url = f'https://dudley.cmis.uk.com/Meetings/tabid/116/ctl/ViewMeetingPublic/mid/543/Meeting/{mid}/Committee/{cid}/Default.aspx' if cid else COUNCIL
        items.append({'title': parts[0], 'date': dt.isoformat(),
                      'time': dt.strftime('%H:%M'),
                      'location': parts[1] if len(parts) == 2 else '',
                      'url': meeting_url,
                      'summary': 'Dudley Council public committee calendar. Check the agenda for access arrangements and changes.'})
    # Committee schedules extend beyond the calendar month. Their default page is
    # centred on the current date. Preserve successful per-committee snapshots.
    previous = ctx.get('previous', {}).get('committee_cache', {})
    cache, checks = {}, [{'url':COUNCIL,'status':'ok'}]
    stamp = ctx['now'].isoformat()
    def collect(pair):
        name, url = pair
        try:
            rows = parse_committee_schedule(ctx['get'](url).text, name, url)
            return url, {'items': rows, 'retrieved_at': stamp}, {'url':url,'status':'ok','retrieved_at':stamp}
        except Exception as exc:
            old = previous.get(url, {'items': [], 'retrieved_at': None})
            return url, old, {'url':url,'status':'stale' if old.get('retrieved_at') else 'unavailable','retrieved_at':old.get('retrieved_at'),'note':type(exc).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, snapshot, check in pool.map(collect, committee_urls.items()):
            cache[url] = snapshot
            checks.append(check)
            items.extend(r for r in snapshot['items'] if today.isoformat() <= r['date'][:10] <= cutoff.isoformat())
    unique = {r['url']: r for r in items}
    failures = sum(c['status'] != 'ok' for c in checks)
    return {'items': sorted(unique.values(), key=lambda x: x['date']),
            'committee_cache': cache, 'source_checks': checks,
            'note': 'Dudley uses CMIS, not Modern.gov. The next 30 days combine the current public calendar and individual committee schedules. Confirm dates, cancellations and public access on the agenda. These are council meetings, not a record of Sonia Kumar’s attendance.' + (f' {failures} committee schedule(s) unavailable; last successful records retained where available.' if failures else '')}


def parse_committee_schedule(html, name, url):
    soup = BeautifulSoup(html, 'html.parser')
    if 'Committee Details' not in soup.get_text(' ',strip=True) or 'critical error' in soup.get_text().lower():
        raise ValueError('CMIS committee details schema not recognised')
    items = []
    for a in soup.select('a[href*="/Meeting/"]'):
        label = a.get_text(' ',strip=True)
        match = re.match(r'(\d{1,2} [A-Za-z]+ \d{4}) - (\d{1,2}:\d{2})', label)
        if not match:
            raise ValueError('CMIS committee meeting date schema changed')
        dt = datetime.strptime(match[1]+' '+match[2], '%d %B %Y %H:%M')
        tr = a.find_parent('tr')
        cells = [c.get_text(' ',strip=True) for c in tr.find_all('td')] if tr else []
        location = cells[1] if len(cells)>1 else ''
        cancelled = any('cancelled' in c.lower() for c in cells)
        items.append({'title':name + (' (cancelled)' if cancelled else ''),
                      'date':dt.isoformat(),'time':match[2],'location':location,
                      'cancelled':cancelled,'url':urljoin(url,a['href']).replace('http://','https://',1),
                      'summary':'Dudley Council committee schedule. Check the agenda for public access and any changes.'})
    return items


def wmca_meetings(ctx):
    html = ctx['get'](WMCA).text
    soup = BeautifulSoup(html, 'html.parser')
    links = soup.select('a[href*="ieListDocuments.aspx"]')
    if not links and 'Calendar of meetings' not in soup.get_text():
        raise ValueError('WMCA calendar schema not recognised')
    today = ctx['now'].date()
    cutoff = today + timedelta(days=30)
    items, seen = [], set()
    for a in links:
        title = a.get('title', '')
        m = re.search(r'(.+),\s*(\d{1,2}/\d{1,2}/\d{4})\s*(.*)', title)
        if not m:
            raise ValueError('WMCA meeting date schema changed')
        day = datetime.strptime(m[2], '%d/%m/%Y').date()
        url = urljoin(WMCA, a['href'])
        if today <= day <= cutoff and url not in seen:
            seen.add(url)
            li = a.find_parent('li')
            text = li.get_text(' ', strip=True) if li else ''
            location = text.rsplit(' - ', 1)[-1] if ' - ' in text else ''
            items.append({'title': re.sub(r'^Meeting of\s+', '', m[1]),
                          'date': day.isoformat(), 'time': m[3].strip(),
                          'location': location, 'url': url,
                          'summary': 'WMCA board or committee meeting. Confirm public access on the agenda. This does not indicate MP attendance.'})
    return {'items': sorted(items, key=lambda x: (x['date'], x.get('time',''))),
            'note': 'Public WMCA meetings for the next 30 days; meeting dates and access can change.'}


def profile(ctx):
    soup = BeautifulSoup(ctx['get'](PROFILE).text, 'html.parser')
    heading = soup.find('h1')
    if 'Dudley' not in soup.get_text() or 'Parliamentary Constituency' not in soup.get_text():
        raise ValueError('Nomis did not return the Dudley 2024 constituency profile')
    items = []
    specs = [('Population aged 16-64', 'Total', 'Working-age population (16–64)'),
             ('Employment and unemployment', 'In employment', 'People in employment (16–64)'),
             ('Claimant count by sex', 'All people', 'People claiming unemployment-related benefits')]
    for prefix, label, title in specs:
        table = next((t for t in soup.find_all('table') if t.caption and prefix in t.caption.get_text()), None)
        if table is None:
            raise ValueError(f'Nomis table missing: {prefix}')
        row = next((r for r in table.select('tbody tr') if r.find('th') and r.find('th').get_text(' ',strip=True).startswith(label)), None)
        if row is None:
            raise ValueError(f'Nomis row missing: {label}')
        cells = [x.get_text(' ', strip=True) for x in row.find_all('td')]
        value = cells[0]
        if not re.fullmatch(r'[\d,]+(?:\.\d+)?', value):
            raise ValueError(f'Nomis estimate unavailable or suppressed: {label}')
        caption = table.caption.get_text(' ', strip=True)
        period = re.search(r'\(([^)]+)\)', caption)
        period = period[1] if period else caption
        rate = cells[1] + '%' if prefix != 'Population aged 16-64' and len(cells)>1 else ''
        items.append({'title': title, 'value': value, 'rate': rate, 'period': period,
                      'url': PROFILE, 'summary': f'{value}' + (f' ({rate})' if rate else '') + f' · {period}. ONS via Nomis; Dudley constituency on 2024 boundaries.'})
    total_url = 'https://www.nomisweb.co.uk/api/v01/dataset/NM_2014_1.data.csv?geography=721420430&date=latest&gender=0&c_age=200&measures=20100'
    total_rows = list(csv.DictReader(io.StringIO(ctx['get'](total_url).text)))
    if len(total_rows) != 1 or total_rows[0].get('GEOGRAPHY_CODE') != 'E14001204':
        raise ValueError('ONS total population constituency series invalid')
    total = total_rows[0]
    population = float(total['OBS_VALUE'])
    items.insert(0, {'title':'Total population estimate','value':format(population,',.0f'),'period':total['DATE_NAME'],'url':total_url,'summary':format(population,',.0f')+' people · '+total['DATE_NAME']+'. ONS mid-year population estimate, Dudley constituency on 2024 boundaries.'})
    items.extend([
        {'title':'Health conditions: official constituency dashboard', 'url':'https://commonslibrary.parliament.uk/research-briefings/cbp-10868/', 'summary':'Additional health context: modelled estimates of diagnosed health-condition prevalence. Census self-rated health is shown separately below.'},
        {'title':'Housing: official constituency house prices dashboard', 'url':'https://commonslibrary.parliament.uk/constituency-data-house-prices/', 'summary':'Additional housing context: constituency house prices in the Commons Library dashboard. Census social-rented household figures are shown separately below.'}
    ])
    return {'items': items, 'note':'ONS figures are for Dudley constituency (2024 boundaries), not the whole Dudley borough. Each figure has its own reference period. Claimant count is not the unemployment rate; employment survey estimates have sampling uncertainty. Census health and housing indicators are shown separately, with their 2021 reference date and aggregation method.',
            'source_checks':[{'url':PROFILE,'status':'ok'}, {'url':total_url,'status':'ok'}, {'url':LIBRARY,'status':'limited','note':'Dashboard and population XLSX return HTTP 403 to automated requests; health/housing numeric feed not verified.'}]}


def parse_rss(text, source_url, only_mp=True):
    root = ET.fromstring(text)
    if root.tag.lower() not in ('rss', '{http://www.w3.org/2005/atom}feed'):
        raise ValueError('Source did not return RSS/Atom')
    result = []
    for el in root.findall('.//item'):
        title = clean(el.findtext('title'))
        description = clean(el.findtext('description'))
        if only_mp and not re.search(r'\bSonia\s+Kumar\b', title+' '+description, re.I):
            continue
        url = el.findtext('link') or ''
        if not url.startswith('https://'):
            continue
        pub = el.findtext('pubDate') or ''
        try:
            date = parsedate_to_datetime(pub).isoformat()
        except (ValueError, TypeError):
            date = ''
        publisher = el.findtext('source') or ('BBC News' if 'bbci' in source_url else 'Sonia Kumar website')
        result.append({'title':title, 'url':url,'date':date,'publisher':publisher,
                       'summary':f'{publisher} — read the original article.', 'source_url':source_url})
    return result


def news(ctx):
    checks, all_items = [], []
    cache_path = Path(ctx.get('root', Path(__file__).resolve().parents[1]))/'.cache'/'news.json'
    try:
        cached = json.loads(cache_path.read_text())
    except (FileNotFoundError, ValueError):
        cached = ctx.get('previous', {}).get('feed_cache', {})
    stamp = ctx['now'].isoformat()
    for url in (OWN_RSS, BBC_RSS, GOOGLE_RSS):
        try:
            rows = parse_rss(ctx['get'](url).text,url)
            cached[url] = {'items':rows,'retrieved_at':stamp}
            checks.append({'url':url,'status':'ok','matching_items':len(rows),'retrieved_at':stamp})
        except Exception as exc:
            old = cached.get(url, {'items': [],'retrieved_at':None})
            rows = old['items']
            checks.append({'url':url,'status':'stale' if old.get('retrieved_at') else 'unavailable',
                           'retrieved_at':old.get('retrieved_at'),'note':type(exc).__name__})
        for row in rows:
            all_items.append({**row,'source_retrieved_at':cached.get(url,{}).get('retrieved_at')})
    if all(x['status'] not in ('ok','stale') for x in checks):
        raise ValueError('All news feeds failed')
    cache_path.parent.mkdir(parents=True,exist_ok=True)
    temp = cache_path.with_suffix('.tmp')
    temp.write_text(json.dumps(cached,ensure_ascii=False))
    temp.replace(cache_path)
    unique = {}
    for item in all_items:
        unique.setdefault(item['title'].casefold(), item)
    items = sorted(unique.values(),key=lambda x:x.get('date',''),reverse=True)[:20]
    failed = [x['url'] for x in checks if x['status'] != 'ok']
    return {'items':items,'source_checks':checks,'feed_cache':cached,
            'note':'Headlines mentioning Sonia Kumar, with links to publishers. Google News RSS supplements the BBC regional feed; it may include opinion or wider coverage. No article text is republished.' + (' Unavailable feeds: '+', '.join(failed)+'. Last successful feed records retained where available.' if failed else '')}


def community_events(ctx):
    soup = BeautifulSoup(ctx['get'](EVENTS).text,'html.parser')
    if 'Events in the Area' not in soup.get_text():
        raise ValueError('Council events page schema not recognised')
    selected = [
        ('Dudley Council upcoming events','https://www.dudley.gov.uk/events/','Council events listings across Dudley borough.'),
        ('Discover Dudley events','https://discover.dudley.gov.uk/events/','Events, exhibitions, fairs and markets.'),
        ('Dudley Community Information Directory','https://dudleyci.co.uk/','Community clubs, activities and local support.'),
        ('Himley Hall events','https://www.himleyhallandpark.co.uk/events','Public events at Himley Hall and Park.'),
        ('Eventbrite: Dudley','https://www.eventbrite.co.uk/d/united-kingdom--dudley/events/','Third-party listings; check location, organiser, availability and cost.')]
    return {'items':[{'title':t,'url':u,'summary':s} for t,u,s in selected],
            'note':'Community listings are links, not a claim that Sonia Kumar will attend. Council listing links are checked via the source page; third-party listings may change.'}


USEFUL = [
    ('Dudley Council services','https://www.dudley.gov.uk/','Bins, council tax, housing, planning and council services.'),
    ('Report a pothole or road problem','https://www.dudley.gov.uk/residents/parking-and-roads/roads-highways-and-pavements/','Use the council’s roads and highways service to find the appropriate report route.'),
    ('NHS services','https://www.nhs.uk/nhs-services/','Find GP, pharmacy, dentist and other NHS services.'),
    ('Benefits information','https://www.gov.uk/browse/benefits','Official benefits information and application routes.'),
    ('Citizens Advice Dudley and Wolverhampton','https://www.citizensadvicedudley.org/','Independent advice on money, benefits, housing and employment.'),
    ('Black Country Foodbank','https://www.blackcountryfoodbank.org.uk/','Find local food support and referral information.'),
    ('Dudley cost of living support','https://www.dudley.gov.uk/council-community/cost-of-living/','Local support for household costs.'),
    ('Dudley Community Information Directory','https://dudleyci.co.uk/','Search community support services and local organisations.')]

def useful_links(ctx):
    # These are a curated directory, never medical, financial or casework advice.
    ctx['get']('https://www.dudley.gov.uk/')
    return {'items':[{'title':t,'url':u,'summary':s} for t,u,s in USEFUL],
            'note':'Curated service directory. The council homepage is checked daily; individual service pages are maintained by their organisations. Contact the service directly to confirm eligibility and availability. This website does not collect casework.'}


SOURCES = {
    'council_meetings':(COUNCIL,council_meetings),
    'wmca_meetings':(WMCA,wmca_meetings),
    'profile':(PROFILE,profile),
    'news':(GOOGLE_RSS,news),
    'community_events':(EVENTS,community_events),
    'useful_links':('https://www.dudley.gov.uk/',useful_links),
}


ONS_COMPONENTS = 'https://ons-dp-prod-cdn.s3.eu-west-2.amazonaws.com/maptiles/ap-geos/v4/E14/E14001204.json'


def census_components(area):
    """ONS customprofiles stores a compressed partition: whole MSOAs, whole
    LSOAs and remaining OAs. Use its single oa21cds partition, never combine
    it with lsoa21cds/msoa21cds (which would overlap and double count).
    """
    props = area.get('properties',{})
    if props.get('areacd') != 'E14001204' or props.get('groupcd') != 'wpc' or props.get('start') != 2024:
        raise ValueError('ONS lookup does not describe current Dudley constituency')
    codes = props.get('oa21cds')
    if not isinstance(codes,list) or not codes or len(set(codes)) != len(codes):
        raise ValueError('ONS component partition empty or contains duplicate areas')
    if any(not re.fullmatch(r'E0[012]\d{6}',code) for code in codes):
        raise ValueError('ONS partition contains an unexpected geography level')
    return codes


def sum_census_partition(text, codes, dimension):
    rows = list(csv.DictReader(io.StringIO(text)))
    expected = {(code,cell) for code in codes for cell in ('0','4','5')}
    seen, totals = set(), {'0':0,'4':0,'5':0}
    for row in rows:
        key = (row.get('GEOGRAPHY_CODE'),row.get(dimension))
        if key not in expected or key in seen:
            raise ValueError('Census response contains duplicate or unexpected geography/cell')
        if row.get('DATE_NAME') != '2021' or row.get('MEASURES') != '20100':
            raise ValueError('Census response period or measure changed')
        value = float(row['OBS_VALUE'])
        if value < 0 or not value.is_integer() or row.get('OBS_STATUS') != 'A':
            raise ValueError('Census observation unavailable or invalid')
        totals[key[1]] += int(value)
        seen.add(key)
    if seen != expected or not totals['0'] or totals['4']+totals['5']>totals['0']:
        raise ValueError('Census response incomplete or denominator invalid')
    return totals


def profile_census(ctx):
    area = ctx['get'](ONS_COMPONENTS).json()
    codes = census_components(area)
    definitions = [
        ('NM_2055_1','c2021_health_6','Self-rated bad or very bad health','people'),
        ('NM_2072_1','c2021_tenure_9','Social-rented households','households'),
    ]
    items,checks = [],[{'url':ONS_COMPONENTS,'status':'ok'}]
    for dataset,dimension,title,unit in definitions:
        url = 'https://www.nomisweb.co.uk/api/v01/dataset/'+dataset+'.data.csv'
        response = ctx['get'](url,params={'geography':','.join(codes),'date':'2021',dimension:'0,4,5','measures':'20100'})
        totals = sum_census_partition(response.text,codes,dimension.upper())
        numerator = totals['4']+totals['5']
        percentage = 100*numerator/totals['0']
        source_url = getattr(response,'url',url)
        items.append({'title':title,'value':f'{percentage:.1f}%','period':'Census 2021',
                      'numerator':numerator,'denominator':totals['0'],'unit':unit,
                      'url':source_url,
                      'summary':f'{percentage:.1f}% ({numerator:,} of {totals["0"]:,} {unit}) · Census 2021. Aggregated from ONS custom-profile component areas for Dudley’s 2024 constituency.'})
        checks.append({'url':source_url,'status':'ok'})
    return {'items':items,'source_checks':checks,'component_codes':codes,
            'note':'Census 2021 figures aggregated for the current Dudley constituency using ONS’s official compressed partition of output areas, LSOAs and MSOAs (one non-overlapping component list). Boundaries are approximated from Census output areas. Component totals can differ slightly from separately published constituency counts because of statistical disclosure control. Health is residents’ self-assessment, not diagnosed conditions. Social rent combines council and other social-landlord tenures. These historical figures are checked daily but do not describe today’s population.'}


SOURCES['profile_census'] = (ONS_COMPONENTS,profile_census)
