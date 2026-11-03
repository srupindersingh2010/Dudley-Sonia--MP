import unittest,tempfile,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fetch import refresh
from schedule import should_run
from build import safeurl
class DataRetention(unittest.TestCase):
 def test_failure_keeps_original_payload_and_retrieval_date(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);now=datetime(2026,11,3,7,tzinfo=timezone.utc)
   refresh('x','https://example.org',lambda c:{'items':[{'title':'Verified record'}]}, {'now':now},root)
   old=json.loads((root/'x.json').read_text())
   def fails(c):raise TimeoutError('secret-url-must-not-be-published')
   refresh('x','https://example.org',fails,{'now':datetime(2026,11,4,7,tzinfo=timezone.utc)},root)
   new=json.loads((root/'x.json').read_text())
   self.assertEqual(new['data'],old['data']);self.assertEqual(new['retrieved_at'],old['retrieved_at']);self.assertEqual(new['status'],'stale')
   self.assertNotIn('secret-url',json.dumps(new))
 def test_first_failure_is_explicit_unavailable_not_fabricated(self):
  with tempfile.TemporaryDirectory() as tmp:
   def fails(c):raise ValueError()
   refresh('x','https://example.org',fails,{'now':datetime.now(timezone.utc)},Path(tmp))
   value=json.loads((Path(tmp)/'x.json').read_text());self.assertIsNone(value['retrieved_at']);self.assertEqual(value['status'],'unavailable')
 def test_legitimate_empty_success_replaces_previous(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);c={'now':datetime.now(timezone.utc)}
   refresh('x','https://example.org',lambda c:{'items':[{'title':'Old'}]},c,p)
   refresh('x','https://example.org',lambda c:{'items':[]},c,p)
   self.assertEqual(json.loads((p/'x.json').read_text())['data']['items'],[])
class Clock(unittest.TestCase):
 def test_winter_and_summer(self):
  for date,chosen in [('2026-01-01T07:00:00+00:00','0 7 * * *'),('2026-07-01T06:00:00+00:00','0 6 * * *'),('2026-03-29T06:00:00+00:00','0 6 * * *'),('2026-10-25T07:00:00+00:00','0 7 * * *')]:
   now=datetime.fromisoformat(date)
   self.assertTrue(should_run('schedule',chosen,now));self.assertFalse(should_run('schedule','0 7 * * *' if chosen=='0 6 * * *' else '0 6 * * *',now))
 def test_delayed_run_uses_nominal_schedule(self):
  self.assertTrue(should_run('schedule','0 7 * * *',datetime(2026,11,3,9,tzinfo=timezone.utc)))
 def test_manual_runs(self):self.assertTrue(should_run('workflow_dispatch',''))
class RenderingSafety(unittest.TestCase):
 def test_untrusted_link_scheme(self):
  self.assertEqual(safeurl('javascript:alert(1)'),'#');self.assertEqual(safeurl('https://example.org'),'https://example.org')
if __name__=='__main__':unittest.main()
