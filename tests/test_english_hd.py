import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

from scripts import build_english_hd, check_local_playback, commit_english_hd
from scripts.playlist import parse_entries


class EnglishHDTests(unittest.TestCase):
    def setUp(self):
        self.seed = build_english_hd.read_json(build_english_hd.ROOT/'data/iptv_candidates.json')

    def approved(self):
        item = copy.deepcopy(next(x for x in self.seed if x['id']=='abc-news-live'))
        item.update(rights_status='approved', rights_checked_at='2026-10-19',
                    rights_evidence_url='https://example.org/licence', rights_approval_scope='third_party_playlist', drm_status='none',
                    access_requirements='none', probe_allowed=True,
                    stream_url='https://example.org/licensed.m3u8',
                    tvg_id='ABCNewsLive1.us@SD',tvg_logo='https://example.org/logo.png')
        return item

    def fixture(self, items):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root/'data').mkdir()
        build_english_hd.write_json(root/'data/iptv_candidates.json',items)
        build_english_hd.write_json(root/'data/iptv_selected.json',[])
        for name in ('live_config.m3u','live_config_base.m3u'):
            (root/name).write_bytes((build_english_hd.ROOT/name).read_bytes())
        return temporary, root

    def test_protected_baseline_hashes_and_counts(self):
        baseline = build_english_hd.read_json(build_english_hd.ROOT/'data/protected_baseline.json')
        for name, expected in baseline.items():
            blob = (build_english_hd.ROOT/name).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(),expected['sha256'])
            self.assertEqual(blob.count(b'#EXTINF:'),expected['entries'])

    def test_unapproved_probe_pass_cannot_publish(self):
        item = copy.deepcopy(self.seed[0]);item['probe_allowed']=True
        temporary,root = self.fixture([item])
        with temporary, patch.object(build_english_hd,'check',return_value=(1920,1080,'PASS','',0.5)):
            self.assertFalse(build_english_hd.build(root))
            self.assertEqual((root/'english_hd.m3u').read_text(),'#EXTM3U\n')
            self.assertEqual(build_english_hd.read_json(root/'data/iptv_candidates.json')[0]['state'],'DISCOVERED')

    def test_official_viewing_page_is_not_third_party_playlist_permission(self):
        item=self.approved()
        item['rights_approval_scope']='official_site_only'
        self.assertFalse(build_english_hd.publishable(item))

    def test_publish_format_utf8_and_protected_files_unchanged(self):
        item = self.approved()
        temporary,root = self.fixture([item])
        original = {name:(root/name).read_bytes() for name in ('live_config.m3u','live_config_base.m3u')}
        with temporary, patch.object(build_english_hd,'check',return_value=(1920,1080,'PASS','',0.2)):
            self.assertTrue(build_english_hd.build(root))
            first = (root/'english_hd.m3u').read_bytes()
            self.assertTrue(build_english_hd.build(root))
            self.assertEqual(first,(root/'english_hd.m3u').read_bytes())
            text = first.decode('utf-8')
            self.assertIn('group-title="美国·新闻"',text)
            self.assertIn('tvg-id="ABCNewsLive1.us@SD"',text)
            self.assertIn('tvg-logo="https://example.org/logo.png"',text)
            self.assertEqual(len(parse_entries(text)),1)
            for name,blob in original.items():self.assertEqual((root/name).read_bytes(),blob)

    def test_no_video_and_low_resolution_rejected(self):
        for output,expected in [(json.dumps({'streams':[]}), 'NO_VIDEO'),
                                (json.dumps({'streams':[{'codec_type':'video','width':640,'height':360}]}),'LOW_RESOLUTION')]:
            with self.subTest(expected=expected), patch.object(build_english_hd.subprocess,'run',return_value=CompletedProcess([],0,output,'')):
                self.assertEqual(build_english_hd.check('https://example.org/a.m3u8')[2],expected)

    def test_multibitrate_master_selects_highest_probed_video(self):
        streams = {'streams': [
            {'codec_type':'video','width':1024,'height':576},
            {'codec_type':'video','width':1280,'height':720},
            {'codec_type':'video','width':1920,'height':1080}]}
        with patch.object(build_english_hd.subprocess,'run',side_effect=[
                CompletedProcess([],0,json.dumps(streams),''), CompletedProcess([],0,'','')]):
            self.assertEqual(build_english_hd.check('https://example.org/master.m3u8')[:3],(1920,1080,'PASS'))

    def test_manifest_metadata_without_decodable_media_does_not_pass(self):
        streams = {'streams': [{'codec_type':'video','width':1920,'height':1080}]}
        with patch.object(build_english_hd.subprocess,'run',side_effect=[
                CompletedProcess([],0,json.dumps(streams),''),
                CompletedProcess([],1,'','Invalid data found when processing input')]) as run:
            result=build_english_hd.check('https://example.org/master.m3u8')
        self.assertEqual(result[2],'MEDIA_DECODE_FAILED')
        self.assertEqual(run.call_count,2)

    def test_master_reports_highest_variant_that_really_decodes(self):
        streams={'streams':[
            {'index':0,'codec_type':'video','width':1920,'height':1080},
            {'index':1,'codec_type':'video','width':1280,'height':720}]}
        with patch.object(build_english_hd.subprocess,'run',side_effect=[
                CompletedProcess([],0,json.dumps(streams),''),
                CompletedProcess([],1,'','Invalid media data'),
                CompletedProcess([],0,'','')]) as run:
            result=build_english_hd.check('https://example.org/master.m3u8')
        self.assertEqual(result[:3],(1280,720,'PASS'))
        self.assertIn('0:0',run.call_args_list[1].args[0])
        self.assertIn('0:1',run.call_args_list[2].args[0])

    def test_transient_source_failure_is_retried_before_rejection(self):
        with patch.object(build_english_hd,'check',side_effect=[
                (0,0,'TIMEOUT','slow',15.0), (1920,1080,'PASS','',0.4)]) as check:
            result=build_english_hd.check_with_retries('https://example.org/live.m3u8', attempts=2)
        self.assertEqual(result[2],'PASS')
        self.assertEqual(check.call_count,2)

    def test_rights_pending_probe_does_not_publish_and_candidate_states_are_separate(self):
        item=copy.deepcopy(next(x for x in self.seed if x['id']=='nbc-news-now'))
        temporary,root=self.fixture([item])
        with temporary, patch.object(build_english_hd,'check',return_value=(1920,1080,'PASS','',0.2)):
            self.assertFalse(build_english_hd.build(root))
            report=build_english_hd.read_json(root/'english_hd_candidates.json')[0]
            self.assertTrue(report['probe_passed'])
            self.assertFalse(report['rights_approved'])
            self.assertFalse(report['published'])
            self.assertFalse(report['nz_verified'])
            self.assertIn('STREAM_FOUND',report['status_flags'])
            self.assertIn('PROBE_PASSED',report['status_flags'])
            self.assertNotIn('RIGHTS_APPROVED',report['status_flags'])

    def test_verification_report_uses_channel_audit_columns(self):
        self.assertEqual(build_english_hd.REPORT_FIELDS,
            ('channel','country','source_url','stream_url','probe_status','width','height',
             'resolution','rights_status','rights_evidence','test_region','checked_at','failure_reason'))

    def test_403_is_access_denied_not_region(self):
        with patch.object(build_english_hd.subprocess,'run',return_value=CompletedProcess([],1,'','HTTP error 403: Forbidden')):
            self.assertEqual(build_english_hd.check('https://example.org/a.m3u8')[2],'ACCESS_DENIED')
        with patch.object(build_english_hd.subprocess,'run',side_effect=TimeoutExpired([],15)):
            self.assertEqual(build_english_hd.check('https://example.org/a.m3u8')[2],'TIMEOUT')

    def test_403_during_segment_decode_is_access_denied_not_region(self):
        streams={'streams':[{'codec_type':'video','width':1920,'height':1080}]}
        with patch.object(build_english_hd.subprocess,'run',side_effect=[
                CompletedProcess([],0,json.dumps(streams),''),
                CompletedProcess([],1,'','HTTP error 403: Forbidden')]):
            self.assertEqual(build_english_hd.check('https://example.org/a.m3u8')[2],'ACCESS_DENIED')

    def test_duplicate_url_and_signed_url_rejected(self):
        item=self.approved();duplicate=copy.deepcopy(item);duplicate['id']='other'
        with self.assertRaises(ValueError):build_english_hd.validate([item,duplicate])
        duplicate=copy.deepcopy(item);duplicate['id']='other';duplicate['stream_url']='https://example.org/other.m3u8'
        with self.assertRaises(ValueError):build_english_hd.validate([item,duplicate])
        self.assertFalse(build_english_hd.safe_stream('https://example.org/live.m3u8?token=secret'))
        self.assertFalse(build_english_hd.safe_stream('https://example.org/watch'))

    def test_non_us_uk_candidate_is_rejected(self):
        item=self.approved();item['country']='NZ'
        with self.assertRaises(ValueError):build_english_hd.validate([item])

    def test_temporary_failure_keeps_last_valid_but_not_fresh_verified(self):
        temporary,root=self.fixture([self.approved()])
        with temporary:
            with patch.object(build_english_hd,'check',return_value=(1920,1080,'PASS','',0.1)):
                build_english_hd.build(root)
            published=(root/'english_hd.m3u').read_bytes()
            with patch.object(build_english_hd,'check',return_value=(0,0,'TIMEOUT','slow',15.0)):
                build_english_hd.build(root)
            self.assertEqual((root/'english_hd.m3u').read_bytes(),published)
            selected=build_english_hd.read_json(root/'data/iptv_selected.json')[0]
            self.assertEqual(selected['publication_status'],'RETAINED_RECHECK')
            self.assertNotEqual(selected['state'],'VERIFIED')
            candidate=build_english_hd.read_json(root/'data/iptv_candidates.json')[0]
            self.assertEqual(candidate['last_successful_probe']['width'],1920)
            report=build_english_hd.read_json(root/'english_hd_candidates.json')[0]
            self.assertTrue(report['published'])
            self.assertFalse(report['probe_passed'])

    def test_revoked_rights_removes_previous_publication(self):
        temporary,root=self.fixture([self.approved()])
        with temporary:
            with patch.object(build_english_hd,'check',return_value=(1920,1080,'PASS','',0.1)):
                build_english_hd.build(root)
            items=build_english_hd.read_json(root/'data/iptv_candidates.json')
            items[0]['rights_status']='restricted'
            build_english_hd.write_json(root/'data/iptv_candidates.json',items)
            build_english_hd.build(root)
            self.assertEqual((root/'english_hd.m3u').read_text(),'#EXTM3U\n')

    def test_candidate_scope_is_only_us_and_uk(self):
        self.assertEqual(len(self.seed),12)
        self.assertEqual({item['country'] for item in self.seed},{'US','GB'})
        self.assertNotIn('tvnz-plus',{item['id'] for item in self.seed})
        workflow=(build_english_hd.ROOT/'.github/workflows/english-hd.yml').read_text()
        self.assertNotIn('build_media.py',workflow)
        self.assertNotIn('live_config.m3u',commit_english_hd.FILES)
        self.assertNotIn('live_config_base.m3u',commit_english_hd.FILES)

    def test_empty_pool_preserves_subscription(self):
        temporary,root=self.fixture([])
        old='#EXTM3U\n#EXTINF:-1 group-title="美国·新闻",Old\nhttps://example.org/old.m3u8\n'
        (root/'english_hd.m3u').write_text(old)
        with temporary:
            self.assertFalse(build_english_hd.build(root))
            self.assertEqual((root/'english_hd.m3u').read_text(),old)
            self.assertEqual(build_english_hd.read_json(root/'english_hd_candidates.json'),[])

    def test_out_of_scope_legacy_channel_is_not_retained_after_migration(self):
        item=copy.deepcopy(next(x for x in self.seed if x['id']=='fox-weather'))
        temporary,root=self.fixture([item])
        old='[]\n'
        build_english_hd.write_json(root/'data/iptv_selected.json',json.loads(old))
        (root/'english_hd.m3u').write_text('#EXTM3U\n#EXTINF:-1 group-title="英文·新闻",Parliament TV\nhttps://example.org/nz.m3u8\n')
        with temporary, patch.object(build_english_hd,'check',return_value=(0,0,'TIMEOUT','slow',10)):
            build_english_hd.build(root)
            self.assertEqual((root/'english_hd.m3u').read_text(encoding='utf-8'),'#EXTM3U\n')

    def test_local_report_separate_and_failure_preserves_success(self):
        temporary,root=self.fixture([])
        playlist=root/'english_hd.m3u';playlist.write_text(build_english_hd.playlist([self.approved()]))
        report=root/'local.json'
        with temporary:
            with patch.object(check_local_playback,'check',return_value=(1920,1080,'PASS','',0.3)):
                _,passed,_=check_local_playback.run(playlist,'NZ',report)
            self.assertTrue(passed);previous=report.read_bytes()
            with patch.object(check_local_playback,'check',return_value=(0,0,'TIMEOUT','slow',15.0)):
                _,passed,failed_path=check_local_playback.run(playlist,'NZ',report)
            self.assertFalse(passed);self.assertEqual(report.read_bytes(),previous)
            self.assertTrue(failed_path.exists())
            self.assertFalse((root/'data/media_verification.json').exists())

    def test_local_playback_can_probe_candidate_report_without_granting_rights(self):
        temporary,root=self.fixture([])
        candidates=root/'candidates.json'
        build_english_hd.write_json(candidates,[{'channel':'NBC News NOW','stream_url':'https://example.org/live.m3u8'}])
        output=root/'local.json'
        with temporary, patch.object(check_local_playback,'check',return_value=(1920,1080,'PASS','',0.3)):
            report,passed,_=check_local_playback.run(region='NZ',output=output,workers=1,timeout=5,candidates=candidates)
            self.assertTrue(passed)
            self.assertEqual(report['results'][0]['name'],'NBC News NOW')
            self.assertTrue(report['rights_unchanged'])
            self.assertEqual(report['runner'],'local')

    def test_push_conflict_fetches_and_rebuilds(self):
        calls=[];heads=iter(['old','commit','new']);remotes=iter(['old','new'])
        pushes=iter([1,0])
        def fake(*args,**kwargs):
            calls.append(args)
            if args[:3]==('git','rev-parse','HEAD'):return CompletedProcess(args,0,next(heads),'')
            if args[:3]==('git','rev-parse','origin/main'):return CompletedProcess(args,0,next(remotes),'')
            if args[:3]==('git','diff','--cached'):return CompletedProcess(args,1,'','')
            if args[:2]==('git','push'):return CompletedProcess(args,next(pushes),'','')
            return CompletedProcess(args,0,'','')
        self.assertTrue(commit_english_hd.push_results(fake))
        self.assertIn(('git','reset','--hard','origin/main'),calls)
        self.assertEqual(sum(x[:2]==('git','push') for x in calls),2)
        self.assertTrue(any('scripts/build_english_hd.py' in x for x in calls))


if __name__=='__main__':unittest.main()
