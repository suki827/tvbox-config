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
REPORT_FIELDS = ('channel', 'country', 'source_url', 'stream_url', 'probe_status',
                 'width', 'height', 'resolution', 'rights_status', 'rights_evidence',
                 'test_region', 'checked_at', 'failure_reason')
TRANSIENT = {'TIMEOUT', 'UNREACHABLE', 'OTHER_ERROR', 'MEDIA_DECODE_FAILED'}
ALLOWED_GROUPS = {'美国·新闻', '美国·财经', '美国·天气', '英国·新闻'}
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
    ids, urls, channels = set(), set(), set()
    for item in candidates:
        if item['id'] in ids:
            raise ValueError('Duplicate candidate ID: ' + item['id'])
        ids.add(item['id'])
        country, category = item.get('country'), item.get('category')
        if country not in {'US', 'GB'} or category not in ALLOWED_GROUPS or item.get('language') != 'en':
            raise ValueError('Invalid category/language: ' + item['id'])
        if (country == 'US' and not category.startswith('美国·')) or (country == 'GB' and not category.startswith('英国·')):
            raise ValueError('Country/category mismatch: ' + item['id'])
        channel = (item.get('name') or '').strip().casefold()
        if not channel or channel in channels:
            raise ValueError('Duplicate or missing channel name: ' + item['id'])
        channels.add(channel)
        url = item.get('stream_url')
        if url:
            if not safe_stream(url) or url in urls:
                raise ValueError('Unsafe or duplicate stream URL: ' + item['id'])
            urls.add(url)
        if item.get('rights_status') == 'approved' and (not item.get('rights_evidence_url') or not item.get('rights_checked_at')
                                                        or item.get('rights_approval_scope') != 'third_party_playlist'):
            raise ValueError('Approved stream lacks rights evidence: ' + item['id'])


def classify_failure(detail, fallback='OTHER_ERROR'):
    lower = detail.lower()
    if any(s in lower for s in ('geo-block', 'region restricted', 'not available in your country')):
        return 'REGION_RESTRICTED'
    if any(s in lower for s in ('403', '401', 'forbidden', 'unauthorized')):
        return 'ACCESS_DENIED'
    if 'timed out' in lower or 'timeout' in lower:
        return 'TIMEOUT'
    if any(s in lower for s in ('404', 'resolve', 'connection refused', 'network is unreachable')):
        return 'UNREACHABLE'
    return fallback


def check(url, timeout=15):
    """Probe metadata and decode a real media frame; a readable manifest alone is insufficient."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-rw_timeout', str(timeout * 1_000_000),
             '-select_streams', 'v', '-show_entries', 'stream=index,codec_type,width,height',
             '-of', 'json', url], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 0, 0, 'TIMEOUT', f'ffprobe exceeded {timeout} seconds', round(time.monotonic()-start, 3)
    except OSError as error:
        return 0, 0, 'OTHER_ERROR', str(error)[:300], round(time.monotonic()-start, 3)
    elapsed = round(time.monotonic()-start, 3)
    detail = (result.stderr or '').strip().replace('\n', ' ')[:300]
    if result.returncode:
        status = classify_failure(detail)
        return 0, 0, status, detail, elapsed
    try:
        streams = json.loads(result.stdout or '{}').get('streams') or []
        videos = [(index, stream) for index, stream in enumerate(streams) if stream.get('codec_type') == 'video']
    except (ValueError, TypeError, StopIteration):
        return 0, 0, 'NO_VIDEO', 'No decodable video stream', elapsed
    if not videos:
        return 0, 0, 'NO_VIDEO', 'No decodable video stream', elapsed
    videos.sort(key=lambda pair: int(pair[1].get('width') or 0) * int(pair[1].get('height') or 0), reverse=True)
    best = videos[0][1]
    best_width, best_height = int(best.get('width') or 0), int(best.get('height') or 0)
    viable = [(index, stream) for index, stream in videos
              if int(stream.get('width') or 0) >= 1280 and int(stream.get('height') or 0) >= 720]
    if not viable:
        return best_width, best_height, 'LOW_RESOLUTION', 'Below 1280x720', elapsed
    last_decode_error = ''
    for fallback_index, stream in viable:
        width, height = int(stream.get('width') or 0), int(stream.get('height') or 0)
        stream_index = stream.get('index', fallback_index)
        try:
            decoded = subprocess.run(
                ['ffmpeg', '-v', 'error', '-rw_timeout', str(timeout * 1_000_000),
                 '-i', url, '-map', f'0:{stream_index}', '-frames:v', '1', '-f', 'null', '-'],
                capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 0, 0, 'TIMEOUT', f'ffmpeg frame decode exceeded {timeout} seconds', round(time.monotonic()-start, 3)
        except OSError as error:
            return 0, 0, 'OTHER_ERROR', str(error)[:300], round(time.monotonic()-start, 3)
        if decoded.returncode == 0:
            return width, height, 'PASS', '', round(time.monotonic()-start, 3)
        last_decode_error = (decoded.stderr or '').strip().replace('\n', ' ')[:300]
        status = classify_failure(last_decode_error, 'MEDIA_DECODE_FAILED')
        if status != 'MEDIA_DECODE_FAILED':
            return 0, 0, status, last_decode_error, round(time.monotonic()-start, 3)
    return 0, 0, 'MEDIA_DECODE_FAILED', last_decode_error or 'Could not decode a video frame', round(time.monotonic()-start, 3)


def check_with_retries(url, timeout=15, attempts=2):
    """Retry transient transport/decode failures, keeping terminal outcomes distinct."""
    result = (0, 0, 'OTHER_ERROR', 'No probe attempt made', 0)
    for _ in range(max(1, min(attempts, 3))):
        result = check(url, timeout)
        if result[2] not in TRANSIENT:
            break
    return result


def publishable(item):
    return (item.get('rights_status') == 'approved' and bool(item.get('rights_evidence_url'))
            and bool(item.get('rights_checked_at'))
            and item.get('rights_approval_scope') == 'third_party_playlist' and item.get('language') == 'en'
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
        tvg_id = re.sub(r'["\r\n]', '', item.get('tvg_id') or channel_id)
        logo = item.get('tvg_logo')
        logo_attr = f' tvg-logo="{logo}"' if isinstance(logo, str) and urlparse(logo).scheme == 'https' and '"' not in logo else ''
        group = item['category']
        lines.extend([f'#EXTINF:-1 tvg-id="{tvg_id}"{logo_attr} group-title="{group}",{name}', url])
    output = '\n'.join(lines) + '\n'
    parse_entries(output)
    return output


def write_report(path, items):
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=REPORT_FIELDS, lineterminator='\n')
        writer.writeheader()
        for item in items:
            width, height = item.get('width') or 0, item.get('height') or 0
            resolution = (f'{height}p' if width >= height * 1.6 and height else
                          f'{width}x{height}' if width and height else '')
            failure = item.get('detail') or item.get('failure_reason') or ''
            if item.get('rights_status') != 'approved':
                failure = failure or 'Rights not approved for third-party playlist publication'
            writer.writerow({
                'channel': item.get('name'), 'country': item.get('country'),
                'source_url': item.get('source_url'), 'stream_url': item.get('stream_url'),
                'probe_status': item.get('probe_status'), 'width': width or '', 'height': height or '',
                'resolution': resolution, 'rights_status': item.get('rights_status'),
                'rights_evidence': item.get('rights_evidence_url'),
                'test_region': item.get('test_region'), 'checked_at': item.get('last_checked'),
                'failure_reason': failure,
            })


def write_candidate_report(path, items):
    """Write discovery, technology, rights, and NZ verification as separate facts."""
    output = []
    for item in items:
        rights_approved = (item.get('rights_status') == 'approved' and bool(item.get('rights_evidence_url'))
                           and bool(item.get('rights_checked_at'))
                           and item.get('rights_approval_scope') == 'third_party_playlist')
        probe_passed = item.get('probe_status') == 'PASS'
        cannot_publish = []
        if not item.get('stream_url'):
            cannot_publish.append(item.get('review_note') or 'No direct HLS/DASH stream found')
        elif not probe_passed:
            cannot_publish.append(item.get('detail') or f"Latest probe status: {item.get('probe_status', 'NOT_CHECKED')}")
        if not rights_approved or item.get('rights_approval_scope') != 'third_party_playlist':
            cannot_publish.append('Third-party IPTV playlist rights are not confirmed')
        if item.get('access_requirements') not in ('none', None) or item.get('drm_status') not in ('none', None):
            cannot_publish.append('Access requirements or DRM status are not cleared')
        status_flags = []
        if item.get('stream_url'):
            status_flags.append('STREAM_FOUND')
        if probe_passed:
            status_flags.append('PROBE_PASSED')
        if rights_approved:
            status_flags.append('RIGHTS_APPROVED')
        if item.get('test_region') == 'NZ' and probe_passed:
            status_flags.append('NZ_VERIFIED')
        if item.get('selected'):
            status_flags.append('PUBLISHED')
        output.append({
            'id': item.get('id'), 'channel': item.get('name'), 'country': item.get('country'),
            'source_url': item.get('source_url'), 'stream_url': item.get('stream_url'),
            'stream_discovery_url': item.get('stream_discovery_url'),
            'stream_status': 'STREAM_FOUND' if item.get('stream_url') else 'NO_DIRECT_STREAM_FOUND',
            'format': item.get('stream_type') or 'unknown',
            'probe_status': item.get('probe_status', 'NOT_CHECKED'),
            'probe_passed': probe_passed, 'width': item.get('width'), 'height': item.get('height'),
            'last_successful_probe': item.get('last_successful_probe'),
            'rights_status': item.get('rights_status', 'pending'),
            'rights_evidence_url': item.get('rights_evidence_url'),
            'rights_approval_scope': item.get('rights_approval_scope', 'unknown'),
            'access_requirements': item.get('access_requirements', 'unknown'),
            'drm_status': item.get('drm_status', 'unknown'),
            'availability_regions': item.get('availability_regions', 'unknown'),
            'token_status': ('not_detected_by_url_heuristic' if item.get('stream_url') else 'unknown'),
            'rights_approved': rights_approved,
            'test_region': item.get('test_region', 'GITHUB_UNVERIFIED'),
            'nz_verified': item.get('test_region') == 'NZ' and probe_passed,
            'published': bool(item.get('selected')),
            'status_flags': status_flags,
            'cannot_publish_reasons': cannot_publish,
            'cannot_publish_reason': '; '.join(dict.fromkeys(cannot_publish)),
        })
    write_json(path, output)


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
        write_candidate_report(root / 'english_hd_candidates.json', [])
        print('Empty candidate pool; previous subscription retained.')
        return False
    previous = read_json(selected_path) if selected_path.exists() else []
    previous_by_id = {item['id']: item for item in previous}
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    probe_items = [item for item in items if item.get('probe_allowed') and safe_stream(item.get('stream_url'))
                   and item.get('rights_status') != 'restricted'][:max_checks]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda item: check_with_retries(item['stream_url'], item.get('probe_timeout', timeout)), probe_items))
    result_by_id = {item['id']: result for item, result in zip(probe_items, results)}
    selected = []
    for item in items:
        item['selected'] = False
        item['test_region'] = region
        if item['id'] in result_by_id:
            width, height, status, detail, elapsed = result_by_id[item['id']]
            last_success = item.get('last_successful_probe')
            if item.get('probe_status') == 'PASS' and not last_success:
                last_success = {'width': item.get('width'), 'height': item.get('height'),
                                'checked_at': item.get('last_checked'), 'test_region': item.get('test_region')}
            item.update(width=width, height=height, probe_status=status, detail=detail,
                        elapsed_seconds=elapsed, last_checked=now)
            if status == 'PASS':
                last_success = {'width': width, 'height': height, 'checked_at': now, 'test_region': region}
            if last_success:
                item['last_successful_probe'] = last_success
        elif item.get('rights_status') == 'restricted':
            item.update(probe_status='SKIPPED_POLICY', detail=item.get('review_note', ''), elapsed_seconds=0)
        else:
            item.update(probe_status='NOT_FOUND' if not item.get('stream_url') else 'NOT_CHECKED',
                        detail=item.get('review_note', 'No directly testable public HLS/DASH candidate'), elapsed_seconds=0)
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
    write_candidate_report(root / 'english_hd_candidates.json', items)
    # Published streams are retained above only when their selected metadata confirms
    # rights and the same URL had a transient probe failure. An untracked legacy list
    # cannot be assumed to be in-scope or rights-cleared during a migration.
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
