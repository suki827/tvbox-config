import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_media
from scripts.playlist import parse_entries


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.sources = build_media.read_json(build_media.ROOT/'data/media_sources.json')
        self.items = build_media.read_json(build_media.ROOT/'data/media_items.json')

    def test_seed_and_catalog_have_unique_valid_entries(self):
        build_media.validate(self.sources, self.items)
        self.assertEqual(len(self.sources), 18)
        self.assertEqual(len({i['id'] for i in self.items}), len(self.items))

    def test_unapproved_stream_never_published_even_if_probe_passes(self):
        item = copy.deepcopy(self.items[0]); item.update(type='live_video', stream_url='https://example.org/live.m3u8', profiles=['A'])
        result = build_media.playlist([item], {item['source_id']: self.sources[0]}, 'live_video', 'A', {item['id']:{'status':'PASS'}})
        self.assertEqual(result, '#EXTM3U\n')

    def test_approved_stream_requires_probe_and_keeps_prior_on_transient_failure(self):
        source = copy.deepcopy(self.sources[0]); source.update(rights_status='approved', rights_checked_at='2026-10-19', access_types=source['access_types']+['live_video'], approved_stream_types=['live_video'])
        item = copy.deepcopy(self.items[0]); item.update(type='live_video', stream_url='https://example.org/live.m3u8', profiles=['A'], rights_status='approved', review_status='approved', drm_status='none', rights_evidence_url='https://example.org/terms', rights_checked_at='2026-10-19', access_requirements='none')
        sources = {source['id']:source}
        passed = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'PASS'}})
        self.assertEqual(len(parse_entries(passed)),1)
        failed = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'TIMEOUT'}},passed)
        self.assertEqual(failed,passed)
        revoked = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'ACCESS_DENIED'}},passed)
        self.assertEqual(revoked,'#EXTM3U\n')

    def test_official_youtube_link_allowed_but_never_as_stream(self):
        self.assertTrue(build_media.safe_url('https://www.youtube.com/watch?v=abc'))
        self.assertFalse(build_media.safe_stream_url('https://www.youtube.com/watch?v=abc'))

    def test_duplicate_or_token_stream_rejected(self):
        item = copy.deepcopy(self.items[0]); item.update(type='live_video',stream_url='https://example.org/live?token=secret')
        with self.assertRaises(ValueError): build_media.validate(self.sources,[item])

    def test_build_does_not_touch_existing_base_playlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data').mkdir();(root/'docs').mkdir()
            for name in ('media_sources.json','media_items.json','channel_health.json'):
                (root/'data'/name).write_bytes((build_media.ROOT/'data'/name).read_bytes())
            original=(build_media.ROOT/'live_config.m3u').read_bytes()
            (root/'live_config.m3u').write_bytes(original)
            build_media.build(root)
            self.assertEqual((root/'live_config.m3u').read_bytes(),original)
            for name in ('premium_tv.m3u','premium_radio.m3u','english_learning.m3u'):
                self.assertEqual((root/name).read_text(),'#EXTM3U\n')

    def test_total_check_failure_keeps_published_catalogs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'data').mkdir(); (root/'docs').mkdir()
            for name in ('media_sources.json', 'media_items.json', 'channel_health.json'):
                (root/'data'/name).write_bytes((build_media.ROOT/'data'/name).read_bytes())
            old = b'{"published":true}\n'
            (root/'premium_catalog.json').write_bytes(old)
            with patch.object(build_media, 'check_web', return_value=('UNREACHABLE', None, 'offline')), \
                 patch.object(build_media, 'probe', return_value=('TIMEOUT', 0, 0, 'offline')):
                with self.assertRaises(RuntimeError): build_media.build(root, do_check=True)
            self.assertEqual((root/'premium_catalog.json').read_bytes(), old)
            self.assertTrue((root/'media_check_report.csv').exists())

    def test_rss_format_validation(self):
        class Response:
            status=200
            headers={}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,size): return b'<rss><channel><item><title>Episode</title></item></channel></rss>'
        with patch('urllib.request.urlopen',return_value=Response()):
            self.assertEqual(build_media.check_web('https://example.org/feed',rss=True)[0],'PASS')

    def test_health_statuses_stay_separate(self):
        old = {'status': 'TIMEOUT', 'consecutive_failures': 2,
               'last_success_at': '2026-10-01', 'quarantined': False}
        def update(status, kind='official_link'):
            return build_media.update_health(old, {'status': status, 'type': kind,
                                                     'checked_at': '2026-10-19'})
        self.assertEqual(update('TIMEOUT')['consecutive_failures'], 3)
        self.assertTrue(update('TIMEOUT')['quarantined'])
        self.assertEqual(update('UNREACHABLE')['consecutive_failures'], 3)
        self.assertEqual(update('PASS')['consecutive_failures'], 0)
        self.assertEqual(update('PASS')['last_success_at'], '2026-10-19')
        for status in ('SKIPPED_POLICY', 'PENDING_RIGHTS', 'ACCESS_DENIED',
                       'REGION_RESTRICTED', 'LOW_RESOLUTION', 'STALE_RSS'):
            result = update(status, 'podcast' if status == 'STALE_RSS' else 'live_video')
            self.assertEqual(result['consecutive_failures'], 0, status)
            self.assertFalse(result['quarantined'], status)
        self.assertEqual(update('ACCESS_DENIED')['region_status'], 'UNKNOWN')
        self.assertEqual(update('REGION_RESTRICTED')['region_status'], 'RESTRICTED')
        self.assertEqual(update('STALE_RSS', 'podcast')['freshness_status'], 'STALE')
        self.assertEqual(update('LOW_RESOLUTION', 'live_video')['quality_status'], 'LOW_RESOLUTION')

    def test_legacy_tvnz_and_stale_rss_quarantine_migration(self):
        history = {'tvnz-plus-home': {'status': 'SKIPPED_POLICY', 'consecutive_failures': 5,
                                     'quarantined': True, 'last_success_at': '2026-10-01'},
                   'voa-podcast': {'status': 'STALE_RSS', 'consecutive_failures': 4,
                                   'quarantined': True},
                   'offline': {'status': 'TIMEOUT', 'consecutive_failures': 2,
                               'quarantined': False}}
        fixed = build_media.migrate_health(history)
        self.assertEqual(fixed['tvnz-plus-home']['consecutive_failures'], 0)
        self.assertFalse(fixed['tvnz-plus-home']['quarantined'])
        self.assertEqual(fixed['tvnz-plus-home']['last_success_at'], '2026-10-01')
        self.assertEqual(fixed['voa-podcast']['consecutive_failures'], 0)
        self.assertFalse(fixed['voa-podcast']['quarantined'])
        self.assertEqual(fixed['offline']['consecutive_failures'], 2)

    def test_403_does_not_infer_region_restriction(self):
        import io
        import urllib.error
        error = urllib.error.HTTPError('https://example.org', 403, 'Forbidden', {}, io.BytesIO())
        with patch('urllib.request.urlopen', side_effect=error):
            status, code, _ = build_media.check_web('https://example.org')
        error.close()
        self.assertEqual((status, code), ('ACCESS_DENIED', 403))

    def test_approved_rnz_audio_is_deduplicated_and_utf8(self):
        sources = {source['id']: source for source in self.sources}
        candidates = [item for item in self.items if item['type'] == 'live_audio']
        self.assertEqual(len(candidates), 2)
        results = {item['id']: {'status': 'PASS'} for item in candidates}
        first = build_media.playlist(candidates, sources, 'live_audio', 'A', results)
        duplicate = copy.deepcopy(candidates[0]); duplicate['id'] = 'duplicate'; duplicate['stream_url'] = 'https://example.org/other.mp3'
        second = build_media.playlist(candidates + [duplicate], sources, 'live_audio', 'A',
                                      results | {'duplicate': {'status': 'PASS'}})
        self.assertEqual(first, second)
        self.assertEqual(len(parse_entries(first)), 2)
        self.assertIn('group-title="精品广播"', first.encode('utf-8').decode('utf-8'))

    def test_web_pass_does_not_change_vod_playback_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'data').mkdir(); (root/'docs').mkdir()
            for name in ('media_sources.json', 'media_items.json', 'channel_health.json'):
                (root/'data'/name).write_bytes((build_media.ROOT/'data'/name).read_bytes())
            with patch.object(build_media, 'check_web', return_value=('PASS', 200, '')), \
                 patch.object(build_media, 'probe', return_value=('PASS', 0, 0, '')):
                build_media.build(root, do_check=True)
            items = json.loads((root/'premium_catalog.json').read_text())
            nasa = next(item for item in items if item['id'] == 'nasa-plus-home')
            self.assertEqual(nasa['link_check_status'], 'PASS')
            self.assertEqual(nasa['playback_status'], 'unknown')

    def test_empty_live_master_keeps_existing_playlist(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'data').mkdir()
            (root/'data/media_sources.json').write_bytes((build_media.ROOT/'data/media_sources.json').read_bytes())
            items = [item for item in self.items if not item['type'].startswith('live_')]
            (root/'data/media_items.json').write_text(json.dumps(items))
            old = '#EXTM3U\n#EXTINF:-1 group-title="精品广播",RNZ National\nhttps://example.org/old.mp3\n'
            (root/'premium_radio.m3u').write_text(old)
            with self.assertRaises(RuntimeError): build_media.build(root, do_check=True)
            self.assertEqual((root/'premium_radio.m3u').read_text(), old)


if __name__=='__main__': unittest.main()
