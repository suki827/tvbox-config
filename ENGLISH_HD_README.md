# English HD IPTV automation

The [Refresh English HD workflow](.github/workflows/english-hd.yml) runs daily at 17:23 UTC and supports manual `workflow_dispatch`. Its GitHub token has `contents: write` permission. The adjacent [Update TVBox live config workflow](.github/workflows/update-live.yml) shares a concurrency group so the two jobs cannot write playlists at the same time.

## Source approval

Set repository variable `ENGLISH_HD_APPROVED_HOSTS` to a comma-separated list of **exact HTTPS hostnames** whose public streams you independently checked for authorized redistribution, for example `stream.example.org,cdn.example.org`. The safe default is empty: no stream is fetched or published. IPTV-org is used for channel/feed metadata and candidate discovery; its inclusion is not proof of a streaming license. An approved host is a human review input, not automatic legal verification. The repository maintainer must verify the channel and stream rights before adding each host. No secrets are needed. Region-specific playback rights still apply.

The workflow bounds probing to 72 URLs, six concurrent ffprobe processes, 22 seconds per process, and 15 minutes for the job. It considers English feeds in NZ, US, GB and CA and the requested content categories. A stream enters the English playlist only after ffprobe returns a video stream at least 1280×720. When several URLs represent one channel, the highest measured resolution wins. A 403 response without explicit geo-block text is reported as `ACCESS_DENIED`, not guessed to be a regional restriction.

## Files and safety

- `live_config_base.m3u` is the preserved original, non-English source. The initial file is an exact copy of the former `live_config.m3u` (4,068 entries). Future regular refreshes add new channels to this base without deleting old ones.
- `english_hd.m3u` is the independent list of streams that passed ffprobe. It starts empty until an authorized stream passes.
- `live_config.m3u` is rebuilt from the base plus validated entries in `group-title="英文高清"`. The merge excludes duplicate URLs and channels and is repeatable without appending copies.
- `english_hd_verification.csv` records every probed candidate's dimensions, status, detail, and URL. Each workflow run also uploads its report as an artifact, even when no stream passes. `CONFIGURATION_REQUIRED` is the initial report status; it is not a verification result.

If candidate discovery or probing produces no passing streams, the builder leaves both playlists as they were. The workflow commits generated files only after at least one stream passed and the merge validated. No-file-change runs exit successfully. GitHub Actions commits made with `GITHUB_TOKEN` do not trigger another workflow run; these workflows have no playlist-based push trigger in any case.

Statuses include `PASS`, `LOW_RESOLUTION`, `TIMEOUT`, `UNREACHABLE`, `REGION_RESTRICTED`, `ACCESS_DENIED`, `OTHER_ERROR`, and `DUPLICATE_CHANNEL`. A prior successful stream may remain in the published playlist after a wholly unsuccessful check; its current reachability is not implied. Playback from GitHub's runner does not guarantee playback in every region.

Run local tests with `python3 -m unittest discover -s tests -v`. The tests use mocked feeds and probe results, so they require no network or approved hosts.
