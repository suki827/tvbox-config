#!/usr/bin/env python3
import re, urllib.request, pathlib

SOURCES = [
    ("新西兰", "https://i.mjh.nz/nz/kodi-tv.m3u8"),
    ("中国", "http://193.123.86.190:14888/TV/iptv.php"),
    ("美国", "https://iptv-org.github.io/iptv/countries/us.m3u"),
    ("大洋洲", "https://iptv-org.github.io/iptv/regions/oce.m3u"),
]

UA = "Mozilla/5.0 TVBox-Live-Updater"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")

def parse_m3u(text):
    out=[]
    name=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            name=line.split(",",1)[1].strip() if "," in line else "频道"
        elif not line.startswith("#") and name:
            out.append((name,line))
            name=None
    return out

def parse_tvbox_txt(text):
    out=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or ",#genre#" in line:
            continue
        if "," in line:
            name,url=line.split(",",1)
            if url.startswith(("http://","https://","rtmp://","rtsp://","udp://")):
                out.append((name.strip(),url.strip()))
    return out

def main():
    lines=["# TVBox直播列表（按国家分类）",""]
    for group,url in SOURCES:
        try:
            text=fetch(url)
            items=parse_m3u(text) if "#EXTM3U" in text or "#EXTINF" in text else parse_tvbox_txt(text)
            lines += [f"{group},#genre#"]
            for name,play in items:
                lines.append(f"{name},{play}")
            lines.append("")
            print(group, len(items))
        except Exception as e:
            print("WARN", group, e)
    pathlib.Path("live_config.txt").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
