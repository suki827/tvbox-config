#!/usr/bin/env python3
import urllib.request
import pathlib

try:
    from .playlist import merge_base_playlists, merge_playlists
except ImportError:
    from playlist import merge_base_playlists, merge_playlists

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

def main(root=None):
    root = pathlib.Path(root) if root is not None else pathlib.Path(__file__).resolve().parents[1]
    lines = ["# TVBox直播列表", ""]
    failed = False
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
            failed = True

    if failed:
        print('At least one source failed; previous playlists left untouched.')
        return False

    txt_content = "\n".join(lines)

    # 同步生成标准 M3U，保留完整分组名
    m3u_lines = ["#EXTM3U"]
    current_group = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(",#genre#"):
            current_group = line[:-len(",#genre#")]
            continue
        if "," not in line:
            continue
        name, play = line.split(",", 1)
        if not play.startswith(("http://", "https://", "rtmp://", "rtsp://", "udp://")):
            continue
        safe_name = name.replace('"', "'")
        safe_group = current_group.replace('"', "'")
        m3u_lines.append(f'#EXTINF:-1 group-title="{safe_group}",{safe_name}')
        m3u_lines.append(play)

    refreshed = "\n".join(m3u_lines) + "\n"
    base_path = root / 'live_config_base.m3u'
    if base_path.exists():
        previous = base_path.read_text(encoding='utf-8-sig')
        base = merge_base_playlists(previous, refreshed)
    else:
        base = refreshed
    hd_path = root / 'english_hd.m3u'
    combined = merge_playlists(base, hd_path.read_text(encoding='utf-8')) if hd_path.exists() else base
    (root / 'live_config.txt').write_text(txt_content, encoding='utf-8')
    base_path.write_text(base, encoding='utf-8')
    (root / 'live_config.m3u').write_text(combined, encoding='utf-8')
    return True

if __name__ == "__main__":
    main()
