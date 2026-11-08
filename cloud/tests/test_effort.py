"""Tests for the WorPT effort engine.

Part 1 (parity): the demo proposal must give exactly the numbers the Google Sheet version computed.
Part 2 (rules): one test per agreed rule, including the places where the new engine deliberately
differs from the Sheet version.
"""
import json, pathlib, sys
import numpy as np, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from worpt.effort import Member, Assignment, Item, compute, mround, letters, label_tree, WEEKS_PER_QUARTER

Qs = lambda y, q: (y, (q - 1) * WEEKS_PER_QUARTER + 1)    # timelines are in weeks; these tests (and the Sheet) think in quarters:
Qe = lambda y, q: (y, q * WEEKS_PER_QUARTER)              # quarter q is weeks 13q-12 to 13q

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'demo2023.json'


def load_demo():
    d = json.loads(FIXTURE.read_text())
    members = [Member(p['id'], p['role'], p['us'], p['fte_accuracy']) for p in d['team']]
    goals = [Item(g['title'], children=[Item(t['title'], start=Qs(*t['start']), end=Qe(*t['end']),
             assignments=[Assignment(a['person'], a['weeks'], a['unfunded'], a['lead']) for a in t['assignments']])
             for t in g['tasks']]) for g in d['goals']]
    return d, members, goals, compute(members, goals, d['n_years'], d['weeks_per_fte'])


# ---------------------------------------------------------------- part 1: parity with the Sheet
def test_demo_person_fte_per_year_matches_sheet():
    d, members, goals, r = load_demo()
    sheet = np.array([p['sheet_fte_per_year'][:d['n_years']] for p in d['team']])
    np.testing.assert_allclose(r['person_year'], sheet, atol=1e-9)


def test_demo_person_totals_match_sheet():
    d, members, goals, r = load_demo()
    np.testing.assert_allclose(r['person_total'], [p['sheet_fte_total'] for p in d['team']], atol=1e-9)


def test_demo_year_fractions_match_sheet():
    d, members, goals, r = load_demo()
    sheet = np.array([t['sheet_year_fraction'][:d['n_years']] for g in d['goals'] for t in g['tasks']])
    np.testing.assert_allclose(r['year_fraction'], sheet, atol=1e-9)


def test_demo_task_fte_matches_sheet():
    d, members, goals, r = load_demo()
    sheet = np.array([t['sheet_fte'] for g in d['goals'] for t in g['tasks']])
    mine = np.array([r['items'][lab]['fte'] for lab in r['leaf_labels']])
    np.testing.assert_allclose(mine, sheet, atol=1e-9)


def test_demo_labels_and_project_total():
    d, members, goals, r = load_demo()
    assert r['leaf_labels'] == ['A1', 'A2', 'A3', 'B1', 'B2', 'C1', 'C2', 'C3']
    np.testing.assert_allclose(r['project_total'], [2.00, 0.67, 1.33], atol=1e-9)   # the Sheet's tables show 2.00 / 0.67 / 1.33


def test_demo_has_no_checks():
    assert load_demo()[3]['checks'] == []


# ---------------------------------------------------------------- part 2: agreed rules
def one_task(members, assignments, start=Qs(1, 1), end=Qe(1, 4), n_years=1):
    return compute(members, [Item('G', children=[Item('T', start=start, end=end, assignments=assignments)])], n_years)


def test_rounding_is_to_nearest_not_up():
    r = one_task([Member('a')], [Assignment('a', 52 * 0.205, lead=True)])
    assert r['person_year'][0, 0, 0] == pytest.approx(0.20)          # "round up" would give 0.25


def test_small_fte_uses_hundredths_and_custom_accuracy_is_respected():
    assert mround(0.0576, 0.01) == pytest.approx(0.06)
    r = one_task([Member('a', fte_accuracy=0.01)], [Assignment('a', 52 * 0.31567, lead=True)])
    assert r['person_year'][0, 0, 0] == pytest.approx(0.32)


def test_team_gives_weeks_to_each_unnamed_member_and_counts_everywhere():
    m = [Member('a'), Member('b'), Member('c')]
    r = one_task(m, [Assignment('a', 10.4, lead=True), Assignment('team', 5.2)])
    np.testing.assert_allclose(r['weeks'][:, 0], [10.4, 5.2, 5.2])
    np.testing.assert_allclose(r['person_year'][:, 0, 0], [0.20, 0.10, 0.10])
    assert r['items']['A1']['fte'][0] == pytest.approx((10.4 + 2 * 5.2) / 52)


def test_named_member_keeps_their_own_weeks_not_team_weeks():
    m = [Member('a'), Member('b')]
    r = one_task(m, [Assignment('a', 2, lead=True), Assignment('b', 9), Assignment('team', 4)])
    np.testing.assert_allclose(r['weeks'][:, 0], [2, 9])


def test_collaborator_receiving_team_weeks_is_fully_unfunded():
    m = [Member('a'), Member('c', role='coll(1)')]
    r = one_task(m, [Assignment('a', 5.2, lead=True), Assignment('team', 5.2)])
    np.testing.assert_allclose(r['person_year'][1, 0], [0.10, 0.10, 0.0])


def test_non_us_member_is_unfunded_whatever_their_role():
    m = [Member('x', role='co-I(1)', us=False)]
    r = one_task(m, [Assignment('x', 5.2, unfunded=0, lead=True)])
    assert m[0].collaborator
    np.testing.assert_allclose(r['person_year'][0, 0], [0.10, 0.10, 0.0])


def test_collaborator_listed_first_is_still_unfunded():
    m = [Member('c', role='coll(1)'), Member('a')]          # the Sheet's onEdit skipped the first row
    r = one_task(m, [Assignment('a', 5.2, lead=True), Assignment('c', 5.2)])
    np.testing.assert_allclose(r['person_year'][0, 0], [0.10, 0.10, 0.0])


def test_partly_unfunded_funded_person():
    r = one_task([Member('a')], [Assignment('a', 10.4, unfunded=5.2, lead=True)])
    np.testing.assert_allclose(r['person_year'][0, 0], [0.20, 0.10, 0.10])


def test_weeks_split_across_years_by_quarters():
    r = one_task([Member('a')], [Assignment('a', 12, lead=True)], start=Qs(1, 3), end=Qe(2, 1), n_years=2)
    np.testing.assert_allclose(r['year_fraction'][0], [2 / 3, 1 / 3])


def test_subtasks_roll_up_to_task_and_goal():
    m = [Member('a'), Member('b')]
    task = Item('T', children=[Item('S1', start=Qs(1, 1), end=Qe(1, 2), assignments=[Assignment('a', 5.2, lead=True)]),
                               Item('S2', start=Qs(1, 4), end=Qe(2, 2), assignments=[Assignment('b', 10.4, lead=True)])])
    r = compute(m, [Item('G', children=[task])], 2)
    assert [lab for lab in r['items']] == ['A', 'A1', 'A1.1', 'A1.2']
    assert r['leaf_labels'] == ['A1.1', 'A1.2']
    for lab in ('A1', 'A'):
        assert r['items'][lab]['fte'][0] == pytest.approx(15.6 / 52)
        assert (r['items'][lab]['start'], r['items'][lab]['end']) == (Qs(1, 1), Qe(2, 2))


def test_effort_on_a_task_with_subtasks_is_flagged_not_counted():
    task = Item('T', assignments=[Assignment('a', 9, lead=True)],
                children=[Item('S', start=Qs(1, 1), end=Qe(1, 1), assignments=[Assignment('a', 5.2, lead=True)])])
    r = compute([Member('a')], [Item('G', children=[task])], 1)
    assert r['person_year'][0, 0, 0] == pytest.approx(0.10)
    assert any(c.item == 'A1' and 'subtasks' in c.message for c in r['checks'])


def test_any_number_of_years_and_goals():
    r = one_task([Member('a')], [Assignment('a', 70, lead=True)], start=Qs(1, 1), end=Qe(7, 4), n_years=7)
    assert r['person_year'].shape == (1, 7, 3)
    assert [letters(i) for i in (0, 25, 26, 27)] == ['A', 'Z', 'AA', 'AB']
    many = [Item(f'G{i}', children=[Item('t')]) for i in range(30)]
    assert label_tree(many)[-2][0] == 'AD'


def test_incomplete_items_are_reported_not_dropped():
    m = [Member('a'), Member('idle')]
    goals = [Item('G', children=[Item('no timeline', assignments=[Assignment('a', 5, lead=True)]),
                                 Item('no lead', start=Qs(1, 1), end=Qe(1, 1), assignments=[Assignment('a', 5)]),
                                 Item('stranger', start=Qs(1, 1), end=Qe(1, 1), assignments=[Assignment('zz', 5, lead=True)])]),
             Item('empty goal')]
    r = compute(m, goals, 1)
    found = {(c.item, c.message.split(' ')[0]) for c in r['checks']}
    assert ('A1', 'has') in found and ('A2', 'has') in found and ('A3', '"zz"') in found
    assert ('B', 'task') in found and ('idle', 'is') in found
    assert r['leaf_labels'] == ['A1', 'A2', 'A3']                     # every item is still there


def test_unfunded_above_weeks_warns_but_is_not_blocked():
    r = one_task([Member('a')], [Assignment('a', 2, unfunded=3, lead=True)])
    assert [c.level for c in r['checks']] == ['warn']


def test_years_split_by_the_weeks_of_the_timeline():
    """Weeks 40-52 of year 1 (13 weeks) and 1-10 of year 2 (10 weeks): 23 weeks of effort split 13 : 10."""
    r = one_task([Member('a', fte_accuracy=0.0001)], [Assignment('a', 23, lead=True)], start=(1, 40), end=(2, 10), n_years=2)
    np.testing.assert_allclose(r['year_fraction'][0], [13 / 23, 10 / 23])
    np.testing.assert_allclose(r['person_year'][0][:, 0], [13 / 52, 10 / 52], atol=1e-4)
    assert (r['items']['A1']['start'], r['items']['A1']['end']) == ((1, 40), (2, 10))


def test_a_one_week_timeline_counts():
    r = one_task([Member('a')], [Assignment('a', 1, lead=True)], start=(2, 52), end=(2, 52), n_years=2)
    np.testing.assert_allclose(r['year_fraction'][0], [0, 1]) and not r['checks']


def test_more_effort_than_the_timeline_has_weeks_warns():
    """10 weeks of effort on a 2-week timeline: more than full time on that item (for "team" too, per person)."""
    r = one_task([Member('a'), Member('b')], [Assignment('a', 10, lead=True), Assignment('team', 3)], start=(1, 15), end=(1, 16))
    msgs = [(c.level, c.item, c.message) for c in r['checks']]
    assert ('warn', 'A1', 'a has 10 weeks of effort on a 2-week timeline, more than full time') in msgs
    assert ('warn', 'A1', 'b has 3 weeks of effort on a 2-week timeline, more than full time') in msgs
    assert {c.person for c in r['checks'] if c.item == 'A1'} == {'a', 'b'}
    r = one_task([Member('a')], [Assignment('a', 2, lead=True)], start=(1, 15), end=(1, 16))
    assert r['checks'] == []                                           # exactly full time is fine


def test_overlapping_items_over_full_time_warn():
    """Two items, each fine alone, overlap in weeks 11-20: 0.6 + 0.6 = 1.2 FTE there."""
    m = [Member('a', fte_accuracy=0.01)]
    goals = [Item('G', children=[Item('x', start=(1, 1), end=(1, 20), assignments=[Assignment('a', 12, lead=True)]),
                                 Item('y', start=(1, 11), end=(1, 30), assignments=[Assignment('a', 12, lead=True)])])]
    r = compute(m, goals, 2)
    assert [(c.level, c.item, c.message) for c in r['checks']] == \
        [('warn', 'a', 'has more than full time in Y1 W11–W20 (up to 1.20 FTE), with the effort spread evenly over each timeline')]
    assert (r['checks'][0].person, r['checks'][0].weeks) == ('a', [[10, 19]])          # for marking the plan: who, and which weeks
    goals[0].children[1].start, goals[0].children[1].end = (1, 21), (1, 40)        # no longer overlapping
    assert compute(m, goals, 2)['checks'] == []


def test_more_than_one_fte_in_a_year_warns():
    r = one_task([Member('a')], [Assignment('a', 60, lead=True)], start=Qs(1, 1), end=Qe(2, 4), n_years=2)   # 30 weeks a year: fine
    assert r['checks'] == []
    r = one_task([Member('a')], [Assignment('a', 60, lead=True)], start=(1, 1), end=(1, 52), n_years=2)       # 60 weeks in one year
    assert ('warn', 'a', 'has more than 1.0 FTE in year 1 (1.15)') in [(c.level, c.item, c.message) for c in r['checks']]
    assert [(c.person, c.weeks) for c in r['checks'] if 'FTE in year' in c.message] == [('a', [[0, 51]])]
