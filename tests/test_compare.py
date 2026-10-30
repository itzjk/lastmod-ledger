import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from lastmod_ledger.core import InputError, NS, QUADRANTS, compare
from lastmod_ledger.reader import Limits, Reader


def run(site, after='after', *options):
    process = subprocess.run([sys.executable, '-m', 'lastmod_ledger', 'compare', str(site / 'before.json'), str(site / (after + '.json')), '--json', *options], capture_output=True, text=True, cwd=site)
    assert not process.stderr
    report = json.loads(process.stdout)
    assert process.returncode == report['exit_code']
    return report


def digest_inputs(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}


def xml_edit(site, side, action):
    path = site / side / 'sitemap.xml'
    tree = ET.parse(path)
    action(tree.getroot())
    tree.write(path, encoding='utf-8', xml_declaration=True)


def manifest_edit(site, side, action):
    path = site / (side + '.json')
    data = json.loads(path.read_text())
    action(data)
    path.write_text(json.dumps(data))


def getrow(report, name='alpha'):
    return next(row for row in report['results'] if row['url'] == 'https://example.test/' + name)


def assert_totals(report):
    counts = report['counts']
    assert sum(counts['quadrants'].values()) == counts['compared']
    assert counts['compared'] + counts['uncompared'] == counts['urls'] == len(report['results'])
    assert sum(counts['presence'].values()) == counts['urls']
    assert report['review_candidates'] == sum(row['review'] for row in report['results'])


def test_four_quadrants_cli_and_read_only(site):
    original = digest_inputs(site)
    report = run(site)
    assert report['exit_code'] == 1
    assert report['schema_version'] == 1
    assert report['counts']['quadrants'] == dict.fromkeys(QUADRANTS, 1)
    expected = dict(alpha=QUADRANTS[1], beta=QUADRANTS[2], gamma=QUADRANTS[0], delta=QUADRANTS[3])
    for name, quadrant in expected.items():
        row = getrow(report, name)
        assert row['result'] == quadrant
        assert row['presence'] == 'common'
        for side in ('before', 'after'):
            value = row[side]
            body = (name.title() + (' revised' if side == 'after' and name in ('alpha', 'gamma') else '') + '\n').encode()
            observation = value['mappings'][0]['observation']
            assert observation['sha256'] == hashlib.sha256(body).hexdigest()
            assert observation['size'] == len(body)
            assert observation['stable'] is True
            assert value['mappings'][0]['source']['pointer'].startswith('/files/')
            entry = value['entries'][0]
            assert entry['source']['path'].endswith(side + '/sitemap.xml')
            assert entry['source']['entry'] in (1, 2, 3, 4)
            assert entry['lastmods'] == ['2026-10-30' if side == 'after' and name in ('beta', 'gamma') else '2026-10-29']
    assert digest_inputs(site) == original
    assert_totals(report)


def test_coverage_retains_candidates(site):
    original = digest_inputs(site)
    report = run(site, 'coverage')
    assert report['exit_code'] == 2
    assert report['review_candidates'] == 2
    assert report['counts']['quadrants'] == dict.fromkeys(QUADRANTS, 1)
    assert report['counts']['presence']['added'] == 2
    missing = getrow(report, 'missing')
    assert missing['result'] is None and missing['bytes_equal'] is None
    assert missing['after']['issues'] == ['missing-file']
    assert digest_inputs(site) == original
    assert_totals(report)


def test_equal_bytes_ignore_mtime(site):
    os.utime(site / 'after' / 'Delta.html', ns=(1000000000, 1000000000))
    report = run(site)
    assert getrow(report, 'delta')['result'] == QUADRANTS[3]


@pytest.mark.parametrize('body', [b'Alpha \n', b'<a href="/new">Alpha</a>\n'])
def test_whitespace_and_link_changes_are_bytes(site, body):
    if body.startswith(b'<'):
        (site / 'before' / 'Alpha.html').write_bytes(b'<a href="/old">Alpha</a>\n')
    (site / 'after' / 'Alpha.html').write_bytes(body)
    assert getrow(run(site))['result'] == QUADRANTS[1]


def test_all_exit_codes_and_empty(site):
    same = compare(site / 'before.json', site / 'before.json')
    assert same['exit_code'] == 0
    assert same['review_candidates'] == 0
    for side in ('before', 'after'):
        xml_edit(site, side, lambda root: root.clear())
        manifest_edit(site, side, lambda data: data.update(files=[]))
    report = run(site)
    assert report['empty'] is True and report['exit_code'] == 2
    text = subprocess.run([sys.executable, '-m', 'lastmod_ledger', 'compare', str(site / 'before.json'), str(site / 'after.json')], capture_output=True, text=True)
    assert 'does not certify the site' in text.stdout
    (site / 'after.json').write_text('{')
    assert run(site)['exit_code'] == 3


@pytest.mark.parametrize('value,status', [('2026-02-30', 'invalid'), ('2026-10-30T13:02:03Z', 'outside-subset'), ('2026-10-30T13:02+02:00', 'outside-subset'), ('2026-10-30T13:02:03.123-04:00', 'outside-subset'), ('2026-10', 'outside-subset'), ('2026', 'outside-subset'), ('2026-13-30T13:02:03Z', 'invalid'), ('2026-10-30T24:00:00Z', 'invalid'), ('2026-10-30T13:02:03+24:00', 'invalid'), ('2026-1-01', 'invalid'), ('', 'invalid'), (' 2026-10-30 ', 'invalid')])
def test_dates(site, value, status):
    xml_edit(site, 'after', lambda root: setattr(root[0].find('{' + NS + '}lastmod'), 'text', value))
    report = run(site)
    row = getrow(report)
    assert row['after']['entries'][0]['date_status'] == status
    assert row['after']['entries'][0]['lastmods'] == [value]
    assert row['result'] is None and row['bytes_equal'] is False
    assert report['exit_code'] == 2


def test_missing_date_is_not_protocol_violation(site):
    xml_edit(site, 'after', lambda root: root[0].remove(root[0].find('{' + NS + '}lastmod')))
    report = run(site)
    row = getrow(report)
    assert row['result'] is None
    assert row['after']['entries'][0]['date_status'] == 'missing'
    assert 'lastmod-missing' in row['after']['issues']


@pytest.mark.parametrize('which', ['xml', 'manifest', 'lastmod', 'loc'])
def test_duplicates_are_ambiguous(site, which):
    if which == 'manifest':
        manifest_edit(site, 'after', lambda data: data['files'].append(data['files'][0].copy()))
    else:
        def duplicate(root):
            element = root[0] if which == 'xml' else root[0].find('{' + NS + '}' + which)
            parent = root if which == 'xml' else root[0]
            parent.append(ET.fromstring(ET.tostring(element)))
        xml_edit(site, 'after', duplicate)
    report = run(site)
    row = getrow(report)
    assert row['result'] is None
    assert report['exit_code'] == 2
    if which == 'xml':
        assert len(row['after']['entries']) == 2
    if which == 'manifest':
        assert len(row['after']['mappings']) == 2


def test_removed_unmapped_and_orphan_mapping(site):
    xml_edit(site, 'after', lambda root: root.remove(root[3]))
    manifest_edit(site, 'after', lambda data: data['files'].pop(1))
    manifest_edit(site, 'after', lambda data: data['files'].append({'url': 'https://example.test/orphan', 'file': 'after/Alpha.html'}))
    report = run(site)
    assert getrow(report, 'delta')['presence'] == 'removed'
    assert 'mapping-without-sitemap-url' in getrow(report, 'delta')['after']['issues']
    assert getrow(report, 'beta')['bytes_equal'] is None
    assert 'unmapped-url' in getrow(report, 'beta')['after']['issues']
    assert getrow(report, 'orphan')['presence'] == 'manifest-only'
    assert_totals(report)


def test_missing_existing_pair_never_becomes_empty_file(site):
    (site / 'before' / 'Alpha.html').write_bytes(b'')
    (site / 'after' / 'Alpha.html').unlink()
    report = run(site)
    assert getrow(report)['bytes_equal'] is None
    assert getrow(report)['result'] is None
    assert report['exit_code'] == 2


@pytest.mark.parametrize('location', ['file', 'parent', 'manifest', 'sitemap'])
def test_symlinks_rejected(site, location):
    if location == 'parent':
        directory = site / 'after'
        directory.rename(site / 'real-after')
        directory.symlink_to(site / 'real-after', target_is_directory=True)
    else:
        path = {'file': site / 'after' / 'Alpha.html', 'manifest': site / 'after.json', 'sitemap': site / 'after' / 'sitemap.xml'}[location]
        target = path.with_name('real-' + path.name)
        path.rename(target)
        path.symlink_to(target)
    report = run(site)
    if location == 'file':
        assert report['exit_code'] == 2
        assert getrow(report)['after']['issues'] == ['symlink']
    else:
        assert report['exit_code'] == 3 and 'symlink' in report['error']


@pytest.mark.parametrize('xml', ['<urlset/>', '<urlset xmlns="https://wrong.test"/>', '<!DOCTYPE urlset><urlset xmlns="' + NS + '"/>', '<!DOCTYPE urlset [<!ENTITY x SYSTEM "file:///etc/passwd">]><urlset xmlns="' + NS + '"><url><loc>&x;</loc></url></urlset>', '<!DOCTYPE urlset [<!ENTITY x "expand">]><urlset xmlns="' + NS + '"/>', '<urlset xmlns="' + NS + '">'])
def test_rejected_xml(site, xml):
    (site / 'after' / 'sitemap.xml').write_text(xml)
    report = run(site)
    assert report['exit_code'] == 3
    assert 'sitemap' in report['error']


def test_sitemap_index_and_extensions_identified(site):
    xml_edit(site, 'after', lambda root: ET.SubElement(root[0], '{urn:images}image'))
    report = run(site)
    assert getrow(report)['after']['entries'][0]['extensions'] == ['{urn:images}image']
    assert report['exit_code'] == 2
    (site / 'after' / 'sitemap.xml').write_text('<sitemapindex xmlns="' + NS + '"><sitemap><loc>https://example.test/map.xml</loc></sitemap></sitemapindex>')
    report = run(site)
    assert report['exit_code'] == 2
    assert report['coverage']['after']['kind'] == 'sitemapindex'
    assert report['coverage']['after']['issues'][0]['code'] == 'sitemap-index-outside-scope'
    (site / 'after' / 'sitemap.xml').write_text('<sitemapindex xmlns="' + NS + '">broken')
    assert run(site)['exit_code'] == 3


def test_exact_decoded_urls_and_shared_file(site):
    variants = ['https://example.test/ümlaut?a=1&b=2', 'https://example.test/a', 'https://example.test/a/', 'http://example.test/a', 'https://example.test/a?x=1', 'https://example.test/a?x=2']
    for side in ('before', 'after'):
        def change(root):
            root.clear()
            root.tag = '{' + NS + '}urlset'
            for url in variants:
                entry = ET.SubElement(root, '{' + NS + '}url')
                ET.SubElement(entry, '{' + NS + '}loc').text = url
                ET.SubElement(entry, '{' + NS + '}lastmod').text = '2026-10-29'
        xml_edit(site, side, change)
        manifest_edit(site, side, lambda data: data.update(files=[{'url': url, 'file': side + '/Delta.html'} for url in variants]))
    report = run(site)
    assert report['exit_code'] == 0
    assert {row['url'] for row in report['results']} == set(variants)
    assert report['counts']['quadrants'][QUADRANTS[3]] == 6


@pytest.mark.parametrize('option,value', [('entries', 3), ('manifest-bytes', 10), ('sitemap-bytes', 10), ('file-bytes', 4), ('total-bytes', 1000)])
def test_limits(site, option, value):
    report = run(site, 'after', '--max-' + option, str(value))
    assert report['exit_code'] in (2, 3)
    if report['exit_code'] == 2:
        assert report['counts']['uncompared'] > 0


def test_concurrent_change_during_file_read(site, monkeypatch):
    real_read = os.read
    target = site / 'after' / 'Alpha.html'
    fired = []
    def read(fd, amount):
        chunk = real_read(fd, amount)
        if chunk == b'Alpha revised\n' and not fired:
            fired.append(True)
            target.write_bytes(b'Alpha changed again\n')
        return chunk
    monkeypatch.setattr(os, 'read', read)
    report = compare(site / 'before.json', site / 'after.json')
    assert fired
    assert report['exit_code'] == 2
    assert getrow(report)['result'] is None
    assert 'concurrent-change' in getrow(report)['after']['issues']


@pytest.mark.parametrize('target', ['after/Alpha.html', 'after/sitemap.xml', 'after.json'])
def test_changed_or_replaced_after_read(site, monkeypatch, target):
    recheck = Reader.recheck
    def change_then_check(self):
        path = site / target
        replacement = path.with_suffix('.replacement')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        recheck(self)
    monkeypatch.setattr(Reader, 'recheck', change_then_check)
    report = compare(site / 'before.json', site / 'after.json')
    assert report['exit_code'] == 2
    assert getrow(report)['result'] is None
    assert any('concurrent-change' in code for code in getrow(report)['after']['issues'])


def test_nonregular_file_does_not_block(site):
    target = site / 'after' / 'Alpha.html'
    target.unlink()
    os.mkfifo(target)
    report = run(site)
    assert report['exit_code'] == 2
    assert getrow(report)['after']['issues'] == ['not-regular-file']


@pytest.mark.parametrize('raw', ['{"sitemap":"after/sitemap.xml","sitemap":"before/sitemap.xml","files":[]}', '{"sitemap":"https://example.test/map.xml","files":[]}', '{"sitemap":"after/sitemap.xml","files":[{"url":"/relative","file":"x"}]}', '{"sitemap":"after/sitemap.xml","files":{},"extra":1}'])
def test_invalid_manifest(site, raw):
    (site / 'after.json').write_text(raw)
    assert run(site)['exit_code'] == 3


def test_xml_entry_without_loc_stays_in_coverage(site):
    xml_edit(site, 'after', lambda root: root[0].remove(root[0].find('{' + NS + '}loc')))
    report = run(site)
    assert report['exit_code'] == 2
    assert len(report['coverage']['after']['entries']) == 4
    assert report['coverage']['after']['entries'][0]['locs'] == []
    assert 'invalid-or-ambiguous-loc' in report['coverage']['after']['entries'][0]['issues']
    assert getrow(report)['result'] is None


def test_xml_entry_limit_distinct_from_manifest_limit(site):
    manifest_edit(site, 'before', lambda data: data.update(files=[]))
    manifest_edit(site, 'after', lambda data: data.update(files=[]))
    report = run(site, 'after', '--max-entries', '3')
    assert report['exit_code'] == 3 and 'sitemap' in report['error'] and 'entry-limit' in report['error']


def test_depth_limit_and_gzip(site):
    (site / 'after' / 'sitemap.xml').write_text('<urlset xmlns="' + NS + '">' + '<url>' * 33 + '</url>' * 33 + '</urlset>')
    assert 'depth/node limit' in run(site)['error']
    (site / 'after' / 'sitemap.xml').write_bytes(b'\x1f\x8bcompressed')
    assert 'compressed sitemap outside scope' in run(site)['error']


def test_growth_during_read_respects_limit(site, monkeypatch):
    real_read = os.read
    target = site / 'after' / 'Alpha.html'
    fired = []
    def read(fd, amount):
        chunk = real_read(fd, amount)
        if chunk == b'Alpha revised\n' and not fired:
            fired.append(True)
            with target.open('ab') as stream:
                stream.write(b'x' * 100)
        return chunk
    monkeypatch.setattr(os, 'read', read)
    report = compare(site / 'before.json', site / 'after.json', Limits(file_bytes=16))
    assert report['exit_code'] == 2
    assert 'byte-limit-during-read' in getrow(report)['after']['issues']


def test_cli_syntax_error_json():
    process = subprocess.run([sys.executable, '-m', 'lastmod_ledger', 'compare', '--json'], capture_output=True, text=True)
    assert process.returncode == 3
    assert json.loads(process.stdout)['status'] == 'input-error'
    assert not process.stderr
