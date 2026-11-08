"""WorPT server: proposal work plans, effort and LaTeX tables, behind nginx at /worpt/ (localhost:8083).

Environment (secrets go in a systemd drop-in, never in a committed file):
  WORPT_CREDENTIAL       shared secret the dashboard sends in X-WorPT-Credential (generate: openssl rand -hex 16).
                         The server refuses to start if it is missing or shorter than 16 characters.
  WORPT_READ_CREDENTIAL  optional read-only key for gooTeX, accepted ONLY on the table routes (at least 16 characters,
                         otherwise ignored with a warning).
  WORPT_DB               database file (default /home/bibman/worpt_data/worpt.db).
  WORPT_TEMPLATES        LaTeX templates folder (default: latexTableTemplates/ in the repository).

The dashboard also sends X-WorPT-User (the signed-in Google email) and X-WorPT-Access ("admin", "core" or "code",
from its ADMIN_EMAILS / CORE_MEMBERS Script Properties). Refusals are HTTP 200 with {"status": "error", ...}.
Run: gunicorn --workers 1 --threads 2 --timeout 60 --bind 127.0.0.1:8083 'worpt_server:create_app()'
"""
import hashlib, hmac, logging, os, pathlib, sys
from flask import Flask, jsonify, request
from worpt.store import Store, User, WorptError
from worpt.effort import compute, label_tree
from worpt.tables import build, paste_in, style, travel_summary, TABLES
from worpt.about import about

log = logging.getLogger('worpt')


def create_app(db_path=None, credential=None, read_credential=None):
    credential = os.environ.get('WORPT_CREDENTIAL', '') if credential is None else credential
    read_credential = os.environ.get('WORPT_READ_CREDENTIAL', '') if read_credential is None else read_credential
    if len(credential) < 16:
        # exit code 3 is gunicorn's "worker failed to boot": gunicorn stops instead of restarting the worker in a tight loop
        print('WorPT: WORPT_CREDENTIAL is missing or shorter than 16 characters; refusing to start.', file=sys.stderr, flush=True)
        raise SystemExit(3)
    if read_credential and len(read_credential) < 16:
        log.warning('WORPT_READ_CREDENTIAL is set but shorter than 16 characters; it will NOT be accepted.')
        read_credential = ''
    db_path = db_path or os.environ.get('WORPT_DB', '/home/bibman/worpt_data/worpt.db')
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store, app = Store(db_path), Flask(__name__)
    same = lambda given, secret: bool(secret) and hmac.compare_digest(given.encode(), secret.encode())

    def ok(**data): return jsonify(status='ok', **data)

    def refuse(message, code='refused', **extra): return jsonify(status='error', code=code, message=message, **extra)

    def key():
        given = request.headers.get('X-WorPT-Credential', '')
        return 'full' if same(given, credential) else 'read' if same(given, read_credential) else None

    def user():
        access = request.headers.get('X-WorPT-Access', 'code').strip().lower()
        u = User(request.headers.get('X-WorPT-User', ''), access if access in ('admin', 'core') else 'code')
        if not u.email: raise WorptError('Please sign in to your Google account, then open WorPT again.', 'signin')
        return u

    body = lambda: request.get_json(silent=True) or {}
    # Deletes take their confirmation in the query string too (?confirm=1, ?confirm_title=...): Apps Script's
    # UrlFetchApp is not guaranteed to send a body with DELETE.
    confirmed = lambda: str(body().get('confirm', request.args.get('confirm', ''))).lower() in ('1', 'true', 'yes')

    @app.before_request
    def gate():
        if request.path == '/health': return None
        k = key()
        if k == 'full' or (k == 'read' and request.method == 'GET' and '/tables' in request.path): return None
        return refuse('WorPT did not recognize the credential (check the WorPT_CREDENTIAL setting).', 'credential')

    @app.errorhandler(WorptError)
    def worpt_error(e): return refuse(e.message, e.code, **e.extra)

    @app.errorhandler(Exception)
    def crashed(e):
        if hasattr(e, 'code') and isinstance(getattr(e, 'code'), int) and e.code < 500:      # 404, 405 ...
            return refuse(f'Unknown request: {request.method} {request.path}', 'unknown')          # refusals are always HTTP 200
        log.exception('Unexpected error on %s %s', request.method, request.path)
        return refuse('WorPT hit an unexpected problem; nothing was changed. Details are in the server log.', 'internal')

    def computed(pid, data):
        prop, node_ids = store.model(pid, data)
        r = compute(prop.members, prop.goals, prop.n_years, prop.weeks_per_fte, prop.rounding)
        label_of = {node_ids[id(it)]: lab for lab, _, it, _ in label_tree(prop.goals)}
        member_of = {m['short_id']: m['id'] for m in data['members']}
        return dict(
            people={member_of[s]: dict(per_year=r['person_year'][i].tolist(), total=r['person_total'][i].tolist()) for i, s in enumerate(r['ids'])},
            items={iid: dict(label=lab, fte=r['items'][lab]['fte'].tolist(), start=r['items'][lab]['start'], end=r['items'][lab]['end'])
                   for iid, lab in label_of.items()},
            project_total=r['project_total'].tolist(), travel=travel_summary(prop),
            checks=[dict(level=c.level, item=c.item, message=c.message, **{k: getattr(c, k) for k in ('person', 'weeks') if getattr(c, k) is not None})
                    for c in r['checks']])

    # ------------------------------------------------ routes
    @app.get('/health')
    def health(): return ok(service='worpt')

    @app.get('/api/me')
    def me():
        u = user()
        return ok(email=u.email, access=u.access, profile=store.my_profile(u), proposals=store.list_proposals(u), about=about())

    @app.get('/api/people')
    def people(): return ok(people=store.people(user(), request.args.get('q', '')))

    @app.post('/api/people')
    def add_person(): return ok(person=store.create_person(user(), body()))

    @app.patch('/api/people/<int:person_id>')
    def edit_person(person_id):
        b = body(); return ok(person=store.update_person(user(), person_id, b.pop('version', None), b))

    @app.get('/api/proposals')
    def proposals(): return ok(proposals=store.list_proposals(user()))

    @app.post('/api/proposals')
    def add_proposal():
        b = body()
        return ok(proposal=store.create_proposal(user(), b.get('title'), b.get('program', ''), b.get('n_years', 3), b.get('leads') or []))

    @app.get('/api/proposals/<pid>')
    def proposal(pid):
        data = store.read(user(), pid)
        return ok(**data, computed=computed(pid, data))

    @app.patch('/api/proposals/<pid>')
    def edit_proposal(pid):
        b = body(); return ok(proposal=store.update_proposal(user(), pid, b.pop('version', None), b))

    @app.delete('/api/proposals/<pid>')
    def delete_proposal(pid): return ok(**store.delete_proposal(user(), pid, body().get('confirm_title', request.args.get('confirm_title'))))

    @app.get('/api/proposals/<pid>/changed')
    def changed(pid): return ok(last_change=store.changed(user(), pid))

    @app.get('/api/proposals/<pid>/snapshots')
    def snapshots(pid): return ok(snapshots=store.snapshots(user(), pid))

    @app.post('/api/proposals/<pid>/snapshots')
    def save_snapshot(pid): return ok(snapshot=store.save_snapshot(user(), pid, body().get('name')))

    @app.post('/api/snapshots/<int:snapshot_id>/restore')
    def restore_snapshot(snapshot_id): return ok(**store.restore_snapshot(user(), snapshot_id))

    @app.delete('/api/snapshots/<int:snapshot_id>')
    def delete_snapshot(snapshot_id): return ok(deleted=store.delete_snapshot(user(), snapshot_id))

    @app.get('/api/proposals/<pid>/history')
    def history(pid): return ok(history=store.history(user(), pid, request.args.get('limit', 200)))

    @app.post('/api/proposals/<pid>/members')
    def add_member(pid): return ok(member=store.add_member(user(), pid, body()))

    @app.patch('/api/members/<int:member_id>')
    def edit_member(member_id):
        b = body(); return ok(member=store.update_member(user(), member_id, b.pop('version', None), b))

    @app.delete('/api/members/<int:member_id>')
    def remove_member(member_id):
        out = store.remove_member(user(), member_id, confirmed())
        return ok(**out) if out.get('needs_confirmation') else ok(removed=out)

    @app.post('/api/proposals/<pid>/items')
    def add_item(pid):
        b = body()
        return ok(item=store.add_item(user(), pid, b.get('parent_id'), b.get('title', ''), b.get('position'), b.get('effort_destination')))

    @app.patch('/api/items/<int:item_id>')
    def edit_item(item_id):
        b = body(); return ok(item=store.update_item(user(), item_id, b.pop('version', None), b))

    @app.delete('/api/items/<int:item_id>')
    def delete_item(item_id):
        out = store.delete_item(user(), item_id, confirmed())
        return ok(**out) if out.get('needs_confirmation') else ok(deleted=out)

    @app.post('/api/items/<int:item_id>/assignments')
    def add_assignment(item_id): return ok(assignment=store.add_assignment(user(), item_id, body()))

    @app.patch('/api/assignments/<int:assignment_id>')
    def edit_assignment(assignment_id):
        b = body(); return ok(assignment=store.update_assignment(user(), assignment_id, b.pop('version', None), b))

    @app.delete('/api/assignments/<int:assignment_id>')
    def delete_assignment(assignment_id): return ok(deleted=store.delete_assignment(user(), assignment_id))

    @app.post('/api/proposals/<pid>/nonlabor')
    def add_nonlabor(pid):
        b = body(); return ok(line=store.add_nonlabor(user(), pid, b.get('item', ''), b.get('amounts') or []))

    @app.patch('/api/nonlabor/<int:row_id>')
    def edit_nonlabor(row_id):
        b = body(); return ok(line=store.update_nonlabor(user(), row_id, b.pop('version', None), b))

    @app.delete('/api/nonlabor/<int:row_id>')
    def delete_nonlabor(row_id): return ok(deleted=store.delete_nonlabor(user(), row_id))

    def work_plan(pid):
        """The work plan's data: the dashboard's person must be on it; gooTeX's read-only key reads any (by its ID)."""
        if key() == 'full': return store.read(user(), pid)
        with store.connect() as db: data = store.export(db, pid)
        if data['proposal'] is None: raise WorptError('That work plan does not exist.', 'not_found')
        return data

    checks_of = lambda out: [dict(level=c.level, item=c.item, message=c.message) for c in out['_checks']]

    @app.get('/api/proposals/<pid>/tables')
    def table_names(pid):
        """The table names; with ?files=1, every file a document needs, ready to write (<table>.tex and worpt.sty), and
        each table's paste-in block (and worpt's preamble line)."""
        data = work_plan(pid)
        if str(request.args.get('files', '')).lower() not in ('1', 'true', 'yes'):
            return ok(tables=list(TABLES), style='worpt')        # /tables/worpt is worpt.sty
        out = build(store.model(pid, data)[0])
        files = {f'{n}.tex': out[n] for n in TABLES}
        files['worpt.sty'] = style()
        blocks = {n: paste_in(n) for n in TABLES + ('worpt',)}
        digest = hashlib.sha256('\0'.join(f'{k}\0{v}' for k, v in sorted(files.items()) + sorted(('block:' + k, v) for k, v in blocks.items())).encode()).hexdigest()
        return ok(work_plan=dict(id=pid, title=data['proposal']['title']), files=files, blocks=blocks, digest=digest, checks=checks_of(out))

    @app.get('/api/proposals/<pid>/tables/<name>')
    def table(pid, name):
        if name not in TABLES + ('worpt',):
            return refuse(f'There is no table called "{name}". Tables: {", ".join(TABLES)}; and worpt (worpt.sty).', 'unknown_table')
        data = work_plan(pid)
        if name == 'worpt': return ok(name=name, latex=style(), block=paste_in(name), checks=[])
        out = build(store.model(pid, data)[0], [name])
        return ok(name=name, latex=out[name], block=paste_in(name), checks=checks_of(out))

    return app
