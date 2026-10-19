# TVBox 配置与精品媒体目录

- 原有综合频道：[`live_config.m3u`](live_config.m3u)，原始基线：[`live_config_base.m3u`](live_config_base.m3u)
- 英文高清频道：[`english_hd.m3u`](english_hd.m3u)
- A 综合精品电视：[`premium_tv.m3u`](premium_tv.m3u)、[`premium_radio.m3u`](premium_radio.m3u)、[`premium_catalog.json`](premium_catalog.json)
- B 英语学习：[`english_learning.m3u`](english_learning.m3u)、[`english_learning_catalog.json`](english_learning_catalog.json)
- 静态目录网页源文件：[`docs/index.html`](docs/index.html)
- 媒体状态、授权门槛、地区限制和 Pages 启用步骤：[`MEDIA_CATALOG.md`](MEDIA_CATALOG.md)

M3U 只收录得到明确第三方播放器授权且技术检测通过的直播源。目前 A/B M3U 为空，官方点播、课程和 Podcast 入口可在 JSON 与静态目录中查看。自动检测报告见 [`data/media_verification.json`](data/media_verification.json) 和 [`media_check_report.csv`](media_check_report.csv)。

运行测试：`python3 -m unittest discover -s tests -v`。本地仅生成目录：`python3 scripts/build_media.py`；检测官方入口、RSS 与获准直播：`python3 scripts/build_media.py --check`。
