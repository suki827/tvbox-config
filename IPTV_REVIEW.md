# 美国 / 英国英文直播源审核

候选范围严格限定为用户指定的 12 个频道。开始/结束时 `live_config.m3u` 与 `live_config_base.m3u` 均各有 4,071 个 `#EXTINF` 条目，基线 SHA-256 同为 `3eccadddfe79704699bc59d54a7b12d810bb95b9cd17f85724635a90098048ef`。英文高清发布流程不修改这两个文件。

IPTV-org 的美国/英国列表只用于发现候选。每个候选分别记录来源、流地址、技术状态和授权状态；即使 HLS 通过 ffprobe/ffmpeg，也不会据此确认再分发权。

## 目标频道逐项结果

| 频道 | 官方观看入口与条件 | 直连候选 / 本轮检测 | 发布决定 |
|---|---|---|---|
| ABC News Live | [ABC News Live](https://abcnews.go.com/Live) 官方直播页面 | Akamai HLS 被索引收录；本轮 `NO_VIDEO` | 未取得第三方 M3U 权利，且无视频轨道 |
| CBS News 24/7 | [CBS 官方说明](https://www.cbsnews.com/streaming/)：免费网页、应用及其合作平台 | Pluto 分发候选；本轮 `TIMEOUT` | 合作平台可看不等于允许第三方播放器接入 |
| NBC News NOW | [NBC News 官方说明](https://nbcnews.zendesk.com/hc/en-us/articles/45174718134419-What-is-NBC-News-NOW)：免费 24/7 服务 | 用户提供的 Xumo CloudFront 地址；本轮 `TIMEOUT` | Xumo 分发地址未提供公开 M3U 再分发许可 |
| Bloomberg Television | [Bloomberg Live TV](https://www.bloomberg.com/livestream) 提供官方直播与设备/频道入口 | 官方域名 manifest 候选；本轮 `TIMEOUT` | 未找到允许第三方 M3U 使用该 feed 的条款 |
| LiveNOW from FOX | [LiveNOW from FOX](https://www.livenowfox.com/) 官方入口 | 第一轮 Amagi/Vizio HLS 读到 1280×720 且首帧解码通过；复测超时，最新状态为 `TIMEOUT` | 可达性不稳定；第三方播放/再分发权仍待书面确认 |
| FOX Weather | [FOX Weather Live](https://www.foxweather.com/live)；[帮助页](https://help.foxweather.com/hc/en-us/articles/4408918479643-How-can-I-watch-the-FOX-Weather-livestream)称官方直播免费 24/7 | 官方域名 HLS 候选；本轮 `TIMEOUT` | 官方网页/App 和列出的 FAST 合作平台不证明任意 M3U 再分发许可 |
| PBS NewsHour | [官方观看说明](https://www.pbs.org/newshour/how-to-watch-pbs-newshour)：节目按时段网页直播并提供点播 | 未发现持续线性频道 HLS，未探测 | 属于官方节目直播/点播入口，不作为 24/7 M3U 频道；PBS 本地台直播有地区权益限制 |
| Scripps News | [Scripps News](https://www.scrippsnews.com/) 官方入口 | Tubi 分发 HLS 候选；本轮 `TIMEOUT` | Tubi 合作分发不能证明可向第三方列表再发布 |
| CNN International | [CNN Live TV 帮助](https://help.cnn.com/us/Answer/Detail/000001007) | 未发现公开、授权的直连 HLS | 完整直播涉及电视服务商/订阅资格；保留官方入口 |
| Sky News | [Sky News Live](https://news.sky.com/watch-live) 官方网页播放器；[App 说明](https://www.sky.com/help/articles/sky-news-app-what-do-you-need-help-with)提示 UK 网络使用要求 | 未发现可公开使用的直连 HLS；没有提取官方播放器地址 | 仅官方网页/App；不据 App 地区说明推断网页以外的访问结果 |
| BBC News | [BBC News](https://www.bbc.com/news)；[BBC 官方订阅地区说明](https://help.bbc.com/hc/en-us/articles/46983028513299-Is-BBC-iPlayer-included-in-the-BBC-subscription) | 未发现获准 TVBox 使用的 HLS | BBC.com 直播权益因地区/产品而异；iPlayer 仅限英国且需要有效 TV licence。NZ 可用性未核实 |
| GB News | [GB News App](https://apps.apple.com/gb/app/gb-news/id1566365113) 官方直播入口 | UK 索引命中的是 Samsung Australia 的 FAST 地址；本轮 `ACCESS_DENIED` | 不把澳洲分发地址当作英国 feed；403 不自动判定为地区限制；无再分发授权 |

## 本轮探测汇总

12 个频道中找到 8 个直接 HLS 候选。首轮短测仅 LiveNOW from FOX 成功解码一帧（720p）；复测时 7 个候选超时（含 LiveNOW），GB News 的澳洲 FAST 地址返回访问拒绝。最新一轮没有稳定通过者，且没有任何 1080p 源通过。所有检测由当前自动化运行环境发起并标记 `GITHUB_UNVERIFIED`，不是新西兰本地测试。

所有 12 个频道目前均无经确认的第三方 M3U 发布许可。候选可以出现 `STREAM_FOUND` 和 `PROBE_PASSED`，但只有人工确认 `RIGHTS_APPROVED` 后才可能进入 `english_hd.m3u`。失败的候选不会清掉已有的、仍获准且只因暂时网络故障待复测的频道；本次迁移主动移除了范围外的 Parliament TV，因此当前列表只有标准 `#EXTM3U` 头、0 条频道。

Raspberry Pi 5 可在新西兰本地运行：

```sh
python3 scripts/check_local_playback.py --candidates english_hd_candidates.json --region NZ --workers 2 --timeout 15
```

该程序只写独立本地检测报告，不提升授权状态。Codex 当前无法访问用户的 Raspberry Pi，因此 NZ 本地检测未完成。
