import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import iterparse
from defusedxml.common import DefusedXmlException

from .reader import Limits, Reader, ReadIssue

NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
PREFIX = '{' + NS + '}'
QUADRANTS = tuple('bytes-' + b + '/date-' + d for b in ('changed', 'unchanged') for d in ('changed', 'unchanged'))
REVIEW = {QUADRANTS[1], QUADRANTS[2]}
NOTICE = 'Review discordant pairs: edits may be minor or on the same day, or affect resources outside the mapped file. These observations do not establish modification time, significance, date correctness, penalties or crawl effects.'


class InputError(Exception):
    pass


def public_url(value):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def date_status(values):
    if not values:
        return 'missing'
    if len(values) != 1:
        return 'ambiguous'
    value = values[0]
    if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            date.fromisoformat(value)
            return 'date'
        except ValueError:
            return 'invalid'
    match = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.[0-9]+)?)?(Z|[+-]([0-9]{2}):([0-9]{2}))', value)
    if match:
        year, month, day, hour, minute, second, zone, zh, zm = match.groups()
        try:
            date(int(year), int(month), int(day))
            if int(hour) < 24 and int(minute) < 60 and int(second or 0) < 60 and int(zh or 0) < 24 and int(zm or 0) < 60:
                return 'outside-subset'
        except ValueError:
            pass
    if re.fullmatch(r'[0-9]{4}(?:-[0-9]{2})?', value):
        try:
            date(int(value[:4]), int(value[5:7]) if len(value) > 4 else 1, 1)
            return 'outside-subset'
        except ValueError:
            pass
    return 'invalid'


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_manifest(path, reader):
    try:
        observed, raw = reader.read(path, reader.limits.manifest_bytes, keep=True)
        manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_keys)
    except (ReadIssue, ValueError, UnicodeError, RecursionError) as error:
        raise InputError(f'manifest {path}: {error}') from error
    if not isinstance(manifest, dict) or set(manifest) != {'sitemap', 'files'}:
        raise InputError(f'manifest {path}: expected exactly sitemap and files')
    if not valid_path(manifest['sitemap']) or not isinstance(manifest['files'], list):
        raise InputError(f'manifest {path}: sitemap must be a local path and files a list')
    if len(manifest['files']) > reader.limits.entries:
        raise InputError(f'manifest {path}: entry-limit')
    for index, row in enumerate(manifest['files'], 1):
        if not isinstance(row, dict) or set(row) != {'url', 'file'} or not public_url(row['url']) or not valid_path(row['file']):
            raise InputError(f'manifest {path}: files[{index}] needs an absolute HTTP(S) url and local file path')
    return manifest, observed


def valid_path(value):
    return isinstance(value, str) and bool(value) and '\x00' not in value and not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', value)


def parse_sitemap(raw, path, limit):
    entries = []
    issues = []
    depth = 0
    nodes = 0
    root = None
    kind = 'urlset'
    try:
        for event, element in iterparse(io.BytesIO(raw), events=('start', 'end'), forbid_dtd=True, forbid_entities=True, forbid_external=True):
            if event == 'start':
                depth += 1
                nodes += 1
                if depth > 32 or nodes > limit * 20 + 1:
                    raise InputError(f'sitemap {path}: XML depth/node limit')
                if root is None:
                    root = element
                    if root.tag == PREFIX + 'sitemapindex':
                        kind = 'sitemapindex'
                        issues.append({'code': 'sitemap-index-outside-scope', 'source': {'path': path, 'xpath': '/sitemapindex'}})
                    elif root.tag != PREFIX + 'urlset':
                        raise InputError(f'sitemap {path}: expected urlset with namespace {NS}')
                continue
            if depth == 2:
                position = len(entries) + 1
                if position > limit:
                    raise InputError(f'sitemap {path}: entry-limit')
                source = {'path': path, 'entry': position, 'xpath': f'/s:{kind}/*[{position}]'}
                loc_nodes = element.findall(PREFIX + 'loc')
                last_nodes = element.findall(PREFIX + 'lastmod')
                locs = [''.join(node.itertext()) for node in loc_nodes]
                dates = [''.join(node.itertext()) for node in last_nodes]
                errors = []
                if element.tag != PREFIX + 'url':
                    errors.append('entry-outside-scope')
                if len(locs) != 1 or not public_url(locs[0]) or any(len(node) for node in loc_nodes):
                    errors.append('invalid-or-ambiguous-loc')
                status = date_status(dates)
                if any(len(node) for node in last_nodes):
                    status = 'invalid'
                if status != 'date':
                    errors.append('lastmod-' + status)
                extensions = [node.tag for node in element if node.tag not in {PREFIX + k for k in ('loc', 'lastmod', 'priority', 'changefreq')}]
                if extensions:
                    errors.append('extension-outside-scope')
                entries.append({'source': source, 'tag': element.tag, 'locs': locs, 'lastmods': dates, 'date_status': status, 'extensions': extensions, 'issues': errors})
                for code in errors:
                    issues.append({'code': code, 'source': source})
                element.clear()
                root.remove(element)
            depth -= 1
    except (ParseError, DefusedXmlException, UnicodeError, LookupError, ValueError) as error:
        raise InputError(f'sitemap {path}: rejected XML ({type(error).__name__}: {error})') from error
    return entries, issues, kind


def snapshot(path, reader):
    path = str(path)
    manifest, observed = load_manifest(path, reader)
    sitemap_path = str(Path(path).parent / manifest['sitemap'])
    try:
        xml_observed, raw = reader.read(sitemap_path, reader.limits.sitemap_bytes, keep=True)
    except ReadIssue as error:
        raise InputError(f'sitemap {sitemap_path}: {error}') from error
    if raw.startswith(b'\x1f\x8b'):
        raise InputError(f'sitemap {sitemap_path}: compressed sitemap outside scope')
    entries, issues, kind = parse_sitemap(raw, sitemap_path, reader.limits.entries)
    mappings = []
    for index, row in enumerate(manifest['files'], 1):
        file_path = str(Path(path).parent / row['file'])
        mapping = {'url': row['url'], 'file': row['file'], 'source': {'path': path, 'pointer': f'/files/{index - 1}'}, 'observation': None, 'issues': []}
        try:
            mapping['observation'], _ = reader.read(file_path, reader.limits.file_bytes)
        except ReadIssue as error:
            mapping['issues'].append(error.code)
            issues.append({'code': error.code, 'source': mapping['source'], 'path': file_path})
        mappings.append(mapping)
    return {'manifest': observed, 'sitemap': xml_observed, 'kind': kind, 'entries': entries, 'mappings': mappings, 'issues': issues}


def indexed_side(snap):
    entries = defaultdict(list)
    mappings = defaultdict(list)
    for entry in snap['entries']:
        if snap['kind'] != 'urlset' or entry['tag'] != PREFIX + 'url':
            continue
        for loc in set(entry['locs']):
            entries[loc].append(entry)
    for mapping in snap['mappings']:
        mappings[mapping['url']].append(mapping)
    return entries, mappings


def row_side(url, snap, index):
    entries, mappings = index
    es, ms = entries.get(url, []), mappings.get(url, [])
    errors = []
    if not snap['manifest']['stable'] or not snap['sitemap']['stable']:
        errors.append('snapshot-concurrent-change')
    if not es:
        if ms:
            errors.append('mapping-without-sitemap-url')
    elif len(es) > 1:
        errors.append('duplicate-sitemap-url')
    else:
        errors.extend(es[0]['issues'])
    if es and not ms:
        errors.append('unmapped-url')
    if len(ms) > 1:
        errors.append('duplicate-manifest-url')
    for mapping in ms:
        errors.extend(mapping['issues'])
        obs = mapping['observation']
        if obs and not obs['stable']:
            errors.append('file-concurrent-change')
    return {'entries': es, 'mappings': ms, 'issues': sorted(set(errors))}


def bytes_ready(side):
    if len(side['entries']) != 1 or len(side['mappings']) != 1:
        return False
    blocked = {'snapshot-concurrent-change', 'invalid-or-ambiguous-loc', 'entry-outside-scope'}
    if blocked.intersection(side['issues']):
        return False
    mapping = side['mappings'][0]
    return not mapping['issues'] and mapping['observation'] is not None and mapping['observation']['stable']


def dates_ready(side):
    return len(side['entries']) == 1 and side['entries'][0]['date_status'] == 'date' and not {'snapshot-concurrent-change', 'invalid-or-ambiguous-loc', 'entry-outside-scope'}.intersection(side['issues'])


def compare(before, after, limits=None):
    reader = Reader(limits or Limits())
    snapshots = [snapshot(before, reader), snapshot(after, reader)]
    reader.recheck()
    indices = [indexed_side(snap) for snap in snapshots]
    urls = sorted(set().union(*(set(es) | set(ms) for es, ms in indices)))
    rows = []
    for url in urls:
        sides = [row_side(url, snap, index) for snap, index in zip(snapshots, indices)]
        present = [bool(side['entries']) for side in sides]
        presence = 'common' if all(present) else 'removed' if present[0] else 'added' if present[1] else 'manifest-only'
        quadrant = None
        bytes_equal = None
        dates_equal = None
        if presence == 'common':
            if all(bytes_ready(side) for side in sides):
                bytes_equal = sides[0]['mappings'][0]['observation']['sha256'] == sides[1]['mappings'][0]['observation']['sha256']
            if all(dates_ready(side) for side in sides):
                dates_equal = sides[0]['entries'][0]['lastmods'][0] == sides[1]['entries'][0]['lastmods'][0]
            if bytes_equal is not None and dates_equal is not None:
                quadrant = 'bytes-' + ('unchanged' if bytes_equal else 'changed') + '/date-' + ('unchanged' if dates_equal else 'changed')
        rows.append({'url': url, 'presence': presence, 'before': sides[0], 'after': sides[1], 'bytes_equal': bytes_equal, 'dates_equal': dates_equal, 'result': quadrant, 'review': quadrant in REVIEW})
    counts = Counter(row['result'] for row in rows if row['result'])
    presence_counts = Counter(row['presence'] for row in rows)
    incomplete_rows = sum(row['result'] is None or bool(row['before']['issues'] or row['after']['issues']) for row in rows)
    complete = bool(rows) and incomplete_rows == 0 and not any(snap['issues'] for snap in snapshots)
    review = sum(row['review'] for row in rows)
    exit_code = 2 if not complete else 1 if review else 0
    return {'schema_version': 1, 'status': 'incomplete' if not complete else 'review' if review else 'complete', 'exit_code': exit_code, 'empty': not rows, 'review_candidates': review, 'counts': {'urls': len(rows), 'compared': sum(counts.values()), 'uncompared': len(rows) - sum(counts.values()), 'incomplete_rows': incomplete_rows, 'presence': {key: presence_counts[key] for key in ('common', 'added', 'removed', 'manifest-only')}, 'quadrants': {key: counts[key] for key in QUADRANTS}}, 'coverage': {key: snap for key, snap in zip(('before', 'after'), snapshots)}, 'results': rows, 'limits': asdict(reader.limits), 'bytes_read': reader.bytes_read, 'notice': NOTICE}
