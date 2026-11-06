"""Parity of the LaTeX tables with the Google Sheet version (Code.gs, Jan 2025).

Each folder in fixtures/ with a proposal.json holds a real proposal (names, IDs, narratives and task
text replaced by placeholders) and, in expected/, the tables the Sheet version made from it. The new
generators must reproduce those tables line for line, except for the differences listed in
known_differences.json, each with its reason. Run `python3 tests/test_parity_tables.py` for a report.
"""
import difflib, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from worpt.model import Person, Assignment, Item, Proposal, TravelCosts, NonlaborItem
from worpt.tables import build, TABLES

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
CASES = sorted(f.parent for f in FIXTURES.glob('*/proposal.json'))


def load(folder):
    d = json.loads((folder / 'proposal.json').read_text())
    members = [Person(p['id'], p['role'], p['us'], p['fte_accuracy'], last=p['last'], first=p['first'], middle=p['middle'],
                      prefix=p['prefix'], suffix=p['suffix'], institution=p['institution'], position=p['position'],
                      bio_summary=p['bio_summary'], task_summary=p['task_summary'], trips=p['trips']) for p in d['team']]
    goals = [Item(g['title'], children=[Item(t['title'], start=tuple(t['start']) if t['start'] else None, end=tuple(t['end']) if t['end'] else None,
             assignments=[Assignment(a['person'], a['weeks'], a['unfunded'], a['lead']) for a in t['assignments']])
             for t in g['tasks']]) for g in d['goals']]
    return Proposal(d['title'], d['program'], d['n_years'], members, goals, [NonlaborItem(n['item'], n['amounts']) for n in d['nonlabor']],
                    TravelCosts(**d['travel']), d['latex_subdir'], rounding=d.get('rounding', 'up'))   # the Sheet version rounded up


def differences(old, new):
    """Changed blocks between two texts, as [old lines, new lines] pairs (trailing spaces ignored)."""
    a, b = [l.rstrip() for l in old.splitlines()], [l.rstrip() for l in new.splitlines()]
    return [[a[i1:i2], b[j1:j2]] for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op != 'equal']


def compare(folder):
    out = build(load(folder))
    known = json.loads((folder / 'known_differences.json').read_text()) if (folder / 'known_differences.json').exists() else {}
    report = {}
    for f in sorted((folder / 'expected').glob('*.txt')):
        if f.stem not in TABLES: continue
        found = differences(f.read_text(), out[f.stem])
        expected = [[k['old'], k['new']] for k in known.get(f.stem, [])]
        report[f.stem] = dict(found=found, unexplained=[d for d in found if d not in expected],
                              missing=[k for k in known.get(f.stem, []) if [k['old'], k['new']] not in found])
    return report


@pytest.mark.parametrize('folder', CASES, ids=[c.name for c in CASES])
def test_tables_match_sheet_version_except_known_differences(folder):
    report = compare(folder)
    assert report, 'no expected tables found'
    for table, r in report.items():
        assert not r['unexplained'], f"{folder.name}/{table}: unexplained differences {r['unexplained'][:3]}"
        assert not r['missing'], f"{folder.name}/{table}: listed differences that no longer occur {r['missing'][:3]}"


if __name__ == '__main__':
    for folder in CASES:
        known = json.loads((folder / 'known_differences.json').read_text()) if (folder / 'known_differences.json').exists() else {}
        for table, r in compare(folder).items():
            n_lines = len((folder / 'expected' / f'{table}.txt').read_text().splitlines())
            status = 'identical' if not r['found'] else f"{len(r['found'])} difference(s), {len(r['unexplained'])} unexplained"
            print(f'{folder.name:10} {table:22} {n_lines:4} lines  {status}')
            for k in known.get(table, []):
                print(f"{'':12}- {k['reason']}")
                for line in k['old']: print(f"{'':14}old: {line[:150]}")
                for line in k['new']: print(f"{'':14}new: {line[:150]}")
            for o, n in r['unexplained']:
                print(f"{'':12}UNEXPLAINED"); [print(f"{'':14}old: {l[:150]}") for l in o]; [print(f"{'':14}new: {l[:150]}") for l in n]
