# TVBox English HD IPTV

正式订阅：[english_hd.m3u](https://raw.githubusercontent.com/suki827/tvbox-config/main/english_hd.m3u)

此列表只收录美国和英国英文直播。频道必须同时满足实际媒体帧解码、至少 1280×720、无登录/DRM 限制，并有明确的第三方播放器使用许可。公开网页、FAST 合作平台或 IPTV-org 的索引记录本身都不构成再分发许可。

当前 12 个目标频道中，发现 8 个直连 HLS 候选。两轮实测里，LiveNOW from FOX 曾有一次成功解码 1280×720，但随后的复测超时；最新报告按最新结果记为失败。没有候选取得可用于第三方 M3U 的许可证明，所以正式列表保持 0 个频道。报告分别保存候选状态和每条 URL 的探测原因：[`english_hd_candidates.json`](english_hd_candidates.json)、[`english_hd_verification.csv`](english_hd_verification.csv)。

## 本地运行

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_english_hd.py --workers 4 --timeout 15 --max-checks 12 --region GITHUB_UNVERIFIED
```

Raspberry Pi 5 安装 `ffmpeg` 后，可在新西兰本地检查候选或正式列表：

```sh
python3 scripts/check_local_playback.py --candidates english_hd_candidates.json --region NZ --workers 2 --timeout 15
python3 scripts/check_local_playback.py --playlist english_hd.m3u --region NZ --workers 2 --timeout 15
```

本地报告独立写入 `local_playback_report.json`。`--region NZ` 是操作者在本地网络运行时的声明；它不会更改候选的授权状态，也不会自动把结果写为新西兰验证。失败报告写到 `.failed.json`，保留上次成功报告。

`.github/workflows/english-hd.yml` 每日运行并支持手动触发。GitHub 托管运行器的报告标记为 `GITHUB_UNVERIFIED`，不能代替新西兰实测。工作流不触碰 `live_config.m3u` 或 `live_config_base.m3u`。
