import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_english_hd
from scripts.playlist import merge_playlists, parse_entries


BASE = '''#EXTM3U
#EXTINF:-1 group-title="新闻",中文新闻
https://example.org/chinese.m3u8
#EXTINF:-1 tvg-id="Existing.us" group-title="美国",Existing
https://example.org/existing.m3u8
'''


class PlaylistTests(unittest.TestCase):
    def test_probe_budget_covers_each_country(self):
        found = [({'country': country}, f'https://example.org/{country}/{i}')
                 for country in ('CA', 'GB', 'NZ', 'US') for i in range(4)]
        selected = build_english_hd.select_candidates(found, 4)
        self.assertEqual({item[0]['country'] for item in selected}, {'NZ', 'US', 'GB', 'CA'})

    def test_merge_preserves_base_and_is_idempotent(self):
        hd = '''#EXTM3U
#EXTINF:-1 tvg-id="New.us" group-title="英文高清",New
https://example.org/new.m3u8
#EXTINF:-1 tvg-id="Existing.us" group-title="英文高清",Existing
https://example.org/other.m3u8
'''
        result = merge_playlists(BASE, hd)
        self.assertTrue(result.startswith(BASE))
        self.assertEqual(result.count('group-title="英文高清"'), 1)
        self.assertEqual(merge_playlists(result, hd), result)
        self.assertIn('中文新闻', result)
        self.assertEqual(len(parse_entries(result)), 3)

    def test_merge_rejects_same_name_even_with_different_id(self):
        hd = '''#EXTM3U
#EXTINF:-1 tvg-id="Other.us" group-title="英文高清",Existing
https://example.org/other.m3u8
'''
        self.assertEqual(merge_playlists(BASE, hd), BASE)

    def test_no_approval_does_not_change_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'live_config_base.m3u').write_text(BASE, encoding='utf-8')
            (root / 'live_config.m3u').write_text(BASE, encoding='utf-8')
            result = build_english_hd.build(root, approved_hosts=set())
            self.assertFalse(result)
            self.assertEqual((root / 'live_config.m3u').read_text(encoding='utf-8'), BASE)
            self.assertFalse((root / 'english_hd.m3u').exists())

    def test_verified_hd_only_and_failure_preserves_previous(self):
        channels = [
            {'id': 'Good.us', 'name': 'Good', 'country': 'US', 'categories': ['news']},
            {'id': 'Low.gb', 'name': 'Low', 'country': 'GB', 'categories': ['documentary']},
        ]
        feeds = [{'channel': x['id'], 'id': None, 'languages': ['eng']} for x in channels]
        streams = [
            {'channel': 'Good.us', 'feed': None, 'url': 'https://approved.example/good.m3u8'},
            {'channel': 'Good.us', 'feed': None, 'url': 'https://approved.example/duplicate.m3u8'},
            {'channel': 'Low.gb', 'feed': None, 'url': 'https://approved.example/low.m3u8'},
        ]
        data = {'channels.json': channels, 'feeds.json': feeds, 'streams.json': streams}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'live_config_base.m3u').write_text(BASE, encoding='utf-8')
            (root / 'live_config.m3u').write_text(BASE, encoding='utf-8')
            def probe(url):
                return (1920, 1080, 'PASS', '') if 'good' in url else (640, 360, 'LOW_RESOLUTION', '')
            with patch.object(build_english_hd, 'fetch', side_effect=data.get), patch.object(build_english_hd, 'check', side_effect=probe):
                self.assertTrue(build_english_hd.build(root, {'approved.example'}, max_checks=10, workers=2))
            hd = (root / 'english_hd.m3u').read_text(encoding='utf-8')
            combined = (root / 'live_config.m3u').read_text(encoding='utf-8')
            self.assertEqual(hd.count('#EXTINF:'), 1)
            self.assertIn('Good', combined)
            self.assertIn('中文新闻', combined)
            with (root / 'english_hd_verification.csv').open(encoding='utf-8', newline='') as handle:
                statuses = [row['status'] for row in csv.DictReader(handle)]
            self.assertEqual(sorted(statuses), ['LOW_RESOLUTION', 'LOW_RESOLUTION', 'PASS'])
            with patch.object(build_english_hd, 'fetch', side_effect=data.get), patch.object(build_english_hd, 'check', return_value=(0, 0, 'TIMEOUT', 'timed out')):
                self.assertFalse(build_english_hd.build(root, {'approved.example'}, max_checks=10, workers=2))
            self.assertEqual((root / 'english_hd.m3u').read_text(encoding='utf-8'), hd)
            self.assertEqual((root / 'live_config.m3u').read_text(encoding='utf-8'), combined)

    def test_probe_classifies_errors(self):
        from subprocess import CompletedProcess, TimeoutExpired
        cases = [
            ('Connection refused', 'UNREACHABLE'),
            ('HTTP error 403: geo blocked', 'REGION_RESTRICTED'),
            ('HTTP error 403: Forbidden', 'ACCESS_DENIED'),
            ('Invalid data found', 'OTHER_ERROR'),
        ]
        for message, expected in cases:
            with self.subTest(message=message), patch.object(build_english_hd.subprocess, 'run', return_value=CompletedProcess([], 1, '', message)):
                self.assertEqual(build_english_hd.check('https://example.org/x')[2], expected)
        with patch.object(build_english_hd.subprocess, 'run', side_effect=TimeoutExpired([], 22)):
            self.assertEqual(build_english_hd.check('https://example.org/x')[2], 'TIMEOUT')

    def test_higher_resolution_stream_wins_for_same_channel(self):
        data = {
            'feeds.json': [{'channel': 'News.us', 'id': None, 'languages': ['eng']}],
            'channels.json': [{'id': 'News.us', 'name': 'News', 'country': 'US', 'categories': ['news']}],
            'streams.json': [
                {'channel': 'News.us', 'feed': None, 'url': 'https://approved.example/720.m3u8'},
                {'channel': 'News.us', 'feed': None, 'url': 'https://approved.example/1080.m3u8'},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'live_config_base.m3u').write_text(BASE, encoding='utf-8')
            def probe(url):
                return (1920, 1080, 'PASS', '') if '1080' in url else (1280, 720, 'PASS', '')
            with patch.object(build_english_hd, 'fetch', side_effect=data.get), patch.object(build_english_hd, 'check', side_effect=probe):
                self.assertTrue(build_english_hd.build(root, {'approved.example'}))
            hd = (root / 'english_hd.m3u').read_text(encoding='utf-8')
            self.assertIn('/1080.m3u8', hd)
            self.assertNotIn('/720.m3u8', hd)


if __name__ == '__main__':
    unittest.main()
