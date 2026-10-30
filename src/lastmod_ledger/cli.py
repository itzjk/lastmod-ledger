import argparse
import json
import sys

from . import __version__
from .core import InputError, compare
from .reader import Limits


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def positive(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('expected a positive integer') from error
    if number < 1:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return number


def parser():
    cli = Parser(description='Compare existing sitemap dates with exact snapshot file bytes.')
    cli.add_argument('--version', action='version', version=__version__)
    commands = cli.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = commands.add_parser('compare', help='Read two local manifests without changing them.')
    command.add_argument('before')
    command.add_argument('after')
    command.add_argument('--json', action='store_true', help='Emit schema_version 1 JSON.')
    defaults = Limits()
    for name in ('entries', 'manifest_bytes', 'sitemap_bytes', 'file_bytes', 'total_bytes'):
        command.add_argument('--max-' + name.replace('_', '-'), type=positive, default=getattr(defaults, name), help=f'Limit (default: {getattr(defaults, name)}).')
    return cli


def quoted(value):
    return json.dumps(value, ensure_ascii=False)


def render(report):
    counts = report['counts']
    lines = [f"lastmod-ledger: {report['status']} | {counts['compared']}/{counts['urls']} URLs compared | {report['review_candidates']} review candidates"]
    for key, snap in report['coverage'].items():
        lines.append(f"{key}: {quoted(snap['manifest']['path'])} -> {quoted(snap['sitemap']['path'])}")
    for quadrant, count in counts['quadrants'].items():
        lines.append(f'{quadrant}: {count}')
    for row in report['results']:
        lines.append(f"\n{quoted(row['url'])}  {row['result'] or row['presence'] + '/uncompared'}")
        for side_name in ('before', 'after'):
            side = row[side_name]
            for entry in side['entries']:
                lines.append(f"  {side_name} XML entry {entry['source']['entry']}: lastmod={quoted(entry['lastmods'])} ({entry['date_status']})")
            for mapping in side['mappings']:
                obs = mapping['observation']
                lines.append(f"  {side_name} {mapping['source']['pointer']}: file={quoted(mapping['file'])}" + (f" size={obs['size']} stable={obs['stable']}" if obs else ' unread'))
                if obs:
                    lines.append(f"    sha256={obs['sha256']}")
            if side['issues']:
                lines.append(f"  {side_name} issues: {', '.join(side['issues'])}")
    presence = counts['presence']
    lines.append(f"\nCoverage: added={presence['added']} removed={presence['removed']} manifest-only={presence['manifest-only']} uncompared={counts['uncompared']}")
    for side_name, snap in report['coverage'].items():
        for issue in snap['issues']:
            lines.append(f"  {side_name}: {issue['code']} at {quoted(issue['source'])}")
        for key in ('manifest', 'sitemap'):
            if not snap[key]['stable']:
                lines.append(f'  {side_name}: concurrent-change in {key}')
    if report['empty']:
        lines.append('Empty comparison: no URLs inspected; this does not certify the site.')
    lines.append(report['notice'])
    lines.append(f"Exit {report['exit_code']}. Snapshot checks detect observed changes; reads are not atomic.")
    return '\n'.join(lines)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser().parse_args(arguments)
        limits = Limits(**{name: getattr(args, 'max_' + name) for name in ('entries', 'manifest_bytes', 'sitemap_bytes', 'file_bytes', 'total_bytes')})
        report = compare(args.before, args.after, limits)
    except (InputError, OSError, ValueError) as error:
        report = {'schema_version': 1, 'status': 'input-error', 'exit_code': 3, 'error': str(error)}
    if '--json' in arguments:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report['exit_code'] == 3:
        print('lastmod-ledger: input-error: ' + quoted(report['error']), file=sys.stderr)
    else:
        print(render(report))
    return report['exit_code']
