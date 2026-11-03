"""Petition ranking checks use synthetic responses only; no network requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import petition_sources


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


class PetitionRanking(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.temporary.name) / 'cache.json'
        self.cache_patch = patch.object(petition_sources, 'CACHE', self.cache_path)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.addCleanup(self.temporary.cleanup)
        self.rows = [
            {'id': number, 'attributes': {
                'state': 'open', 'signature_count': 100 - number if number < 32 else 1,
                'updated_at': 'unchanged-version'}}
            for number in range(33)
        ]
        self.local_counts = {number: 20 - number % 10 for number in range(33)}
        self.local_counts[20] = 70
        self.local_counts[32] = 1
        self.details_requested = []

    def get(self, url):
        if 'petitions.json' in url:
            return FakeResponse({'data': self.rows, 'links': {}})
        number = int(url.rsplit('/', 1)[1].split('.')[0])
        self.details_requested.append(number)
        return FakeResponse({'data': {'attributes': {
            'state': 'open', 'signature_count': self.rows[number]['attributes']['signature_count'],
            'action': f'Petition {number}', 'closing_date': '2027-01-01',
            'signatures_by_constituency': [
                {'name': 'Other seat', 'ons_code': 'E00000000', 'signature_count': 5000},
                {'name': 'Dudley', 'ons_code': 'E14001204',
                 'signature_count': self.local_counts[number]},
            ],
        }}})

    def test_local_support_overrides_national_popularity(self):
        result = petition_sources.fetch_petitions({'get': self.get})
        self.assertEqual(result['items'][0]['title'], 'Petition 20')
        self.assertEqual(result['items'][0]['local_signatures'], 70)
        self.assertEqual(result['items'][0]['national_signatures'], 80)
        expected = sorted(self.local_counts.values(), reverse=True)[:10]
        self.assertEqual([item['local_signatures'] for item in result['items']], expected)

    def test_upper_bound_skips_only_impossible_top_ten_candidates(self):
        result = petition_sources.fetch_petitions({'get': self.get})
        cutoff = result['items'][-1]['local_signatures']
        skipped = set(self.local_counts) - set(self.details_requested)
        self.assertEqual(skipped, {32})
        for number in skipped:
            self.assertLess(self.rows[number]['attributes']['signature_count'], cutoff)
        self.assertIn(20, self.details_requested)

    def test_unchanged_details_are_reused_after_listing_refresh(self):
        petition_sources.fetch_petitions({'get': self.get})
        self.details_requested.clear()
        result = petition_sources.fetch_petitions({'get': self.get})
        self.assertEqual(result['detail_requests'], 0)
        self.assertEqual(self.details_requested, [])
        self.assertTrue(json.loads(self.cache_path.read_text()))

    def test_detail_failure_prevents_partial_published_ranking(self):
        def fail_one_detail(url):
            if url.endswith('/20.json'):
                raise TimeoutError('upstream unavailable')
            return self.get(url)

        with self.assertRaisesRegex(RuntimeError, 'Incomplete petition ranking'):
            petition_sources.fetch_petitions({'get': fail_one_detail})
        # Cache progress is useful for retrying, but no incomplete result returns.
        self.assertTrue(self.cache_path.exists())
        self.assertTrue(json.loads(self.cache_path.read_text()))


if __name__ == '__main__':
    unittest.main()
