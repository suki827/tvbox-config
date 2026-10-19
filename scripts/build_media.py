#!/usr/bin/env python3
"""Build curated A/B catalogs; publish only explicitly licensed, probed streams."""
import argparse
import csv
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'live_video', 'live_audio', 'vod', 'podcast', 'official_link'}
REPORT_FIELDS = ['id', 'source_id', 'type', 'status', 'http_status', 'width', 'height', 'detail', 'test_region', 'checked_at']
TOKEN_RE = re.compile(r'(?:token|expires|exp|signature|sig|auth|key)=', re.I)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_url(url):
    if not url or any(c.isspace() for c in url):
        return False
    parsed = urllib.parse.urlparse(url)
    return (parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
            and not TOKEN_RE.search(parsed.query))


def safe_stream_url(url):
    if not safe_url(url):
        return False
    host = urllib.parse.urlparse(url).hostname.lower()
    return host not in ('youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com')


def validate(sources, items):
    if len(sources) != 18 or len({s['id'] for s in sources}) != 18:
        raise ValueError('Exactly 18 unique source IDs are required')
    source_ids = {s['id'] for s in sources}
    if len({i['id'] for i in items}) != len(items):
        raise ValueError('Duplicate item ID')
    seen_streams = set()
    for source in sources:
        for field in ('name', 'country', 'language', 'categories', 'profiles', 'official_url',
                      'access_types', 'availability_regions', 'access_cost', 'access_requirements',
                      'rights_status', 'rights_evidence_url', 'rights_checked_at', 'last_verified_at'):
            if field not in source:
                raise ValueError(f"Missing source field {source['id']}.{field}")
        if not safe_url(source['official_url']) or not set(source['access_types']) <= KINDS:
            raise ValueError(f"Invalid source {source['id']}")
    for item in items:
        if item['source_id'] not in source_ids or item['type'] not in KINDS:
            raise ValueError(f"Invalid source/type for {item['id']}")
        if not safe_url(item['official_url']):
            raise ValueError(f"Invalid official URL for {item['id']}")
        stream = item.get('stream_url')
        if stream:
            if not safe_stream_url(stream) or stream in seen_streams:
                raise ValueError(f"Unsafe or duplicate stream for {item['id']}")
            seen_streams.add(stream)
        if item.get('rss_url') and not safe_url(item['rss_url']):
            raise ValueError(f"Invalid RSS for {item['id']}")
        if item['type'] not in ('live_video', 'live_audio') and stream:
            raise ValueError(f"Non-live item has a stream: {item['id']}")


def check_web(url, rss=False):
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'CuratedMedia/1.0', 'Accept': 'application/rss+xml, application/atom+xml, text/html, */*'})
        with urllib.request.urlopen(request, timeout=8) as response:
            status = response.status
            body = response.read(512_000) if rss else b''
        if rss:
            root = ET.fromstring(body)
            if root.tag not in ('rss', '{http://www.w3.org/2005/Atom}feed'):
                return 'INVALID_RSS', status, 'Root is not RSS or Atom'
            entries = root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
            if not entries:
                return 'EMPTY_RSS', status, 'No feed entries'
            dates = []
            for entry in entries:
                raw = entry.findtext('pubDate') or entry.findtext('{http://www.w3.org/2005/Atom}updated')
                if raw:
                    try:
                        date = parsedate_to_datetime(raw) if entry.findtext('pubDate') else datetime.fromisoformat(raw.replace('Z', '+00:00'))
                        dates.append(date.astimezone(timezone.utc))
                    except (ValueError, TypeError):
                        pass
            latest = max(dates) if dates else None
            detail = f'{len(entries)} entries inspected; latest=' + (latest.isoformat() if latest else 'unknown')
            return ('STALE_RSS' if latest and datetime.now(timezone.utc)-latest > timedelta(days=30) else 'PASS'), status, detail
        return 'PASS', status, ''
    except urllib.error.HTTPError as error:
        return ('REGION_RESTRICTED' if error.code == 451 else 'ACCESS_DENIED' if error.code in (401, 403) else 'UNREACHABLE'), error.code, str(error)
    except TimeoutError:
        return 'TIMEOUT', None, 'HTTP request exceeded 8 seconds'
    except (urllib.error.URLError, ET.ParseError, ValueError) as error:
        return 'OTHER_ERROR' if isinstance(error, ET.ParseError) else 'UNREACHABLE', None, str(error)[:300]


def probe(item):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-rw_timeout', '8000000',
                                 '-show_entries', 'stream=codec_type,width,height', '-of', 'json',
                                 item['stream_url']], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', 0, 0, 'ffprobe exceeded 15 seconds'
    except OSError as error:
        return 'OTHER_ERROR', 0, 0, str(error)
    if result.returncode:
        detail = result.stderr.strip()[:300]
        low = detail.lower()
        status = ('REGION_RESTRICTED' if any(x in low for x in ('geo-block', 'geo restricted', 'region restricted', 'not available in your country'))
                  else 'TIMEOUT' if 'timed out' in low or 'timeout' in low
                  else 'ACCESS_DENIED' if any(x in low for x in ('403', '401', 'forbidden', 'unauthorized'))
                  else 'UNREACHABLE' if any(x in low for x in ('404', 'resolve', 'connection refused', 'network is unreachable'))
                  else 'OTHER_ERROR')
        return status, 0, 0, detail
    try:
        streams = json.loads(result.stdout)['streams']
    except (ValueError, KeyError, TypeError):
        return 'OTHER_ERROR', 0, 0, 'Invalid ffprobe output'
    wanted = 'video' if item['type'] == 'live_video' else 'audio'
    matches = [s for s in streams if s.get('codec_type') == wanted]
    if not matches:
        return 'OTHER_ERROR', 0, 0, f'No {wanted} stream'
    width = int(matches[0].get('width') or 0)
    height = int(matches[0].get('height') or 0)
    if wanted == 'video' and (width < 1280 or height < 720):
        return 'LOW_RESOLUTION', width, height, 'Below 1280×720'
    return 'PASS', width, height, ''


def stream_eligible(item, source):
    return (item['type'] in ('live_video', 'live_audio') and item['type'] in source['access_types']
            and safe_stream_url(item.get('stream_url')) and item.get('drm_status') == 'none'
            and item.get('review_status') == 'approved'
            and item.get('rights_status') == 'approved'
            and source.get('rights_status') == 'approved'
            and safe_url(item.get('rights_evidence_url')) and item.get('rights_checked_at')
            and safe_url(source.get('rights_evidence_url')) and source.get('rights_checked_at')
            and item.get('access_requirements') == 'none')


def playlist(items, source_by_id, kind, profile, results, old_text=''):
    selected = []
    old_urls = set(re.findall(r'^https://[^\s]+$', old_text, re.M))
    used = set()
    for item in items:
        if item['type'] != kind or profile not in item['profiles']:
            continue
        source = source_by_id[item['source_id']]
        if not stream_eligible(item, source):
            continue
        url = item['stream_url']
        status = results.get(item['id'], {}).get('status')
        if status == 'PASS' or (status in ('TIMEOUT', 'UNREACHABLE', 'OTHER_ERROR') and url in old_urls):
            if url not in used:
                used.add(url)
                selected.append(item)
    lines = ['#EXTM3U']
    for item in selected:
        name = item['title'].replace('\n', ' ').replace(',', '，').replace('"', '')
        group = '精品电视' if profile == 'A' else '英语学习'
        if kind == 'live_audio':
            group = '精品广播'
        lines.extend([f'#EXTINF:-1 tvg-id="{item["id"]}" group-title="{group}",{name}', item['stream_url']])
    return '\n'.join(lines) + '\n'


def build(root=ROOT, do_check=False, region='NZ_UNVERIFIED'):
    sources = read_json(root/'data/media_sources.json')
    items = read_json(root/'data/media_items.json')
    validate(sources, items)
    source_by_id = {s['id']: s for s in sources}
    previous = read_json(root/'data/channel_health.json') if (root/'data/channel_health.json').exists() else {}
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds') if do_check else None
    reports = []
    def inspect(item):
        status, http, width, height, detail = 'NOT_CHECKED', None, 0, 0, 'Run with --check to test connectivity'
        source = source_by_id[item['source_id']]
        if item['type'] in ('live_video', 'live_audio'):
            if stream_eligible(item, source):
                status, width, height, detail = probe(item) if do_check else (status, width, height, detail)
            else:
                status, detail = 'PENDING_RIGHTS', 'Direct stream or third-party playback rights unapproved'
        elif item['type'] == 'podcast' and item.get('rss_url'):
            status, http, detail = check_web(item['rss_url'], rss=True) if do_check else (status, http, detail)
        elif do_check and source.get('automated_checks_allowed', True) is False:
            status, detail = 'SKIPPED_POLICY', 'Source disallows automated access; use official link manually'
        elif do_check:
            status, http, detail = check_web(item['official_url'])
        return {'id': item['id'], 'source_id': item['source_id'], 'type': item['type'], 'status': status, 'http_status': http,
                'width': width, 'height': height, 'detail': detail, 'test_region': region,
                'checked_at': checked_at}
    if do_check:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(inspect, item) for item in items]
            reports = [future.result() for future in futures]
    else:
        reports = [inspect(item) for item in items]
    results = {r['id']: r for r in reports}
    health = dict(previous)
    if do_check:
        for report in reports:
            old = previous.get(report['id'], {})
            failures = 0 if report['status'] == 'PASS' else old.get('consecutive_failures', 0) + 1
            health[report['id']] = {'status': report['status'], 'consecutive_failures': failures,
                                    'quarantined': failures >= 3, 'last_checked_at': checked_at,
                                    'last_success_at': checked_at if report['status'] == 'PASS' else old.get('last_success_at')}
        write_json(root/'data/channel_health.json', health)
        write_json(root/'data/media_verification.json', {'checked_at': checked_at, 'test_region': region, 'results': reports})
        with (root/'media_check_report.csv').open('w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=REPORT_FIELDS)
            writer.writeheader(); writer.writerows(reports)
        if not any(report['status'] == 'PASS' for report in reports):
            raise RuntimeError('No official entry passed connectivity checks; published catalogs remain unchanged')
    for profile, filename in [('A','premium_tv.m3u'), ('A','premium_radio.m3u'), ('B','english_learning.m3u')]:
        kind = 'live_audio' if 'radio' in filename else 'live_video'
        path = root/filename
        old = path.read_text(encoding='utf-8') if path.exists() else ''
        new = playlist(items, source_by_id, kind, profile, results, old)
        if not do_check and old:
            continue
        if old != new:
            path.write_text(new, encoding='utf-8')
    for profile, filename in [('A','premium_catalog.json'), ('B','english_learning_catalog.json')]:
        catalog = []
        for item in items:
            if profile not in item['profiles']:
                continue
            entry = dict(item)
            entry['source_name'] = source_by_id[item['source_id']]['name']
            entry['nz_access'] = source_by_id[item['source_id']]['nz_access']
            entry['availability_regions'] = source_by_id[item['source_id']]['availability_regions']
            entry['access_requirements'] = source_by_id[item['source_id']]['access_requirements']
            entry['link_check_status'] = results[item['id']]['status'] if do_check else 'NOT_CHECKED'
            catalog.append(entry)
        write_json(root/filename, catalog)
    (root/'docs').mkdir(exist_ok=True)
    site_items = []
    for item in items:
        entry = dict(item)
        entry['link_check_status'] = results[item['id']]['status'] if do_check else 'NOT_CHECKED'
        site_items.append(entry)
    write_json(root/'docs/catalog.json', {'sources': sources, 'items': site_items})
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check links, RSS and approved streams')
    parser.add_argument('--region', default=os.environ.get('MEDIA_TEST_REGION', 'NZ_UNVERIFIED'))
    args = parser.parse_args()
    reports = build(do_check=args.check, region=args.region)
    print(json.dumps({'items': len(reports), 'passed': sum(r['status'] == 'PASS' for r in reports),
                      'streams_passed': sum(r['status'] == 'PASS' and r['type'].startswith('live_') for r in reports),
                      'test_region': args.region}, ensure_ascii=False))
