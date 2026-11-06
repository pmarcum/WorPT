"""Tests for the LaTeX table generators: one test per deliberate correction, plus subtasks and helpers."""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from worpt.model import Person, Assignment, Item, Proposal, TravelCosts, NonlaborItem
from worpt.tables import build, jrep, jsub, fixed, dollars, general, TABLES


def person(pid, role, last, us=True, trips=()):
    return Person(pid, role, us, last=last, first=last[0], institution='Inst', position='scientist', trips=[list(t) for t in trips])


def proposal(goals, members=None, n_years=1, **kw):
    members = members or [person('a', 'PI', 'Alpha'), person('b', 'co-I(1)', 'Beta'), person('c', 'coll(1)', 'Gamma')]
    return Proposal('T', 'NASA', n_years, members, goals, **kw)


def task(title, people, start=(1, 1), end=(1, 4)):
    return Item(title, start=start, end=end, assignments=[Assignment(p, w, u, k == 0) for k, (p, w, u) in enumerate(people)])


# ------------------------------------------------ helpers behave like JavaScript
def test_js_replace_semantics():
    assert jrep('x [A] [A]', '[A]', 'y') == 'x y [A]'                  # first occurrence only
    assert jrep('[A]', '[A]', 'cost $$5') == 'cost $5'                  # $$ means $
    assert jrep('[A]', '[A]', '$\\sim$15') == '$\\sim$15'               # ordinary LaTeX dollars untouched
    assert jsub('a[B]b[B]', r'\[B\]', '1') == 'a1b1'


def test_number_formats():
    assert fixed(0.125, 2) == '0.13' and fixed(0.0, 2) == '0.00'       # JavaScript toFixed rounds halves up
    assert dollars(2843) == '2,845' and dollars(18724.6) == '18,725'
    assert general(2.0) == '2' and general(1.2) == '1.2'


def test_every_table_builds_without_leftover_placeholders():
    out = build(proposal([Item('Goal', children=[task('T1', [('a', 4, 0), ('b', 2, 0)])])],
                         nonlabor=[NonlaborItem('Equipment', [500])], travel=TravelCosts([700, 1750, 0], [264, 320, 0], [500, 800, 0], [60, 100, 0], [5, 5])))
    for name in TABLES:
        assert not re.search(r'\[(INSERT|START|END)[A-Z]*\]', out[name]), name


# ------------------------------------------------ deliberate corrections
def test_fix1_nonlabor_domestic_travel_is_the_years_total():
    members = [person('a', 'PI', 'Alpha', trips=[(3, 0)])]
    tc = TravelCosts([700, 1750, 0], [264, 320, 0], [500, 800, 0], [60, 100, 0], [5, 5])   # one domestic trip = $2,820
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0)])])], members, travel=tc), ['isANONnonlabor'])
    assert '8,460' in out['isANONnonlabor'] and '2,820' not in out['isANONnonlabor']


def test_fix2_team_weeks_count_each_unnamed_member():
    m = [person('a', 'PI', 'Alpha'), person('b', 'co-I(1)', 'Beta'), person('c', 'co-I(2)', 'Gamma'), person('d', 'co-I(3)', 'Delta')]
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0), ('team', 2, 0)])])], m), ['NOTANONschedule'])
    assert re.search(r'\{T\}[^\n]*?6|T[^\n]{0,40}\b6\b', out['NOTANONschedule'])          # 3 unnamed people x 2 weeks


def test_fix3_hst_falls_back_to_the_pis_full_name():
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0)])])]), ['NOTANONhst'])['NOTANONhst']
    assert '\\def\\SciencePIname{A  Alpha}' in out and '\\def\\AdminPIname{A  Alpha}' in out


def test_fix4_trip_caption_singular_and_within_grant_years():
    m = [person('a', 'PI', 'Alpha', trips=[(1, 0), (5, 0)])]
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0)])])], m, n_years=1), ['isANONtravel'])['isANONtravel']
    line = [l for l in out.splitlines() if 'domestic trip' in l][0]
    assert '1 domestic trip;' in line or '1 domestic trip ' in line or line.count('1 domestic trip') == 1 and '1 domestic trips' not in line


def test_fix5_team_with_named_experts_in_anonymous_tasks():
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0), ('b', 2, 0), ('team', 1, 0)])])]), ['isANONtasks'])['isANONtasks']
    assert 'co-I(1), team' in out


def test_fix6_negligible_unfunded_effort_gets_the_minor_row():
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0), ('c', 0.5, 0.5)])])]), ['NOTANONfte'])['NOTANONfte']   # 0.01 FTE
    unfunded = out.split('{\\FteUnfundedBannerText}')[1].split('{\\FteBothBannerText}')[0]
    assert 'Gamma' in unfunded and 'minor' in unfunded


# ------------------------------------------------ subtasks
def test_subtasks_appear_with_dotted_labels_and_parent_rolls_up():
    parent = Item('Parent task', children=[task('Sub one', [('a', 4, 0)], (1, 1), (1, 2)), task('Sub two', [('b', 2, 0)], (1, 3), (1, 4))])
    out = build(proposal([Item('Goal', children=[parent])]), ['NOTANONtasks', 'isANONtasks', 'NOTANONschedule'])
    for name in ('NOTANONtasks', 'isANONtasks', 'NOTANONschedule'):
        assert 'A1.1' in out[name] and 'A1.2' in out[name] and 'Parent task' in out[name], name
    sched = out['NOTANONschedule']
    parent_row = sched.split('{Parent task}')[1].split('% begin task')[0]
    assert '{' + fixed(6 / 52, 2) + '}' in parent_row and '{} &  % assignments' in parent_row   # rolled-up FTE, no people of its own
