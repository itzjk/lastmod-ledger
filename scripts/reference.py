import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def load(path):
    path = Path(path)
    manifest = json.loads(path.read_text())
    entries = ET.parse(path.parent / manifest['sitemap']).getroot()
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    dates = {e.findtext('s:loc', namespaces=ns): e.findtext('s:lastmod', namespaces=ns) for e in entries}
    hashes = {row['url']: hashlib.sha256((path.parent / row['file']).read_bytes()).hexdigest() for row in manifest['files']}
    return dates, hashes


if __name__ == '__main__':
    before, after = map(load, sys.argv[1:3])
    counts = {}
    for url in sorted(before[0].keys() & after[0].keys()):
        result = 'bytes-' + ('unchanged' if before[1][url] == after[1][url] else 'changed')
        result += '/date-' + ('unchanged' if before[0][url] == after[0][url] else 'changed')
        counts[result] = counts.get(result, 0) + 1
        print(url, result)
    print(json.dumps(counts, sort_keys=True))
