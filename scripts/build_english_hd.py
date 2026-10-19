#!/usr/bin/env python3
"""Generate English HD IPTV playlists from explicitly approved public sources."""
import csv
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://iptv-org.github.io/api/"
GROUP = 'group-title="英文高清"'
COUNTRIES = {"NZ", "US", "GB", "CA"}
CATEGORIES = {"news", "documentary", "education", "kids", "entertainment", "movies", "series", "lifestyle", "travel", "cooking", "science"}


def fetch(name):
    req = urllib.request.Request(API + name, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def entries(content):
    result = []
    current = None
    for line in content.splitlines()[1:]:
        if line.startswith("#EXTINF:"):
            if current:
                result.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current:
        result.append(current)
    return result


def check(url):
    try:
        process = subprocess.run(
            ["ffprobe", "-v", "error", "-rw_timeout", "12000000",
             "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "json", url],
            capture_output=True, text=True, timeout=22,
        )
        video = (json.loads(process.stdout or "{}").get("streams") or [{}])[0]
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        return width, height, process.returncode == 0 and width >= 1280 and height >= 720
    except Exception:
        return 0, 0, False


def main():
    approved_hosts = {host.strip().lower() for host in os.getenv("ENGLISH_HD_APPROVED_HOSTS", "").split(",") if host.strip()}
    feeds = fetch("feeds.json")
    english_feeds = {(f.get("channel"), f.get("id")) for f in feeds if "eng" in (f.get("languages") or [])}
    channels = {
        channel["id"]: channel for channel in fetch("channels.json")
        if channel.get("country") in COUNTRIES
        and set(channel.get("categories") or []).intersection(CATEGORIES)
        and not channel.get("is_nsfw") and not channel.get("closed")
    }
    candidates = []
    seen = set()
    for stream in fetch("streams.json"):
        channel = channels.get(stream.get("channel"))
        url = stream.get("url", "")
        if not channel or not url.startswith("https://") or url in seen:
            continue
        if (stream.get("channel"), stream.get("feed")) not in english_feeds and (stream.get("channel"), None) not in english_feeds:
            continue
        host = urllib.parse.urlparse(url).hostname or ""
        if host.lower() not in approved_hosts:
            continue
        seen.add(url)
        candidates.append((channel, url))

    passed = []
    report = []
    for channel, url in candidates[:int(os.getenv("ENGLISH_HD_MAX_CHECKS", "150"))]:
        width, height, good = check(url)
        report.append([channel["id"], channel["name"], channel["country"], width, height, "PASS" if good else "FAIL", url])
        if good:
            passed.append((channel, url))

    passed.sort(key=lambda item: (item[0]["country"], item[0]["name"]))
    hd_lines = ["#EXTM3U"]
    for channel, url in passed:
        hd_lines.extend([
            '#EXTINF:-1 tvg-id="{}" {},{}'.format(channel["id"], GROUP, channel["name"].replace(",", " ")),
            url,
        ])

    hd_path = ROOT / "english_hd.m3u"
    existing_hd = hd_path.read_text(encoding="utf-8") if hd_path.exists() else "#EXTM3U\n"
    if passed:
        hd_path.write_text("\n".join(hd_lines) + "\n", encoding="utf-8")
    elif not hd_path.exists():
        hd_path.write_text(existing_hd, encoding="utf-8")

    with (ROOT / "english_hd_verification.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "name", "country", "width", "height", "status", "url"])
        writer.writerows(report)

    target = ROOT / "live_config.m3u"
    original = entries(target.read_text(encoding="utf-8-sig"))
    english = entries(hd_path.read_text(encoding="utf-8"))
    retained = [entry for entry in original if GROUP not in entry[0]]
    if not english:
        english = [entry for entry in original if GROUP in entry[0]]
    output = ["#EXTM3U"]
    for entry in retained + english:
        output.extend(entry)
    target.write_text("\n".join(output) + "\n", encoding="utf-8")
    print("Candidates:", len(candidates), "Checked:", len(report), "HD passed:", len(passed))


if __name__ == "__main__":
    main()
