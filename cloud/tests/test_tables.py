"""Tests for the LaTeX table generators: one test per deliberate correction, plus subtasks and helpers."""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from worpt.model import Person, Assignment, Item, Proposal, TravelCosts, NonlaborItem
from worpt import tables
from worpt.tables import build, jrep, jsub, fixed, dollars, general, team_order, TABLES
from test_parity_tables import SHEET_TEMPLATES


def person(pid, role, last, us=True, trips=(), other_months=()):
    return Person(pid, role, us, last=last, first=last[0], institution='Inst', position='scientist', trips=[list(t) for t in trips],
                  other_months=list(other_months))


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
    out = build(proposal([Item('G', children=[task('t', [('a', 4, 0), ('team', 2, 0)])])], m), ['isANONschedule'])
    assert re.search(r'\{T\}[^\n]*?6|T[^\n]{0,40}\b6\b', out['isANONschedule'])          # 3 unnamed people x 2 weeks


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
    out = build(proposal([Item('Goal', children=[parent])]), ['NOTANONtasks', 'isANONtasks', 'isANONschedule'])
    for name in ('NOTANONtasks', 'isANONtasks', 'isANONschedule'):
        assert 'A1.1' in out[name] and 'A1.2' in out[name] and 'Parent task' in out[name], name
    sched = out['isANONschedule']
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
    tex = build(proposal(goals, m), ['isANONschedule'])['isANONschedule']
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
    tex = build(proposal([Item('G', children=[task('t', [('a', 26, 13), ('c', 52, 0)])])], m), ['isANONschedule'])['isANONschedule']
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
    tex = build(proposal([Item('Goal', children=[parent, task('Alone', [('a', 1, 0)], (1, 40), (1, 44))])]), ['isANONschedule'])['isANONschedule']
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


# ------------------------------------------------ the work-effort table (NASA's Table of Work Effort)
def test_work_effort_months_come_from_the_ftes_and_add_up():
    """NASA Support = funded FTE x 12, Total = all FTE x 12, to one decimal; Other Funded Projects as entered (to one
    decimal); the Sum columns add each person's years and the bottom row the team, using the months as shown; no
    months at all is \\ZeroMonths; roles as NASA names them, the team in the tables' order."""
    members = [person('c', 'coll(1)', 'Gamma', us=False, other_months=[0.25]), person('b', 'co-I(1)', 'Beta'),
               person('a', 'PI', 'Alpha', other_months=[1, 2])]
    goals = [Item('Goal', children=[task('T1', [('a', 26, 0), ('b', 13, 13), ('c', 5.2, 0)], start=(1, 1), end=(1, 52))])]
    t = build(proposal(goals, members, n_years=2), ['NOTANONworkEffort'])['NOTANONworkEffort']
    rows = {m.group(1): m.group(2) for m in re.finditer(r'\\NameFormat\{\\WorPTunlessMeasuring\{[A-Z] +(\w+)\}\} & \\RoleFormat\{([^}]*)\}', t)}
    assert list(rows) == ['Alpha', 'Beta', 'Gamma'] and rows == {'Alpha': 'PI', 'Beta': 'Co-I', 'Gamma': 'Collaborator'}
    cells = lambda who: re.findall(r'\\MonthsFormat\{([^}]*)\}', next(l for l in t.splitlines() if who in l))
    z = '\\ZeroMonths'
    assert cells('Alpha') == ['6.0', '6.0', '1.0', z, z, '2.0', '6.0', '6.0', '3.0']     # year 1, year 2, sum
    assert cells('Beta') == [z, '3.0', z, z, z, z, z, '3.0', z]                          # wholly unfunded
    assert cells('Gamma') == [z, '1.2', '0.3', z, z, z, z, '1.2', '0.3']                 # a collaborator: no NASA support
    assert re.findall(r'\\WorkEffortSumCell\{([^}]*)\}', t) == ['6.0', '10.2', '1.3', z, z, '2.0', '6.0', '10.2', '3.3']
    spec = next(l for l in t.splitlines() if l.startswith('|>{\\columncolor'))                      # the year columns, shaded
    assert [spec.count(c) for c in ('OddYearColor', 'EvenYearColor', 'SumColor')] == [3, 3, 3] and '[INSERT' not in t


# ------------------------------------------------ team summaries, named and anonymous
def summaries_team():
    pi = Person('PI', 'PI', True, last='Doe', first='Jane', middle='Q.', prefix='Dr.', institution='Lunar Institute',
                bio_summary="will lead Task A1.1 (Photometry), drawing on her 20 years of work with Dr. Roe. She will also support Task A2.1.")
    co = Person('co-I 1', 'co-I(1)', True, last='Roe', first='Rick', prefix='Prof.',
                bio_summary="will lead Task A2.1. He works with Jane Doe's group; his He II maps and the He-3 data are his. He trained himself.")
    gs = Person('gst 1', 'gst(1)', True, last='Poe', first='Pat', bio_summary='Pat Poe will support Task A1.1 at the Lunar Institute.')
    cl = Person('collab 1', 'coll(1)', False, last='Moe', first='Mo', bio_summary='will support Task A2.1; we work with her and her team.')
    return Proposal('T', 'NASA', 1, [cl, gs, co, pi], [Item('Goal', children=[task('T1', [('PI', 4, 0)])])])


def test_anonymous_team_summaries_call_people_by_their_spelled_out_role():
    """Each paragraph starts with the person's role, spelled out and numbered as in the anonymous tables; team members'
    names in the text become their roles, and the gendered pronouns the paragraph's own role (possessive before a noun).
    A capital He inside a sentence, or before an ionization stage or a number, is helium and stays."""
    out = build(summaries_team(), ['isANONteamSummaries'])['isANONteamSummaries']
    paras = re.findall(r'\\LabelFontstyle\{([^}]*)\} (.*?) *(?:\\par|\n\})', out, re.S)
    assert [p[0] for p in paras] == ['The PI', 'Co-I 1', 'Grad student 1', 'Collaborator 1']       # the tables' order
    text = dict(paras)
    assert text['The PI'] == "will lead Task A1.1 (Photometry), drawing on the PI's 20 years of work with Co-I 1. The PI will also support Task A2.1."
    assert text['Co-I 1'] == "will lead Task A2.1. Co-I 1 works with the PI's group; Co-I 1's He II maps and the He-3 data are Co-I 1's. Co-I 1 trained themself."
    assert text['Collaborator 1'] == 'will support Task A2.1; we work with Collaborator 1 and Collaborator 1\'s team.'
    assert not re.search(r'Jane|Doe|Rick|Roe|\b[Ss]he\b|\bher\b|\bhis\b', out)
    assert [tables.anon_label(r) for r in ('PI', 'Sci-PI', 'Admin-PI', 'co-I(2)', 'pd(1)', 'gst(3)', 'ust(1)', 'coll(4)')] == \
        ['The PI', 'The Science PI', 'The Admin-PI', 'Co-I 2', 'Postdoc 1', 'Grad student 3', 'Undergrad 1', 'Collaborator 4']


def test_team_summaries_warn_about_a_repeated_name_and_what_anonymizing_leaves():
    """The named table warns when a summary starts with the person's name (the table already puts it in front); the
    anonymous one when a paragraph still has a team member's first or last name, or institution, after anonymizing."""
    checks = build(summaries_team(), ['NOTANONteamSummaries', 'isANONteamSummaries'])['_checks']
    said = sorted((c.item, c.message) for c in checks if 'summary' in c.message)
    assert said == [('gst 1', 'anonymous team summary still names "Lunar Institute"'),
                    ('gst 1', 'team summary starts with their name, which the table already puts in front of it')]
    named = build(summaries_team(), ['NOTANONteamSummaries'])['NOTANONteamSummaries']
    assert 'Dr. \\NameFontstyle{Jane Q. Doe}, \\NameFontstyle{PI}, will lead Task A1.1' in named


# ------------------------------------------------ planned papers
def test_planned_papers_come_from_items_titled_paper_n():
    """Any category, task or subtask titled "Paper N: title" (any capitals, any spaces) is paper N; the file lists them in
    number order, whatever their place in the plan. A number used twice keeps the first item's title, with a warning,
    and a "Paper N:" with nothing after it is warned about too. Numbers need not follow on from each other."""
    goals = [Item('Paper 5: A review', children=[
                 Item('Write paper 2 later'), Item('paper 2 :  Halo light profiles of $M_\\star$ galaxies'),
                 Item('Observations', children=[Item('PAPER 1:Deep imaging'), Item('Paper 1: Another'), Item('Paper 3:')]),
                 Item('Paper one: not a number')])]
    out = build(Proposal('T', 'NASA', 1, [Person('PI', 'PI', True, last='Doe')], goals), ['isANONpapers'])
    assert re.findall(r'^\\WorPTpaper\{(\d+)\}\{(.*)\}   % (\S+)$', out['isANONpapers'], re.M) == [
        ('1', 'Deep imaging', 'A3.1'), ('2', 'Halo light profiles of $M_\\star$ galaxies', 'A2'), ('3', '', 'A3.3'), ('5', 'A review', 'A')]
    assert out['isANONpapers'].index('\\WorPTresetPapers') < out['isANONpapers'].index('\\WorPTpaper{1}')
    said = [(c.item, c.message) for c in out['_checks'] if 'Paper' in c.message]
    assert said == [('A3.2', 'is also titled "Paper 1:", like A3.1; Paper 1 keeps A3.1\'s title'),
                    ('A3.3', 'is titled "Paper 3:" with nothing after it, so Paper 3 has no title')]
    none = build(Proposal('T', 'NASA', 1, [Person('PI', 'PI', True, last='Doe')], [Item('Goal')]), ['isANONpapers'])['isANONpapers']
    assert '\\WorPTresetPapers' in none and '\\WorPTpaper{' not in none
