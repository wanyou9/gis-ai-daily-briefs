"""Exercise the real validator against isolated mutations of the published tree."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'scripts/validate_site.py'
        if not path.exists():
            cls.validate = None
        else:
            spec = importlib.util.spec_from_file_location('validate_site', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls.validate = staticmethod(module.validate)

    def setUp(self):
        self.assertIsNotNone(self.validate, 'pre-publication validator is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'site'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def mutate(self, path, edit):
        target = self.root / path
        data = json.loads(target.read_text(encoding='utf-8'))
        edit(data)
        target.write_text(json.dumps(data), encoding='utf-8')

    def rejects(self, text):
        self.assertTrue(any(text in error for error in self.validate(self.root)), text)

    def test_repository_passes(self):
        self.assertEqual(self.validate(self.root), [])

    def test_rejects_string_task(self):
        self.mutate('index/2026/10.json', lambda d: d['briefs'][2].update(tasks=['ROUTINE-20261003-G03']))
        self.rejects('task must be an object')

    def test_rejects_character_date_index(self):
        self.mutate('index/2026/10.json', lambda d: d['scheduled_date_index'].update({'2026-10-03': list('DAILY-20261003')}))
        self.rejects('scheduled_date_index')

    def test_rejects_missing_task_lookup(self):
        self.mutate('index/2026/10.json', lambda d: d['task_index'].pop('ROUTINE-20261003-G03'))
        self.rejects('task_index')

    def test_rejects_wrong_task_target(self):
        self.mutate('index/2026/10.json', lambda d: d['task_index']['ROUTINE-20261003-G03'].update(brief_id='DAILY-20261004'))
        self.rejects('task_index')

    def test_rejects_stale_recent_briefs(self):
        self.mutate('brief_index.json', lambda d: d['recent_briefs'].pop())
        self.rejects('recent_briefs')

    def test_rejects_wrong_count(self):
        self.mutate('index/2026.json', lambda d: d.update(brief_count=1))
        self.rejects('brief_count')

    def test_rejects_missing_month_navigation(self):
        path = self.root / '2026/index.html'
        path.write_text(path.read_text().replace('href="10/index.html"', 'href="09/index.html"'))
        self.rejects('2026/index.html')

    def test_rejects_stale_homepage(self):
        path = self.root / 'index.html'
        path.write_text(path.read_text().replace('2026/10/2026-10-06_', '2026/10/2026-10-05_'))
        self.rejects('index.html')

    def test_rejects_missing_report(self):
        month = json.loads((self.root / 'index/2026/10.json').read_text())
        (self.root / month['briefs'][2]['report']).unlink()
        self.rejects('missing file')

    def test_rejects_malformed_json(self):
        (self.root / 'index/2026/10.json').write_text('{')
        self.rejects('invalid JSON')

    def test_rejects_duplicate_task(self):
        self.mutate('index/2026/10.json', lambda d: d['briefs'][2]['tasks'].append(d['briefs'][2]['tasks'][0]))
        self.rejects('duplicate task')

    def test_rejects_unknown_task_lookup(self):
        self.mutate('index/2026/10.json', lambda d: d['task_index'].update({'EXTRA': {}}))
        self.rejects('task_index')


if __name__ == '__main__':
    unittest.main()
