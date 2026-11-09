"""WorPT storage: one SQLite database, with the permission rules and work-plan rules applied on every change.

Every editable row carries a `version`; an update must quote the version it started from, otherwise it is
refused as a conflict and the current row is returned (nothing is overwritten silently). Every change is
written to the `history` table (who, when, the row before and after), so anything can be restored.

Who may do what (agreed 5 November 2026):
  * admin (ADMIN_EMAILS) and core (CORE_MEMBERS) may create proposals; access-code users may not.
  * admins see every proposal; everyone else sees the proposals they are on.
  * anyone on a proposal may edit its plan (goals, tasks, effort, budget and travel, including each member's trips);
    leads and admins manage its team and leads.
  * a proposal always keeps at least one lead; leads and admins may delete it, after typing its title.
  * a profile may be edited by its owner, leads of any proposal the person is on, core members and admins.
"""
import contextlib, datetime, json, re, secrets, sqlite3
from .tables import numbered_roles
from .model import Person, Assignment, Item, Proposal, TravelCosts, NonlaborItem
from .effort import WEEKS_PER_YEAR, WEEKS_PER_QUARTER

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE, first TEXT NOT NULL DEFAULT '', middle TEXT NOT NULL DEFAULT '',
  last TEXT NOT NULL DEFAULT '', prefix TEXT NOT NULL DEFAULT '', suffix TEXT NOT NULL DEFAULT '',
  institution TEXT NOT NULL DEFAULT '', position TEXT NOT NULL DEFAULT '', us INTEGER NOT NULL DEFAULT 1,
  expertise TEXT NOT NULL DEFAULT '', pronoun TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, program TEXT NOT NULL DEFAULT '', n_years INTEGER NOT NULL DEFAULT 3,
  rounding TEXT NOT NULL DEFAULT 'nearest', latex_subdir TEXT NOT NULL DEFAULT 'do_NOT_manually_edit',
  travel TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, created_by TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  person_id INTEGER NOT NULL REFERENCES people(id), short_id TEXT NOT NULL, role TEXT NOT NULL,
  is_lead INTEGER NOT NULL DEFAULT 0, fte_accuracy REAL, bio_summary TEXT NOT NULL DEFAULT '',
  task_summary TEXT NOT NULL DEFAULT '', trips TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (proposal_id, short_id), UNIQUE (proposal_id, person_id));
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES items(id) ON DELETE CASCADE, position INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '',
  start_year INTEGER, start_week INTEGER, end_year INTEGER, end_week INTEGER, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS assignments (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  member_id INTEGER REFERENCES members(id) ON DELETE CASCADE, is_team INTEGER NOT NULL DEFAULT 0,
  is_lead INTEGER NOT NULL DEFAULT 0, weeks REAL NOT NULL DEFAULT 0, unfunded REAL NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS nonlabor (
  id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, item TEXT NOT NULL DEFAULT '', amounts TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, user TEXT NOT NULL, proposal_id TEXT, tbl TEXT NOT NULL,
  row_id TEXT NOT NULL, action TEXT NOT NULL, before TEXT, after TEXT);
CREATE INDEX IF NOT EXISTS history_proposal ON history (proposal_id, id);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  at TEXT NOT NULL, user TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS snapshots_proposal ON snapshots (proposal_id, id);
"""
LEVELS = ('goal', 'task', 'subtask')
TRAVEL_DEFAULT = dict(airfare=[0, 0, 0], perdiem=[0, 0, 0], conference=[0, 0, 0], ground=[0, 0, 0], days=[0, 0])
EDITABLE = dict(
    people=('email', 'first', 'middle', 'last', 'prefix', 'suffix', 'institution', 'position', 'us', 'expertise', 'pronoun'),
    proposals=('title', 'program', 'n_years', 'rounding', 'travel'),
    members=('role', 'is_lead', 'fte_accuracy', 'bio_summary', 'task_summary', 'trips'),     # short_id follows the role
    items=('title', 'short_title', 'description', 'start_year', 'start_week', 'end_year', 'end_week'),
    assignments=('member_id', 'is_team', 'is_lead', 'weeks', 'unfunded'),
    nonlabor=('item', 'amounts'))
JSON_COLS = {'travel', 'trips', 'amounts'}
DERIVED = dict(members=('short_id',))           # set by the server itself, never taken from a request
PRONOUNS = ('', 'he', 'she', 'they')
AUTO_SNAPSHOT_DAYS = 60          # automatic snapshots are kept this long; named ones until someone deletes them
# Columns added after the first release, so an existing database gains them when the server starts.
ADDED_COLUMNS = [('people', 'expertise', "TEXT NOT NULL DEFAULT ''"), ('people', 'pronoun', "TEXT NOT NULL DEFAULT ''"),
                 ('items', 'start_week', 'INTEGER'), ('items', 'end_week', 'INTEGER'), ('items', 'short_title', "TEXT NOT NULL DEFAULT ''"),
                 ('items', 'description', "TEXT NOT NULL DEFAULT ''")]   # a note on what the item stands for; shown in the dashboard only
TIMELINE = ('start_year', 'start_week', 'end_year', 'end_week')


def weeks_from_quarters(item):
    """An item's timeline in weeks, from one saved in quarters (before November 2026): quarter q is weeks 13q-12 to 13q."""
    if 'start_week' in item: return item
    q0, q1 = item.pop('start_q', None), item.pop('end_q', None)
    return dict(item, start_week=None if q0 is None else (q0 - 1) * WEEKS_PER_QUARTER + 1, end_week=None if q1 is None else q1 * WEEKS_PER_QUARTER)
ROLE_WORDS = {'co-i': 'co-I', 'coi': 'co-I', 'coll': 'collab'}       # how a numbered role's label starts; others keep their code (pd, gst, ust)
# Roles WorPT numbers by itself (co-I(1), co-I(2)...): what may be typed or chosen, and the code it is stored as.
NUMBERED_ROLES = {'co-i': 'co-I', 'coi': 'co-I', 'co-investigator': 'co-I', 'coll': 'coll', 'collab': 'coll', 'collaborator': 'coll',
                  'gst': 'gst', 'grad': 'gst', 'grad student': 'gst', 'graduate student': 'gst', 'pd': 'pd', 'postdoc': 'pd',
                  'ust': 'ust', 'undergrad': 'ust', 'undergrad student': 'ust', 'undergraduate': 'ust', 'undergraduate student': 'ust'}
SINGLE_ROLES = {'pi': 'PI', 'sci-pi': 'Sci-PI', 'admin-pi': 'Admin-PI'}          # one person each, no number


def canonical_role(text):
    """'co-I', 'Co-I(3)', 'collaborator' -> 'co-I(0)', 'coll(0)' (the number is set by Store.renumber_roles); 'pi' -> 'PI';
    any other role as typed."""
    t = (text or '').strip()
    m = re.fullmatch(r'(.+?)\s*\(\s*\d+\s*\)', t)
    base = (m.group(1) if m else t).strip()
    if base.lower() in NUMBERED_ROLES: return NUMBERED_ROLES[base.lower()] + '(0)'
    return SINGLE_ROLES.get(base.lower(), t)


def role_label(role):
    """A member's label, which also stands for them in the tables, comes from their role and never their name, so
    proposals can stay anonymous, and is kept short for the tables: PI -> PI, co-I(1) -> co-I 1, coll(2) -> collab 2,
    pd(1) -> pd 1, gst(1) -> gst 1, ust(1) -> ust 1."""
    m = re.fullmatch(r'\s*([A-Za-z][A-Za-z-]*)\s*\(\s*(\d+)\s*\)\s*', role or '')
    return f'{ROLE_WORDS.get(m.group(1).lower(), m.group(1))} {m.group(2)}' if m else (role or '').strip()


class WorptError(Exception):
    """A refusal with a plain explanation; `code` lets the dashboard react (e.g. 'conflict', 'parent_has_effort')."""
    def __init__(self, message, code='refused', **extra):
        super().__init__(message); self.message, self.code, self.extra = message, code, extra


class User:
    def __init__(self, email, access):
        self.email, self.access = (email or '').strip().lower(), access   # access: 'admin', 'core' or 'code'
    admin = property(lambda s: s.access == 'admin')
    core = property(lambda s: s.access in ('admin', 'core'))


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)
            for table, column, kind in ADDED_COLUMNS:
                if column not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
            # timelines are kept in weeks (from November 2026): convert ones kept in quarters, exactly, then drop the quarters
            if 'start_q' in {r['name'] for r in db.execute('PRAGMA table_info(items)')}:
                db.execute(f'UPDATE items SET start_week = (start_q - 1) * {WEEKS_PER_QUARTER} + 1 WHERE start_q IS NOT NULL AND start_week IS NULL')
                db.execute(f'UPDATE items SET end_week = end_q * {WEEKS_PER_QUARTER} WHERE end_q IS NOT NULL AND end_week IS NULL')
                db.execute('ALTER TABLE items DROP COLUMN start_q'); db.execute('ALTER TABLE items DROP COLUMN end_q')
            # roles are numbered by WorPT, and labels come from roles (from November 2026): bring older members in line
            for (pid,) in db.execute('SELECT DISTINCT proposal_id FROM members').fetchall():
                self.renumber_roles(db, User('worpt-server', 'admin'), pid)

    @contextlib.contextmanager
    def connect(self):
        """One transaction: everything inside is saved together, or (on any refusal or error) nothing is."""
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON'); db.execute('PRAGMA journal_mode = WAL')
        try:
            with db: yield db
        finally:
            db.close()

    # ------------------------------------------------ small helpers
    @staticmethod
    def row(r):
        if r is None: return None
        d = dict(r)
        for k in JSON_COLS & d.keys(): d[k] = json.loads(d[k])
        for k in ('us', 'is_lead', 'is_team'):
            if k in d: d[k] = bool(d[k])
        return d

    def one(self, db, sql, *args):
        return self.row(db.execute(sql, args).fetchone())

    def all(self, db, sql, *args):
        return [self.row(r) for r in db.execute(sql, args).fetchall()]

    def log(self, db, user, proposal_id, tbl, row_id, action, before=None, after=None):
        db.execute('INSERT INTO history (at, user, proposal_id, tbl, row_id, action, before, after) VALUES (?,?,?,?,?,?,?,?)',
                   (now(), user.email, proposal_id, tbl, str(row_id), action,
                    None if before is None else json.dumps(before), None if after is None else json.dumps(after)))

    def get(self, db, tbl, rid, what):
        r = self.one(db, f'SELECT * FROM {tbl} WHERE id = ?', rid)
        if r is None: raise WorptError(f'That {what} no longer exists (someone may have deleted it).', 'not_found')
        return r

    def update_row(self, db, user, tbl, rid, version, fields, proposal_id, what):
        self.daily_snapshot(db, user, proposal_id)
        before = self.get(db, tbl, rid, what)
        if version is None or int(version) != before['version']:
            raise WorptError(f'Someone else changed this {what} after you opened it. Both versions are shown so you can choose.',
                             'conflict', current=before)
        fields = {k: v for k, v in fields.items() if k in EDITABLE[tbl] + DERIVED.get(tbl, ())}
        if not fields: return before
        sets = ', '.join(f'{k} = ?' for k in fields)
        vals = [json.dumps(v) if k in JSON_COLS else v for k, v in fields.items()]
        db.execute(f'UPDATE {tbl} SET {sets}, version = version + 1 WHERE id = ?', (*vals, rid))
        after = self.get(db, tbl, rid, what)
        self.log(db, user, proposal_id, tbl, rid, 'update', before, after)
        return after

    def insert_row(self, db, user, tbl, values, proposal_id):
        self.daily_snapshot(db, user, proposal_id)
        cols = ', '.join(values)
        vals = [json.dumps(v) if k in JSON_COLS else v for k, v in values.items()]
        cur = db.execute(f'INSERT INTO {tbl} ({cols}) VALUES ({",".join("?" * len(values))})', vals)
        rid = values.get('id', cur.lastrowid)
        after = self.get(db, tbl, rid, tbl)
        self.log(db, user, proposal_id, tbl, rid, 'insert', None, after)
        return after

    def delete_row(self, db, user, tbl, rid, proposal_id, what):
        self.daily_snapshot(db, user, proposal_id)
        before = self.get(db, tbl, rid, what)
        db.execute(f'DELETE FROM {tbl} WHERE id = ?', (rid,))
        self.log(db, user, proposal_id, tbl, rid, 'delete', before, None)
        return before

    # ------------------------------------------------ who is who
    def person_for(self, db, user):
        return self.one(db, 'SELECT * FROM people WHERE email = ?', user.email) if user.email else None

    def membership(self, db, user, proposal_id):
        me = self.person_for(db, user)
        return me and self.one(db, 'SELECT * FROM members WHERE proposal_id = ? AND person_id = ?', proposal_id, me['id'])

    def proposal(self, db, user, proposal_id, need='view'):
        p = self.one(db, 'SELECT * FROM proposals WHERE id = ?', proposal_id)
        m = p and self.membership(db, user, proposal_id)
        if p is None or not (user.admin or m):
            raise WorptError('That work plan does not exist, or you are not on its team.', 'not_found')
        if need == 'team' and not (user.admin or m['is_lead']):
            raise WorptError("Only this work plan's full editors (or an admin) can change its team and full editors.")
        return p

    def can_edit_person(self, db, user, person_id):
        if user.core: return True
        me = self.person_for(db, user)
        if me and me['id'] == person_id: return True
        return bool(me and db.execute(
            'SELECT 1 FROM members l JOIN members m ON m.proposal_id = l.proposal_id '
            'WHERE l.person_id = ? AND l.is_lead = 1 AND m.person_id = ?', (me['id'], person_id)).fetchone())

    def is_any_lead(self, db, user):
        me = self.person_for(db, user)
        return bool(me and db.execute('SELECT 1 FROM members WHERE person_id = ? AND is_lead = 1', (me['id'],)).fetchone())

    # ------------------------------------------------ people (profiles)
    @staticmethod
    def clean_person(fields):
        f = dict(fields)
        if 'email' in f: f['email'] = (f['email'] or '').strip().lower() or None
        if 'us' in f: f['us'] = 1 if f['us'] else 0
        for k in ('first', 'middle', 'last', 'prefix', 'suffix', 'institution', 'position', 'expertise', 'pronoun'):
            if k in f: f[k] = (f[k] or '').strip()
        if 'pronoun' in f:
            f['pronoun'] = f['pronoun'].lower()
            if f['pronoun'] not in PRONOUNS: raise WorptError('The pronoun is he, she, they, or left blank.', 'invalid')
        return f

    def check_email_free(self, db, email, person_id=None):
        if email:
            other = self.one(db, 'SELECT * FROM people WHERE email = ? AND id != ?', email, person_id or -1)
            if other: raise WorptError(f'{email} already belongs to the profile of {other["first"]} {other["last"]}; '
                                       'each Google email can have only one profile.', 'duplicate_email', existing=other)

    def create_person(self, user, fields):
        with self.connect() as db:
            if not (user.core or self.is_any_lead(db, user)):
                raise WorptError('Only admins, core members and full editors of a work plan can add people.')
            f = self.clean_person({k: v for k, v in fields.items() if k in EDITABLE['people']})
            if not f.get('last'): raise WorptError('A profile needs at least a last name.', 'missing')
            self.check_email_free(db, f.get('email'))
            return self.insert_row(db, user, 'people', f, None)

    def update_person(self, user, person_id, version, fields):
        with self.connect() as db:
            if not self.can_edit_person(db, user, person_id):
                raise WorptError("You can edit your own profile, or the profiles of people on work plans where you are a full editor.")
            f = self.clean_person({k: v for k, v in fields.items() if k in EDITABLE['people']})
            if 'email' in f: self.check_email_free(db, f['email'], person_id)
            p = self.update_row(db, user, 'people', person_id, version, f, None, 'profile')
            for m in self.all(db, 'SELECT * FROM members WHERE person_id = ?', person_id):
                if not p['us'] and canonical_role(m['role']) != 'coll(0)':     # non-US means collaborator, on every work plan
                    save = lambda role, m=m: self.update_row(db, user, 'members', m['id'], m['version'], dict(role=role, short_id=role_label(role)),
                                                             m['proposal_id'], 'team member')
                    self.renumber_roles(db, user, m['proposal_id'], dict(id=m['id'], role='coll(0)', last=p['last']), save)
                else: self.renumber_roles(db, user, m['proposal_id'])            # numbers follow last names, which may have changed
            return p

    def my_profile(self, user):
        with self.connect() as db: return self.person_for(db, user)

    def people(self, user, query=''):
        with self.connect() as db:
            if not (user.core or self.is_any_lead(db, user)):
                me = self.person_for(db, user)
                return [me] if me else []
            q = f'%{query.strip().lower()}%'
            return self.all(db, "SELECT * FROM people WHERE lower(first || ' ' || last || ' ' || coalesce(email, '')) LIKE ? "
                            "ORDER BY last, first", q)

    # ------------------------------------------------ proposals
    def create_proposal(self, user, title, program='', n_years=3, leads=()):
        if not user.core: raise WorptError('Only admins and core members can create work plans.')
        title = (title or '').strip()
        if not title: raise WorptError('A work plan needs a title.', 'missing')
        n_years = self.check_years(n_years)
        if not leads: raise WorptError('Name at least one full editor for the new work plan.', 'missing')
        with self.connect() as db:
            pid = secrets.token_urlsafe(9)
            p = self.insert_row(db, user, 'proposals', dict(id=pid, title=title, program=(program or '').strip(), n_years=n_years,
                                travel=TRAVEL_DEFAULT, created_at=now(), created_by=user.email), pid)
            for lead in leads:
                self.add_member_db(db, user, pid, dict(lead, is_lead=True))
            return p

    @staticmethod
    def check_years(n):
        try: n = int(n)
        except (TypeError, ValueError): raise WorptError('The number of years must be a whole number.', 'invalid')
        if n < 1: raise WorptError('A work plan needs at least one year.', 'invalid')
        return n

    LIST = ("SELECT p.*, (SELECT max(at) FROM history h WHERE h.proposal_id = p.id) AS last_changed_at, "
            "(SELECT group_concat(trim(pe.first || ' ' || pe.last), ', ') FROM members l JOIN people pe ON pe.id = l.person_id "
            "WHERE l.proposal_id = p.id AND l.is_lead = 1) AS leads FROM proposals p ")

    def list_proposals(self, user):
        with self.connect() as db:
            if user.admin: return self.all(db, self.LIST + 'ORDER BY last_changed_at DESC')
            me = self.person_for(db, user)
            return self.all(db, self.LIST + 'JOIN members m ON m.proposal_id = p.id WHERE m.person_id = ? '
                            'ORDER BY last_changed_at DESC', me['id']) if me else []

    @staticmethod
    def last_change(db, proposal_id):
        return db.execute('SELECT coalesce(max(id), 0) FROM history WHERE proposal_id = ?', (proposal_id,)).fetchone()[0]

    def changed(self, user, proposal_id):
        """The number of the proposal's newest recorded change: the dashboard reloads only when it grows."""
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            return self.last_change(db, proposal_id)

    def update_proposal(self, user, proposal_id, version, fields):
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            f = dict(fields)
            if 'n_years' in f: f['n_years'] = self.check_years(f['n_years'])
            if 'title' in f and not (f['title'] or '').strip(): raise WorptError('A work plan needs a title.', 'missing')
            if 'rounding' in f and f['rounding'] not in ('nearest', 'up'): raise WorptError('Rounding is "nearest" or "up".', 'invalid')
            old = self.one(db, 'SELECT n_years, version FROM proposals WHERE id = ?', proposal_id)
            if 'n_years' in f and f['n_years'] != old['n_years'] and version is not None and int(version) == old['version']:
                self.snapshot(db, user, proposal_id, 'before', f'Before changing the number of years from {old["n_years"]} to {f["n_years"]}')
            return self.update_row(db, user, 'proposals', proposal_id, version, f, proposal_id, 'proposal')

    def delete_proposal(self, user, proposal_id, confirm_title):
        with self.connect() as db:
            p = self.proposal(db, user, proposal_id, need='team')
            if (confirm_title or '').strip() != p['title'].strip():
                raise WorptError('To delete this work plan, type its title exactly as it appears.', 'confirm_title')
            snapshot = self.export(db, proposal_id)
            db.execute('DELETE FROM proposals WHERE id = ?', (proposal_id,))
            self.log(db, user, proposal_id, 'proposal_snapshot', proposal_id, 'delete', snapshot, None)
            return {'deleted': p['title']}

    # ------------------------------------------------ team members
    def renumber_roles(self, db, user, proposal_id, edit=None, write=None):
        """Number the numbered roles 1, 2, ... within each kind, in the tables' order (by kind of role, then by last name;
        see tables.team_order), so the numbers never leave gaps; labels follow.
        edit: a member being added (id None) or changed, as dict(id, role, last); write(role) then saves that member with
        its final role, between freeing the labels that change and giving the others theirs, so labels never clash."""
        rows = self.all(db, 'SELECT m.*, p.last FROM members m JOIN people p ON p.id = m.person_id WHERE m.proposal_id = ? ORDER BY m.id', proposal_id)
        if edit is not None:
            rows = [r for r in rows if r['id'] != edit['id']] + [dict(edit, short_id=None)]
        final = numbered_roles([dict(r, role=canonical_role(r['role']), was=r['role']) for r in rows])
        mine = next((new for r, new in final if edit is not None and r['id'] == edit['id']), None)
        others = [(r, new) for r, new in final if (edit is None or r['id'] != edit['id']) and (new != r['was'] or role_label(new) != r['short_id'])]
        for r, _ in others:                                             # free the labels that change, so two can swap
            db.execute('UPDATE members SET short_id = ? WHERE id = ?', (f'~{r["id"]}', r['id']))
        out = write(mine) if write else None
        for r, new in others:
            before = self.get(db, 'members', r['id'], 'team member')
            db.execute('UPDATE members SET role = ?, short_id = ?, version = version + 1 WHERE id = ?', (new, role_label(new), r['id']))
            self.log(db, user, proposal_id, 'members', r['id'], 'update', dict(before, short_id=r['short_id']),
                     self.get(db, 'members', r['id'], 'team member'))
        return out

    def check_member_fields(self, db, proposal_id, f, member_id=None, person=None):
        f.pop('short_id', None)                                         # the label always comes from the role
        if 'role' in f:
            if not (f['role'] or '').strip(): raise WorptError('Each team member needs a role (e.g. PI, co-I, Collaborator).', 'missing')
            f['role'] = canonical_role(f['role'])
            if person is not None and not person['us']: f['role'] = 'coll(0)'   # non-US institution: always a collaborator
            if not f['role'].endswith('(0)'):                            # numbered roles get their number from renumber_roles()
                f['short_id'] = role_label(f['role'])
                if f['short_id'].lower() == 'team': raise WorptError('"team" stands for "everyone not named"; choose another role.', 'invalid')
                other = self.one(db, 'SELECT id, role FROM members WHERE proposal_id = ? AND lower(short_id) = lower(?) AND id != ?',
                                 proposal_id, f['short_id'], member_id or -1)
                if other: raise WorptError(f'Someone on this work plan is already {other["role"]}; only one person can have that role.', 'duplicate')
        if 'is_lead' in f: f['is_lead'] = 1 if f['is_lead'] else 0
        return f

    def add_member_db(self, db, user, proposal_id, fields):
        person = self.get(db, 'people', fields.get('person_id'), 'profile')
        if self.one(db, 'SELECT id FROM members WHERE proposal_id = ? AND person_id = ?', proposal_id, person['id']):
            raise WorptError(f'{person["first"]} {person["last"]} is already on this work plan.', 'duplicate')
        f = {k: v for k, v in fields.items() if k in EDITABLE['members']}
        f.setdefault('role', '')
        f = self.check_member_fields(db, proposal_id, f, person=person)
        add = lambda role: self.insert_row(db, user, 'members', dict(f, role=role, short_id=role_label(role), proposal_id=proposal_id,
                                                                     person_id=person['id']), proposal_id)
        m = self.renumber_roles(db, user, proposal_id, dict(id=None, role=f['role'], last=person['last']), add)
        return self.get(db, 'members', m['id'], 'team member')

    def add_member(self, user, proposal_id, fields):
        with self.connect() as db:
            self.proposal(db, user, proposal_id, need='team')
            return self.add_member_db(db, user, proposal_id, fields)

    def update_member(self, user, member_id, version, fields):
        with self.connect() as db:
            m = self.get(db, 'members', member_id, 'team member')
            # trips are part of the budget, which anyone on the proposal may edit; everything else about a member is the team's
            self.proposal(db, user, m['proposal_id'], need='view' if set(fields) <= {'trips'} else 'team')
            person = self.get(db, 'people', m['person_id'], 'profile')
            f = self.check_member_fields(db, m['proposal_id'], dict(fields), member_id, person)
            if m['is_lead'] and 'is_lead' in f and not f['is_lead']: self.keep_a_lead(db, m)
            save = lambda role: self.update_row(db, user, 'members', member_id, version,
                                                dict(f, **({} if role is None else dict(role=role, short_id=role_label(role)))), m['proposal_id'], 'team member')
            if 'role' not in f: return save(None)
            return self.renumber_roles(db, user, m['proposal_id'], dict(id=member_id, role=f['role'], last=person['last']), save)

    def keep_a_lead(self, db, m):
        n = db.execute('SELECT count(*) FROM members WHERE proposal_id = ? AND is_lead = 1', (m['proposal_id'],)).fetchone()[0]
        if n <= 1: raise WorptError('A work plan must always have at least one full editor. Make someone else a full editor first.', 'last_lead')

    def remove_member(self, user, member_id, confirm=False):
        with self.connect() as db:
            m = self.get(db, 'members', member_id, 'team member')
            self.proposal(db, user, m['proposal_id'], need='team')
            if m['is_lead']: self.keep_a_lead(db, m)
            work = self.all(db, 'SELECT * FROM assignments WHERE member_id = ?', member_id)
            if not confirm:
                return {'needs_confirmation': True, 'assignments': len(work),
                        'message': f'Removing {m["short_id"]} also removes their {len(work)} assignment(s).'}
            person = self.get(db, 'people', m['person_id'], 'profile')
            self.snapshot(db, user, m['proposal_id'], 'before', f'Before taking {person["first"]} {person["last"]} ({m["short_id"]}) off the team')
            for a in work: self.delete_row(db, user, 'assignments', a['id'], m['proposal_id'], 'assignment')
            gone = self.delete_row(db, user, 'members', member_id, m['proposal_id'], 'team member')
            self.renumber_roles(db, user, m['proposal_id'])                      # close the gap (co-I(2) becomes co-I(1)...)
            return gone

    # ------------------------------------------------ goals, tasks, subtasks
    def depth(self, db, item_id):
        d = 0
        while True:
            parent = db.execute('SELECT parent_id FROM items WHERE id = ?', (item_id,)).fetchone()[0]
            if parent is None: return d
            item_id, d = parent, d + 1

    def height(self, db, item_id):
        kids = [r[0] for r in db.execute('SELECT id FROM items WHERE parent_id = ?', (item_id,))]
        return 1 + max((self.height(db, k) for k in kids), default=0)

    def has_children(self, db, item_id):
        return bool(db.execute('SELECT 1 FROM items WHERE parent_id = ?', (item_id,)).fetchone())

    def renumber(self, db, proposal_id, parent_id, skip=None):
        """Number the items under parent_id 0, 1, 2… in their order, leaving out item `skip` (one being moved)."""
        ids = [r[0] for r in db.execute('SELECT id FROM items WHERE proposal_id = ? AND parent_id IS ? AND id IS NOT ? ORDER BY position, id',
                                        (proposal_id, parent_id, skip))]
        db.executemany('UPDATE items SET position = ? WHERE id = ?', [(k, i) for k, i in enumerate(ids)])

    def place(self, db, proposal_id, parent_id, position, skip=None):
        """Make room at `position` (0 = first; None = last) among the items under parent_id, other than item `skip`."""
        n = db.execute('SELECT count(*) FROM items WHERE proposal_id = ? AND parent_id IS ? AND id IS NOT ?', (proposal_id, parent_id, skip)).fetchone()[0]
        position = n if position is None else max(0, min(int(position), n))
        db.execute('UPDATE items SET position = position + 1 WHERE proposal_id = ? AND parent_id IS ? AND id IS NOT ? AND position >= ?',
                   (proposal_id, parent_id, skip, position))
        return position

    def check_new_parent(self, db, user, proposal_id, parent_id, subtree_height, effort_destination=None, new_item_id=None):
        """A new parent must be in the same proposal, keep the tree within 3 levels, and must not hold effort itself."""
        if parent_id is None: return
        parent = self.get(db, 'items', parent_id, 'item')
        if parent['proposal_id'] != proposal_id: raise WorptError('An item can only be placed inside the same work plan.', 'invalid')
        if self.depth(db, parent_id) + subtree_height > 2:
            raise WorptError('WorPT has three levels: task category, task and subtask. This would make a fourth.', 'too_deep')
        work = self.all(db, 'SELECT * FROM assignments WHERE item_id = ?', parent_id)
        timed = parent['start_year'] is not None or parent['end_year'] is not None
        if (work or timed) and not self.has_children(db, parent_id):
            if effort_destination not in ('new_child', 'remove'):
                raise WorptError(f'"{parent["title"]}" has its own effort ({len(work)} assignment(s)) and timeline. Once it has subtasks, '
                                 'effort is entered on the subtasks: move its effort into the new subtask, or remove it?',
                                 'parent_has_effort', assignments=work)
            return dict(work=work, parent=parent, destination=effort_destination)

    def add_item(self, user, proposal_id, parent_id=None, title='', position=None, effort_destination=None):
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            move = self.check_new_parent(db, user, proposal_id, parent_id, 1, effort_destination)
            pos = self.place(db, proposal_id, parent_id, position)
            item = self.insert_row(db, user, 'items', dict(proposal_id=proposal_id, parent_id=parent_id, position=pos,
                                                           title=(title or '').strip()), proposal_id)
            if move: item = self.move_effort(db, user, proposal_id, move, item)
            return item

    def move_effort(self, db, user, proposal_id, move, child):
        parent = move['parent']
        for a in move['work']:
            # someone already on the child (an item being moved in can have its own effort): their weeks are added together
            same = self.one(db, 'SELECT * FROM assignments WHERE item_id = ? AND member_id IS ? AND is_team = ?', child['id'], a['member_id'], a['is_team'])
            if move['destination'] == 'new_child' and same:
                self.update_row(db, user, 'assignments', same['id'], same['version'], dict(weeks=same['weeks'] + a['weeks'], unfunded=same['unfunded'] + a['unfunded'],
                                is_lead=max(same['is_lead'], a['is_lead'])), proposal_id, 'assignment')
                self.delete_row(db, user, 'assignments', a['id'], proposal_id, 'assignment')
            elif move['destination'] == 'new_child':
                db.execute('UPDATE assignments SET item_id = ?, version = version + 1 WHERE id = ?', (child['id'], a['id']))
                self.log(db, user, proposal_id, 'assignments', a['id'], 'move', a, self.get(db, 'assignments', a['id'], 'assignment'))
            else:
                self.delete_row(db, user, 'assignments', a['id'], proposal_id, 'assignment')
        timeline = {k: parent[k] for k in TIMELINE}
        self.update_row(db, user, 'items', parent['id'], parent['version'], dict.fromkeys(timeline), proposal_id, 'item')
        if move['destination'] == 'new_child' and child['start_year'] is None and child['end_year'] is None:    # a child with its own timeline keeps it
            child = self.update_row(db, user, 'items', child['id'], child['version'], timeline, proposal_id, 'item')
        return child

    def update_item(self, user, item_id, version, fields):
        with self.connect() as db:
            it = self.get(db, 'items', item_id, 'item')
            self.proposal(db, user, it['proposal_id'])
            f = dict(fields)
            if any(k in f for k in TIMELINE):
                if self.depth(db, item_id) == 0: raise WorptError('A task category has no timeline of its own; give its tasks timelines.', 'invalid')
                if self.has_children(db, item_id): raise WorptError("This task's timeline comes from its subtasks.", 'invalid')
                for k in ('start_year', 'end_year'):
                    if f.get(k) is not None and int(f[k]) < 1: raise WorptError('Years are counted from 1.', 'invalid')
                for k in ('start_week', 'end_week'):
                    if f.get(k) is not None and not 1 <= int(f[k]) <= WEEKS_PER_YEAR: raise WorptError(f'Weeks are 1 to {WEEKS_PER_YEAR}.', 'invalid')
            for k in ('title', 'short_title'):
                if k in f: f[k] = (f[k] or '').strip()
            if 'description' in f: f['description'] = (f['description'] or '').replace('\r\n', '\n').strip()   # its paragraphs kept
            out = self.update_row(db, user, 'items', item_id, version, f, it['proposal_id'], 'item')
            if 'parent_id' in fields or 'position' in fields:
                out = self.move_item(db, user, out, fields.get('parent_id', it['parent_id']), fields.get('position'), fields.get('effort_destination'))
            return out

    def move_item(self, db, user, it, parent_id, position, effort_destination):
        pid = it['proposal_id']
        node = parent_id
        while node is not None:                                      # not into itself or its own subtasks
            if node == it['id']: raise WorptError('An item cannot be moved inside itself.', 'invalid')
            node = db.execute('SELECT parent_id FROM items WHERE id = ?', (node,)).fetchone()[0]
        h = self.height(db, it['id'])
        if parent_id is None:
            if h > 3: raise WorptError('WorPT has three levels: task category, task and subtask.', 'too_deep')
            if it['start_year'] is not None or self.one(db, 'SELECT id FROM assignments WHERE item_id = ?', it['id']):
                raise WorptError('This item has its own effort or timeline, so it cannot become a task category; task categories carry no effort.', 'invalid')
        move = self.check_new_parent(db, user, pid, parent_id, h, effort_destination) if parent_id != it['parent_id'] else None
        old_parent = it['parent_id']
        if position is None and parent_id == old_parent: return it                # nowhere new to go
        self.renumber(db, pid, old_parent, skip=it['id'])                        # take it out of its old place
        pos = self.place(db, pid, parent_id, position, skip=it['id'])            # position: where it goes among the others
        db.execute('UPDATE items SET parent_id = ?, position = ?, version = version + 1 WHERE id = ?', (parent_id, pos, it['id']))
        self.renumber(db, pid, parent_id)
        moved = self.get(db, 'items', it['id'], 'item')
        self.log(db, user, pid, 'items', it['id'], 'move', it, moved)
        if move: moved = self.move_effort(db, user, pid, move, moved)
        return moved

    def delete_item(self, user, item_id, confirm=False):
        with self.connect() as db:
            it = self.get(db, 'items', item_id, 'item')
            pid = it['proposal_id']
            self.proposal(db, user, pid)
            ids, frontier = [item_id], [item_id]
            while frontier:
                frontier = [r[0] for r in db.execute(f'SELECT id FROM items WHERE parent_id IN ({",".join("?" * len(frontier))})', frontier)]
                ids += frontier
            work = self.all(db, f'SELECT * FROM assignments WHERE item_id IN ({",".join("?" * len(ids))})', *ids)
            if not confirm:
                return {'needs_confirmation': True, 'items_below': len(ids) - 1, 'assignments': len(work),
                        'message': f'Deleting "{it["title"]}" also deletes {len(ids) - 1} item(s) under it and {len(work)} assignment(s).'}
            if it['parent_id'] is None or len(ids) > 1:                # a task category, or a task with subtasks
                self.snapshot(db, user, pid, 'before', f'Before deleting "{it["title"]}" and what was under it')
            for a in work: self.delete_row(db, user, 'assignments', a['id'], pid, 'assignment')
            for i in reversed(ids): self.delete_row(db, user, 'items', i, pid, 'item')
            self.renumber(db, pid, it['parent_id'])
            return it

    # ------------------------------------------------ effort
    def check_assignment(self, db, item, f, assignment_id=None):
        if self.depth(db, item['id']) == 0: raise WorptError('A task category carries no effort; add a task to it and assign people there.', 'invalid')
        if self.has_children(db, item['id']): raise WorptError('This task has subtasks; enter effort on its subtasks.', 'invalid')
        if f.get('is_team'): f['member_id'] = None
        elif 'member_id' in f:
            m = self.get(db, 'members', f['member_id'], 'team member')
            if m['proposal_id'] != item['proposal_id']: raise WorptError('That person is not on this work plan.', 'invalid')
        who = 'is_team = 1' if f.get('is_team') else 'member_id = ?'
        args = () if f.get('is_team') else (f.get('member_id'),)
        if ('member_id' in f or f.get('is_team')) and self.one(db, f'SELECT id FROM assignments WHERE item_id = ? AND {who} AND id != ?', item['id'], *args, assignment_id or -1):
            raise WorptError('That person is already on this item; change their weeks instead.', 'duplicate')
        for k in ('weeks', 'unfunded'):
            if k in f:
                f[k] = float(f[k] or 0)
                if f[k] < 0: raise WorptError('Weeks cannot be negative.', 'invalid')
        for k in ('is_team', 'is_lead'):
            if k in f: f[k] = 1 if f[k] else 0
        return f

    def add_assignment(self, user, item_id, fields):
        with self.connect() as db:
            item = self.get(db, 'items', item_id, 'item')
            self.proposal(db, user, item['proposal_id'])
            f = self.check_assignment(db, item, {k: v for k, v in fields.items() if k in EDITABLE['assignments']})
            if not f.get('is_team') and f.get('member_id') is None: raise WorptError('Choose a person (or "Everyone not named").', 'missing')
            if f.get('is_lead'): self.clear_lead(db, user, item)
            pos = db.execute('SELECT coalesce(max(position) + 1, 0) FROM assignments WHERE item_id = ?', (item_id,)).fetchone()[0]
            return self.insert_row(db, user, 'assignments', dict(f, item_id=item_id, position=pos), item['proposal_id'])

    def clear_lead(self, db, user, item, keep=None):
        for a in self.all(db, 'SELECT * FROM assignments WHERE item_id = ? AND is_lead = 1 AND id != ?', item['id'], keep or -1):
            self.update_row(db, user, 'assignments', a['id'], a['version'], {'is_lead': 0}, item['proposal_id'], 'assignment')

    def update_assignment(self, user, assignment_id, version, fields):
        with self.connect() as db:
            a = self.get(db, 'assignments', assignment_id, 'assignment')
            item = self.get(db, 'items', a['item_id'], 'item')
            self.proposal(db, user, item['proposal_id'])
            f = self.check_assignment(db, item, dict(fields), assignment_id)
            out = self.update_row(db, user, 'assignments', assignment_id, version, f, item['proposal_id'], 'assignment')
            if f.get('is_lead'): self.clear_lead(db, user, item, keep=assignment_id)
            return out

    def delete_assignment(self, user, assignment_id):
        with self.connect() as db:
            a = self.get(db, 'assignments', assignment_id, 'assignment')
            item = self.get(db, 'items', a['item_id'], 'item')
            self.proposal(db, user, item['proposal_id'])
            return self.delete_row(db, user, 'assignments', assignment_id, item['proposal_id'], 'assignment')

    # ------------------------------------------------ non-labor budget
    def add_nonlabor(self, user, proposal_id, item, amounts):
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            pos = db.execute('SELECT coalesce(max(position) + 1, 0) FROM nonlabor WHERE proposal_id = ?', (proposal_id,)).fetchone()[0]
            return self.insert_row(db, user, 'nonlabor', dict(proposal_id=proposal_id, position=pos, item=item or '',
                                                              amounts=[float(v or 0) for v in amounts or []]), proposal_id)

    def update_nonlabor(self, user, row_id, version, fields):
        with self.connect() as db:
            r = self.get(db, 'nonlabor', row_id, 'budget line')
            self.proposal(db, user, r['proposal_id'])
            f = dict(fields)
            if 'amounts' in f: f['amounts'] = [float(v or 0) for v in f['amounts']]
            return self.update_row(db, user, 'nonlabor', row_id, version, f, r['proposal_id'], 'budget line')

    def delete_nonlabor(self, user, row_id):
        with self.connect() as db:
            r = self.get(db, 'nonlabor', row_id, 'budget line')
            self.proposal(db, user, r['proposal_id'])
            return self.delete_row(db, user, 'nonlabor', row_id, r['proposal_id'], 'budget line')

    # ------------------------------------------------ reading a whole proposal
    def export(self, db, proposal_id):
        p = self.one(db, 'SELECT * FROM proposals WHERE id = ?', proposal_id)
        members = self.all(db, 'SELECT m.*, p.first, p.middle, p.last, p.prefix, p.suffix, p.institution, p.position, p.us, p.expertise, p.pronoun, '
                           'p.email, p.version AS person_version FROM members m JOIN people p ON p.id = m.person_id '
                           'WHERE m.proposal_id = ? ORDER BY m.id', proposal_id)
        items = self.all(db, 'SELECT * FROM items WHERE proposal_id = ? ORDER BY position, id', proposal_id)
        ids = [i['id'] for i in items] or [-1]
        work = self.all(db, f'SELECT * FROM assignments WHERE item_id IN ({",".join("?" * len(ids))}) ORDER BY position, id', *ids)
        budget = self.all(db, 'SELECT * FROM nonlabor WHERE proposal_id = ? ORDER BY position, id', proposal_id)
        return dict(proposal=p, members=members, items=items, assignments=work, nonlabor=budget)

    def read(self, user, proposal_id):
        with self.connect() as db:
            p = self.proposal(db, user, proposal_id)
            m = self.membership(db, user, proposal_id)
            return dict(self.export(db, proposal_id), last_change=self.last_change(db, proposal_id), you=dict(email=user.email, access=user.access,
                        member_id=m and m['id'], lead=bool(m and m['is_lead']), can_manage_team=user.admin or bool(m and m['is_lead'])))

    def history(self, user, proposal_id, limit=200):
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            return self.all(db, 'SELECT * FROM history WHERE proposal_id = ? ORDER BY id DESC LIMIT ?', proposal_id, int(limit))

    # ------------------------------------------------ snapshots
    def snapshot(self, db, user, proposal_id, kind, name=''):
        """Save the whole proposal as it stands (plan, team, budget, settings). kind: 'daily', 'before' (automatic, just
        before something drastic) or 'named' (saved by someone). Automatic ones older than AUTO_SNAPSHOT_DAYS are removed."""
        data = self.export(db, proposal_id)
        if data['proposal'] is None: return None
        cur = db.execute('INSERT INTO snapshots (proposal_id, at, user, kind, name, data) VALUES (?,?,?,?,?,?)',
                         (proposal_id, now(), user.email, kind, name, json.dumps(data)))
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=AUTO_SNAPSHOT_DAYS)).isoformat(timespec='seconds')
        db.execute("DELETE FROM snapshots WHERE proposal_id = ? AND kind != 'named' AND at < ?", (proposal_id, cutoff))
        return cur.lastrowid

    def daily_snapshot(self, db, user, proposal_id):
        """The first change of each day (UTC) saves how the proposal stood before it."""
        if proposal_id and not db.execute("SELECT 1 FROM snapshots WHERE proposal_id = ? AND kind = 'daily' AND substr(at, 1, 10) = ?",
                                          (proposal_id, now()[:10])).fetchone():
            self.snapshot(db, user, proposal_id, 'daily', 'Start of the day')

    def snapshots(self, user, proposal_id):
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            return self.all(db, 'SELECT id, at, user, kind, name FROM snapshots WHERE proposal_id = ? ORDER BY id DESC', proposal_id)

    def save_snapshot(self, user, proposal_id, name):
        name = (name or '').strip()[:200]
        if not name: raise WorptError('Give the snapshot a name, e.g. "before the co-I review".', 'missing')
        with self.connect() as db:
            self.proposal(db, user, proposal_id)
            sid = self.snapshot(db, user, proposal_id, 'named', name)
            return self.one(db, 'SELECT id, at, user, kind, name FROM snapshots WHERE id = ?', sid)

    def delete_snapshot(self, user, snapshot_id):
        with self.connect() as db:
            s = self.get(db, 'snapshots', snapshot_id, 'snapshot')
            self.proposal(db, user, s['proposal_id'], need='team')
            db.execute('DELETE FROM snapshots WHERE id = ?', (snapshot_id,))
            return {'id': snapshot_id}

    def restore_snapshot(self, user, snapshot_id):
        """Put the proposal back as it was in a snapshot: its settings, team, plan, effort and budget. Profiles are shared
        between proposals and stay as they are. How things stood just before is saved first, so a restore can be undone."""
        with self.connect() as db:
            s = self.get(db, 'snapshots', snapshot_id, 'snapshot')
            pid = s['proposal_id']
            self.proposal(db, user, pid, need='team')
            data, me = json.loads(s['data']), self.person_for(db, user)
            if not user.admin and not any(me and m['person_id'] == me['id'] and m['is_lead'] for m in data['members']):
                raise WorptError('That snapshot is from before you were a full editor of this work plan, so restoring it would take '
                                 'away your access. Ask another full editor or an admin to restore it.', 'refused')
            self.snapshot(db, user, pid, 'before', f'Before restoring the snapshot of {s["at"]}')
            p = data['proposal']
            db.execute('UPDATE proposals SET title = ?, program = ?, n_years = ?, rounding = ?, travel = ?, version = version + 1 WHERE id = ?',
                       (p['title'], p['program'], p['n_years'], p['rounding'], json.dumps(p['travel']), pid))
            for tbl in ('items', 'members', 'nonlabor'):                  # assignments go with their items and members
                db.execute(f'DELETE FROM {tbl} WHERE proposal_id = ?', (pid,))
            member_id, back = {}, []
            for m in data['members']:                                       # people still on file, numbered as they are today
                person = self.one(db, 'SELECT * FROM people WHERE id = ?', m['person_id'])
                if person is None: continue
                back.append(dict(m, last=person['last'], role=canonical_role(m['role']) if person['us'] else 'coll(0)'))
            for m, role in numbered_roles(back):
                cur = db.execute('INSERT INTO members (proposal_id, person_id, short_id, role, is_lead, fte_accuracy, bio_summary, task_summary, trips) '
                                 'VALUES (?,?,?,?,?,?,?,?,?)', (pid, m['person_id'], role_label(role), role, int(m['is_lead']), m['fte_accuracy'],
                                                                m['bio_summary'], m['task_summary'], json.dumps(m['trips'])))
                member_id[m['id']] = cur.lastrowid
            item_id, pending = {}, [weeks_from_quarters(dict(i)) for i in data['items']]   # snapshots saved before weeks have quarters
            while pending:                                                  # parents before their children
                ready = [i for i in pending if i['parent_id'] is None or i['parent_id'] in item_id]
                if not ready: break
                for i in ready:
                    cur = db.execute('INSERT INTO items (proposal_id, parent_id, position, title, short_title, description, start_year, start_week, end_year, end_week) '
                                     'VALUES (?,?,?,?,?,?,?,?,?,?)',
                                     (pid, item_id.get(i['parent_id']), i['position'], i['title'], i.get('short_title', ''),   # older snapshots have
                                      i.get('description', ''), i['start_year'], i['start_week'], i['end_year'], i['end_week']))  # neither of these
                    item_id[i['id']] = cur.lastrowid
                    pending.remove(i)
            for a in data['assignments']:
                if a['item_id'] not in item_id or (not a['is_team'] and a['member_id'] not in member_id): continue
                db.execute('INSERT INTO assignments (item_id, member_id, is_team, is_lead, weeks, unfunded, position) VALUES (?,?,?,?,?,?,?)',
                           (item_id[a['item_id']], None if a['is_team'] else member_id[a['member_id']], int(a['is_team']), int(a['is_lead']),
                            a['weeks'], a['unfunded'], a['position']))
            for r in data['nonlabor']:
                db.execute('INSERT INTO nonlabor (proposal_id, position, item, amounts) VALUES (?,?,?,?)', (pid, r['position'], r['item'], json.dumps(r['amounts'])))
            self.log(db, user, pid, 'proposal_snapshot', snapshot_id, 'restore', None, {'snapshot_at': s['at'], 'name': s['name']})
            return {'restored': s['at'], 'name': s['name']}

    def model(self, proposal_id, data=None):
        """The proposal as worpt.model objects (for the effort engine and the tables), plus id maps for the dashboard."""
        if data is None:
            with self.connect() as db: data = self.export(db, proposal_id)
        p, short = data['proposal'], {m['id']: m['short_id'] for m in data['members']}
        members = [Person(m['short_id'], m['role'], m['us'], m['fte_accuracy'], last=m['last'], first=m['first'], middle=m['middle'],
                          prefix=m['prefix'], suffix=m['suffix'], institution=m['institution'], position=m['position'],
                          bio_summary=m['bio_summary'], task_summary=m['task_summary'], trips=m['trips']) for m in data['members']]
        nodes = {i['id']: Item(i['title'], short_title=i.get('short_title', ''), start=(i['start_year'], i['start_week']) if i['start_year'] and i['start_week'] else None,
                               end=(i['end_year'], i['end_week']) if i['end_year'] and i['end_week'] else None) for i in data['items']}
        for a in data['assignments']:
            nodes[a['item_id']].assignments.append(Assignment('team' if a['is_team'] else short[a['member_id']], a['weeks'], a['unfunded'], a['is_lead']))
        goals, order = [], {}
        for i in data['items']:                                     # items are sorted by position
            (goals if i['parent_id'] is None else nodes[i['parent_id']].children).append(nodes[i['id']])
        travel = dict(TRAVEL_DEFAULT, **(p['travel'] or {}))
        prop = Proposal(p['title'], p['program'], p['n_years'], members, goals, [NonlaborItem(r['item'], r['amounts']) for r in data['nonlabor']],
                        TravelCosts(**travel), p['latex_subdir'], p['rounding'])
        return prop, {id(n): iid for iid, n in nodes.items()}
