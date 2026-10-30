import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'


def generate(root):
    root = Path(root)
    for side in ('before', 'after', 'coverage'):
        folder = root / side
        folder.mkdir(parents=True, exist_ok=True)
        names = ['Alpha', 'Beta', 'Gamma', 'Delta']
        if side == 'coverage':
            names += ['Epsilon', 'Missing']
        entries = []
        files = []
        for name in names:
            changed = side != 'before' and name in ('Alpha', 'Gamma')
            body = name + (' revised' if changed else '') + '\n'
            if name != 'Missing':
                (folder / (name + '.html')).write_bytes(body.encode())
            date = '2026-10-30' if side != 'before' and name in ('Beta', 'Gamma') else '2026-10-29'
            url = 'https://example.test/' + name.lower()
            entries.append(f'  <url><loc>{escape(url)}</loc><lastmod>{date}</lastmod></url>')
            files.append({'url': url, 'file': name + '.html'})
        (folder / 'sitemap.xml').write_text(f'<urlset xmlns="{NS}">\n' + '\n'.join(entries) + '\n</urlset>\n', encoding='utf-8')
        (root / (side + '.json')).write_text(json.dumps({'sitemap': side + '/sitemap.xml', 'files': [dict(row, file=side + '/' + row['file']) for row in files]}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    generate(sys.argv[1] if len(sys.argv) > 1 else 'examples')
