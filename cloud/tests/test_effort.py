"""Tests for the WorPT effort engine.

Part 1 (parity): the demo proposal must give exactly the numbers the Google Sheet version computed.
Part 2 (rules): one test per agreed rule, including the places where the new engine deliberately
differs from the Sheet version.
"""
import json, pathlib, sys
import numpy as np, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from worpt.effort import Member, Assignment, Item, compute, mround, letters, label_tree

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'demo2023.json'


def load_demo():
    d = json.loads(FIXTURE.read_text())
    members = [Member(p['id'], p['role'], p['us'], p['fte_accuracy']) for p in d['team']]
    goals = [Item(g['title'], children=[Item(t['title'], start=tuple(t['start']), end=tuple(t['end']),
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
def one_task(members, assignments, start=(1, 1), end=(1, 4), n_years=1):
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
    r = one_task([Member('a')], [Assignment('a', 12, lead=True)], start=(1, 3), end=(2, 1), n_years=2)
    np.testing.assert_allclose(r['year_fraction'][0], [2 / 3, 1 / 3])


def test_subtasks_roll_up_to_task_and_goal():
    m = [Member('a'), Member('b')]
    task = Item('T', children=[Item('S1', start=(1, 1), end=(1, 2), assignments=[Assignment('a', 5.2, lead=True)]),
                               Item('S2', start=(1, 4), end=(2, 2), assignments=[Assignment('b', 10.4, lead=True)])])
    r = compute(m, [Item('G', children=[task])], 2)
    assert [lab for lab in r['items']] == ['A', 'A1', 'A1.1', 'A1.2']
    assert r['leaf_labels'] == ['A1.1', 'A1.2']
    for lab in ('A1', 'A'):
        assert r['items'][lab]['fte'][0] == pytest.approx(15.6 / 52)
        assert (r['items'][lab]['start'], r['items'][lab]['end']) == ((1, 1), (2, 2))


def test_effort_on_a_task_with_subtasks_is_flagged_not_counted():
    task = Item('T', assignments=[Assignment('a', 9, lead=True)],
                children=[Item('S', start=(1, 1), end=(1, 1), assignments=[Assignment('a', 5.2, lead=True)])])
    r = compute([Member('a')], [Item('G', children=[task])], 1)
    assert r['person_year'][0, 0, 0] == pytest.approx(0.10)
    assert any(c.item == 'A1' and 'subtasks' in c.message for c in r['checks'])


def test_any_number_of_years_and_goals():
    r = one_task([Member('a')], [Assignment('a', 70, lead=True)], start=(1, 1), end=(7, 4), n_years=7)
    assert r['person_year'].shape == (1, 7, 3)
    assert [letters(i) for i in (0, 25, 26, 27)] == ['A', 'Z', 'AA', 'AB']
    many = [Item(f'G{i}', children=[Item('t')]) for i in range(30)]
    assert label_tree(many)[-2][0] == 'AD'


def test_incomplete_items_are_reported_not_dropped():
    m = [Member('a'), Member('idle')]
    goals = [Item('G', children=[Item('no timeline', assignments=[Assignment('a', 5, lead=True)]),
                                 Item('no lead', start=(1, 1), end=(1, 1), assignments=[Assignment('a', 5)]),
                                 Item('stranger', start=(1, 1), end=(1, 1), assignments=[Assignment('zz', 5, lead=True)])]),
             Item('empty goal')]
    r = compute(m, goals, 1)
    found = {(c.item, c.message.split(' ')[0]) for c in r['checks']}
    assert ('A1', 'has') in found and ('A2', 'has') in found and ('A3', '"zz"') in found
    assert ('B', 'goal') in found and ('idle', 'is') in found
    assert r['leaf_labels'] == ['A1', 'A2', 'A3']                     # every item is still there


def test_unfunded_above_weeks_warns_but_is_not_blocked():
    r = one_task([Member('a')], [Assignment('a', 2, unfunded=3, lead=True)])
    assert [c.level for c in r['checks']] == ['warn']
