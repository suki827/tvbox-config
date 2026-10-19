#!/usr/bin/env python3
"""Probe reviewed IPTV candidates and publish only authorised HD video streams."""
import argparse
import csv
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qsl

try:
    from .playlist import parse_entries
except ImportError:
    from playlist import parse_entries

ROOT = Path(__file__).resolve().parents[1]
REPORT_FIELDS = ('id', 'name', 'category', 'country', 'rights_status', 'state',
                 'probe_status', 'width', 'height', 'elapsed_seconds', 'test_region',
                 'last_checked', 'selected', 'detail', 'stream_url')
TRANSIENT = {'TIMEOUT', 'UNREACHABLE', 'OTHER_ERROR'}
ALLOWED_GROUPS = {'英文·新闻', '英文·纪录片', '英文·科学', '英文·儿童', '英文·娱乐', '英文·生活'}
SENSITIVE_QUERY = {'token', 'access_token', 'auth', 'signature', 'sig', 'expires', 'exp', 'key', 'session'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_stream(url):
    if not isinstance(url, str) or any(char.isspace() for char in url):
        return False
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
            and parsed.path.lower().endswith(('.m3u8', '.mpd'))
            and not {key.lower() for key, _ in parse_qsl(parsed.query)} & SENSITIVE_QUERY)


def validate(candidates):
    ids, urls = set(), set()
    for item in candidates:
        if item['id'] in ids:
            raise ValueError('Duplicate candidate ID: ' + item['id'])
        ids.add(item['id'])
        if item['category'] not in ALLOWED_GROUPS or item['language'] != 'en':
            raise ValueError('Invalid category/language: ' + item['id'])
        url = item.get('stream_url')
        if url:
            if not safe_stream(url) or url in urls:
                raise ValueError('Unsafe or duplicate stream URL: ' + item['id'])
            urls.add(url)
        if item.get('rights_status') == 'approved' and (not item.get('rights_evidence_url') or not item.get('rights_checked_at')):
            raise ValueError('Approved stream lacks rights evidence: ' + item['id'])


def check(url, timeout=15):
    """Return ffprobe video dimensions, status, detail and elapsed seconds."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-rw_timeout', str(timeout * 1_000_000),
             '-select_streams', 'v', '-show_entries', 'stream=codec_type,width,height',
             '-of', 'json', url], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 0, 0, 'TIMEOUT', f'ffprobe exceeded {timeout} seconds', round(time.monotonic()-start, 3)
    except OSError as error:
        return 0, 0, 'OTHER_ERROR', str(error)[:300], round(time.monotonic()-start, 3)
    elapsed = round(time.monotonic()-start, 3)
    detail = (result.stderr or '').strip().replace('\n', ' ')[:300]
    if result.returncode:
        lower = detail.lower()
        status = ('REGION_RESTRICTED' if any(s in lower for s in ('geo-block', 'region restricted', 'not available in your country'))
                  else 'ACCESS_DENIED' if any(s in lower for s in ('403', '401', 'forbidden', 'unauthorized'))
                  else 'TIMEOUT' if 'timed out' in lower or 'timeout' in lower
                  else 'UNREACHABLE' if any(s in lower for s in ('404', 'resolve', 'connection refused', 'network is unreachable'))
                  else 'OTHER_ERROR')
        return 0, 0, status, detail, elapsed
    try:
        streams = json.loads(result.stdout or '{}').get('streams') or []
        video = max((stream for stream in streams if stream.get('codec_type') == 'video'),
                    key=lambda stream: int(stream.get('width') or 0) * int(stream.get('height') or 0))
        width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    except (ValueError, TypeError, StopIteration):
        return 0, 0, 'NO_VIDEO', 'No decodable video stream', elapsed
    if width < 1280 or height < 720:
        return width, height, 'LOW_RESOLUTION', 'Below 1280x720', elapsed
    return width, height, 'PASS', '', elapsed


def publishable(item):
    return (item.get('rights_status') == 'approved' and bool(item.get('rights_evidence_url'))
            and bool(item.get('rights_checked_at')) and item.get('language') == 'en'
            and item.get('access_requirements') == 'none' and item.get('drm_status') == 'none'
            and safe_stream(item.get('stream_url')))


def playlist(selected):
    lines = ['#EXTM3U']
    seen_urls, seen_channels = set(), set()
    for item in sorted(selected, key=lambda x: (x['category'], -int(x.get('width') or 0)*int(x.get('height') or 0), x['name'])):
        url, channel = item['stream_url'], item['id'].casefold()
        if url in seen_urls or channel in seen_channels:
            continue
        seen_urls.add(url); seen_channels.add(channel)
        name = re.sub(r'[\r\n",]', ' ', item['name']).strip()
        channel_id = re.sub(r'[^a-zA-Z0-9._-]', '', item['id'])
        group = item['category']
        lines.extend([f'#EXTINF:-1 tvg-id="{channel_id}" group-title="{group}",{name}', url])
    output = '\n'.join(lines) + '\n'
    parse_entries(output)
    return output


def write_report(path, items):
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=REPORT_FIELDS, lineterminator='\n')
        writer.writeheader()
        for item in items:
            writer.writerow({key: item.get(key) for key in REPORT_FIELDS})


def build(root=ROOT, workers=4, timeout=15, max_checks=24, region='NZ_UNVERIFIED'):
    root = Path(root)
    candidates_path = root / 'data/iptv_candidates.json'
    selected_path = root / 'data/iptv_selected.json'
    items = read_json(candidates_path)
    validate(items)
    if not 1 <= workers <= 8 or not 2 <= timeout <= 60 or not 1 <= max_checks <= 150:
        raise ValueError('workers 1-8, timeout 2-60, max_checks 1-150 required')
    if not items:
        write_report(root / 'english_hd_verification.csv', [])
        print('Empty candidate pool; previous subscription retained.')
        return False
    previous = read_json(selected_path) if selected_path.exists() else []
    previous_by_id = {item['id']: item for item in previous}
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    probe_items = [item for item in items if item.get('probe_allowed') and safe_stream(item.get('stream_url'))
                   and item.get('rights_status') != 'restricted'][:max_checks]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda item: check(item['stream_url'], item.get('probe_timeout', timeout)), probe_items))
    result_by_id = {item['id']: result for item, result in zip(probe_items, results)}
    selected = []
    for item in items:
        item['selected'] = False
        item['test_region'] = region
        if item['id'] in result_by_id:
            width, height, status, detail, elapsed = result_by_id[item['id']]
            item.update(width=width, height=height, probe_status=status, detail=detail,
                        elapsed_seconds=elapsed, last_checked=now)
        elif item.get('rights_status') == 'restricted':
            item.update(probe_status='SKIPPED_POLICY', detail=item.get('review_note', ''), elapsed_seconds=0)
        else:
            item.update(probe_status='NOT_CHECKED', detail='No public stream or automated probing not permitted', elapsed_seconds=0)
        status = item['probe_status']
        if publishable(item) and status == 'PASS':
            item['state'] = 'VERIFIED'
            item['selected'] = True
            selected.append(dict(item, publication_status='VERIFIED'))
        elif publishable(item) and status in TRANSIENT and item['id'] in previous_by_id and previous_by_id[item['id']].get('stream_url') == item['stream_url']:
            item['state'] = 'DISCOVERED'
            item['selected'] = True
            saved = dict(previous_by_id[item['id']])
            saved.update(state='DISCOVERED', probe_status=status, last_checked=now,
                         publication_status='RETAINED_RECHECK', selected=True)
            selected.append(saved)
        else:
            item['state'] = 'REJECTED' if item.get('rights_status') == 'restricted' or status in {'LOW_RESOLUTION', 'NO_VIDEO'} else 'DISCOVERED'
    write_json(candidates_path, items)
    write_report(root / 'english_hd_verification.csv', items)
    # Never replace a valid subscription when every candidate is temporarily missing.
    if not selected and not previous and (root / 'english_hd.m3u').exists() and parse_entries((root / 'english_hd.m3u').read_text(encoding='utf-8')):
        print('Prior subscription exists without review records; retained for manual rights review.')
        return False
    output = playlist(selected)
    playlist_path = root / 'english_hd.m3u'
    if not playlist_path.exists() or playlist_path.read_text(encoding='utf-8') != output:
        playlist_path.write_text(output, encoding='utf-8')
    if not selected_path.exists() or read_json(selected_path) != selected:
        write_json(selected_path, selected)
    print(f'Candidates={len(items)} probed={len(probe_items)} fresh_verified={sum(x["publication_status"] == "VERIFIED" for x in selected)} published={len(selected)} region={region}')
    return bool(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=int(os.getenv('ENGLISH_HD_WORKERS', '4')))
    parser.add_argument('--timeout', type=int, default=int(os.getenv('ENGLISH_HD_TIMEOUT', '15')))
    parser.add_argument('--max-checks', type=int, default=int(os.getenv('ENGLISH_HD_MAX_CHECKS', '24')))
    parser.add_argument('--region', default=os.getenv('ENGLISH_HD_TEST_REGION', 'NZ_UNVERIFIED'))
    args = parser.parse_args()
    build(workers=args.workers, timeout=args.timeout, max_checks=args.max_checks, region=args.region)


if __name__ == '__main__':
    main()
