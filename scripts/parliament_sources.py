"""Official Hansard, motions and Bill sponsorship adapters.

Query parameter names are taken from each service's published Swagger schema.
Do not drop the queryParameters./parameters. prefixes: unrecognised parameters
can otherwise silently return other Members' records.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

MEMBER = 5274
HANSARD = 'https://hansard-api.parliament.uk/search/contributions/Spoken.json'
EDMS = 'https://oralquestionsandmotions-api.parliament.uk/EarlyDayMotions/list'
BILLS = 'https://bills-api.parliament.uk/api/v1/Bills'


def plain(value):
    return BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True)


def speeches(ctx):
    params = {'queryParameters.memberId': MEMBER, 'queryParameters.house': 'Commons',
              'queryParameters.take': 20, 'queryParameters.skip': 0,
              'queryParameters.orderBy': 'SittingDateDesc'}
    data = ctx['get'](HANSARD, params=params).json()
    if not isinstance(data, dict) or not isinstance(data.get('Results'), list):
        raise ValueError('Hansard response schema changed')
    rows = data['Results']
    if any(row.get('MemberId') != MEMBER for row in rows):
        raise ValueError('Hansard member filter was not applied')
    items = []
    for row in rows:
        day = row['SittingDate'][:10]
        debate = row['DebateSectionExtId']
        contribution = row['ContributionExtId']
        redirect = ctx['get']('https://hansard-api.parliament.uk/search/parlisearchredirect.json',
                              params={'externalId': contribution}).json()
        if not isinstance(redirect, str) or not redirect.startswith('/Commons/'):
            raise ValueError('Hansard contribution URL could not be verified')
        url = urljoin('https://hansard.parliament.uk', redirect)
        items.append({'title': plain(row['DebateSection']), 'date': day, 'url': url,
                      'summary': plain(row.get('ContributionTextFull') or row.get('ContributionText')),
                      'section': row.get('Section'), 'member_id': MEMBER,
                      'id': contribution, 'quote': True})
    return {'items': items, 'total': data.get('SpokenResultCount'),
            'note': 'Latest 20 spoken contributions, including oral questions and interventions. Extracts are Sonia Kumar’s words in the official record, not site commentary. Follow the source link for the full debate and context.'}


def edms(ctx):
    items = []
    skip = 0
    while True:
        params = {'parameters.memberId': MEMBER, 'parameters.includeSponsoredByMember': 'true',
                  'parameters.take': 100, 'parameters.skip': skip}
        data = ctx['get'](EDMS, params=params).json()
        if not isinstance(data, dict) or not data.get('Success') or not isinstance(data.get('Response'), list):
            raise ValueError('Early Day Motions response schema changed')
        rows = data['Response']
        for row in rows:
            detail = ctx['get'](f"https://oralquestionsandmotions-api.parliament.uk/EarlyDayMotion/{row['Id']}").json()
            if not detail.get('Success') or not isinstance(detail.get('Response'), dict):
                raise ValueError('EDM details could not be verified')
            record = detail['Response']
            sponsors = [s for s in record.get('Sponsors', []) if s.get('MemberId') == MEMBER]
            is_primary = row.get('MemberId') == MEMBER
            if not is_primary and not sponsors:
                raise ValueError('EDM member sponsorship filter was not applied')
            withdrawn = any(s.get('IsWithdrawn') for s in sponsors)
            role = 'Tabled by Sonia Kumar' if is_primary else ('Signature withdrawn' if withdrawn else 'Signed by Sonia Kumar')
            items.append({'title': row['Title'], 'date': row['DateTabled'][:10],
                          'url': f"https://edm.parliament.uk/early-day-motion/{row['Id']}",
                          'summary': f"{role}. EDM {row['UINWithAmendmentSuffix']}; {row.get('SponsorsCount', 0)} sponsors.",
                          'id': row['Id'], 'role': role,
                          'motion_text': plain(row.get('MotionText')),
                          'signed_date': sponsors[0].get('CreatedWhen', '')[:10] if sponsors else None})
        total = data.get('PagingInfo', {}).get('Total')
        if total is None:
            raise ValueError('EDM pagination metadata missing')
        skip += len(rows)
        if skip >= total:
            break
        if not rows or skip > 10000:
            raise ValueError('EDM pagination did not complete')
    return {'items': sorted(items, key=lambda i: i['date'], reverse=True),
            'note': 'Motions tabled or signed by Sonia Kumar across published records. An Early Day Motion records an opinion or request; it is not legislation or a scheduled debate. Withdrawn signatures, where present, are identified.'}


def bills(ctx):
    items = []
    skip = 0
    while True:
        data = ctx['get'](BILLS, params={'MemberId': MEMBER, 'Take': 100, 'Skip': skip}).json()
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or 'totalResults' not in data:
            raise ValueError('Bills response schema changed')
        rows = data['items']
        for row in rows:
            detail = ctx['get'](f"{BILLS}/{row['billId']}").json()
            sponsors = [s for s in detail.get('sponsors', []) if (s.get('member') or {}).get('memberId') == MEMBER]
            if not sponsors:
                raise ValueError('Bill member sponsorship filter could not be independently verified')
            role = 'Lead sponsor' if min(s.get('sortOrder', 1) for s in sponsors) == 1 else 'Co-sponsor'
            status = 'Royal Assent' if detail.get('isAct') else (detail.get('currentStage') or {}).get('description', 'See Bill page')
            if detail.get('billWithdrawn'):
                status = 'Withdrawn'
            if detail.get('isDefeated'):
                status = 'Defeated'
            items.append({'title': detail['shortTitle'], 'date': (detail.get('lastUpdate') or '')[:10],
                          'url': f"https://bills.parliament.uk/bills/{row['billId']}",
                          'summary': f'{role}. Stage: {status}.', 'role': role,
                          'description': plain(detail.get('longTitle')), 'id': row['billId']})
        skip += len(rows)
        if skip >= data['totalResults']:
            break
        if not rows or skip > 10000:
            raise ValueError('Bills pagination did not complete')
    return {'items': items,
            'note': 'Bills where the official Bills API lists Sonia Kumar as a sponsor, verified against each Bill’s sponsor list. Other supporting Members named only in proceedings may not be included. The date is the Bill record’s last update, not its introduction date.'}


SOURCES = {
    'speeches': ('https://hansard.parliament.uk/search/Contributions?memberId=5274', speeches),
    'edms': ('https://edm.parliament.uk/early-day-motions?MemberId=5274&IncludeSponsoredByMember=true', edms),
    'bills': ('https://bills.parliament.uk/?SearchTerm=&MemberId=5274', bills),
}
