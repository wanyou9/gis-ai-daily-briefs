#!/usr/bin/env python3
"""Read-only publication gate for the static manifests and archive navigation.

Monthly manifests are the source of truth. No third-party packages are required.
Legacy July briefs legitimately have no tasks; catch-up tasks may have a scheduled
date different from their containing brief's logical/completion date.
"""
import argparse
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.hrefs = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.extend(value for key, value in attrs if key == 'href')


def brief_date(brief):
    return brief.get('logical_date', brief.get('date', ''))


def validate(root):
    root = Path(root).resolve()
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    def read(path):
        try:
            value = json.loads((root / path).read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError('top level must be an object')
            return value
        except (OSError, ValueError) as exc:
            errors.append(f'{path}: invalid JSON or unreadable file: {exc}')
            return None

    def file_exists(path, context):
        if not isinstance(path, str) or not path:
            errors.append(f'{context}: missing file path')
            return
        parsed = urlsplit(path)
        target = (root / unquote(parsed.path)).resolve()
        check(not parsed.scheme and target.is_relative_to(root) and target.is_file(),
              f'{context}: missing file or unsafe path: {path}')

    def links(path):
        try:
            return Links((root / path).read_text(encoding='utf-8')).hrefs
        except OSError as exc:
            errors.append(f'{path}: {exc}')
            return []

    months = {}
    briefs = {}
    for path in sorted(root.glob('index/[0-9][0-9][0-9][0-9]/[0-9][0-9].json')):
        name = path.relative_to(root).as_posix()
        month = read(name)
        if month is None:
            continue
        months[name] = month
        entries = month.get('briefs')
        if not isinstance(entries, list):
            errors.append(f'{name}: briefs must be an array')
            continue
        check(month.get('brief_count') == len(entries), f'{name}: brief_count mismatch')
        expected_tasks = {}
        expected_dates = defaultdict(list)
        month_links = links(f'{path.parent.name}/{path.stem}/index.html')
        for brief in entries:
            if not isinstance(brief, dict):
                errors.append(f'{name}: brief must be an object')
                continue
            bid = brief.get('brief_id')
            check(isinstance(bid, str) and bool(bid), f'{name}: missing brief_id')
            if not isinstance(bid, str):
                continue
            check(bid not in briefs, f'{name}: duplicate brief {bid}')
            briefs[bid] = brief
            report = brief.get('report')
            file_exists(report, f'{name}: {bid}')
            if isinstance(report, str):
                check(Path(report).name in [unquote(h) for h in month_links],
                      f'{name}: month navigation missing {bid}')
            for field in ('summary_image', 'release_report', 'release_summary_image'):
                if field in brief:
                    file_exists(brief[field], f'{name}: {bid}.{field}')
            tasks = brief.get('tasks', [])
            if not isinstance(tasks, list):
                errors.append(f'{name}: {bid}: tasks must be an array')
                continue
            if brief.get('kind') in ('DAILY_ROTATION', 'MONTH_END_31_AUDIT') and brief.get('status') != 'HISTORICAL_HTML_MIGRATED':
                check(bool(tasks), f'{name}: {bid}: missing tasks')
            if not tasks and brief.get('status') == 'HISTORICAL_HTML_MIGRATED':
                expected_dates[brief['date']].append(bid)
            for task in tasks:
                if not isinstance(task, dict):
                    errors.append(f'{name}: {bid}: task must be an object')
                    continue
                tid, scheduled = task.get('task_id'), task.get('scheduled_date')
                if not isinstance(tid, str) or not tid:
                    errors.append(f'{name}: {bid}: invalid task_id')
                    continue
                try:
                    date.fromisoformat(scheduled)
                except (TypeError, ValueError):
                    errors.append(f'{name}: {tid}: invalid scheduled_date')
                    continue
                check(tid not in expected_tasks, f'{name}: duplicate task {tid}')
                expected_tasks[tid] = (brief, task)
                expected_dates[scheduled].append(tid)
        actual_dates = month.get('scheduled_date_index')
        check(isinstance(actual_dates, dict) and actual_dates == dict(expected_dates),
              f'{name}: scheduled_date_index mismatch')
        actual_tasks = month.get('task_index')
        if not isinstance(actual_tasks, dict):
            errors.append(f'{name}: task_index must be an object')
            continue
        check(set(actual_tasks) == set(expected_tasks), f'{name}: task_index keys mismatch')
        for tid, (brief, task) in expected_tasks.items():
            lookup = actual_tasks.get(tid)
            if not isinstance(lookup, dict):
                errors.append(f'{name}: task_index missing object for {tid}')
                continue
            for field in ('brief_id', 'report', 'completed_run_date'):
                check(lookup.get(field) == brief.get(field), f'{name}: task_index {tid}.{field} mismatch')
            # Older catch-up records use the task date as logical_date.
            check(lookup.get('logical_date') in (brief.get('logical_date'), task['scheduled_date']),
                  f'{name}: task_index {tid}.logical_date mismatch')
            check(lookup.get('scheduled_date') == task['scheduled_date'], f'{name}: task_index {tid}.scheduled_date mismatch')
            check(isinstance(lookup.get('anchor'), str) and lookup['anchor'] in (task.get('anchor'), brief.get('index_anchor')),
                  f'{name}: task_index {tid}.anchor mismatch')

    manifest = read('brief_index.json')
    if manifest is None:
        return errors
    check(bool(months), 'no monthly manifests found')
    check(manifest.get('brief_count') == len(briefs), 'brief_index.json: brief_count mismatch')
    limit = manifest.get('retention', {}).get('root_recent_brief_limit')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        errors.append('brief_index.json: invalid recent brief limit')
        return errors
    recent = sorted(briefs.values(), key=lambda b: (brief_date(b), b['brief_id']))[-limit:]
    actual_recent = manifest.get('recent_briefs')
    check(isinstance(actual_recent, list) and sorted(actual_recent, key=lambda b: (brief_date(b), b['brief_id'])) == recent,
          'brief_index.json: recent_briefs differ from latest monthly records')
    home_links = links('index.html')
    report_links = [unquote(h) for h in home_links if unquote(h) in {b['report'] for b in briefs.values()}]
    check(report_links == [b['report'] for b in reversed(recent)], 'index.html: latest report links missing, stale, or out of order')
    years = manifest.get('years', [])
    check(isinstance(years, list), 'brief_index.json: years must be an array')
    if not isinstance(years, list):
        return errors
    expected_years = {name.split('/')[1] for name in months}
    check({str(y.get('year')) for y in years} == expected_years and len(years) == len(expected_years), 'brief_index.json: years mismatch')
    for year in years:
        y = str(year['year'])
        year_path = f'index/{y}.json'
        annual = read(year_path)
        if annual is None:
            continue
        shards = {p: m for p, m in months.items() if p.split('/')[1] == y}
        count = sum(len(m.get('briefs', [])) for m in shards.values())
        check(annual.get('brief_count') == count and year.get('brief_count') == count, f'{year_path}: brief_count mismatch')
        check(year.get('month_count') == len(shards), f'{year_path}: month_count mismatch')
        annual_months = annual.get('months', [])
        check({m.get('manifest') for m in annual_months} == set(shards) and len(annual_months) == len(shards), f'{year_path}: months mismatch')
        for month in annual_months:
            source = shards.get(month.get('manifest'))
            if source is not None:
                check(month.get('brief_count') == len(source['briefs']), f'{year_path}: month brief_count mismatch')
            file_exists(month.get('index'), year_path)
        check(year.get('index') == f'{y}/index.html' and year.get('manifest') == year_path, f'{year_path}: root year links mismatch')
        check(f'{y}/index.html' in home_links, f'index.html: missing year {y}')
        year_links = links(f'{y}/index.html')
        check('../index.html' in year_links, f'{y}/index.html: missing home link')
        for p in shards:
            check(f'{Path(p).stem}/index.html' in year_links, f'{y}/index.html: missing month {Path(p).stem}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = validate(args.root)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors = [f'invalid manifest structure: {exc}']
    if errors:
        print('\n'.join(f'ERROR: {error}' for error in errors))
        return 1
    print('Validated monthly task/date indexes, root/year manifests, files and navigation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
