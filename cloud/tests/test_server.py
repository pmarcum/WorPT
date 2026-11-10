"""End-to-end tests of the WorPT server through its HTTP API (Flask test client, a fresh database per test).

Covers the credential gate, the permission rules, every kind of change, conflicts, the work-plan rules
(three levels, effort only on the lowest level, at least one lead, non-US means collaborator), delete
previews, history, and that tables read through the API are identical to the tables built directly
from the parity fixtures (so storing a proposal loses nothing).
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from worpt_server import create_app
from worpt.tables import build, TABLES, numbered_roles
from worpt.store import role_label
from test_parity_tables import load, CASES

KEY, READ = 'k' * 24, 'r' * 24


class Api:
    def __init__(self, client, email, access='code', key=KEY):
        self.c, self.h = client, {'X-WorPT-Credential': key, 'X-WorPT-User': email, 'X-WorPT-Access': access}

    def __getattr__(self, verb):                     # api.get(url), api.post(url, json), api.patch(...), api.delete(...)
        def call(url, body=None):
            r = getattr(self.c, verb)(url, headers=self.h, json=body)
            assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
            return r.get_json()
        return call

    def ok(self, verb, url, body=None):
        out = getattr(self, verb)(url, body); assert out['status'] == 'ok', out; return out

    def no(self, verb, url, body=None, code=None):
        out = getattr(self, verb)(url, body); assert out['status'] == 'error', out
        if code: assert out['code'] == code, out
        return out


@pytest.fixture
def client(tmp_path):
    return create_app(str(tmp_path / 'worpt.db'), KEY, READ).test_client()


@pytest.fixture
def team(client):
    """A proposal led by Ann (core) with Bob as a plain member; Cat (core) and Dan (code) are not on it; Eve is an admin."""
    ann, bob, cat = Api(client, 'Ann@x.org', 'core'), Api(client, 'bob@x.org'), Api(client, 'cat@x.org', 'core')
    dan, eve = Api(client, 'dan@x.org'), Api(client, 'eve@x.org', 'admin')
    p = {n: ann.ok('post', '/api/people', dict(first=n.title(), last=n.title() + 'son', email=f'{n}@x.org'))['person']
         for n in ('ann', 'bob', 'cat', 'dan')}
    prop = ann.ok('post', '/api/proposals', dict(title='Test Proposal', program='NASA/ADAP', n_years=3,
                                                 leads=[dict(person_id=p['ann']['id'], short_id='AA', role='PI')]))['proposal']
    bob_m = ann.ok('post', f"/api/proposals/{prop['id']}/members", dict(person_id=p['bob']['id'], short_id='BB', role='co-I(1)'))['member']
    goal = ann.ok('post', f"/api/proposals/{prop['id']}/items", dict(title='Goal A'))['item']
    task = ann.ok('post', f"/api/proposals/{prop['id']}/items", dict(title='Task A1', parent_id=goal['id']))['item']
    return dict(ann=ann, bob=bob, cat=cat, dan=dan, eve=eve, people=p, prop=prop, pid=prop['id'], bob_m=bob_m, goal=goal, task=task)


def timed(api, task, years=(1, 1, 1, 52)):
    sy, sw, ey, ew = years                                       # (start year, start week, end year, end week)
    return api.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], start_year=sy, start_week=sw, end_year=ey, end_week=ew))['item']


# ------------------------------------------------ credential gate
def test_health_needs_no_credential(client):
    assert client.get('/health').get_json() == {'service': 'worpt', 'status': 'ok'}


def test_wrong_or_missing_credential_is_refused(client):
    Api(client, 'a@x.org', key='wrong' * 5).no('get', '/api/me', code='credential')
    assert client.get('/api/me').get_json()['code'] == 'credential'


def test_short_credential_refuses_to_start(tmp_path):
    with pytest.raises(SystemExit): create_app(str(tmp_path / 'w.db'), 'short')


def test_short_read_credential_is_ignored(tmp_path, client):
    app = create_app(str(tmp_path / 'w.db'), KEY, 'short-read')
    assert app.test_client().get('/api/proposals/x/tables', headers={'X-WorPT-Credential': 'short-read'}).get_json()['code'] == 'credential'


def test_sign_in_needed(client):
    Api(client, '').no('get', '/api/me', code='signin')


def test_read_key_only_reads_tables(team, client):
    r = Api(client, '', key=READ)
    r.no('get', '/api/proposals', code='credential')
    r.no('get', f"/api/proposals/{team['pid']}", code='credential')
    r.no('post', '/api/people', dict(last='X'), code='credential')
    r.no('delete', f"/api/proposals/{team['pid']}/tables/isANONfte", code='credential')
    assert r.ok('get', f"/api/proposals/{team['pid']}/tables")['tables'] == list(TABLES)
    assert 'Goal' in json.dumps(r.ok('get', f"/api/proposals/{team['pid']}/tables/NOTANONtasks"))
    r.no('get', '/api/proposals/nosuch/tables/isANONfte', code='not_found')
    r.no('get', '/api/proposals/nosuch/tables', code='not_found')
    r.no('get', f"/api/proposals/{team['pid']}/tables/nosuch", code='unknown_table')
    sty = r.ok('get', f"/api/proposals/{team['pid']}/tables/worpt")                # worpt.sty, for gooTeX to bring in too
    assert r.ok('get', f"/api/proposals/{team['pid']}/tables")['style'] == 'worpt' and '\\ProvidesPackage{worpt}' in sty['latex']
    every = r.ok('get', f"/api/proposals/{team['pid']}/tables?files=1")                # all of it in one request, for gooTeX
    assert sorted(every['files']) == sorted([f'{n}.tex' for n in TABLES] + ['worpt.sty']) and every['work_plan']['id'] == team['pid']
    one = r.ok('get', f"/api/proposals/{team['pid']}/tables/NOTANONtasks")
    assert every['files']['worpt.sty'] == sty['latex'] and every['files']['NOTANONtasks.tex'] == one['latex']
    assert sorted(every['blocks']) == sorted(list(TABLES) + ['worpt']) and every['blocks']['NOTANONtasks'] == one['block']    # paste-in blocks
    assert '\\input{NOTANONtasks}' in one['block'] and every['blocks']['worpt'] == sty['block'] and sty['block'].startswith('\\usepackage{worpt}')
    assert r.ok('get', f"/api/proposals/{team['pid']}/tables?files=1")['digest'] == every['digest']                 # unchanged: same digest
    ann = team['ann']; p = team['people']['bob']
    ann.ok('patch', f"/api/people/{p['id']}", dict(version=p['version'], institution='Elsewhere'))                  # a profile edit
    assert r.ok('get', f"/api/proposals/{team['pid']}/tables?files=1")['digest'] != every['digest']                 # changes the digest
    r.no('get', '/api/proposals/nosuch/tables?files=1', code='not_found')


def test_unknown_route(client):
    Api(client, 'a@x.org').no('get', '/api/nothing-here', code='unknown')
    Api(client, 'a@x.org').no('put', '/api/proposals', code='unknown')


# ------------------------------------------------ who sees and does what
def test_emails_are_case_insensitive(team):
    me = team['ann'].ok('get', '/api/me')
    assert me['email'] == 'ann@x.org' and me['profile']['first'] == 'Ann' and len(me['proposals']) == 1


def test_who_sees_the_proposal(team):
    pid = team['pid']
    for who in ('ann', 'bob', 'eve'): assert [p['id'] for p in team[who].ok('get', '/api/proposals')['proposals']] == [pid]
    for who in ('cat', 'dan'):
        assert team[who].ok('get', '/api/proposals')['proposals'] == []
        team[who].no('get', f'/api/proposals/{pid}', code='not_found')
    you = team['bob'].ok('get', f'/api/proposals/{pid}')['you']
    assert you['member_id'] == team['bob_m']['id'] and not you['lead'] and not you['can_manage_team']
    assert team['eve'].ok('get', f'/api/proposals/{pid}')['you']['can_manage_team']


def test_who_creates_proposals(team):
    lead = [dict(person_id=team['people']['dan']['id'], short_id='DD', role='PI')]
    team['dan'].no('post', '/api/proposals', dict(title='T', leads=lead))
    team['cat'].no('post', '/api/proposals', dict(title='T', leads=[]), code='missing')
    team['cat'].no('post', '/api/proposals', dict(title=' ', leads=lead), code='missing')
    team['cat'].no('post', '/api/proposals', dict(title='T', n_years=0, leads=lead), code='invalid')
    p = team['cat'].ok('post', '/api/proposals', dict(title='Cat proposal', n_years=7, leads=lead))['proposal']
    assert p['n_years'] == 7 and [x['title'] for x in team['dan'].ok('get', '/api/proposals')['proposals']] == ['Cat proposal']


def test_any_member_edits_the_plan_but_only_leads_manage_the_team(team):
    pid, bob = team['pid'], team['bob']
    bob.ok('post', f'/api/proposals/{pid}/items', dict(title='Goal B'))
    bob.ok('post', f"/api/items/{team['task']['id']}/assignments", dict(member_id=team['bob_m']['id'], weeks=4))
    bob.ok('post', f'/api/proposals/{pid}/nonlabor', dict(item='Publications', amounts=[1000, 0, 2000]))
    bob.no('post', f'/api/proposals/{pid}/members', dict(person_id=team['people']['cat']['id'], short_id='CC', role='co-I(2)'))
    bob.no('patch', f"/api/members/{team['bob_m']['id']}", dict(version=1, is_lead=True))
    bob.no('delete', f'/api/proposals/{pid}', dict(confirm_title='Test Proposal'))
    team['dan'].no('post', f'/api/proposals/{pid}/items', dict(title='X'), code='not_found')
    team['eve'].ok('post', f'/api/proposals/{pid}/members', dict(person_id=team['people']['cat']['id'], short_id='CC', role='co-I(2)'))


def test_profiles(team):
    ann, bob, dan, p = team['ann'], team['bob'], team['dan'], team['people']
    dan.no('post', '/api/people', dict(last='Nobody'))                                   # not core, not a lead
    ann.no('post', '/api/people', dict(first='No last name'), code='missing')
    ann.no('post', '/api/people', dict(last='Dup', email='BOB@x.org'), code='duplicate_email')
    bob.ok('patch', f"/api/people/{p['bob']['id']}", dict(version=1, institution='GSFC'))           # own profile
    bob.no('patch', f"/api/people/{p['ann']['id']}", dict(version=1, institution='X'))             # someone else's
    ann.ok('patch', f"/api/people/{p['bob']['id']}", dict(version=2, position='Scientist'))        # a lead of Bob's proposal
    assert [x['first'] for x in dan.ok('get', '/api/people')['people']] == ['Dan']               # others see only themselves
    assert [x['first'] for x in ann.ok('get', '/api/people?q=BOB')['people']] == ['Bob']


def test_non_us_person_becomes_a_collaborator_everywhere(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    ann.ok('patch', f"/api/people/{p['bob']['id']}", dict(version=1, us=False))
    roles = {m['short_id']: m['role'] for m in ann.ok('get', f'/api/proposals/{pid}')['members']}
    assert roles == {'PI': 'PI', 'collab 1': 'coll(1)'}                  # the label follows the new role
    ann.ok('patch', f"/api/people/{p['cat']['id']}", dict(version=1, us=False))
    cat_m = ann.ok('post', f'/api/proposals/{pid}/members', dict(person_id=p['cat']['id'], short_id='CC', role='co-I(2)'))['member']
    assert cat_m['role'] == 'coll(2)'
    timed(ann, team['task'])
    ann.ok('post', f"/api/items/{team['task']['id']}/assignments", dict(member_id=cat_m['id'], weeks=26))
    people = ann.ok('get', f'/api/proposals/{pid}')['computed']['people']
    unfunded, funded = people[str(cat_m['id'])]['total'][1:]                # [total, unfunded, funded]
    assert funded == 0 and unfunded > 0                                      # collaborators are 100% unfunded


# ------------------------------------------------ team and leads
def test_member_fields(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    url = f'/api/proposals/{pid}/members'
    ann.no('post', url, dict(person_id=p['bob']['id'], role='co-I(3)'), code='duplicate')            # already on the proposal
    ann.no('post', url, dict(person_id=p['cat']['id'], role='pi'), code='duplicate')                 # Ann is the PI
    ann.no('post', url, dict(person_id=p['cat']['id'], role='Team'), code='invalid')
    ann.no('post', url, dict(person_id=p['cat']['id'], role=''), code='missing')
    ann.no('post', url, dict(person_id=9999, role='co-I(2)'), code='not_found')


def test_labels_come_from_roles_never_from_names(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    labels = {m['role']: m['short_id'] for m in ann.ok('get', f'/api/proposals/{pid}')['members']}
    assert labels == {'PI': 'PI', 'co-I(1)': 'co-I 1'}                    # what the client sent as short_id is ignored
    for role, label in [('coll(2)', 'collab 1'), ('Grad student', 'gst 1'), ('pd(3)', 'pd 1'), ('Undergrad student', 'ust 1'),
                        ('sci-pi', 'Sci-PI')]:
        m = ann.ok('patch', f"/api/members/{team['bob_m']['id']}", dict(version=ann.ok('get', f'/api/proposals/{pid}')['members'][1]['version'], role=role))['member']
        assert m['short_id'] == label, (role, m)
    assert 'Sci-PI' in ann.ok('get', f'/api/proposals/{pid}/tables/NOTANONschedule')['latex']


def roles(api, pid):
    return {m['person_id']: (m['role'], m['short_id']) for m in api.ok('get', f'/api/proposals/{pid}')['members']}


def test_roles_are_numbered_by_worpt_in_last_name_order(team, client):
    ann, pid, p = team['ann'], team['pid'], team['people']
    url = f'/api/proposals/{pid}/members'
    assert team['bob_m']['version'] == 1                                  # a new member starts at version 1
    cat = ann.ok('post', url, dict(person_id=p['cat']['id'], role='co-I'))['member']            # just "co-I"
    assert (cat['role'], cat['short_id']) == ('co-I(2)', 'co-I 2')        # Bobson, then Catson
    aal = ann.ok('post', '/api/people', dict(first='Al', last='Aalto'))['person']
    al = ann.ok('post', url, dict(person_id=aal['id'], role='Co-I(7)'))['member']               # a typed number is not kept
    assert roles(ann, pid) == {p['ann']['id']: ('PI', 'PI'), aal['id']: ('co-I(1)', 'co-I 1'),
                               p['bob']['id']: ('co-I(2)', 'co-I 2'), p['cat']['id']: ('co-I(3)', 'co-I 3')}
    bob = next(m for m in ann.ok('get', f'/api/proposals/{pid}')['members'] if m['person_id'] == p['bob']['id'])
    assert bob['version'] == 2                                            # renumbering is a change others see
    ann.ok('delete', f"/api/members/{al['id']}", dict(confirm=True))      # close the gap
    assert roles(ann, pid)[p['bob']['id']] == ('co-I(1)', 'co-I 1') and roles(ann, pid)[p['cat']['id']] == ('co-I(2)', 'co-I 2')
    cat = next(m for m in ann.ok('get', f'/api/proposals/{pid}')['members'] if m['person_id'] == p['cat']['id'])
    cat = ann.ok('patch', f"/api/members/{cat['id']}", dict(version=cat['version'], role='Collaborator'))['member']
    assert (cat['role'], cat['short_id']) == ('coll(1)', 'collab 1') and roles(ann, pid)[p['bob']['id']] == ('co-I(1)', 'co-I 1')
    ann.ok('patch', f"/api/members/{cat['id']}", dict(version=cat['version'], role='co-I'))
    assert roles(ann, pid)[p['cat']['id']] == ('co-I(2)', 'co-I 2')
    ann.ok('patch', f"/api/people/{p['cat']['id']}", dict(version=p['cat']['version'], last='Abbot'))   # a new last name reorders
    assert roles(ann, pid)[p['cat']['id']] == ('co-I(1)', 'co-I 1') and roles(ann, pid)[p['bob']['id']] == ('co-I(2)', 'co-I 2')
    ann.ok('patch', f"/api/people/{p['cat']['id']}", dict(version=p['cat']['version'] + 1, us=False))  # non-US: a collaborator
    assert roles(ann, pid)[p['cat']['id']] == ('coll(1)', 'collab 1') and roles(ann, pid)[p['bob']['id']] == ('co-I(1)', 'co-I 1')
    dan = ann.ok('post', url, dict(person_id=p['dan']['id'], role='sci-pi(2)'))['member']   # one Science PI, so no number
    assert (dan['role'], dan['short_id']) == ('Sci-PI', 'Sci-PI')
    ann.no('patch', f"/api/members/{team['bob_m']['id']}", dict(version=2, role='SCI-pi'), code='duplicate')


def test_restoring_a_snapshot_renumbers_the_team(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    ann.ok('post', f'/api/proposals/{pid}/members', dict(person_id=p['cat']['id'], role='co-I'))
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='three of us'))['snapshot']
    ann.ok('patch', f"/api/people/{p['bob']['id']}", dict(version=p['bob']['version'], last='Zed'))   # Catson is now first
    assert roles(ann, pid)[p['cat']['id']] == ('co-I(1)', 'co-I 1')
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert roles(ann, pid)[p['cat']['id']] == ('co-I(1)', 'co-I 1') and roles(ann, pid)[p['bob']['id']] == ('co-I(2)', 'co-I 2')


def test_profiles_have_expertise_and_pronoun(team):
    ann, p = team['ann'], team['people']
    x = ann.ok('patch', f"/api/people/{p['ann']['id']}", dict(version=1, expertise=' galaxy photometry ', pronoun='She'))['person']
    assert (x['expertise'], x['pronoun']) == ('galaxy photometry', 'she')
    ann.no('patch', f"/api/people/{p['ann']['id']}", dict(version=2, pronoun='it'), code='invalid')


def test_an_older_database_is_brought_up_to_date(tmp_path):
    import sqlite3
    db = tmp_path / 'old.db'
    c = sqlite3.connect(db)
    c.executescript('''CREATE TABLE people (id INTEGER PRIMARY KEY, email TEXT UNIQUE, first TEXT NOT NULL DEFAULT '', middle TEXT NOT NULL DEFAULT '',
      last TEXT NOT NULL DEFAULT '', prefix TEXT NOT NULL DEFAULT '', suffix TEXT NOT NULL DEFAULT '', institution TEXT NOT NULL DEFAULT '',
      position TEXT NOT NULL DEFAULT '', us INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1);
      CREATE TABLE proposals (id TEXT PRIMARY KEY, title TEXT NOT NULL, program TEXT NOT NULL DEFAULT '', n_years INTEGER NOT NULL DEFAULT 3,
      rounding TEXT NOT NULL DEFAULT 'nearest', latex_subdir TEXT NOT NULL DEFAULT 'do_NOT_manually_edit', travel TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL, created_by TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
      CREATE TABLE members (id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL, person_id INTEGER NOT NULL, short_id TEXT NOT NULL, role TEXT NOT NULL,
      is_lead INTEGER NOT NULL DEFAULT 0, fte_accuracy REAL, bio_summary TEXT NOT NULL DEFAULT '', task_summary TEXT NOT NULL DEFAULT '',
      trips TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 1, UNIQUE (proposal_id, short_id), UNIQUE (proposal_id, person_id));
      INSERT INTO people (id, last) VALUES (1, 'Marcum'), (2, 'Bobson');
      INSERT INTO proposals (id, title, created_at, created_by) VALUES ('p1', 'Old', '2026-11-06', 'x');
      INSERT INTO members (proposal_id, person_id, short_id, role, is_lead) VALUES ('p1', 1, 'PM', 'PI', 1), ('p1', 2, 'BB', 'Co-I(3)', 0);
      CREATE TABLE items (id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL, parent_id INTEGER, position INTEGER NOT NULL,
      title TEXT NOT NULL DEFAULT '', start_year INTEGER, start_q INTEGER, end_year INTEGER, end_q INTEGER, version INTEGER NOT NULL DEFAULT 1);
      INSERT INTO items (id, proposal_id, parent_id, position, title, start_year, start_q, end_year, end_q) VALUES
        (1, 'p1', NULL, 0, 'Goal', NULL, NULL, NULL, NULL), (2, 'p1', 1, 0, 'Task', 1, 2, 2, 3), (3, 'p1', 1, 1, 'Undated', NULL, NULL, NULL, NULL);''')
    c.commit(); c.close()
    app = create_app(str(db), KEY, READ)
    out = Api(app.test_client(), 'eve@x.org', 'admin').ok('get', '/api/proposals/p1')
    assert {(m['role'], m['short_id']) for m in out['members']} == {('PI', 'PI'), ('co-I(1)', 'co-I 1')} and out['members'][0]['expertise'] == ''
    timeline = {i['title']: (i['start_year'], i['start_week'], i['end_year'], i['end_week']) for i in out['items']}
    assert timeline == {'Goal': (None,) * 4, 'Task': (1, 14, 2, 39), 'Undated': (None,) * 4}     # Q2 of year 1 to Q3 of year 2, in weeks
    assert 'start_q' not in out['items'][0]
    with sqlite3.connect(db) as c: assert 'start_q' not in {r[1] for r in c.execute('PRAGMA table_info(items)')}


def test_older_labels_are_shortened_when_the_server_starts(tmp_path):
    """Labels made before November 9, 2026 ("postdoc 1", "grad 1"...) become the short ones ("pd 1", "gst 1") at startup,
    and the people keep their tasks (assignments point to the member, not the label)."""
    import sqlite3
    db = tmp_path / 'w.db'
    api = Api(create_app(str(db), KEY, READ).test_client(), 'ann@x.org', 'core')
    p = {n: api.ok('post', '/api/people', dict(first=n, last=n + 'son', email=f'{n}@x.org'))['person'] for n in ('ann', 'bob', 'cat')}
    pid = api.ok('post', '/api/proposals', dict(title='T', program='NASA/ADAP', n_years=1, leads=[dict(person_id=p['ann']['id'], role='PI')]))['proposal']['id']
    for n, role in (('bob', 'pd'), ('cat', 'gst')): api.ok('post', f'/api/proposals/{pid}/members', dict(person_id=p[n]['id'], role=role))
    goal = api.ok('post', f'/api/proposals/{pid}/items', dict(title='Goal'))['item']
    task = api.ok('post', f'/api/proposals/{pid}/items', dict(title='Task', parent_id=goal['id']))['item']
    bob = next(m for m in api.ok('get', f'/api/proposals/{pid}')['members'] if m['person_id'] == p['bob']['id'])
    api.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=bob['id'], weeks=2))
    with sqlite3.connect(db) as c:                                      # as an older server labeled them
        c.execute("UPDATE members SET short_id = 'postdoc 1' WHERE role = 'pd(1)'"); c.execute("UPDATE members SET short_id = 'grad 1' WHERE role = 'gst(1)'")
    api = Api(create_app(str(db), KEY, READ).test_client(), 'ann@x.org', 'core')
    assert {m['short_id'] for m in api.ok('get', f'/api/proposals/{pid}')['members']} == {'PI', 'pd 1', 'gst 1'}
    sched = api.ok('get', f'/api/proposals/{pid}/tables/NOTANONschedule')['latex']
    assert '\\FundedUsTeam{pd 1}' in sched and 'TeamMark{\\TeamFundedColor}' in sched.split('% begin task')[1]   # still on the task


def test_a_proposal_always_keeps_a_lead(team):
    ann, aa = team['ann'], team['ann'].ok('get', f"/api/proposals/{team['pid']}")['members'][0]
    ann.no('patch', f"/api/members/{aa['id']}", dict(version=aa['version'], is_lead=False), code='last_lead')
    ann.no('delete', f"/api/members/{aa['id']}", dict(confirm=True), code='last_lead')
    ann.ok('patch', f"/api/members/{team['bob_m']['id']}", dict(version=1, is_lead=True))
    assert team['bob'].ok('get', f"/api/proposals/{team['pid']}")['you']['can_manage_team']
    ann.ok('patch', f"/api/members/{aa['id']}", dict(version=aa['version'], is_lead=False))
    ann.no('post', f"/api/proposals/{team['pid']}/members", dict(person_id=team['people']['cat']['id'], short_id='CC', role='x'))


def test_removing_a_member_previews_then_removes_their_effort(team):
    ann, m = team['ann'], team['bob_m']
    ann.ok('post', f"/api/items/{team['task']['id']}/assignments", dict(member_id=m['id'], weeks=4))
    preview = ann.ok('delete', f"/api/members/{m['id']}", {})
    assert preview['needs_confirmation'] and preview['assignments'] == 1
    assert len(ann.ok('get', f"/api/proposals/{team['pid']}")['members']) == 2           # nothing removed yet
    ann.ok('delete', f"/api/members/{m['id']}", dict(confirm=True))
    data = ann.ok('get', f"/api/proposals/{team['pid']}")
    assert len(data['members']) == 1 and data['assignments'] == []
    team['bob'].no('get', f"/api/proposals/{team['pid']}", code='not_found')


# ------------------------------------------------ goals, tasks, subtasks and effort
def test_three_levels_and_labels(team):
    ann, pid, task = team['ann'], team['pid'], team['task']
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']))['item']
    ann.no('post', f'/api/proposals/{pid}/items', dict(title='Too deep', parent_id=sub['id']), code='too_deep')
    first = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub first', parent_id=task['id'], position=0))['item']
    labels = {i: v['label'] for i, v in ann.ok('get', f'/api/proposals/{pid}')['computed']['items'].items()}
    assert labels == {str(team['goal']['id']): 'A', str(task['id']): 'A1', str(first['id']): 'A1.1', str(sub['id']): 'A1.2'}


def test_effort_only_on_the_lowest_level(team):
    ann, pid, goal, task, m = team['ann'], team['pid'], team['goal'], team['task'], team['bob_m']
    ann.no('post', f"/api/items/{goal['id']}/assignments", dict(member_id=m['id'], weeks=2), code='invalid')
    ann.no('post', f"/api/items/{task['id']}/assignments", dict(weeks=2), code='missing')
    ann.no('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=-1), code='invalid')
    a = ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=10, unfunded=2))['assignment']
    ann.no('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=3), code='duplicate')
    t = ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], start_year=1, start_week=1, end_year=2, end_week=52))['item']
    # adding a subtask under a task with effort asks where the effort goes
    out = ann.no('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']), code='parent_has_effort')
    assert len(out['assignments']) == 1
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id'], effort_destination='new_child'))['item']
    assert (sub['start_year'], sub['end_week']) == (1, 52)
    data = ann.ok('get', f'/api/proposals/{pid}')
    assert [x['item_id'] for x in data['assignments']] == [sub['id']]
    assert {i['id']: i['start_year'] for i in data['items']}[task['id']] is None
    ann.no('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=1), code='invalid')
    ann.no('patch', f"/api/items/{task['id']}", dict(version=t['version'] + 1, start_year=1), code='invalid')
    ann.no('patch', f"/api/items/{goal['id']}", dict(version=goal['version'], start_year=1), code='invalid')
    ann.no('patch', f"/api/items/{sub['id']}", dict(version=sub['version'], start_week=53), code='invalid')
    ann.no('patch', f"/api/items/{sub['id']}", dict(version=sub['version'], end_week=0), code='invalid')
    computed = data['computed']
    assert computed['items'][str(task['id'])]['fte'] == computed['items'][str(sub['id'])]['fte']   # parents roll up
    assert computed['items'][str(task['id'])]['start'] == [1, 1]


def test_remove_effort_when_adding_a_subtask(team):
    ann, pid, task, m = team['ann'], team['pid'], team['task'], team['bob_m']
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=10))
    ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id'], effort_destination='remove'))
    assert ann.ok('get', f'/api/proposals/{pid}')['assignments'] == []


def test_one_lead_per_item_and_team_assignment(team):
    ann, task, m = team['ann'], timed(team['ann'], team['task']), team['bob_m']
    a1 = ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=4, is_lead=True))['assignment']
    a2 = ann.ok('post', f"/api/items/{task['id']}/assignments", dict(is_team=True, weeks=2, is_lead=True))['assignment']
    ann.no('post', f"/api/items/{task['id']}/assignments", dict(is_team=True, weeks=1), code='duplicate')
    leads = {a['id']: a['is_lead'] for a in ann.ok('get', f"/api/proposals/{team['pid']}")['assignments']}
    assert leads == {a1['id']: False, a2['id']: True}
    people = ann.ok('get', f"/api/proposals/{team['pid']}")['computed']['people']
    totals = {k: v['total'][0] for k, v in people.items()}
    aa = ann.ok('get', f"/api/proposals/{team['pid']}")['members'][0]['id']
    assert totals[str(aa)] > 0 and totals[str(m['id'])] > totals[str(aa)]      # 'team' gives its weeks to each unnamed member


def test_moving_items(team):
    ann, pid, goal, task = team['ann'], team['pid'], team['goal'], team['task']
    g2 = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Goal B'))['item']
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']))['item']
    ann.no('patch', f"/api/items/{goal['id']}", dict(version=goal['version'], parent_id=sub['id']), code='invalid')   # into itself
    ann.no('patch', f"/api/items/{task['id']}", dict(version=task['version'], parent_id=sub['id']), code='invalid')
    moved = ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], parent_id=g2['id']))['item']
    assert moved['parent_id'] == g2['id'] and moved['version'] == task['version'] + 1
    ann.no('patch', f"/api/items/{g2['id']}", dict(version=g2['version'], parent_id=goal['id']), code='too_deep')
    labels = {v['label'] for v in ann.ok('get', f'/api/proposals/{pid}')['computed']['items'].values()}
    assert labels == {'A', 'B', 'B1', 'B1.1'}


def test_moving_up_and_down_one_place(team):
    ann, pid, goal = team['ann'], team['pid'], team['goal']
    for t in ('T2', 'T3', 'T4'): ann.ok('post', f'/api/proposals/{pid}/items', dict(title=t, parent_id=goal['id']))
    def order():
        items = ann.ok('get', f'/api/proposals/{pid}')['items']
        kids = sorted((i for i in items if i['parent_id'] == goal['id']), key=lambda i: i['position'])
        assert [i['position'] for i in kids] == list(range(len(kids)))           # always numbered 0, 1, 2… with no gaps
        return [i['title'] for i in kids], {i['title']: i for i in kids}
    names, it = order(); assert names == ['Task A1', 'T2', 'T3', 'T4']
    def move(title, by):
        i = order()[1][title]; ann.ok('patch', f"/api/items/{i['id']}", dict(version=i['version'], parent_id=goal['id'], position=i['position'] + by))
        return order()[0]
    assert move('T3', -1) == ['Task A1', 'T3', 'T2', 'T4']
    assert move('T3', -1) == ['T3', 'Task A1', 'T2', 'T4']
    assert move('T3', -1) == ['T3', 'Task A1', 'T2', 'T4']                        # already first
    assert move('Task A1', 1) == ['T3', 'T2', 'Task A1', 'T4']
    assert move('Task A1', 1) == ['T3', 'T2', 'T4', 'Task A1']
    assert move('Task A1', 1) == ['T3', 'T2', 'T4', 'Task A1']                     # already last
    assert move('T2', 1) == ['T3', 'T4', 'T2', 'Task A1']


def test_subtask_up_to_a_task_and_task_down_to_a_subtask(team):
    ann, pid, goal, task, m = team['ann'], team['pid'], team['goal'], team['task'], team['bob_m']
    t2 = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='T2', parent_id=goal['id']))['item']
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']))['item']
    sub = ann.ok('patch', f"/api/items/{sub['id']}", dict(version=sub['version'], start_year=1, start_week=5, end_year=1, end_week=20))['item']
    ann.ok('post', f"/api/items/{sub['id']}/assignments", dict(member_id=m['id'], weeks=6, is_lead=True))
    # up a level, right after its old task: its effort and timeline go with it
    up = ann.ok('patch', f"/api/items/{sub['id']}", dict(version=sub['version'], parent_id=goal['id'], position=1))['item']
    d = ann.ok('get', f'/api/proposals/{pid}')
    assert [i['title'] for i in sorted((i for i in d['items'] if i['parent_id'] == goal['id']), key=lambda i: i['position'])] == ['Task A1', 'Sub', 'T2']
    assert (up['start_week'], up['end_week']) == (5, 20) and [a['item_id'] for a in d['assignments']] == [sub['id']]
    # down a level, under a task with effort of its own: that effort moves into it, and the same person's weeks add up
    t2 = ann.ok('patch', f"/api/items/{t2['id']}", dict(version=t2['version'], start_year=1, start_week=1, end_year=1, end_week=30))['item']
    ann.ok('post', f"/api/items/{t2['id']}/assignments", dict(member_id=m['id'], weeks=4))
    out = ann.no('patch', f"/api/items/{up['id']}", dict(version=up['version'], parent_id=t2['id']), code='parent_has_effort')
    down = ann.ok('patch', f"/api/items/{up['id']}", dict(version=up['version'], parent_id=t2['id'], effort_destination='new_child'))['item']
    d = ann.ok('get', f'/api/proposals/{pid}')
    assert down['parent_id'] == t2['id'] and (down['start_week'], down['end_week']) == (5, 20)       # keeps its own timeline
    assert [(a['item_id'], a['weeks'], a['is_lead']) for a in d['assignments']] == [(sub['id'], 10, True)]
    assert {i['id']: i['start_year'] for i in d['items']}[t2['id']] is None
    ann.no('patch', f"/api/items/{t2['id']}", dict(version=d and [i for i in d['items'] if i['id'] == t2['id']][0]['version'], parent_id=task['id']), code='too_deep')


def test_deleting_an_item_previews_counts(team):
    ann, pid, task, m = team['ann'], team['pid'], team['task'], team['bob_m']
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']))['item']
    ann.ok('post', f"/api/items/{sub['id']}/assignments", dict(member_id=m['id'], weeks=3))
    preview = ann.ok('delete', f"/api/items/{team['goal']['id']}", {})
    assert (preview['items_below'], preview['assignments']) == (2, 1)
    ann.ok('delete', f"/api/items/{team['goal']['id']}", dict(confirm=True))
    data = ann.ok('get', f'/api/proposals/{pid}')
    assert data['items'] == [] and data['assignments'] == []


# ------------------------------------------------ conflicts, deletes, history
def test_editing_conflict_returns_the_current_version(team):
    ann, bob, task = team['ann'], team['bob'], team['task']
    ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], title='Ann title'))
    out = bob.no('patch', f"/api/items/{task['id']}", dict(version=task['version'], title='Bob title'), code='conflict')
    assert out['current']['title'] == 'Ann title'
    bob.no('patch', f"/api/items/{task['id']}", dict(title='No version'), code='conflict')
    bob.ok('patch', f"/api/items/{task['id']}", dict(version=out['current']['version'], title='Bob title'))


def test_a_refused_change_saves_nothing(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    before = len(ann.ok('get', f'/api/proposals/{pid}/history')['history'])
    ann.no('post', '/api/proposals', dict(title='Two leads', leads=[dict(person_id=p['cat']['id'], short_id='CC', role='PI'),
                                                                     dict(person_id=p['cat']['id'], short_id='C2', role='co-I')]), code='duplicate')
    assert len(team['eve'].ok('get', '/api/proposals')['proposals']) == 1
    assert len(ann.ok('get', f'/api/proposals/{pid}/history')['history']) == before


def test_deleting_a_proposal_needs_its_title(team):
    ann, pid = team['ann'], team['pid']
    ann.no('delete', f'/api/proposals/{pid}', dict(confirm_title='test proposal'), code='confirm_title')
    ann.ok('delete', f'/api/proposals/{pid}', dict(confirm_title='Test Proposal'))
    assert team['eve'].ok('get', '/api/proposals')['proposals'] == []


def test_history_records_every_change(team):
    ann, pid = team['ann'], team['pid']
    ann.ok('patch', f'/api/proposals/{pid}', dict(version=team['prop']['version'], program='NASA/XRP'))
    h = ann.ok('get', f'/api/proposals/{pid}/history')['history']
    assert {(x['tbl'], x['action']) for x in h} >= {('proposals', 'insert'), ('members', 'insert'), ('items', 'insert'), ('proposals', 'update')}
    upd = next(x for x in h if x['tbl'] == 'proposals' and x['action'] == 'update')
    assert upd['user'] == 'ann@x.org' and json.loads(upd['before'])['program'] == 'NASA/ADAP' and json.loads(upd['after'])['program'] == 'NASA/XRP'
    team['dan'].no('get', f'/api/proposals/{pid}/history', code='not_found')


def test_proposal_settings(team):
    ann, pid, v = team['ann'], team['pid'], team['prop']['version']
    ann.no('patch', f'/api/proposals/{pid}', dict(version=v, rounding='down'), code='invalid')
    ann.no('patch', f'/api/proposals/{pid}', dict(version=v, n_years='x'), code='invalid')
    ann.no('patch', f'/api/proposals/{pid}', dict(version=v, title=''), code='missing')
    p = ann.ok('patch', f'/api/proposals/{pid}', dict(version=v, rounding='up', n_years=5, created_by='someone@else'))['proposal']
    assert (p['rounding'], p['n_years'], p['created_by']) == ('up', 5, 'ann@x.org')


def test_budget_lines(team):
    ann, pid = team['ann'], team['pid']
    line = ann.ok('post', f'/api/proposals/{pid}/nonlabor', dict(item='Publications', amounts=[1000, '', 2000]))['line']
    assert line['amounts'] == [1000, 0, 2000]
    line = ann.ok('patch', f"/api/nonlabor/{line['id']}", dict(version=line['version'], amounts=[5, 6, 7]))['line']
    assert 'Publications' in ann.ok('get', f'/api/proposals/{pid}/tables/isANONnonlabor')['latex']
    ann.ok('delete', f"/api/nonlabor/{line['id']}")
    assert ann.ok('get', f'/api/proposals/{pid}')['nonlabor'] == []


# ------------------------------------------------ tables through the API = tables from the fixtures
def store_fixture(api, folder):
    """Enter a parity fixture through the API, the way the dashboard would."""
    d = json.loads((folder / 'proposal.json').read_text())
    people = [api.ok('post', '/api/people', {k: t[k] for k in ('first', 'middle', 'last', 'prefix', 'suffix', 'institution', 'position', 'us')})['person']
              for t in d['team']]
    member = lambda t, p: dict(person_id=p['id'], short_id=t['id'], role=t['role'], fte_accuracy=t['fte_accuracy'],
                               bio_summary=t['bio_summary'], task_summary=t['task_summary'], trips=t['trips'])
    prop = api.ok('post', '/api/proposals', dict(title=d['title'], program=d['program'], n_years=d['n_years'],
                                                 leads=[member(d['team'][0], people[0])]))['proposal']
    pid = prop['id']
    api.ok('patch', f'/api/proposals/{pid}', dict(version=prop['version'], travel=d['travel'], rounding=d.get('rounding', 'up')))
    ids = {d['team'][0]['id']: api.ok('get', f'/api/proposals/{pid}')['members'][0]['id']}
    for t, p in zip(d['team'][1:], people[1:]):
        ids[t['id']] = api.ok('post', f'/api/proposals/{pid}/members', member(t, p))['member']['id']
    for g in d['goals']:
        goal = api.ok('post', f'/api/proposals/{pid}/items', dict(title=g['title']))['item']
        for t in g['tasks']:
            task = api.ok('post', f'/api/proposals/{pid}/items', dict(title=t['title'], parent_id=goal['id']))['item']
            if t['start'] or t['end']:
                (sy, sq), (ey, eq) = t['start'] or (None, None), t['end'] or (None, None)     # the fixture's timelines are in quarters
                api.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], start_year=sy, start_week=sq and (sq - 1) * 13 + 1,
                                                                   end_year=ey, end_week=eq and eq * 13))
            for a in t['assignments']:
                who = dict(is_team=True) if a['person'] == 'team' else dict(member_id=ids[a['person']])
                api.ok('post', f"/api/items/{task['id']}/assignments", dict(who, weeks=a['weeks'], unfunded=a['unfunded'], is_lead=a['lead']))
    for n in d['nonlabor']:
        api.ok('post', f'/api/proposals/{pid}/nonlabor', dict(item=n['item'], amounts=n['amounts']))
    return pid


def relabeled(p):
    """The fixture as the server stores it: numbered roles renumbered in the Sheet's order, and each person's ID replaced
    by their role's label."""
    new = {}
    for m, role in numbered_roles(p.members): new[m.id], m.role = role_label(role), role
    for m in p.members: m.id = new[m.id]
    def walk(items):
        for it in items:
            for a in it.assignments: a.person = new.get(a.person, a.person)
            walk(it.children)
    walk(p.goals)
    return p


@pytest.mark.parametrize('folder', CASES, ids=[c.name for c in CASES])
def test_tables_through_the_api_match_the_fixture(client, folder):
    admin = Api(client, 'admin@x.org', 'admin')
    pid = store_fixture(admin, folder)
    direct = build(relabeled(load(folder)))
    for name in TABLES:
        got = admin.ok('get', f'/api/proposals/{pid}/tables/{name}')
        assert got['latex'] == direct[name], f'{folder.name}/{name} differs after storing'
    gootex = Api(client, '', key=READ)                          # gooTeX's read-only key gets the same tables
    assert gootex.ok('get', f'/api/proposals/{pid}/tables/isANONfte')['latex'] == direct['isANONfte']


# ------------------------------------------------ what the dashboard polls and lists
def test_changed_grows_with_each_change(team):
    ann, bob, pid = team['ann'], team['bob'], team['pid']
    first = ann.ok('get', f'/api/proposals/{pid}/changed')['last_change']
    assert first == ann.ok('get', f'/api/proposals/{pid}')['last_change'] > 0
    assert bob.ok('get', f'/api/proposals/{pid}/changed')['last_change'] == first          # nothing changed yet
    bob.ok('patch', f"/api/items/{team['task']['id']}", dict(version=team['task']['version'], title='Renamed'))
    assert ann.ok('get', f'/api/proposals/{pid}/changed')['last_change'] > first
    team['dan'].no('get', f'/api/proposals/{pid}/changed', code='not_found')


def test_proposal_list_shows_leads_and_last_change(team):
    p = team['ann'].ok('get', '/api/proposals')['proposals'][0]
    assert p['leads'] == 'Ann Annson' and p['last_changed_at']


def test_travel_summary(team):
    ann, pid = team['ann'], team['pid']
    ann.ok('patch', f"/api/proposals/{pid}", dict(version=team['prop']['version'],
           travel=dict(airfare=[700, 1750, 0], perdiem=[264, 320, 0], conference=[500, 800, 0], ground=[60, 100, 0], days=[5, 5])))
    ann.ok('patch', f"/api/members/{team['bob_m']['id']}", dict(version=1, trips=[[1, 0], [2, 1], [0, 0]]))
    t = ann.ok('get', f'/api/proposals/{pid}')['computed']['travel']
    assert [(y['dom_trips'], y['int_trips']) for y in t] == [(1, 0), (2, 1), (0, 0)]
    assert t[0]['dom_per_trip'] == 700 + 264 * 5 + 500 + 60 * 5 and t[1]['dom_total'] == 2 * t[1]['dom_per_trip']


def test_deletes_accept_confirmation_in_the_query_string(team):
    ann, pid, m = team['ann'], team['pid'], team['bob_m']
    assert ann.ok('delete', f"/api/members/{m['id']}?confirm=0")['needs_confirmation']
    ann.ok('delete', f"/api/members/{m['id']}?confirm=1")
    assert ann.ok('delete', f"/api/items/{team['goal']['id']}")['needs_confirmation']
    ann.ok('delete', f"/api/items/{team['goal']['id']}?confirm=true")
    ann.no('delete', f'/api/proposals/{pid}?confirm_title=Wrong', code='confirm_title')
    ann.ok('delete', f'/api/proposals/{pid}?confirm_title=Test%20Proposal')


def test_any_member_edits_trips_but_not_other_member_fields(team):
    bob, m = team['bob'], team['bob_m']
    aa = team['ann'].ok('get', f"/api/proposals/{team['pid']}")['members'][0]
    assert bob.ok('patch', f"/api/members/{aa['id']}", dict(version=aa['version'], trips=[[1, 0], [0, 0], [0, 1]]))['member']['trips'][2] == [0, 1]
    bob.no('patch', f"/api/members/{aa['id']}", dict(version=aa['version'] + 1, trips=[[0, 0]], role='co-I'))
    bob.no('patch', f"/api/members/{m['id']}", dict(version=1, task_summary='x'))


# ------------------------------------------------ snapshots
def plan_of(api, pid):
    """The parts of a proposal a restore brings back, without ids and versions."""
    d = api.ok('get', f'/api/proposals/{pid}')
    title = {i['id']: i['title'] for i in d['items']}
    who = {m['id']: m['short_id'] for m in d['members']}
    return dict(settings={k: d['proposal'][k] for k in ('title', 'program', 'n_years', 'rounding', 'travel')},
                members=sorted((m['short_id'], m['role'], m['is_lead'], m['bio_summary']) for m in d['members']),
                items=sorted((i['title'], title.get(i['parent_id']), i['position'], i['start_year'], i['end_week']) for i in d['items']),
                work=sorted((title[a['item_id']], 'team' if a['is_team'] else who[a['member_id']], a['weeks'], a['is_lead']) for a in d['assignments']),
                budget=sorted((r['item'], tuple(r['amounts'])) for r in d['nonlabor']))


def test_first_change_of_the_day_saves_a_snapshot_once(team):
    ann, pid = team['ann'], team['pid']
    snaps = ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots']
    assert [s['kind'] for s in snaps].count('daily') == 1
    ann.ok('patch', f"/api/items/{team['task']['id']}", dict(version=team['task']['version'], title='Again'))
    assert [s['kind'] for s in ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots']].count('daily') == 1


def test_restore_brings_the_whole_proposal_back_and_can_be_undone(team):
    ann, pid, task, m = team['ann'], team['pid'], timed(team['ann'], team['task']), team['bob_m']
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=6, is_lead=True))
    ann.ok('post', f'/api/proposals/{pid}/nonlabor', dict(item='Publications', amounts=[1000, 0, 0]))
    before = plan_of(ann, pid)
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='before the review'))['snapshot']
    ann.no('post', f'/api/proposals/{pid}/snapshots', dict(name='  '), code='missing')
    # a big mistake: a task category deleted, a member added, settings changed
    cat = ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=team['people']['cat']['id'], role='co-I(2)'))['member']
    ann.ok('delete', f"/api/items/{team['goal']['id']}?confirm=1")
    v = ann.ok('get', f'/api/proposals/{pid}')['proposal']['version']
    ann.ok('patch', f'/api/proposals/{pid}', dict(version=v, n_years=5, title='Oops'))
    kinds = [(s['kind'], s['name']) for s in ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots']]
    assert ('before', 'Before changing the number of years from 3 to 5') in kinds
    assert any(k == 'before' and n.startswith('Before deleting "Goal A"') for k, n in kinds)
    mistake = plan_of(ann, pid)
    team['bob'].no('post', f"/api/snapshots/{snap['id']}/restore")                  # not a full editor
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert plan_of(ann, pid) == before                                           # Cat (added later) is off the team again
    tables = ann.ok('get', f'/api/proposals/{pid}/tables/NOTANONschedule')['latex']
    assert 'Goal A' in tables and 'co-I 1' in tables
    undo = next(s for s in ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots'] if s['name'].startswith('Before restoring'))
    ann.ok('post', f"/api/snapshots/{undo['id']}/restore")
    assert plan_of(ann, pid) == mistake                                          # the restore itself was undone


def test_restore_refuses_to_lock_out_the_person_restoring(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='early'))['snapshot']
    ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=p['cat']['id'], role='co-I(2)', is_lead=True))
    team['cat'].no('post', f"/api/snapshots/{snap['id']}/restore", code='refused')
    team['eve'].ok('post', f"/api/snapshots/{snap['id']}/restore")                # an admin may


def test_a_snapshot_saved_in_quarters_restores_in_weeks(team, tmp_path):
    ann, pid = team['ann'], team['pid']
    timed(ann, team['task'], (1, 14, 2, 39))
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='before weeks'))['snapshot']
    import sqlite3                                                      # make it look like one saved before timelines were in weeks
    with sqlite3.connect(tmp_path / 'worpt.db') as c:
        data = json.loads(c.execute('SELECT data FROM snapshots WHERE id = ?', (snap['id'],)).fetchone()[0])
        for i in data['items']:
            w0, w1 = i.pop('start_week'), i.pop('end_week')
            i['start_q'], i['end_q'] = w0 and (w0 - 1) // 13 + 1, w1 and (w1 - 1) // 13 + 1
        c.execute('UPDATE snapshots SET data = ? WHERE id = ?', (json.dumps(data), snap['id']))
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    task = next(i for i in ann.ok('get', f'/api/proposals/{pid}')['items'] if i['title'] == 'Task A1')
    assert (task['start_year'], task['start_week'], task['end_year'], task['end_week']) == (1, 14, 2, 39)


def test_old_automatic_snapshots_are_removed_named_ones_kept(team, tmp_path):
    import sqlite3
    ann, pid = team['ann'], team['pid']
    ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='keep me'))
    db = sqlite3.connect(tmp_path / 'worpt.db'); db.execute("UPDATE snapshots SET at = '2026-01-01T00:00:00+00:00'"); db.commit(); db.close()
    ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='new'))          # any new snapshot tidies up
    names = [s['name'] for s in ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots']]
    assert names == ['new', 'keep me']


def test_deleting_a_snapshot(team):
    ann, pid = team['ann'], team['pid']
    s = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='temp'))['snapshot']
    team['bob'].no('delete', f"/api/snapshots/{s['id']}")
    ann.ok('delete', f"/api/snapshots/{s['id']}")
    assert 'temp' not in [x['name'] for x in ann.ok('get', f'/api/proposals/{pid}/snapshots')['snapshots']]
    team['dan'].no('get', f'/api/proposals/{pid}/snapshots', code='not_found')


def test_short_titles_go_in_the_one_line_tables(team, tmp_path):
    """A short title, when given, is what the schedule and the task management table show; the other tables keep the
    full title. It is kept in snapshots, and snapshots saved before short titles existed restore without one."""
    ann, pid, task = team['ann'], team['pid'], timed(team['ann'], team['task'])
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=team['bob_m']['id'], weeks=2, is_lead=True))
    task = next(i for i in ann.ok('get', f'/api/proposals/{pid}')['items'] if i['id'] == task['id'])
    assert task['short_title'] == ''
    task = ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], title='Calibrate the zero points of every field', short_title='  Calibrate fields  '))['item']
    assert task['short_title'] == 'Calibrate fields'
    tex = lambda name: ann.ok('get', f'/api/proposals/{pid}/tables/{name}')['latex']
    assert '{Calibrate fields}' in tex('NOTANONschedule') and 'every field' not in tex('NOTANONschedule')
    assert '{Calibrate fields}' in tex('NOTANONtasks')
    assert 'Calibrate the zero points of every field' in tex('isANONtasks')
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='with short'))['snapshot']
    ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], short_title=''))
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert [i['short_title'] for i in ann.ok('get', f'/api/proposals/{pid}')['items'] if i['title'].startswith('Calibrate')] == ['Calibrate fields']
    import sqlite3                                                      # a snapshot from before short titles
    with sqlite3.connect(tmp_path / 'worpt.db') as c:
        data = json.loads(c.execute('SELECT data FROM snapshots WHERE id = ?', (snap['id'],)).fetchone()[0])
        for i in data['items']: i.pop('short_title')
        c.execute('UPDATE snapshots SET data = ? WHERE id = ?', (json.dumps(data), snap['id']))
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert {i['short_title'] for i in ann.ok('get', f'/api/proposals/{pid}')['items']} == {''}


def test_items_have_a_description_for_the_team_only(team, tmp_path):
    """A description (what the item stands for and involves) can go on any item, a category included. Its paragraphs are
    kept; it is never printed in a table; it is kept in snapshots, and older snapshots restore without one."""
    ann, pid, goal, task = team['ann'], team['pid'], team['goal'], team['task']
    assert task['description'] == ''
    text = '  Calibrate every field against the reference catalog.\r\n\r\nIncludes the bright-star fields, done by hand.  '
    task = ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], description=text))['item']
    assert task['description'] == 'Calibrate every field against the reference catalog.\n\nIncludes the bright-star fields, done by hand.'
    goal = ann.ok('patch', f"/api/items/{goal['id']}", dict(version=goal['version'], description='The whole calibration effort.'))['item']
    assert goal['description'] == 'The whole calibration effort.'
    every = ann.ok('get', f'/api/proposals/{pid}/tables?files=1')
    assert 'reference catalog' not in json.dumps(every) and 'calibration effort' not in json.dumps(every)
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='described'))['snapshot']
    ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], description=''))
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert sorted(i['description'] for i in ann.ok('get', f'/api/proposals/{pid}')['items']) == sorted([goal['description'], task['description']])
    import sqlite3                                                      # a snapshot from before descriptions
    with sqlite3.connect(tmp_path / 'worpt.db') as c:
        data = json.loads(c.execute('SELECT data FROM snapshots WHERE id = ?', (snap['id'],)).fetchone()[0])
        for i in data['items']: i.pop('description')
        c.execute('UPDATE snapshots SET data = ? WHERE id = ?', (json.dumps(data), snap['id']))
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert {i['description'] for i in ann.ok('get', f'/api/proposals/{pid}')['items']} == {''}


# ------------------------------------------------ undo and redo
def full(api, pid):
    """Everything about a work plan an undo should put back, ids included (but not versions)."""
    d = api.ok('get', f'/api/proposals/{pid}')
    strip = lambda rows: sorted(tuple(sorted((k, json.dumps(v)) for k, v in r.items() if k not in ('version', 'person_version'))) for r in rows)
    return dict(proposal={k: v for k, v in d['proposal'].items() if k != 'version'},
                members=strip(d['members']), items=strip(d['items']), work=strip(d['assignments']), budget=strip(d['nonlabor']))


def undo(api, pid, which='undo', **expect):
    out = api.ok('post', f'/api/proposals/{pid}/{which}')
    for k, v in expect.items(): assert out[k] == v, out
    return out


def you(api, pid): return api.ok('get', f'/api/proposals/{pid}')['you']


def item(api, pid, iid): return next(i for i in api.ok('get', f'/api/proposals/{pid}')['items'] if i['id'] == iid)


def test_undo_and_redo_a_bar(team):
    ann, pid, task = team['ann'], team['pid'], team['task']
    plain = full(ann, pid)
    task = timed(ann, task, (1, 5, 1, 20))
    drawn = full(ann, pid)
    assert you(ann, pid)['undo'] == 'drawing the bar of "Task A1"' and you(ann, pid)['redo'] is None
    undo(ann, pid, done='drawing the bar of "Task A1"', redo='drawing the bar of "Task A1"')
    assert full(ann, pid) == plain
    undo(ann, pid, 'redo', done='drawing the bar of "Task A1"')
    assert full(ann, pid) == drawn
    t = item(ann, pid, task['id'])
    ann.ok('patch', f"/api/items/{t['id']}", dict(version=t['version'], start_year=None, start_week=None, end_year=None, end_week=None))
    assert you(ann, pid)['undo'] == 'removing the bar of "Task A1"'
    undo(ann, pid)
    assert full(ann, pid) == drawn


def test_undo_goes_back_one_change_at_a_time_and_stops_where_the_plan_was_made(team):
    ann, pid, task, m = team['ann'], team['pid'], team['task'], team['bob_m']
    states = [full(ann, pid)]
    task = timed(ann, task); states.append(full(ann, pid))
    a = ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=6))['assignment']; states.append(full(ann, pid))
    ann.ok('patch', f"/api/assignments/{a['id']}", dict(version=a['version'], weeks=9, is_lead=True)); states.append(full(ann, pid))
    t = item(ann, pid, task['id'])
    ann.ok('patch', f"/api/items/{t['id']}", dict(version=t['version'], title='Renamed', description='Why')); states.append(full(ann, pid))
    v = ann.ok('get', f'/api/proposals/{pid}')['proposal']
    ann.ok('patch', f'/api/proposals/{pid}', dict(version=v['version'], travel=dict(v['travel'], airfare=[900, 0, 0]))); states.append(full(ann, pid))
    line = ann.ok('post', f'/api/proposals/{pid}/nonlabor', dict(item='Publications', amounts=[1000, 0, 0]))['line']; states.append(full(ann, pid))
    ann.ok('delete', f"/api/nonlabor/{line['id']}"); states.append(full(ann, pid))
    words = ['deleting the budget line "Publications"', 'adding the budget line "Publications"', 'changing the travel costs', 'renaming "Task A1"',
             'changing the task lead of "Task A1"', 'putting Bob Bobson on "Task A1"', 'drawing the bar of "Task A1"']
    for k, w in enumerate(words):
        undo(ann, pid, done=w)
        assert full(ann, pid) == states[-2 - k], w
    for k, w in enumerate(reversed(words)):                          # and all the way forward again (titles as they are now)
        undo(ann, pid, 'redo', done=w.replace('"Task A1"', '"Renamed"') if k > 3 else w)
        assert full(ann, pid) == states[k + 1], w
    ann.no('post', f'/api/proposals/{pid}/redo', code='nothing')
    for _ in words: undo(ann, pid)
    undo(ann, pid, done='adding "Task A1"'); undo(ann, pid, done='adding "Goal A"')
    undo(ann, pid, done='adding Bob Bobson to the team')
    ann.no('post', f'/api/proposals/{pid}/undo', code='nothing')     # making the work plan itself is not undone
    assert you(ann, pid)['undo'] is None and ann.ok('get', f'/api/proposals/{pid}')['items'] == []


def test_undoing_a_delete_brings_everything_back_under_its_own_ids(team):
    ann, pid, goal, task, m = team['ann'], team['pid'], team['goal'], team['task'], team['bob_m']
    t2 = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Task A2', parent_id=goal['id']))['item']
    sub = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id']))['item']
    sub = timed(ann, sub)
    ann.ok('post', f"/api/items/{sub['id']}/assignments", dict(member_id=m['id'], weeks=3, is_lead=True))
    ann.ok('post', f"/api/items/{sub['id']}/assignments", dict(is_team=True, weeks=1))
    before = full(ann, pid)
    ann.ok('delete', f"/api/items/{task['id']}?confirm=1")
    assert item(ann, pid, t2['id'])['position'] == 0
    assert you(ann, pid)['undo'] == 'deleting "Task A1"'
    undo(ann, pid)
    assert full(ann, pid) == before                                  # ids, positions, effort and leads
    new = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='New', parent_id=goal['id']))['item']
    ann.ok('delete', f"/api/items/{new['id']}?confirm=1")
    newer = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Newer', parent_id=goal['id']))['item']
    assert newer['id'] > new['id']                                   # a number is never used twice


def test_undoing_a_move_puts_the_item_back_in_its_place(team):
    ann, pid, goal, task = team['ann'], team['pid'], team['goal'], team['task']
    g2 = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Goal B'))['item']
    t2 = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Task A2', parent_id=goal['id']))['item']
    ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Task B1', parent_id=g2['id']))
    before = full(ann, pid)
    task = item(ann, pid, task['id'])
    ann.ok('patch', f"/api/items/{task['id']}", dict(version=task['version'], parent_id=g2['id'], position=1))
    assert you(ann, pid)['undo'] == 'moving "Task A1"'
    undo(ann, pid)
    assert full(ann, pid) == before
    t2 = item(ann, pid, t2['id'])
    ann.ok('patch', f"/api/items/{t2['id']}", dict(version=t2['version'], position=0))       # within its task category
    undo(ann, pid)
    assert full(ann, pid) == before


def test_undoing_a_new_subtask_gives_its_task_back_its_effort(team):
    ann, pid, task, m = team['ann'], team['pid'], timed(team['ann'], team['task']), team['bob_m']
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=6, is_lead=True))
    before = full(ann, pid)
    ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub', parent_id=task['id'], effort_destination='new_child'))
    assert you(ann, pid)['undo'] == 'adding "Sub"'
    undo(ann, pid)
    assert full(ann, pid) == before


def test_undoing_team_changes_puts_labels_back(team):
    ann, pid, p, task = team['ann'], team['pid'], team['people'], timed(team['ann'], team['task'])
    cat = ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=p['cat']['id'], role='co-I'))['member']   # Catson: co-I 2
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=team['bob_m']['id'], weeks=4))
    before = full(ann, pid)
    labels = lambda: sorted(m['short_id'] for m in ann.ok('get', f'/api/proposals/{pid}')['members'])
    assert labels() == ['PI', 'co-I 1', 'co-I 2']
    ann.ok('delete', f"/api/members/{team['bob_m']['id']}?confirm=1")                  # Catson becomes co-I 1
    assert labels() == ['PI', 'co-I 1'] and you(ann, pid)['undo'] == 'taking Bob Bobson off the team'
    undo(ann, pid)
    assert full(ann, pid) == before
    cat = next(m for m in ann.ok('get', f'/api/proposals/{pid}')['members'] if m['id'] == cat['id'])
    ann.ok('patch', f"/api/members/{cat['id']}", dict(version=cat['version'], role='Sci-PI'))
    assert you(ann, pid)['undo'] == "changing Cat Catson's role"
    undo(ann, pid)
    assert full(ann, pid) == before


def test_a_profile_changed_in_a_work_plan_is_undone_there(team):
    ann, pid, p = team['ann'], team['pid'], team['people']
    ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=p['cat']['id'], role='co-I'))
    before = full(ann, pid)
    bob = ann.ok('get', f"/api/proposals/{pid}")['members']
    ann.ok('patch', f"/api/people/{p['bob']['id']}", dict(version=p['bob']['version'], last='Zed', made_in=pid))   # renumbers the co-Is
    assert you(ann, pid)['undo'] == "changing Bob Zed's profile"
    undo(ann, pid)
    assert full(ann, pid) == before and ann.ok('get', '/api/people')['people'][1]['last'] == 'Bobson'


def test_undo_skips_what_someone_else_changed_since(team):
    ann, bob, pid, task = team['ann'], team['bob'], team['pid'], team['task']
    t2 = ann.ok('post', f"/api/proposals/{pid}/items", dict(title='Task A2', parent_id=team['goal']['id']))['item']
    task = timed(ann, task, (1, 1, 1, 10))
    task = timed(ann, task, (1, 1, 1, 20))
    timed(bob, task, (1, 1, 1, 30))                                  # Bob moves the same bar
    assert you(bob, pid)['undo'] == 'changing the bar of "Task A1"'
    out = ann.no('post', f'/api/proposals/{pid}/undo', code='stuck')
    assert 'Bob Bobson changed it since' in out['message'] and 'Undo again' in out['message']
    assert item(ann, pid, task['id'])['end_week'] == 30              # Bob's change stays
    out = ann.no('post', f'/api/proposals/{pid}/undo', code='stuck')    # her first bar: Bob's change is still on it
    assert 'Bob Bobson changed it since' in out['message']
    undo(ann, pid, done='adding "Task A2"')                          # her change before those goes back
    assert all(i['id'] != t2['id'] for i in ann.ok('get', f'/api/proposals/{pid}')['items'])


def test_undo_never_breaks_the_plan_s_rules(team):
    ann, bob, pid, task, m = team['ann'], team['bob'], team['pid'], timed(team['ann'], team['task']), team['bob_m']
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=6))
    ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub 1', parent_id=task['id'], effort_destination='new_child'))
    bob.ok('post', f'/api/proposals/{pid}/items', dict(title='Sub 2', parent_id=task['id']))          # Bob adds another subtask
    out = ann.no('post', f'/api/proposals/{pid}/undo', code='stuck')    # her effort would go back on a task with subtasks
    assert '"Task A1" would be a task with subtasks with its own' in out['message']
    assert sorted(i['title'] for i in ann.ok('get', f'/api/proposals/{pid}')['items']) == ['Goal A', 'Sub 1', 'Sub 2', 'Task A1']
    t = ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Task A2', parent_id=team['goal']['id']))['item']
    bob.ok('post', f'/api/proposals/{pid}/items', dict(title='Under it', parent_id=t['id']))
    out = ann.no('post', f'/api/proposals/{pid}/undo', code='stuck')    # Bob put something under her new task
    assert 'Bob Bobson changed it since' in out['message']


def test_undo_is_your_own_and_a_new_change_ends_redo(team):
    ann, bob, pid, task = team['ann'], team['bob'], team['pid'], team['task']
    timed(ann, task)
    bob.no('post', f'/api/proposals/{pid}/undo', code='nothing')     # Bob has nothing of his own to undo
    team['dan'].no('post', f'/api/proposals/{pid}/undo', code='not_found')
    undo(ann, pid)
    assert you(ann, pid)['redo'] == 'drawing the bar of "Task A1"'
    ann.ok('post', f'/api/proposals/{pid}/items', dict(title='Goal B'))
    assert you(ann, pid)['redo'] is None
    ann.no('post', f'/api/proposals/{pid}/redo', code='nothing')


def test_undoing_a_restore_and_the_changes_before_it(team):
    ann, pid, task, m = team['ann'], team['pid'], timed(team['ann'], team['task']), team['bob_m']
    snap = ann.ok('post', f'/api/proposals/{pid}/snapshots', dict(name='early'))['snapshot']
    first = full(ann, pid)
    ann.ok('post', f"/api/items/{task['id']}/assignments", dict(member_id=m['id'], weeks=6, is_lead=True))
    ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=team['people']['cat']['id'], role='co-I'))
    ann.ok('delete', f"/api/items/{team['goal']['id']}?confirm=1")
    later = full(ann, pid)
    ann.ok('post', f"/api/snapshots/{snap['id']}/restore")
    assert full(ann, pid) == first                                   # a restore keeps the rows' own numbers
    assert you(ann, pid)['undo'] == 'restoring the snapshot "early"'
    undo(ann, pid)
    assert full(ann, pid) == later
    undo(ann, pid, done='deleting "Goal A"'); undo(ann, pid, done='adding Cat Catson to the team')
    undo(ann, pid, done='putting Bob Bobson on "Task A1"')
    assert full(ann, pid) == first


def test_undo_needs_the_same_rights_as_the_change(team):
    ann, eve, pid, p = team['ann'], team['eve'], team['pid'], team['people']
    ann.ok('post', f"/api/proposals/{pid}/members", dict(person_id=p['cat']['id'], role='co-I', is_lead=True))
    me = next(m for m in eve.ok('get', f'/api/proposals/{pid}')['members'] if m['person_id'] == p['ann']['id'])
    eve.ok('patch', f"/api/members/{me['id']}", dict(version=me['version'], is_lead=False))   # Ann is no longer a full editor
    ann.no('post', f'/api/proposals/{pid}/undo', code='refused')
    assert you(ann, pid)['undo'] == 'adding Cat Catson to the team'  # still there, if she becomes a full editor again
