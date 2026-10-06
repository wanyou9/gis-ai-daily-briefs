import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublishedIndexRegressionTests(unittest.TestCase):
    def test_october_tasks_are_objects(self):
        month = json.loads((ROOT / 'index/2026/10.json').read_text())
        for brief in month['briefs']:
            for task in brief['tasks']:
                self.assertIsInstance(task, dict, brief['brief_id'])

    def test_october_third_lookup(self):
        month = json.loads((ROOT / 'index/2026/10.json').read_text())
        task = 'ROUTINE-20261003-G03'
        self.assertEqual(month['scheduled_date_index']['2026-10-03'], [task])
        self.assertEqual(month['task_index'][task]['brief_id'], 'DAILY-20261003')

    def test_homepage_exposes_latest_report(self):
        month = json.loads((ROOT / 'index/2026/10.json').read_text())
        self.assertIn(month['briefs'][-1]['report'], (ROOT / 'index.html').read_text())

    def test_year_archive_exposes_october(self):
        self.assertIn('href="10/index.html"', (ROOT / '2026/index.html').read_text())


if __name__ == '__main__':
    unittest.main()
