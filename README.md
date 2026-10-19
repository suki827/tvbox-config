# TVBox 英文高清 IPTV

核心订阅：[`english_hd.m3u`](english_hd.m3u) · [播放器直连地址](https://raw.githubusercontent.com/suki827/tvbox-config/main/english_hd.m3u)

本订阅只发布来源使用条件明确、无需登录或 DRM、经过 `ffprobe` 验证至少 1280×720 的英文视频直播。当前收录 **Parliament TV (New Zealand)**：新西兰议会官方直播，Kordia 提供直播平台；主 HLS 包含 1080p 码率，适用于 TVBox、VLC。议会非开会时可能播放重播或待播画面。自动检测区域为 `NZ_UNVERIFIED`；新西兰实际播放仍需在当地设备复测。它的[官方使用条件](https://www3.parliament.nz/en/get-involved/information-for-the-press/parliament-tv-terms-and-conditions/)要求遵守广播法律义务，不得用于商业广告或误导性呈现。

## 构建与复测

- 候选池：[`data/iptv_candidates.json`](data/iptv_candidates.json)；正式选择：[`data/iptv_selected.json`](data/iptv_selected.json)。候选中的 `ffprobe` 成功只是技术结果，`rights_status=pending` 的频道不会发布。
- 本机测试：`python3 -m unittest discover -s tests -v`
- 执行检测：`python3 scripts/build_english_hd.py --workers 4 --timeout 15 --max-checks 24`
- Raspberry Pi 5：安装 `ffmpeg` 后运行 `python3 scripts/check_local_playback.py --playlist english_hd.m3u --region NZ --workers 2 --timeout 45`。报告写入 `local_playback_report.json`；全失败写入 `.failed.json`，保留原成功报告。`--region` 是操作者声明，不构成自动定位证明。

[`english_hd_verification.csv`](english_hd_verification.csv) 包含本轮每条候选的权限状态、检测状态、分辨率、耗时和检测区域。每天运行一次的 `english-hd.yml` 只处理英文高清 IPTV。旧媒体目录、Podcast、课程、A/B 文件保留但停止自动更新。综合列表 `live_config.m3u` 和 `live_config_base.m3u` 完全独立，英文高清流程不写入它们；旧综合列表自动更新已暂停，仅保留手动触发入口。

TVNZ+ 是需要账户的新西兰官方服务；目前未发现面向 TVBox 的公开、受支持第三方播放器 API 或 OAuth 接入。遵守[TVNZ+ 官方条款](https://corporate.tvnz.co.nz/house-rules/)，仅保留[官方观看入口](https://www.tvnz.co.nz/)，不探测旧列表中的 TVNZ 直链，也不处理账号、Cookie 或令牌。
