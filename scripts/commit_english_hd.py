#!/usr/bin/env python3
"""Commit checked IPTV results, rebuilding after a remote-main push race."""
import subprocess
import sys

FILES = ('english_hd.m3u', 'english_hd_verification.csv',
         'english_hd_candidates.json', 'data/iptv_candidates.json', 'data/iptv_selected.json')


def command(*args, check=True, capture_output=False):
    return subprocess.run(args, check=check, text=True, capture_output=capture_output)


def push_results(run=command, attempts=3):
    run('git', 'config', 'user.name', 'github-actions[bot]')
    run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    for attempt in range(1, attempts + 1):
        run('git', 'fetch', 'origin', 'main')
        head = run('git', 'rev-parse', 'HEAD', capture_output=True).stdout.strip()
        remote = run('git', 'rev-parse', 'origin/main', capture_output=True).stdout.strip()
        if head != remote:
            print(f'Remote main advanced; rebuilding attempt {attempt}.', flush=True)
            run('git', 'reset', '--hard', 'origin/main')
            run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
            run(sys.executable, 'scripts/build_english_hd.py', '--region', 'NZ_UNVERIFIED')
        run('git', 'diff', '--exit-code', '--', 'live_config.m3u', 'live_config_base.m3u')
        run('git', 'add', '--', *FILES)
        diff = run('git', 'diff', '--cached', '--quiet', check=False)
        if diff.returncode == 0:
            print('No IPTV result changes.')
            return True
        if diff.returncode != 1:
            raise RuntimeError('Cannot inspect staged IPTV results')
        run('git', 'commit', '-m', 'chore: refresh English HD IPTV verification')
        if run('git', 'push', 'origin', 'HEAD:main', check=False).returncode == 0:
            return True
        print(f'Push attempt {attempt} failed; fetching current main.', flush=True)
    raise RuntimeError('Could not push after three attempts; check contents:write and branch protection')


if __name__ == '__main__':
    push_results()
