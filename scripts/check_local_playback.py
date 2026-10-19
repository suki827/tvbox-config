#!/usr/bin/env python3
"""Check a published IPTV playlist from an operator-controlled local network."""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    from .build_english_hd import ROOT, check, safe_stream
    from .playlist import parse_entries
except ImportError:
    from build_english_hd import ROOT, check, safe_stream
    from playlist import parse_entries


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def run(playlist=ROOT/'english_hd.m3u', region='NZ', output=ROOT/'local_playback_report.json', workers=2, timeout=15, candidates=None):
    playlist, output = Path(playlist), Path(output)
    if not 1 <= workers <= 8 or not 2 <= timeout <= 60:
        raise ValueError('workers must be 1-8 and timeout 2-60 seconds')
    if candidates:
        candidate_path = Path(candidates)
        sources = json.loads(candidate_path.read_text(encoding='utf-8'))
        targets = [{'name': item.get('channel') or item.get('name') or item.get('id'),
                    'url': item.get('stream_url')} for item in sources if item.get('stream_url')]
        if any(not safe_stream(item['url']) for item in targets):
            raise ValueError('Candidate file contains an unsafe or non-video URL')
        source_name = candidate_path.name
    else:
        entries = parse_entries(playlist.read_text(encoding='utf-8-sig'))
        if any(not safe_stream(entry.url) for entry in entries):
            raise ValueError('Playlist contains an unsafe or non-video URL')
        targets = [{'name': entry.header.split(',', 1)[-1], 'url': entry.url} for entry in entries]
        source_name = playlist.name
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    def probe(item):
        width, height, status, detail, elapsed = check(item['url'], timeout)
        return {'name': item['name'], 'status': status,
                'width': width, 'height': height, 'startup_seconds': elapsed,
                'detail': detail, 'checked_at': checked_at}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(probe, targets))
    report = {'checked_at': checked_at, 'declared_region': region,
              'region_basis': 'operator_declared_local_network', 'runner': 'local',
              'playlist': playlist.name if not candidates else None,
              'candidate_file': source_name if candidates else None,
              'rights_unchanged': True, 'results': results}
    success = bool(results) and any(item['status'] == 'PASS' for item in results)
    target = output if success else output.with_name(output.stem + '.failed.json')
    atomic_json(target, report)
    return report, success, target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--playlist', type=Path, default=ROOT/'english_hd.m3u')
    parser.add_argument('--candidates', type=Path, help='Probe direct URLs in a candidate JSON report without changing rights data')
    parser.add_argument('--region', required=True, help='Operator-declared region, not geolocation proof')
    parser.add_argument('--output', type=Path, default=ROOT/'local_playback_report.json')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=15)
    args = parser.parse_args()
    report, success, target = run(args.playlist, args.region, args.output, args.workers, args.timeout, args.candidates)
    print(json.dumps({'channels': len(report['results']), 'passed': sum(r['status']=='PASS' for r in report['results']),
                      'declared_region': args.region, 'report': str(target)}, ensure_ascii=False))
    raise SystemExit(0 if success else 1)
