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
        source = copy.deepcopy(self.sources[0]); source.update(rights_status='approved', rights_checked_at='2026-10-19', access_types=source['access_types']+['live_video'])
        item = copy.deepcopy(self.items[0]); item.update(type='live_video', stream_url='https://example.org/live.m3u8', profiles=['A'], rights_status='approved', review_status='approved', drm_status='none', rights_evidence_url='https://example.org/terms', rights_checked_at='2026-10-19', access_requirements='none')
        sources = {source['id']:source}
        passed = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'PASS'}})
        self.assertEqual(len(parse_entries(passed)),1)
        failed = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'TIMEOUT'}},passed)
        self.assertEqual(failed,passed)
        revoked = build_media.playlist([item],sources,'live_video','A',{item['id']:{'status':'ACCESS_DENIED'}},passed)
        self.assertEqual(revoked,'#EXTM3U\n')

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
            with patch.object(build_media, 'check_web', return_value=('UNREACHABLE', None, 'offline')):
                with self.assertRaises(RuntimeError): build_media.build(root, do_check=True)
            self.assertEqual((root/'premium_catalog.json').read_bytes(), old)
            self.assertTrue((root/'media_check_report.csv').exists())

    def test_rss_format_validation(self):
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,size): return b'<rss><channel><item><title>Episode</title></item></channel></rss>'
        with patch('urllib.request.urlopen',return_value=Response()):
            self.assertEqual(build_media.check_web('https://example.org/feed',rss=True)[0],'PASS')


if __name__=='__main__': unittest.main()
