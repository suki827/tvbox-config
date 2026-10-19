import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_live


class UpdateLiveTests(unittest.TestCase):
    def test_refresh_keeps_verified_english_group(self):
        hd = '#EXTM3U\n#EXTINF:-1 tvg-id="HD.us" group-title="英文高清",HD\nhttps://example.org/hd.m3u8\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'english_hd.m3u').write_text(hd, encoding='utf-8')
            old = '#EXTM3U\n#EXTINF:-1 group-title="中国",旧频道\nhttps://example.org/old.m3u8\n'
            (root / 'live_config_base.m3u').write_text(old, encoding='utf-8')
            with patch.object(update_live, 'SOURCES', [('新闻', 'https://example.org/list')]), patch.object(
                update_live, 'fetch', return_value='#EXTM3U\n#EXTINF:-1,New\nhttps://example.org/new.m3u8\n'
            ):
                self.assertTrue(update_live.main(root=root))
            combined = (root / 'live_config.m3u').read_text(encoding='utf-8')
            self.assertIn('group-title="英文高清"', combined)
            self.assertIn('group-title="新闻"', combined)
            self.assertIn('旧频道', combined)
            self.assertEqual((root / 'live_config_base.m3u').read_text(encoding='utf-8').count('#EXTINF:'), 2)

    def test_fetch_failure_preserves_previous_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('live_config_base.m3u', 'live_config.m3u'):
                (root / name).write_text('#EXTM3U\n', encoding='utf-8')
            with patch.object(update_live, 'SOURCES', [('新闻', 'https://example.org/list')]), patch.object(
                update_live, 'fetch', side_effect=TimeoutError('timed out')
            ):
                self.assertFalse(update_live.main(root=root))
            self.assertEqual((root / 'live_config.m3u').read_text(encoding='utf-8'), '#EXTM3U\n')


if __name__ == '__main__':
    unittest.main()
