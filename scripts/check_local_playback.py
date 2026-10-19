#!/usr/bin/env python3
"""Probe approved media on an operator-controlled network (for example a Raspberry Pi)."""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    from .build_media import ROOT, probe, read_json, stream_eligible, validate
except ImportError:
    from build_media import ROOT, probe, read_json, stream_eligible, validate


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def run(root=ROOT, region='NZ', output=None, workers=2, timeout=15):
    root = Path(root)
    output = Path(output) if output else root / 'local_playback_report.json'
    if workers < 1 or workers > 8 or timeout < 2 or timeout > 60:
        raise ValueError('workers must be 1–8 and timeout must be 2–60 seconds')
    sources = read_json(root / 'data/media_sources.json')
    items = read_json(root / 'data/media_items.json')
    validate(sources, items)
    source_by_id = {source['id']: source for source in sources}
    candidates = [item for item in items if stream_eligible(item, source_by_id[item['source_id']])]
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    def check(item):
        start = time.monotonic()
        status, width, height, detail = probe(item, timeout=timeout)
        return {'id': item['id'], 'source_id': item['source_id'], 'type': item['type'],
                'status': status, 'ffprobe_passed': status == 'PASS', 'width': width,
                'height': height, 'startup_seconds': round(time.monotonic() - start, 3),
                'detail': detail, 'checked_at': checked_at}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(check, candidates))
    report = {'checked_at': checked_at, 'declared_region': region,
              'region_basis': 'operator_declared_local_network', 'runner': 'local',
              'rights_unchanged': True, 'candidate_count': len(candidates), 'results': results}
    if any(result['ffprobe_passed'] for result in results):
        atomic_json(output, report)
        return report, True
    failed_path = output.with_name(output.stem + '.failed.json')
    atomic_json(failed_path, report)
    return report, False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', required=True, help='Operator-declared test region, e.g. NZ')
    parser.add_argument('--output', type=Path, default=ROOT / 'local_playback_report.json')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=15, help='Per-stream ffprobe timeout in seconds')
    args = parser.parse_args()
    result, passed = run(region=args.region, output=args.output,
                         workers=args.workers, timeout=args.timeout)
    print(json.dumps({'candidate_count': result['candidate_count'],
                      'passed': sum(x['ffprobe_passed'] for x in result['results']),
                      'declared_region': result['declared_region'],
                      'report': str(args.output if passed else args.output.with_name(args.output.stem + '.failed.json'))},
                     ensure_ascii=False))
    raise SystemExit(0 if passed else 1)
