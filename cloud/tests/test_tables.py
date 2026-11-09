"""Tests for the LaTeX table generators: one test per deliberate correction, plus subtasks and helpers."""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from worpt.model import Person, Assignment, Item, Proposal, TravelCosts, NonlaborItem
from worpt import tables
from worpt.tables import build, jrep, jsub, fixed, dollars, general, team_order, TABLES
from test_parity_tables import SHEET_TEMPLATES


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


def test_fix2_team_weeks_count_each_unnamed_member(monkeypatch):
    """In the Sheet version's schedule, which lists each task's assignments as "id weeks"."""
    monkeypatch.setattr(tables, 'TEMPLATE_DIR', SHEET_TEMPLATES)
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
    assert '{' + fixed(6 / 52, 2) + '}' in parent_row and 'Mark{' not in parent_row        # rolled-up FTE, no people of its own


# ------------------------------------------------ the schedule's team columns
def team_rows(tex):
    """For each task row of a schedule: its label and its team cells (lead, funded, unfunded or none), in team order."""
    marks = dict(TeamLeadColor='lead', TeamFundedColor='funded', TeamUnfundedColor='unfunded')   # (the unfunded mark is an open box)
    out = {}
    for row in tex.split('% begin task')[1:]:
        label = re.search(r'\\(?:Sub)?[tT]askTitleLabel\{([^}]*)\}', row).group(1)
        cells = row.split('% timeline for this task')[1].split('% who leads it')[0]
        out[label] = [marks[m] if m else 'none' for m in re.findall(r'(?:\\Team(?:Open)?Mark\{\\(\w+)\}|\{\}) &', cells)]
    return out


def test_schedule_marks_who_leads_and_who_works_on_each_task():
    m = [person('a', 'PI', 'Alpha'), person('b', 'co-I(1)', 'Beta'), person('c', 'coll(1)', 'Gamma'),
         person('d', 'coll(2)', 'Delta', us=False), person('e', 'co-I(2)', 'Epsilon')]
    goals = [Item('G', children=[task('t1', [('b', 4, 0), ('a', 2, 1), ('c', 1, 0)]),     # lead; some of a's weeks unfunded; c a collaborator
                                 task('t2', [('a', 3, 0), ('team', 1, 0)]),                 # team: everyone not named
                                 task('t3', [('d', 2, 0), ('e', 1, 0)])])]                  # an international lead
    tex = build(proposal(goals, m), ['NOTANONschedule'])['NOTANONschedule']
    order = re.findall(r'\\rotatebox\{90\}\{\\(\w+Team)\{([^}]*)\}\}', tex)          # the column labels
    labels = dict((pid, kind) for kind, pid in order)
    assert labels == dict(a='FundedUsTeam', b='FundedUsTeam', c='UnfundedUsTeam', d='InternationalTeam', e='FundedUsTeam')
    ids = [pid for _, pid in order]
    rows = {k: dict(zip(ids, v)) for k, v in team_rows(tex).items()}
    assert rows['A1'] == dict(a='unfunded', b='lead', c='unfunded', d='none', e='none')
    assert rows['A2'] == dict(a='lead', b='funded', c='unfunded', d='unfunded', e='funded')
    assert rows['A3'] == dict(a='none', b='none', c='none', d='lead', e='funded')


def test_schedule_foot_gives_each_members_funded_and_unfunded_fte():
    m = [person('a', 'PI', 'Alpha'), person('c', 'coll(1)', 'Gamma')]
    tex = build(proposal([Item('G', children=[task('t', [('a', 26, 13), ('c', 52, 0)])])], m), ['NOTANONschedule'])['NOTANONschedule']
    funded = tex.split('\\TeamFundedFteLabel')[-1].split('\\\\')[0]          # the foot rows (the labels are defined above them too)
    unfunded = tex.split('\\TeamUnfundedFteLabel')[-1].split('\\\\')[0]
    ids = re.findall(r'\\rotatebox\{90\}\{\\\w+Team\{([^}]*)\}\}', tex)
    values = lambda part: dict(zip(ids, re.findall(r'\\Team(?:Funded|Unfunded|Zero)FteFormat\{([^}]*)\}', part)))
    assert values(funded) == dict(a='0.25', c='0.00') and values(unfunded) == dict(a='0.25', c='1.00')
    assert '\\FteGrandTotalFormat{0.25}' in funded and '\\FteGrandTotalFormat{1.25}' in unfunded            # the totals, in the Total FTE column
    assert '\\TeamZeroFteFormat{0.00}' in funded


def test_schedule_sets_tasks_with_subtasks_apart():
    """A task with subtasks: light blue timeline over its subtasks' span and its FTE (theirs added up) in italics; its
    subtasks indented, with their own FTE as a task's; a category's row gives its FTE (its tasks added up), in bold."""
    parent = Item('Parent task', children=[task('Sub one', [('a', 4, 0)], (1, 1), (1, 10)), task('Sub two', [('b', 2, 0)], (1, 20), (1, 30))])
    tex = build(proposal([Item('Goal', children=[parent, task('Alone', [('a', 1, 0)], (1, 40), (1, 44))])]), ['NOTANONschedule'])['NOTANONschedule']
    rows = {re.search(r'\{(A[\d.]*)\}', r).group(1): r for r in tex.split('% begin task')[1:]}
    timeline = lambda r: re.findall(r'WorPTcellcolor\{\\(\w+)\}', r)
    assert timeline(rows['A1']) and set(timeline(rows['A1'])) == {'ParentTimelineColor'} and '\\FteRolledUpFormat{' + fixed(6 / 52, 2) + '}' in rows['A1']
    for sub, weeks in (('A1.1', 4), ('A1.2', 2)):
        assert '\\SubtaskTitleLabel{' + sub + '}' in rows[sub] and set(timeline(rows[sub])) == {'TimelineColor'}
        assert '\\FteTotalFormat{' + fixed(weeks / 52, 2) + '}' in rows[sub]
    assert '\\TaskTitleLabel{A2}' in rows['A2'] and '\\FteTotalFormat{' + fixed(1 / 52, 2) + '}' in rows['A2']
    assert [len(timeline(rows[k])) for k in ('A1.1', 'A1.2', 'A1')] == [3, 3, 7]    # months 1-3 and 5-7; the parent spans 1-7
    category = tex.split('\\TaskCategoryLabel{A}')[1].split('% begin task')[0]
    assert '\\FteCategoryFormat{' + fixed(7 / 52, 2) + '}' in category


def test_team_order_by_kind_of_role_then_last_name():
    """PI, Admin PI, Science PI, co-Is, postdocs, grad students, undergrads, anyone with another role, collaborators."""
    m = [person('c2', 'coll(2)', 'Able'), person('u1', 'ust(1)', 'Young'), person('o', 'Consultant', 'Baker'), person('s', 'Sci-PI', 'Zed'),
         person('g1', 'gst(1)', 'Moss'), person('a', 'Admin-PI', 'Yu'), person('c1', 'co-I(2)', 'Cole'), person('p1', 'pd(1)', 'Abel'),
         person('c0', 'co-I(1)', 'Adams'), person('pi', 'PI', 'Zimmer'), person('k1', 'coll(1)', 'Aaron')]
    assert [x.id for x in team_order(m)] == ['pi', 'a', 's', 'c0', 'c1', 'p1', 'g1', 'u1', 'o', 'k1', 'c2']
