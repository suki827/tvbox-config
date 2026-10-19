#!/usr/bin/env python3
"""Discover English HD streams from independently approved hosts."""

import csv
import json
import os
import subprocess
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from .playlist import ENGLISH_GROUP, merge_playlists, parse_entries
except ImportError:  # direct invocation in Actions
    from playlist import ENGLISH_GROUP, merge_playlists, parse_entries

ROOT = Path(__file__).resolve().parents[1]
API = 'https://iptv-org.github.io/api/'
COUNTRIES = {'NZ', 'US', 'GB', 'CA'}
CATEGORIES = {'news', 'documentary', 'education', 'kids', 'animation',
              'entertainment', 'movies', 'series', 'lifestyle', 'travel',
              'cooking', 'science'}
REPORT_FIELDS = ['id', 'name', 'country', 'width', 'height', 'status', 'detail', 'url']


def fetch(name):
    request = urllib.request.Request(API + name, headers={'User-Agent': 'TVBox-English-HD/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def check(url):
    """Return measured dimensions, a precise status, and ffprobe detail."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-rw_timeout', '12000000',
             '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
             '-of', 'json', url],
            capture_output=True, text=True, timeout=22,
        )
    except subprocess.TimeoutExpired:
        return 0, 0, 'TIMEOUT', 'ffprobe exceeded 22 seconds'
    except OSError as error:
        return 0, 0, 'OTHER_ERROR', str(error)

    detail = (result.stderr or '').strip().replace('\n', ' ')[:500]
    if result.returncode:
        lower = detail.casefold()
        if any(word in lower for word in ('geo-block', 'geo blocked', 'geoblock', 'geo restricted',
                                          'region restricted', 'not available in your country')):
            status = 'REGION_RESTRICTED'
        elif any(word in lower for word in ('timed out', 'timeout')):
            status = 'TIMEOUT'
        elif any(word in lower for word in ('403', '401', 'forbidden', 'unauthorized')):
            status = 'ACCESS_DENIED'
        elif any(word in lower for word in ('connection refused', 'could not resolve',
                                            'name or service not known', 'network is unreachable',
                                            'server returned 404', 'http error 404')):
            status = 'UNREACHABLE'
        else:
            status = 'OTHER_ERROR'
        return 0, 0, status, detail
    try:
        video = (json.loads(result.stdout or '{}').get('streams') or [{}])[0]
        width, height = int(video.get('width', 0)), int(video.get('height', 0))
    except (ValueError, TypeError, KeyError, IndexError):
        return 0, 0, 'OTHER_ERROR', 'Invalid ffprobe video metadata'
    if width == 0 or height == 0:
        return 0, 0, 'OTHER_ERROR', 'No video stream'
    if width < 1280 or height < 720:
        return width, height, 'LOW_RESOLUTION', detail
    return width, height, 'PASS', detail


def is_approved(url, hosts):
    if any(character.isspace() for character in url):
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == 'https' and (parsed.hostname or '').lower() in hosts


def candidates(feeds, channels, streams, approved_hosts):
    english_feeds = {(feed.get('channel'), feed.get('id')) for feed in feeds
                     if 'eng' in (feed.get('languages') or [])}
    allowed_channels = {channel['id']: channel for channel in channels
                        if channel.get('id') and channel.get('country') in COUNTRIES
                        and set(channel.get('categories') or []).intersection(CATEGORIES)
                        and not channel.get('is_nsfw') and not channel.get('closed')}
    found = []
    seen_urls = set()
    for stream in streams:
        channel = allowed_channels.get(stream.get('channel'))
        url = stream.get('url') or ''
        if (not channel or not is_approved(url, approved_hosts)
                or url in seen_urls or (stream.get('channel'), stream.get('feed')) not in english_feeds):
            continue
        seen_urls.add(url)
        found.append((channel, url))
    return sorted(found, key=lambda pair: (pair[0]['country'], pair[0]['name'], pair[1]))


def select_candidates(found, limit):
    """Share the bounded probe budget across all four requested countries."""
    queues = {country: [] for country in ('NZ', 'US', 'GB', 'CA')}
    for pair in found:
        queues[pair[0]['country']].append(pair)
    chosen = []
    while len(chosen) < limit and any(queues.values()):
        for country in queues:
            if queues[country] and len(chosen) < limit:
                chosen.append(queues[country].pop(0))
    return chosen


def write_report(path, rows):
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(REPORT_FIELDS)
        writer.writerows(rows)


def build(root=ROOT, approved_hosts=None, max_checks=72, workers=6):
    root = Path(root)
    approved_hosts = approved_hosts if approved_hosts is not None else {
        host.strip().lower() for host in os.getenv('ENGLISH_HD_APPROVED_HOSTS', '').split(',') if host.strip()
    }
    if not approved_hosts:
        write_report(root / 'english_hd_verification.csv',
                     [['', '', '', '', '', 'CONFIGURATION_REQUIRED', 'Set ENGLISH_HD_APPROVED_HOSTS', '']])
        print('No independently approved hosts configured; playlists unchanged.')
        return False

    found = candidates(fetch('feeds.json'), fetch('channels.json'), fetch('streams.json'), approved_hosts)
    selected = select_candidates(found, max(1, min(max_checks, 150)))
    print(f'Candidates={len(found)} selected={len(selected)} workers={workers}', flush=True)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        results = list(pool.map(lambda pair: check(pair[1]), selected))
    pass_order = sorted((index for index, result in enumerate(results) if result[2] == 'PASS'),
                        key=lambda index: (-results[index][0] * results[index][1],
                                           selected[index][0]['country'], selected[index][0]['name']))
    selected_indices = set()
    seen_ids = set()
    seen_names = set()
    for index in pass_order:
        channel = selected[index][0]
        channel_id = channel['id'].casefold()
        name = channel['name'].strip().casefold()
        if channel_id not in seen_ids and name not in seen_names:
            selected_indices.add(index)
            seen_ids.add(channel_id)
            seen_names.add(name)
    rows = []
    passed = []
    for index, ((channel, url), (width, height, status, detail)) in enumerate(zip(selected, results)):
        if status == 'PASS' and index not in selected_indices:
            status, detail = 'DUPLICATE_CHANNEL', 'Higher resolution stream selected for this channel'
        rows.append([channel['id'], channel['name'], channel['country'], width, height, status, detail, url])
        if status == 'PASS':
            passed.append((channel, url, width, height))
    write_report(root / 'english_hd_verification.csv', rows)
    counts = {status: sum(row[5] == status for row in rows) for status in {row[5] for row in rows}}
    print(f'Checked={len(rows)} statuses={counts}', flush=True)
    if not passed:
        print('No HD streams passed; previous playlists unchanged.')
        return False

    base_path = root / 'live_config_base.m3u'
    combined_path = root / 'live_config.m3u'
    base = base_path.read_text(encoding='utf-8-sig') if base_path.exists() else combined_path.read_text(encoding='utf-8-sig')
    passed.sort(key=lambda item: (item[0]['country'], item[0]['name'], -item[2] * item[3]))
    lines = ['#EXTM3U']
    for channel, url, _, _ in passed:
        name = channel['name'].replace('\n', ' ').replace('\r', ' ')
        channel_id = channel['id'].replace('"', '').replace('\n', '').replace('\r', '')
        lines.extend([f'#EXTINF:-1 tvg-id="{channel_id}" {ENGLISH_GROUP},{name}', url])
    hd = '\n'.join(lines) + '\n'
    combined = merge_playlists(base, hd)
    parse_entries(hd)
    (root / 'english_hd.m3u').write_text(hd, encoding='utf-8')
    combined_path.write_text(combined, encoding='utf-8')
    print(f'Published verified={len(passed)} merged_entries={len(parse_entries(combined))}', flush=True)
    return True


def main():
    max_checks = int(os.getenv('ENGLISH_HD_MAX_CHECKS', '72'))
    workers = int(os.getenv('ENGLISH_HD_WORKERS', '6'))
    validated = build(max_checks=max_checks, workers=workers)
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a', encoding='utf-8') as output:
            output.write(f'validated={str(validated).lower()}\n')


if __name__ == '__main__':
    main()
