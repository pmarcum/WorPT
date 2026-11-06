# WorPT server (in progress)

The server half of the rebuilt WorPT. It will run on the shared VM beside BibMan and gooTeX
(port 8083, behind nginx). So far it holds only the **effort engine**.

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

## Tests

```
cd cloud
pip install -r requirements.txt
python3 -m pytest tests            # parity with the Google Sheet version + one test per rule
python3 tests/parity_report.py     # side-by-side old vs new numbers for the demo proposal
```

`tests/fixtures/demo2023.json` holds the inputs and the Sheet's own results for the
"WorPT Proposal Demo 2023" spreadsheet.
