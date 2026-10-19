# 精品媒体目录

本项目保留原有 `live_config.m3u` 和 `live_config_base.m3u`。A/B 新目录由 `data/media_sources.json`、`data/media_items.json` 生成；`docs/` 是可用 GitHub Pages 发布的静态页面。HTTP 200、官网可浏览、`ffprobe` 成功分别只说明入口或技术连通性，**均不证明第三方播放器转播授权**。

## 五种接入

- `live_video`：只有来源和项目的第三方播放授权均标记 `approved`、有证据与审核日期、无登录要求、URL 无短期令牌、`ffprobe` 视频达到 1280×720，才进入 `premium_tv.m3u` 或 `english_learning.m3u`。
- `live_audio`：同样的授权和播放门槛，进入 `premium_radio.m3u`。
- `vod`：官方点播网页，收在 JSON 目录。官网返回 200 不表示视频可在新西兰播放。
- `podcast`：只有官方 RSS URL 实际通过 XML 与更新日期检测，才视为健康的订阅来源；过期 RSS 标记为 `STALE_RSS`。网页入口本身仍可放在目录。
- `official_link`：官网、官方 App 或课程页，只提供“打开官方入口”。

`rights_status`、`review_status` 和 `playback_status` 分开记录。RNZ 对第三方播放器公开提供广播流，National 与 Concert 已通过 `ffprobe`；其余电视直播候选均为 `pending`，没有发布直连流。公开页面和 IPTV-org 收录都不是授权证明。没有获准的直连流时，M3U 只有 `#EXTM3U`，这是预期的安全结果。TVNZ+ 官方条款禁止自动工具访问，其入口自动检测标记 `SKIPPED_POLICY`。

## 初始 18 家媒体

| 媒体 | A/B | 当前入口 | 新西兰或授权说明 |
|---|---|---|---|
| RNZ | A/B | National、Concert 官方广播流；Morning Report、Saturday Podcast | 官方明确支持第三方播放器；广播已通过 `ffprobe`；本次非 NZ 实测 |
| TVNZ+ | A | 官方频道及 App | 内容限新西兰；需账户；自动访问禁用 |
| BBC News | B | 官网 | BBC.com 直播权利按地区；NZ 未核实 |
| BBC Learning English | B | 4 个具体节目页与示例单集文字稿 | Podcast RSS 未核实 |
| CNN | — | 官网 | 完整电视直播需要订阅或电视服务商 |
| DW English | A | 官方直播页 | 第三方直连授权待核实 |
| France 24 English | A | 官方观看方式 | 第三方直连授权待核实 |
| Al Jazeera English | A | 官方直播页 | 第三方直连授权待核实 |
| PBS / NOVA | — | 官方节目页 | 多数 PBS 视频权益偏向美国 |
| PBS KIDS | — | 官方儿童入口 | 地区限制需逐项确认 |
| NASA+ | A | 官方直播、点播页 | 免费官方服务；第三方流授权待核实 |
| VOA Learning English | B | Level 1/2、Everyday Grammar 与官方 RSS | RSS 格式有效但最新节目为 2025-03-31，已标记过期；视频在 NZ 的播放未实测 |
| ABC Education | B | 官方课程页 | 官方课程入口；NZ 视频播放未实测 |
| ABC News Australia | A | ABC NEWS 国际直播入口 | 国际直播官网可用；ABC iview 其他直播限澳洲 |
| NHK WORLD-JAPAN | A | 官网 | 第三方直连授权待核实 |
| British Council | B | LearnEnglish 课程与 Podcast 页面 | RSS 直链未核实 |
| TED / TED-Ed | B | 官方课程入口 | TED 内容须遵守官方嵌入及分发政策 |
| Bloomberg Television | A | 官方直播页 | 自动检测可能返回 403；第三方授权待核实 |

每条来源的官网与证据 URL 在 `data/media_sources.json`，具体节目和待审直播候选在 `data/media_items.json`。RNZ 广播的证据是 [RNZ 官方播放器帮助页](https://www.rnz.co.nz/listen/audiohelp)；两条主数据记录含官方直连地址。其余七个重点电视直播候选的 `stream_url` 为 `null`，`rights_status=pending`，`drm_status=unknown`，没有运行流检测；页面可在静态目录按“电视直播”筛选后打开。`availability_regions` 是官方公布的限制，`nz_access=NZ_UNVERIFIED` 则表示尚未从有凭据的新西兰网络实测。

## 检测与更新

`python3 scripts/build_media.py --check` 每日由现有 `english-hd.yml` 工作流运行，最多 6 个并发任务；网页/RSS 8 秒、流 `ffprobe` 15 秒。检测结果在 `data/media_verification.json`、`media_check_report.csv`；状态在 `data/channel_health.json`。只有 `TIMEOUT`、`UNREACHABLE` 递增技术失败计数，连续 3 次后隔离复测，仍继续每天复测。`SKIPPED_POLICY`、`PENDING_RIGHTS`、`STALE_RSS`、`LOW_RESOLUTION` 不作为临时网络故障；403 只记 `ACCESS_DENIED`，不推断地区限制。旧版 TVNZ+、VOA、Bloomberg 的错误隔离计数已迁移修复。暂时超时或不可达时，只有已经发布、仍有有效授权证据的流才保留上一版；访问拒绝、权利撤销或不达画质门槛不保留。

GitHub 托管运行器的检测区域标记 `NZ_UNVERIFIED`。在实际位于新西兰的树莓派上安装 Python 3 与 `ffprobe`（Debian/Raspberry Pi OS：`sudo apt install ffmpeg`），克隆仓库后运行 `python3 scripts/check_local_playback.py --region NZ --workers 2 --timeout 15`。可用 `--output` 指定报告位置。它仅检测已授权的直播候选，记录分辨率、启动耗时、结果及操作者声明的地区；失败时写 `.failed.json` 而保留上一版成功报告。报告默认在 `.gitignore` 中，仅留本机，不需要公网入口或 GitHub Token。若自行上传，建议使用只限此仓库 `Contents: read and write` 的细粒度 Token，通过树莓派受限环境变量提供，绝不要存入仓库；上传报告也不改变授权字段。未从确认的新西兰网络运行前，不得称为 NZ 实测。`ENGLISH_HD_APPROVED_HOSTS` 是旧版英文高清工作流的可选 Repository Variable；安全默认值为空，即不接受 IPTV-org 流。新目录没有必需的 Repository Variable。

## GitHub Pages

本仓库目前只提交静态页面源文件，不假定 Pages 已启用。要发布：仓库 **Settings → Pages → Build and deployment → Deploy from a branch**，选择 `main` 和 `/docs`，保存后等待 Pages 部署成功。成功后才能将对应 URL 当作已上线页面。A/B 原始订阅文件在仓库根目录；若需在播放器使用，请选 GitHub `raw` 文件链接。空 M3U 表示当前没有经过授权与技术验证的直播。

## 官方限制资料

- [TVNZ+ 条款](https://corporate.tvnz.co.nz/house-rules/)
- [CNN 直播登录要求](https://help.cnn.com/us/Answer/Detail/000001007)
- [BBC News 国际直播可用地区](https://help.bbc.com/hc/en-us/articles/42343579768851-Can-I-watch-the-BBC-News-channel-online-via-BBC-com-and-or-BBC-app)
- [ABC 海外访问说明](https://help.abc.net.au/hc/en-us/articles/13845760226831-How-can-I-access-ABC-services-overseas)；[ABC iview 澳洲直播限制](https://help.abc.net.au/hc/en-us/articles/8552173461519-How-do-I-watch-live-streams-on-ABC-iview)
- [PBS 分发权利常见问题](https://help.pbs.org/support/solutions/articles/12000096220-common-questions)
- [TED 使用政策](https://www.ted.com/about/our-organization/our-policies-terms/ted-talks-usage-policy)
- [NASA 官方观看方式](https://www.nasa.gov/ways-to-watch/)
