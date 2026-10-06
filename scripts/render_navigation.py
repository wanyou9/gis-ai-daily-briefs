#!/usr/bin/env python3
"""Refresh root/year navigation from manifests, preserving existing page styling.

Run after the external publisher updates JSON, then run validate_site.py.
This deliberately does not infer or repair task metadata or alter report assets.
"""
import argparse
from html import escape
import json
from pathlib import Path
import re


def refresh(root):
    root = Path(root)
    manifest = json.loads((root / 'brief_index.json').read_text(encoding='utf-8'))

    def replace_main(path, content):
        page = (root / path).read_text(encoding='utf-8')
        page, count = re.subn(r'<main>.*?</main>', lambda _: '<main>' + content + '</main>', page, flags=re.S)
        if count != 1:
            raise ValueError(f'{path}: expected exactly one main element')
        page = re.sub(r'data-updated="[^"]*"', 'data-updated="' + escape(manifest['updated_date'], quote=True) + '"', page)
        (root / path).write_text(page, encoding='utf-8')

    def e(value):
        return escape(str(value), quote=True)

    years = sorted(manifest['years'], key=lambda y: y['year'], reverse=True)
    home = '<nav>' + ''.join(f'<a href="{e(y["index"])}">{e(y["year"])} 年</a>' for y in years) + '</nav>'
    recent = sorted(manifest['recent_briefs'], key=lambda b: (b.get('logical_date', b.get('date', '')), b['brief_id']), reverse=True)
    for brief in recent:
        logical_date = brief.get('logical_date', brief.get('date', ''))
        home += (f'<article class="card"><div class="meta">{e(logical_date)} · {e(brief["brief_id"])}</div>'
                 f'<h2><a href="{e(brief["report"])}">{e(brief["title"])}</a></h2>'
                 f'<p>{e(brief.get("summary", "历史简报已登记。"))}</p>'
                 f'<span class="status">{e(brief["status"])}</span></article>')
    replace_main('index.html', home)
    for year in years:
        annual = json.loads((root / year['manifest']).read_text(encoding='utf-8'))
        body = '<nav><a href="../index.html">站点首页</a></nav>'
        for month in sorted(annual['months'], key=lambda m: m['month'], reverse=True):
            href = Path(month['index']).relative_to(str(year['year'])).as_posix()
            body += (f'<article class="card"><h2><a href="{e(href)}">{e(year["year"])} 年 {int(month["month"])} 月</a></h2>'
                     f'<p>{int(month["brief_count"])} 份简报 · {e(month["status"])}</p></article>')
        replace_main(year['index'], body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    refresh(parser.parse_args().root)
