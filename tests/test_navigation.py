import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.render_navigation import refresh
from scripts.validate_site import Links

ROOT = Path(__file__).resolve().parents[1]


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('brief_index.json', 'index.html', 'index/2026.json', '2026/index.html'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_refresh_is_idempotent(self):
        refresh(self.root)
        first = [(self.root / p).read_bytes() for p in ('index.html', '2026/index.html')]
        refresh(self.root)
        self.assertEqual(first, [(self.root / p).read_bytes() for p in ('index.html', '2026/index.html')])

    def test_refresh_uses_manifest_and_escapes_text(self):
        path = self.root / 'brief_index.json'
        data = json.loads(path.read_text())
        data['recent_briefs'][-1]['title'] = '<script>alert("x")</script> & title'
        data['recent_briefs'][-1]['report'] = '2026/10/new.html?a=1&b=2'
        path.write_text(json.dumps(data))
        refresh(self.root)
        page = (self.root / 'index.html').read_text()
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>', page)
        self.assertEqual(Links(page).hrefs[1], '2026/10/new.html?a=1&b=2')

    def test_refresh_updates_year_counts(self):
        path = self.root / 'index/2026.json'
        data = json.loads(path.read_text())
        data['months'][-1]['brief_count'] = 7
        path.write_text(json.dumps(data))
        refresh(self.root)
        self.assertIn('7 份简报', (self.root / '2026/index.html').read_text())


if __name__ == '__main__':
    unittest.main()
