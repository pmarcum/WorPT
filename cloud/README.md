# WorPT server (in progress)

The server half of the rebuilt WorPT. It runs on the shared VM beside BibMan and gooTeX
(port 8083, behind nginx at `/worpt/`). It holds the **effort engine**, the **LaTeX table
generators**, and the **storage and API** the WorPT dashboard uses. The dashboard itself is
`Index.html` and `apps_script/` at the top of the repository; [DEPLOY.md](../DEPLOY.md) sets up both.

## Effort engine — `worpt/effort.py`

Turns the weeks assigned on work-plan items into FTE:

- Effort, people and timelines live only on lowest-level items (goal > task > subtask; labels A, A1, A1.1).
- Timelines are in weeks (52 to a year, 13 to a quarter); an item's weeks of effort are split across years in proportion
  to its timeline's weeks in each year. The schedule table shows them in month columns under quarter labels.
- Person FTE per year = weeks / 52, rounded to the nearest 0.01 below 0.1 FTE, otherwise to the
  nearest 0.05 (or the person's own FTE accuracy).
- Funded = rounded total − rounded unfunded; all-years figures are sums of the rounded yearly values.
- `team` gives its weeks to every team member not named on the item.
- Collaborators (a `coll…` role, or anyone at a non-US institution) are always 100% unfunded.
- Roles are chosen, not numbered by hand: co-I, postdoc (`pd`), grad student (`gst`), undergrad student (`ust`) and
  collaborator (`coll`) are numbered 1, 2, … by the server in the tables' order (PI, Admin-PI, Sci-PI, co-Is, postdocs,
  grad students, undergrads, anyone with another role, collaborators; within each, by last name), and renumbered with no
  gaps whenever someone joins, leaves, changes role or changes last name. PI, Sci-PI and Admin-PI are one person each.
  Each member is shown by a label made from the role (co-I 1, collab 1…), never their name.
- Tasks and goals roll up from their children. Nothing is dropped silently; problems are returned as `checks`.
- Over full time is a warning, never refused: more weeks of effort on an item than its timeline has weeks; a person
  over full time in any week (each item's effort spread evenly over its timeline); more than 1.0 FTE in a year.

Rounding is to the nearest step by default (`rounding='nearest'`); `rounding='up'` always rounds up.

## Tables — `worpt/tables.py`

`build(proposal)` returns the LaTeX for the schedule, task lists (named and anonymous), FTE tables
(named and anonymous), HST table, team summaries, travel and non-labor budget tables, using the
templates in `latexTableTemplates/`. The data a proposal holds is described in `worpt/model.py`.
Subtasks appear as A1.1, A1.2 …; a task with subtasks shows their combined timeline and FTE.

Corrections compared with the Google Sheet version (each is covered by a test):

1. Non-labor table: the Domestic travel line is the year's total, not the cost of one trip.
2. Schedule: "team" weeks count every team member they cover.
3. HST table: a missing Science/Admin PI falls back to the PI's full name (not its first letter).
4. Travel caption: trips are counted only within the grant years, and "1 trip" is singular.
5. Anonymous task list: "team" next to named experts is shown as "team".
6. FTE tables: negligible effort gets the template's "minor" row instead of disappearing.

(Biosketch and current & pending tables come later, with the people profiles.)

## Server — `worpt_server.py` and `worpt/store.py`

A Flask app (one gunicorn worker, localhost only) with one SQLite database. Browsers never reach it
directly: the WorPT dashboard (Apps Script) calls it with a shared credential, the signed-in Google
email and the person's access level (`admin` from ADMIN_EMAILS, `core` from CORE_MEMBERS, otherwise
`code` for access-code users). gooTeX may use a separate read-only key that only reads tables; how gooTeX asks for them is in [GOOTEX_INTERFACE.md](GOOTEX_INTERFACE.md).

| Setting (environment) | Meaning |
|---|---|
| `WORPT_CREDENTIAL` | shared secret for the dashboard; the server will not start without one of 16+ characters |
| `WORPT_READ_CREDENTIAL` | optional read-only key for gooTeX (table routes only) |
| `WORPT_DB` | database file, default `/home/bibman/worpt_data/worpt.db` |
| `WORPT_TEMPLATES` | LaTeX templates folder, default `latexTableTemplates/` in this repository |

Secrets go in a systemd drop-in readable only by root, never in a committed file. Installing,
updating, restoring and removing the server are covered in [DEPLOY.md](../DEPLOY.md). `worpt_backup.py` makes a
nightly copy of the database and keeps the newest 14.

Rules the server applies to every change:

- Admins and core members create proposals; admins see every proposal, everyone else only the ones they are on.
- Anyone on a proposal edits its plan and budget (including each member's trips); its full editors (and
  admins) manage the team and its full editors, and may
  delete the proposal after typing its title. A proposal always keeps at least one full editor
  (stored as `is_lead` on a member; a task's lead is `is_lead` on an assignment).
- A profile may be edited by its owner, full editors of a proposal the person is on, core members and admins.
  Someone at a non-US institution is a collaborator (`coll(n)`) on every proposal.
- Three levels (goal > task > subtask); effort and timelines only on the lowest level. Adding a
  subtask to a task that has effort asks whether to move that effort into the subtask or remove it.
- Removing a member or deleting an item first returns what would be removed; nothing goes until confirmed.
- Every row has a version: a change based on an outdated version is refused and the current row is
  returned, so nothing is overwritten silently. Every change is recorded in `history` (who, when,
  before and after). A refused request saves nothing.
- Snapshots: the whole proposal (settings, team, plan, effort, budget) is saved at the first change of
  each day (UTC) and just before deleting a task category or a task with subtasks, taking someone off
  the team, changing the number of years, or restoring; anyone on the proposal can also save a named one.
  Full editors restore or delete them. Automatic snapshots are kept for 60 days, named ones until deleted.
  A restore never removes the person doing it, and can itself be undone.
- Undo and redo (`POST /api/proposals/<id>/undo`, `.../redo`; Ctrl+Z and Ctrl+Y in the dashboard): everything one
  request changes is one step (`steps`; its rows in `history` carry the step's number). A person undoes their own
  steps in a work plan, newest first, back to the work plan's creation, and redoes what they undid until they make a
  new change there; this is kept in the database, so it survives a reload. Only the columns a step changed are put
  back, and only if nobody changed them since: otherwise the step is skipped (the refusal, code `stuck`, says who
  changed it) and the next undo goes on to the step before. An undo that would break the rules above (after
  others' changes) is refused the same way. Undo needs the same rights as the change. Row numbers are never used
  twice (`top_ids`), so a deleted row comes back under its own number, and a restore keeps the snapshot's numbers
  and records each row it changes, so changes made before a restore can still be undone after it. A profile
  changed with a work plan open is undone in that plan. `GET /api/proposals/<id>` says what undo and redo would
  do (`you.undo`, `you.redo`), in words. Changes made before undo existed (November 2026) can't be undone.
- Refusals are HTTP 200 with `{"status": "error", "code": ..., "message": ...}`.
- `GET /api/proposals/<id>/changed` returns the number of the proposal's newest change; the dashboard asks
  every 10 seconds while it is visible and reloads only when the number grows.
- `GET /api/proposals/<id>/tables/<name>` with the dashboard's key also returns `preview`: the table compiled on its
  own (`worpt/preview.py`), with its default settings, in the newest AASTeX class that compiles on the server (else
  article), as PNG pages; or an `error` for people. One compile at a time, 60 seconds at most; the last 5 are kept in
  memory. Needs pdflatex and pdftocairo. gooTeX's read-only key gets no preview. A newly installed AASTeX is used
  after WorPT's next restart.
- `GET /api/me` also says what is running (`about`): the commit the server was started from, the latest change
  to the page (Index.html) on GitHub, and whether GitHub has server changes not yet pulled and restarted on the VM.
  For the last two, the server asks GitHub's API (api.github.com) at most once every 10 minutes; if GitHub can't
  be reached, only the server's own commit is given.

## Tests

```
cd cloud
pip install -r requirements.txt
python3 -m pytest tests            # parity with the Google Sheet version, one test per rule, and the server API
python3 tests/parity_report.py     # side-by-side old vs new numbers for the demo proposal
python3 tests/test_parity_tables.py   # table-by-table comparison with the Sheet version's output
```

`tests/fixtures/demo2023.json` holds the inputs and the Sheet's own results for the
"WorPT Proposal Demo 2023" spreadsheet. `tests/fixtures/rst_ilc/` and `tests/fixtures/isfm2025/`
hold two real proposals with every name, ID, narrative and task title replaced by placeholders,
the tables the Sheet version made from them (`expected/`), and the deliberate differences with
their reasons (`known_differences.json`).

`tests/test_server.py` drives the API end to end with a fresh database for each test, and checks
that the two real proposals, entered through the API, give exactly the same tables as the fixtures.
