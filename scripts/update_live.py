#!/usr/bin/env python3
import urllib.request
import pathlib

SOURCES = [
    ("新西兰", "https://i.mjh.nz/nz/kodi-tv.m3u8"),
    ("中国", "http://193.123.86.190:14888/TV/iptv.php"),
    ("美国", "https://iptv-org.github.io/iptv/countries/us.m3u"),
    ("大洋洲", "https://iptv-org.github.io/iptv/regions/oce.m3u"),

    # 以下分类对应用户提供的文件名
    ("animation", "https://iptv-org.github.io/iptv/categories/animation.m3u"),
    ("documentary", "https://iptv-org.github.io/iptv/categories/documentary.m3u"),
    ("kids", "https://iptv-org.github.io/iptv/categories/kids.m3u"),
    ("music", "https://iptv-org.github.io/iptv/categories/music.m3u"),
    ("movies", "https://iptv-org.github.io/iptv/categories/movies.m3u"),
]

UA = "Mozilla/5.0 TVBox-Live-Updater"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")

def parse_m3u(text):
    out = []
    name = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            name = line.split(",", 1)[1].strip() if "," in line else "频道"
        elif not line.startswith("#") and name:
            out.append((name, line))
            name = None
    return out

def parse_tvbox_txt(text):
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ",#genre#" in line:
            continue
        if "," in line:
            name, url = line.split(",", 1)
            if url.startswith(("http://", "https://", "rtmp://", "rtsp://", "udp://")):
                out.append((name.strip(), url.strip()))
    return out

def should_skip(name, play):
    n = name.lower()
    p = play.lower()
    return (
        "咪视界" in name
        or "睛彩" in name
        or "cmvideo.cn" in p
    )

def main():
    lines = ["# TVBox直播列表", ""]
    for group, url in SOURCES:
        try:
            text = fetch(url)
            items = parse_m3u(text) if "#EXTM3U" in text or "#EXTINF" in text else parse_tvbox_txt(text)

            seen = set()
            cleaned = []
            for name, play in items:
                if should_skip(name, play):
                    continue
                key = (name, play)
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append((name, play))

            lines.append(f"{group},#genre#")
            for name, play in cleaned:
                lines.append(f"{name},{play}")
            lines.append("")
            print(group, len(cleaned))
        except Exception as e:
            print("WARN", group, e)

    pathlib.Path("live_config.txt").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
