# 英文高清 IPTV 候选审核

2026-10-19 从 `live_config.m3u` 的 4,071 个 M3U 条目读取名称、分组、tvg-id、tvg-logo、URL 和扩展名，人工精选高质量英文频道写入 `data/iptv_candidates.json`。原列表可发现流，但不证明语言、画质、地区可用性或第三方播放许可。`data/iptv_selected.json` 与候选池独立。两个受保护列表的基线哈希记录于 `data/protected_baseline.json`。

## 已发布

| 频道 | 依据 | 本轮结果 | 注意 |
|---|---|---|---|
| Parliament TV (New Zealand) | [议会转播条款](https://www3.parliament.nz/en/get-involved/information-for-the-press/parliament-tv-terms-and-conditions/)；[议会与 Kordia 平台说明](https://www3.parliament.nz/en/footer/about-us/parliamentary-service/parliament-sector-annual-reports/p%C5%ABrongo-%C4%81-tau-o-te-r%C4%81ngai-p%C4%81remata-202324-parliament-sector-annual-report-202324/introduction-and-shared-highlights/) | Kordia 主 HLS 的 1080p 轨道通过 `ffprobe`；1080p 子流首帧通过 `ffmpeg` 解码 | 仅在议会开会时直播议事；不可用于商业广告、赞助或误导性呈现；NZ 本地尚未实测 |

议会官方年度报告的稳定链接如发生变更，应从[议会官网](https://www.parliament.nz/)核对 Kordia 合作关系。正式流在 `english_hd.m3u`，此文档不复制播放 URL。

## 待审核与拒绝

技术检测通过但**未取得第三方播放器明确许可**：ABC News Australia、France 24 English、Bloomberg TV Asia。NHK WORLD-JAPAN 曾在本轮早一次探测中达到 720p，但最终复测超时；仍不具备发布许可。它们均为 `DISCOVERED`，不会进入 M3U。其他候选的无视频轨道、超时、服务器错误等细节见 `english_hd_verification.csv`。已有列表中 CNN、BBC、DW、Al Jazeera 等代理流不因名称或公开可达而获得授权。PBS KIDS 美国权益受限，不针对新西兰做绕过检测。

### TVNZ+

[TVNZ+ House Rules](https://corporate.tvnz.co.nz/house-rules/)规定账户仅限家庭使用、内容仅限新西兰、未经明确许可不得另作使用，并禁止自动工具及绕过访问或认证限制。[官方 TVNZ+](https://www.tvnz.co.nz/)提供网站和受支持设备入口；调查中未找到公开的、供 TVBox 调用的 OAuth/API 或第三方播放器方案。仓库不收集登录资料，不保存会话，也不发布 TVNZ+ 的 M3U 直链。候选数据中该项为 `REJECTED`（仅指直接 M3U 接入），官网入口继续保留。

## 状态含义

- `DISCOVERED`：发现或技术可达，但尚不满足全部发布条件。
- `VERIFIED`：来源条件和视频检测都通过，本轮可发布。
- `REJECTED`：本轮明确不合格，包括无视频、低于 720p 或直接接入不被支持。
- `RETAINED_RECHECK`：此前已发布且仍有有效许可的流本轮暂时超时；保留 URL，但本轮不标 `VERIFIED`。

GitHub Actions 从美国托管运行器检测，统一标记 `NZ_UNVERIFIED`。本地脚本报告独立保存，只有确实在新西兰网络上运行且由操作者确认时才可作为 NZ 实测证据。
