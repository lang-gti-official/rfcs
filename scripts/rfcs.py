#!/usr/bin/env python3
"""Create and validate the RFC catalog; Python standard library only."""
import argparse
from datetime import date
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ('draft', 'review', 'accepted', 'implemented', 'deferred', 'rejected', 'withdrawn', 'superseded')
AREAS = ('language', 'stdlib', 'compiler', 'tooling', 'process')
FIELDS = ('Status', 'Authors', 'Created', 'Updated', 'Area', 'Proposal', 'Decision', 'Implementation', 'Supersedes', 'Superseded by')
SECTIONS = ('Summary', 'Motivation and goals', 'Non-goals', 'Guide-level design', 'Semantic rules', 'Compiler and tooling design', 'Compatibility and migration', 'Safety and correctness', 'Performance and resource costs', 'Alternatives and tradeoffs', 'Unresolved questions', 'Implementation plan', 'Validation and release criteria', 'Decision record', 'References')
NAME = re.compile(r'([0-9]{4,})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md\Z')
REPO = 'https://github.com/lang-gti-official/rfcs/'


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def read_rfc(path):
    match = NAME.fullmatch(path.name)
    require(match is not None and int(match[1]) > 0, f'{path.name}: use NNNN-feature-name.md with a positive number')
    number = int(match[1])
    text = path.read_text(encoding='utf-8')
    title = re.match(rf'# RFC {number:04d}: ([^\n|]+)\n', text)
    require(title is not None and title[1].strip(), f'{path.name}: heading must match RFC {number:04d}')
    header = text.split('\n## ', 1)[0]
    rows = re.findall(r'^\| ([A-Za-z ]+) \| ([^|\n]+) \|$', header, re.M)
    rows = [(key, value.strip()) for key, value in rows if key != 'Field']
    fields = dict(rows)
    require(len(rows) == len(fields), f'{path.name}: duplicate metadata field')
    require(set(fields) == set(FIELDS) and all(fields.values()), f'{path.name}: metadata fields must be exactly {", ".join(FIELDS)}')
    status = fields['Status']
    require(status in STATUSES, f'{path.name}: unknown status {status!r}')
    require(fields['Area'] in AREAS, f'{path.name}: unknown area')
    try:
        created, updated = (date.fromisoformat(fields[key]) for key in ('Created', 'Updated'))
    except ValueError as error:
        raise Invalid(f'{path.name}: use valid ISO dates (YYYY-MM-DD)') from error
    require(created <= updated, f'{path.name}: Updated predates Created')
    headings = re.findall(r'^## (.+)$', text, re.M)
    for section in SECTIONS:
        require(headings.count(section) == 1, f'{path.name}: expected one {section!r} section')
        body = re.search(rf'^## {re.escape(section)}\n(.*?)(?=^## |\Z)', text, re.M | re.S)[1]
        require(body.strip(), f'{path.name}: empty {section!r} section')
    proposal = fields['Proposal']
    require(proposal == 'pending' or re.fullmatch(re.escape(REPO) + r'pull/[1-9][0-9]*(?:#[\w-]+)?', proposal), f'{path.name}: Proposal must be a proposal PR URL or pending')
    if status in ('review', 'accepted', 'implemented', 'rejected', 'superseded'):
        require(proposal != 'pending', f'{path.name}: {status} needs a proposal PR link')
    decision = fields['Decision']
    require(decision == 'pending' or re.fullmatch(re.escape(REPO) + r'(?:pull|issues|discussions)/[1-9][0-9]*(?:#[\w-]+)?', decision), f'{path.name}: link a decision PR, issue or discussion in this repository')
    if status in ('accepted', 'implemented', 'rejected', 'superseded'):
        require(decision != 'pending', f'{path.name}: {status} needs a decision link')
    if status == 'implemented':
        links = [item.strip() for item in fields['Implementation'].split(',')]
        require(all(re.fullmatch(r'https://github\.com/lang-gti-official/[^/]+/(pull/[1-9][0-9]*|commit/[0-9a-f]{40})(?:#[\w-]+)?', link) for link in links), f'{path.name}: implemented needs landed implementation PR/commit links')
    for key in ('Supersedes', 'Superseded by'):
        value = fields[key]
        require(value == 'none' or re.fullmatch(r'[0-9]{4,}(?:, [0-9]{4,})*', value), f'{path.name}: {key} must contain RFC numbers or none')
        fields[key] = [] if value == 'none' else [int(part) for part in value.split(', ')]
    require((status == 'superseded') == bool(fields['Superseded by']), f'{path.name}: superseded status and replacement reference must agree')
    return dict(fields, number=number, title=title[1].strip(), path=path)


def catalog(root):
    rows = [read_rfc(path) for path in sorted((root / 'rfcs').glob('*.md')) if path.name != 'README.md']
    ids = {row['number']: row for row in rows}
    require(len(ids) == len(rows), 'Duplicate RFC number; assign an unused number before merging')
    for row in rows:
        for field in ('Supersedes', 'Superseded by'):
            for number in row[field]:
                require(number in ids and number != row['number'], f'{row["path"].name}: invalid {field} reference {number:04d}')
    for row in rows:
        for number in row['Superseded by']:
            require(row['number'] in ids[number]['Supersedes'], f'RFC {number:04d} must link back with Supersedes')
    return sorted(rows, key=lambda row: row['number'])


def index_text(rows):
    header = '# Proposal index\n\nGenerated by `python3 scripts/rfcs.py index`; edit the RFC documents, then regenerate.\n\n[Submission guide](../CONTRIBUTING.md) · [Open proposal PRs](https://github.com/lang-gti-official/rfcs/pulls)\n\n'
    if not rows:
        return header + 'No proposals have been cataloged yet. Use the [feature template](../templates/feature.md) to start the first draft.\n'
    table = '| RFC | Proposal | Status | Area | Updated |\n| --- | --- | --- | --- | --- |\n'
    return header + table + ''.join(f'| {row["number"]:04d} | [{row["title"]}]({row["path"].name}) | {row["Status"]} | {row["Area"]} | {row["Updated"]} |\n' for row in rows)


def local_links(root):
    for path in root.rglob('*.md'):
        if '.git' in path.relative_to(root).parts:
            continue
        for target in re.findall(r'\[[^\]\n]*\]\(([^\s)]+)\)', path.read_text(encoding='utf-8')):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            dest = ((root / parsed.path.lstrip('/')) if parsed.path.startswith('/') else path.parent / unquote(parsed.path)).resolve()
            require(dest.is_relative_to(root.resolve()) and dest.exists(), f'{path.relative_to(root)}: broken local file link {target}')


def check(root):
    rows = catalog(root)
    path = root / 'rfcs/README.md'
    require(path.exists() and path.read_text(encoding='utf-8') == index_text(rows), 'Proposal index is stale; run python3 scripts/rfcs.py index')
    local_links(root)
    return len(rows)


def create(root, slug, title, author, area):
    require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug), 'Use a lowercase hyphenated slug')
    require(area in AREAS, 'Unknown proposal area')
    require(all(value.strip() and not any(char in value for char in '\n\r|[]') for value in (title, author)), 'Title and author must be nonempty single-line values without table or link delimiters')
    rows = catalog(root)
    number = max((row['number'] for row in rows), default=0) + 1
    path = root / 'rfcs' / f'{number:04d}-{slug}.md'
    text = (root / 'templates/feature.md').read_text(encoding='utf-8')
    values = {'number': f'{number:04d}', 'title': title, 'author': author, 'date': date.today().isoformat(), 'area': area}
    for key, value in values.items():
        text = text.replace('{{' + key + '}}', value)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(text)
    (root / 'rfcs/README.md').write_text(index_text(catalog(root)), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='Create a draft and update the catalog')
    new.add_argument('slug')
    new.add_argument('--title', required=True)
    new.add_argument('--author', required=True)
    new.add_argument('--area', choices=AREAS, required=True)
    commands.add_parser('index', help='Regenerate the proposal index')
    commands.add_parser('check', help='Check documents, references and the index')
    args = parser.parse_args()
    try:
        if args.command == 'new':
            print(create(ROOT, args.slug, args.title, args.author, args.area).relative_to(ROOT))
        elif args.command == 'index':
            (ROOT / 'rfcs/README.md').write_text(index_text(catalog(ROOT)), encoding='utf-8')
            print('Updated proposal index')
        else:
            print(f'Checked {check(ROOT)} RFCs, metadata, local file links and index')
    except (Invalid, OSError) as error:
        parser.exit(1, f'RFC check: {error}\n')


if __name__ == '__main__':
    main()
