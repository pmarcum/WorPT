# WorPT server (in progress)

The server half of the rebuilt WorPT. It will run on the shared VM beside BibMan and gooTeX
(port 8083, behind nginx). So far it holds the **effort engine** and the **LaTeX table generators**.

## Effort engine — `worpt/effort.py`

Turns the weeks assigned on work-plan items into FTE:

- Effort, people and timelines live only on lowest-level items (goal > task > subtask; labels A, A1, A1.1).
- An item's weeks are split across years in proportion to its quarters in each year.
- Person FTE per year = weeks / 52, rounded to the nearest 0.01 below 0.1 FTE, otherwise to the
  nearest 0.05 (or the person's own FTE accuracy).
- Funded = rounded total − rounded unfunded; all-years figures are sums of the rounded yearly values.
- `team` gives its weeks to every team member not named on the item.
- Collaborators (a `coll…` role, or anyone at a non-US institution) are always 100% unfunded.
- Tasks and goals roll up from their children. Nothing is dropped silently; problems are returned as `checks`.

Rounding is to the nearest step by default (`rounding='nearest'`); `rounding='up'` reproduces the
Google Sheet version of January 2025, which rounded up.

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

## Tests

```
cd cloud
pip install -r requirements.txt
python3 -m pytest tests            # parity with the Google Sheet version + one test per rule
python3 tests/parity_report.py     # side-by-side old vs new numbers for the demo proposal
python3 tests/test_parity_tables.py   # table-by-table comparison with the Sheet version's output
```

`tests/fixtures/demo2023.json` holds the inputs and the Sheet's own results for the
"WorPT Proposal Demo 2023" spreadsheet. `tests/fixtures/rst_ilc/` and `tests/fixtures/isfm2025/`
hold two real proposals with every name, ID, narrative and task title replaced by placeholders,
the tables the Sheet version made from them (`expected/`), and the deliberate differences with
their reasons (`known_differences.json`).
