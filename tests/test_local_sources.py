import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import local_sources as ls

class Response:
    def __init__(self,text): self.text=text

class LocalSourceTests(unittest.TestCase):
    def test_cmis_json_decodes_without_executing_script(self):
        rows=[{'id':12,'subject':'18:00 Cabinet : Chamber','start':'2026/11/05 18:00'}]
        html='<script>notExecuted(); x={"appointments":'+json.dumps(json.dumps(rows))+'};</script>'
        self.assertEqual(ls.cmis_appointments(html),rows)
        with self.assertRaises(ValueError):ls.cmis_appointments('<h1>Critical error</h1>')

    def test_committee_schedule_preserves_cancellation_and_agenda(self):
        html='''<h1>Cabinet</h1><p>Committee Details</p><table><tr><td><a href="/Meetings/Meeting/12/Committee/468/Default.aspx">05 December 2026 - 18:00 : TBC</a></td><td>Council Chamber</td><td>Cancelled</td></tr></table>'''
        rows=ls.parse_committee_schedule(html,'Cabinet','https://dudley.cmis.uk.com/Committees/x')
        self.assertEqual(rows[0]['date'],'2026-12-05T18:00:00')
        self.assertTrue(rows[0]['cancelled'])
        self.assertEqual(rows[0]['location'],'Council Chamber')
        self.assertIn('/Committee/468/',rows[0]['url'])

    def test_council_supplement_extends_past_current_month(self):
        appointments=[{'id':1,'subject':'18:00 Cabinet : Chamber','start':'2026/11/28 18:00'}]
        calendar='"appointments":'+json.dumps(json.dumps(appointments))
        index='<a href="https://dudley.cmis.uk.com/Committees/id/468/Default.aspx">Cabinet</a>'
        index=index.replace('Committees/id/','Committees/ViewCMIS_CommitteeDetails/id/')
        committee='''<p>Committee Details</p><table><tr><td><a href="/Meetings/Meeting/2/Committee/468/Default.aspx">05 December 2026 - 18:00 : TBC</a></td><td>Council Chamber</td><td>Scheduled</td></tr></table>'''
        def get(url):return Response(calendar if url==ls.COUNCIL else index if url.endswith('2015Onwards.aspx') else committee)
        result=ls.council_meetings({'get':get,'now':datetime(2026,11,25,tzinfo=timezone.utc)})
        self.assertEqual(len(result['items']),2)
        self.assertTrue(any(r['date'].startswith('2026-12-05') for r in result['items']))

    def test_failed_feed_keeps_last_good_even_when_other_feeds_work(self):
        old={'title':'Sonia Kumar public update','url':'https://sonia-kumar.co.uk/public-update/','date':'2026-10-01','source_url':ls.OWN_RSS}
        previous={'feed_cache':{ls.OWN_RSS:{'items':[old],'retrieved_at':'2026-10-02T07:00:00+00:00'}}}
        def get(url):
            if url==ls.OWN_RSS:raise RuntimeError('Feed unavailable')
            return Response('<rss><channel></channel></rss>')
        with tempfile.TemporaryDirectory() as tmp:
            result=ls.news({'get':get,'now':datetime(2026,11,3,tzinfo=timezone.utc),'previous':previous,'root':Path(tmp)})
            self.assertEqual(result['items'][0]['title'],old['title'])
            self.assertEqual(result['items'][0]['source_retrieved_at'],'2026-10-02T07:00:00+00:00')
            self.assertEqual(result['source_checks'][0]['status'],'stale')
            self.assertTrue((Path(tmp)/'.cache/news.json').exists())

class CensusPartitionTests(unittest.TestCase):
    def test_uses_only_ons_output_area_partition_to_avoid_overlap(self):
        area={'properties':{'areacd':'E14001204','groupcd':'wpc','start':2024,
            'oa21cds':['E00049289','E01009748','E02002002'],
            'lsoa21cds':['E01009748','E02002002'],'msoa21cds':['E02002002']}}
        self.assertEqual(ls.census_components(area),['E00049289','E01009748','E02002002'])
        area['properties']['oa21cds'].append('E00049289')
        with self.assertRaises(ValueError):ls.census_components(area)

    def test_complete_cells_and_valid_denominators_required(self):
        header='GEOGRAPHY_CODE,C2021_HEALTH_6,DATE_NAME,MEASURES,OBS_VALUE,OBS_STATUS\n'
        csv=header+'E00049289,0,2021,20100,100,A\nE00049289,4,2021,20100,5,A\nE00049289,5,2021,20100,2,A\n'
        self.assertEqual(ls.sum_census_partition(csv,['E00049289'],'C2021_HEALTH_6'),{'0':100,'4':5,'5':2})
        with self.assertRaises(ValueError):ls.sum_census_partition(csv+'E00049289,5,2021,20100,2,A\n',['E00049289'],'C2021_HEALTH_6')
        with self.assertRaises(ValueError):ls.sum_census_partition(csv,['E00049289','E00049351'],'C2021_HEALTH_6')

if __name__=='__main__':unittest.main()
