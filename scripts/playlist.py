"""Lossless M3U entry handling shared by both playlist update jobs."""

import re
from dataclasses import dataclass

ENGLISH_GROUP = 'group-title="英文高清"'
ID_RE = re.compile(r'\btvg-id="([^"]+)"')


@dataclass(frozen=True)
class Entry:
    lines: tuple[str, ...]
    url: str

    @property
    def header(self):
        return self.lines[0]

    @property
    def id_key(self):
        match = ID_RE.search(self.header)
        return match.group(1).casefold() if match and match.group(1) else ''

    @property
    def name_key(self):
        return self.header.split(',', 1)[-1].strip().casefold()


def parse_entries(content):
    if not content.lstrip('\ufeff').startswith('#EXTM3U'):
        raise ValueError('Missing #EXTM3U header')
    blocks = []
    current = None
    for line in content.splitlines():
        if line.startswith('#EXTINF:'):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append(current)
    entries = []
    for block in blocks:
        urls = [line for line in block[1:] if line and not line.startswith('#')]
        if len(urls) != 1 or ',' not in block[0]:
            raise ValueError('Malformed M3U entry: ' + block[0])
        entries.append(Entry(tuple(block), urls[0]))
    return entries


def merge_playlists(base, english):
    """Keep every non-English base entry and add only genuinely new HD entries."""
    base_entries = parse_entries(base)
    english_entries = parse_entries(english)
    first_entry = next((i for i, line in enumerate(base.splitlines()) if line.startswith('#EXTINF:')), None)
    prefix = base.splitlines()[:first_entry] if first_entry is not None else base.splitlines()
    retained = [entry for entry in base_entries if ENGLISH_GROUP not in entry.header]
    seen_urls = {entry.url for entry in retained}
    seen_ids = {entry.id_key for entry in retained if entry.id_key}
    seen_names = {entry.name_key for entry in retained}
    result = list(prefix)
    for entry in retained:
        result.extend(entry.lines)
    for entry in english_entries:
        if ENGLISH_GROUP not in entry.header:
            raise ValueError('English playlist contains an entry outside the English group')
        if entry.url in seen_urls or entry.name_key in seen_names or (entry.id_key and entry.id_key in seen_ids):
            continue
        result.extend(entry.lines)
        seen_urls.add(entry.url)
        seen_names.add(entry.name_key)
        if entry.id_key:
            seen_ids.add(entry.id_key)
    merged = '\n'.join(result).rstrip('\n') + '\n'
    parse_entries(merged)
    return merged


def merge_base_playlists(previous, refreshed):
    """Add fresh non-English channels without deleting the existing base."""
    old_entries = [entry for entry in parse_entries(previous) if ENGLISH_GROUP not in entry.header]
    new_entries = [entry for entry in parse_entries(refreshed) if ENGLISH_GROUP not in entry.header]
    urls = {entry.url for entry in old_entries}
    ids = {entry.id_key for entry in old_entries if entry.id_key}
    names = {entry.name_key for entry in old_entries}
    lines = ['#EXTM3U']
    for entry in old_entries:
        lines.extend(entry.lines)
    for entry in new_entries:
        if entry.url in urls or entry.name_key in names or (entry.id_key and entry.id_key in ids):
            continue
        lines.extend(entry.lines)
        urls.add(entry.url)
        names.add(entry.name_key)
        if entry.id_key:
            ids.add(entry.id_key)
    return '\n'.join(lines) + '\n'
