"""Exact ranking of open petitions by Dudley signatures, with a bounded-request cache.

The listing's national count is an upper bound on a petition's local count. We
scan in descending national order and stop only when no unscanned petition can
enter the local top ten. No national-signature threshold is imposed.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from urllib.parse import urlparse, parse_qs

BASE = 'https://petition.parliament.uk'
LIST = BASE + '/petitions.json?state=open'
ONS_CODE = 'E14001204'
CACHE = Path(__file__).resolve().parents[1] / '.cache' / 'petitions.json'


def _get_json(ctx, url):
    if urlparse(url).hostname != 'petition.parliament.uk':
        raise ValueError('Unexpected petition source host')
    response = ctx['get'](url)
    return response.json()


def _listing(ctx):
    first = _get_json(ctx, LIST)
    if not isinstance(first.get('data'), list):
        raise ValueError('Invalid petitions listing')
    last_url = first.get('links', {}).get('last') or LIST
    last_page = int(parse_qs(urlparse(last_url).query).get('page', ['1'])[0])
    if not 1 <= last_page <= 1000:
        raise ValueError('Unexpected petitions page count')
    rows = list(first['data'])
    def page(number):
        data = _get_json(ctx, f'{BASE}/petitions.json?state=open&page={number}')
        if not isinstance(data.get('data'), list):
            raise ValueError('Invalid petitions page')
        return data['data']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for chunk in pool.map(page, range(2, last_page + 1)):
            rows.extend(chunk)
    # A petition may move pages while signatures change. De-duplicate safely;
    # no claim is made that the live service is a transactionally frozen snapshot.
    seen = {}
    for row in rows:
        if row['attributes'].get('state') == 'open':
            seen[str(row['id'])] = row
    return sorted(seen.values(), key=lambda row: (-int(row['attributes']['signature_count']), str(row['id'])))


def fetch_petitions(ctx):
    rows = _listing(ctx)
    try:
        cache = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    matches = []
    examined = 0
    fetched = 0
    threshold = None
    failure = None

    def detail(row):
        key = str(row['id'])
        attrs = row['attributes']
        previous = cache.get(key)
        # updated_at changes when the source data changes; use cached details
        # only for this identical version of the listing item.
        if previous and previous.get('version') == attrs.get('updated_at'):
            return key, previous, False
        data = _get_json(ctx, f'{BASE}/petitions/{key}.json')
        value = data['data']['attributes']
        if not isinstance(value.get('signatures_by_constituency'), list):
            raise ValueError('Petition lacks constituency breakdown')
        constituency = next((entry for entry in value['signatures_by_constituency']
                             if entry.get('ons_code') == ONS_CODE and entry.get('name') == 'Dudley'), None)
        # No Dudley entry means zero signatures, not a national count fallback.
        local = int(constituency['signature_count']) if constituency else 0
        return key, {'version': attrs.get('updated_at'), 'local': local,
                     'national': int(value['signature_count']), 'state': value['state'],
                     'title': value['action'], 'closing_date': value['closing_date']}, True

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, len(rows), 16):
                # Stopping threshold includes ties (scan equality too).
                if threshold is not None and int(rows[start]['attributes']['signature_count']) < threshold:
                    break
                for key, value, was_fetched in pool.map(detail, rows[start:start + 16]):
                    cache[key] = value
                    examined += 1
                    fetched += int(was_fetched)
                    if value['state'] != 'open':
                        continue
                    matches.append({'title': value['title'], 'url': f'{BASE}/petitions/{key}',
                                    'date': value['closing_date'], 'local_signatures': value['local'],
                                    'national_signatures': value['national'],
                                    'summary': f"{value['local']:,} signatures from Dudley; {value['national']:,} nationally. Closes {value['closing_date']}.",
                                    'ons_code': ONS_CODE})
                matches.sort(key=lambda item: (-item['local_signatures'], item['url']))
                if len(matches) >= 10:
                    threshold = matches[9]['local_signatures']
                if examined % 128 == 0 or examined == len(rows):
                    print(f'  Petitions: checked {examined}/{len(rows)} candidates; local top-10 cutoff {threshold}', flush=True)
    except Exception as exc:
        failure = exc
    finally:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        # Save successful cache progress even if one upstream request failed.
        temporary = CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps(cache, ensure_ascii=False))
        temporary.replace(CACHE)
    if failure:
        raise RuntimeError(f'Incomplete petition ranking; keeping last complete snapshot ({type(failure).__name__})') from failure
    return {'items': matches[:10], 'candidate_count': len(rows), 'examined_count': examined,
            'detail_requests': fetched,
            'note': 'Open petitions ranked by signatures recorded in Dudley (ONS E14001204), not national totals. All open-petition listing pages checked; candidates eliminated only when national signatures are below the local top-ten cutoff. Live counts can change during collection. Petition signatures are not an opinion poll.'}


SOURCES = {'petitions': (LIST, fetch_petitions)}
