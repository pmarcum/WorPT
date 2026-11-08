"""WorPT effort engine: turns weeks assigned on work-plan items into FTE.

Rules (see the WorPT design decisions):
  * Effort, people and timelines live only on lowest-level items (goal > task > subtask).
  * Timelines are in weeks: 52 to a year, 13 to a quarter. An item's weeks of effort are split across years in
    proportion to its timeline's weeks that fall in each year.
  * Person FTE per year = weeks that year / weeks_per_fte, rounded to a step: 0.01 below 0.1 FTE,
    otherwise the person's FTE accuracy (default 0.05); rounding='nearest' (default) or 'up'.
  * Funded = rounded total - rounded unfunded. All-years figures are sums of rounded yearly values.
  * "team" gives its weeks to every team member not named on that item.
  * Collaborators (role "coll..." or a non-US institution) are always 100% unfunded.
  * Parents roll up from their children: FTE is summed, the timeline spans the children.
Nothing is dropped silently: anything incomplete is reported in `checks`, and so is anyone over full time (warnings only).
"""
from dataclasses import dataclass, field
import numpy as np

TEAM = 'team'
SMALL_FTE, SMALL_STEP, DEFAULT_STEP = 0.1, 0.01, 0.05
WEEKS_PER_YEAR, WEEKS_PER_QUARTER = 52, 13       # a timeline's calendar (not the same as weeks_per_fte, the weeks in one FTE)


def week_index(yw):
    """(year, week), both counted from 1, as a week counted from 0 over the whole project."""
    return (yw[0] - 1) * WEEKS_PER_YEAR + yw[1] - 1


def year_week(w):
    return None if w is None else (int(w) // WEEKS_PER_YEAR + 1, int(w) % WEEKS_PER_YEAR + 1)


def week_span(a, b):
    """Weeks a to b (counted from 0 over the project) as text: "Y1 W15-W20", or "Y1 W50-Y2 W3"."""
    (ya, wa), (yb, wb) = year_week(a), year_week(b)
    return f'Y{ya} W{wa}' + ('' if a == b else f'\u2013W{wb}' if ya == yb else f'\u2013Y{yb} W{wb}')


@dataclass
class Member:
    id: str
    role: str = ''
    us: bool = True
    fte_accuracy: float | None = None

    @property
    def collaborator(self):
        return (not self.us) or self.role.strip().lower().startswith('coll')


@dataclass
class Assignment:
    person: str          # a member id, or "team"
    weeks: float = 0.0
    unfunded: float = 0.0
    lead: bool = False


@dataclass
class Item:
    title: str
    children: list = field(default_factory=list)
    start: tuple | None = None   # (year, week), both counted from 1; week 1 to 52
    end: tuple | None = None
    assignments: list = field(default_factory=list)


@dataclass
class Check:
    level: str           # "fix" (needs attention) or "warn"
    item: str            # label such as "A1.2", or a member id
    message: str


def mround(x, step, mode='nearest'):
    """Round to a multiple of `step`: 'nearest' (halves go up) or 'up' (ceiling)."""
    q = np.asarray(x) / step
    return np.round((np.ceil(q - 1e-9) if mode == 'up' else np.floor(q + 0.5 + 1e-9)) * step, 10)


def letters(n):
    """0 -> A, 25 -> Z, 26 -> AA ... (no limit on the number of goals)."""
    s = ''
    n += 1
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def label_tree(goals):
    """Return [(label, depth, item, parent_label)] in display order: A, A1, A1.1 ..."""
    out = []
    def walk(item, label, depth, parent):
        out.append((label, depth, item, parent))
        for k, child in enumerate(item.children, 1):
            walk(child, f'{label}{k}' if depth == 0 else f'{label}.{k}', depth + 1, label)
    for g, goal in enumerate(goals): walk(goal, letters(g), 0, None)
    return out


def compute(members, goals, n_years, weeks_per_fte=52, rounding='nearest'):
    """Compute person FTE per year, item FTE and roll-ups. Returns a dict of numpy arrays and checks."""
    checks, ids = [], [m.id for m in members]
    pidx = {pid: i for i, pid in enumerate(ids)}
    collab = np.array([m.collaborator for m in members], bool)
    step = np.array([m.fte_accuracy or DEFAULT_STEP for m in members], float)
    tree = label_tree(goals)
    leaves = [(lab, it) for lab, d, it, _ in tree if d > 0 and not it.children]
    for lab, d, it, _ in tree:
        if it.children and it.assignments:
            checks.append(Check('fix', lab, 'has subtasks and its own effort; move its effort into a subtask (not counted until then)'))
        if d == 0 and not it.children:
            checks.append(Check('fix', lab, 'task category has no tasks'))

    # Year fractions per leaf, from the weeks of its timeline that fall in each year.
    n_w = WEEKS_PER_YEAR * n_years
    qs = np.array([week_index(it.start) if it.start else -1 for _, it in leaves])
    qe = np.array([week_index(it.end) if it.end else -2 for _, it in leaves])
    ww = np.arange(n_w)
    inside = (ww >= qs[:, None]) & (ww <= qe[:, None])
    span = inside.sum(1)
    frac = np.divide(inside.reshape(len(leaves), n_years, WEEKS_PER_YEAR).sum(2), span[:, None], out=np.zeros((len(leaves), n_years)), where=span[:, None] > 0)
    for (lab, it), s, e in zip(leaves, qs, qe):
        if it.start is None or it.end is None: checks.append(Check('fix', lab, 'has no timeline, so its weeks are not counted in any year'))
        elif e < s: checks.append(Check('fix', lab, 'ends before it starts'))
        elif e >= n_w: checks.append(Check('fix', lab, f'runs past year {n_years}; weeks after that are not counted'))

    # Weeks per person per leaf (total and unfunded), with "team" expanded to unnamed members.
    rows, cols, wk, uf = [], [], [], []
    for li, (lab, it) in enumerate(leaves):
        named = {a.person for a in it.assignments if a.person.lower() != TEAM}
        if not any(a.lead for a in it.assignments): checks.append(Check('fix', lab, 'has no task lead'))
        if not it.assignments or not any(a.weeks for a in it.assignments): checks.append(Check('fix', lab, 'has no weeks assigned'))
        for a in it.assignments:
            if a.unfunded > a.weeks: checks.append(Check('warn', lab, f'{a.person}: unfunded weeks ({a.unfunded:g}) exceed weeks ({a.weeks:g})'))
            if a.person.lower() == TEAM:
                who = [pidx[p] for p in ids if p not in named]
            elif a.person in pidx:
                who = [pidx[a.person]]
            else:
                checks.append(Check('fix', lab, f'"{a.person}" is not on the team; their weeks are not counted')); continue
            rows += who; cols += [li] * len(who); wk += [a.weeks] * len(who); uf += [a.unfunded] * len(who)
    W, U = np.zeros((len(members), len(leaves))), np.zeros((len(members), len(leaves)))
    rows, cols, wk, uf = np.array(rows, int), np.array(cols, int), np.array(wk, float), np.array(uf, float)
    np.add.at(W, (rows, cols), wk)
    np.add.at(U, (rows, cols), uf)
    U[collab] = W[collab]                      # collaborators: always 100% unfunded

    # More weeks of effort on an item than its timeline has weeks: more than full time on it.
    length = np.where((qs >= 0) & (qe >= qs), qe - qs + 1, 0)
    for li, pi in zip(*np.nonzero((W.T > length[:, None]) & (length[:, None] > 0))):
        checks.append(Check('warn', leaves[li][0], f'{ids[pi]} has {W[pi, li]:g} weeks of effort on a {length[li]}-week timeline, more than full time'))

    # Person FTE per year: raw, then rounded; funded = total - unfunded.
    raw_t, raw_u = W @ frac / weeks_per_fte, U @ frac / weeks_per_fte
    rnd = lambda x: mround(x, np.where(x < SMALL_FTE, SMALL_STEP, step[:, None]), rounding)
    fte_t, fte_u = rnd(raw_t), rnd(raw_u)
    person_year = np.stack([fte_t, fte_u, np.round(fte_t - fte_u, 10)], axis=2)        # (P, Y, [total, unfunded, funded])
    person_total = np.round(person_year.sum(1), 10)                                       # (P, 3)
    for m, t in zip(members, person_total[:, 0]):
        if t == 0: checks.append(Check('fix', m.id, 'is on no item, so no effort is counted for them'))

    # Over full time: in some weeks, with each item's effort spread evenly over its timeline; and in a year, in FTE.
    load = W @ np.divide(inside, span[:, None], out=np.zeros(inside.shape), where=span[:, None] > 0)    # (P, weeks)
    over = load > 1 + 1e-9
    edges = np.diff(np.pad(over, ((0, 0), (1, 1))).astype(int), axis=1)                             # +1 where a run starts, -1 after it ends
    for pi in np.nonzero(over.any(1))[0]:
        runs = list(zip(np.nonzero(edges[pi] == 1)[0], np.nonzero(edges[pi] == -1)[0] - 1))
        when = ', '.join(week_span(a, b) for a, b in runs[:3]) + (f' and {len(runs) - 3} more stretches' if len(runs) > 3 else '')
        checks.append(Check('warn', ids[pi], f'has more than full time in {when} (up to {load[pi].max():.2f} FTE), with the effort spread evenly over each timeline'))
    for pi, ys in ((pi, np.nonzero(fte_t[pi] > 1 + 1e-9)[0]) for pi in range(len(members))):
        if len(ys): checks.append(Check('warn', ids[pi], 'has more than 1.0 FTE in ' + ', '.join(f'year {y + 1} ({fte_t[pi, y]:.2f})' for y in ys)))

    # Item FTE (unrounded) and roll-ups up the tree.
    leaf_fte = np.stack([W.sum(0), U.sum(0), W.sum(0) - U.sum(0)], 1) / weeks_per_fte
    items, by_label = {}, {}
    for (lab, it), f, s, e in zip(leaves, leaf_fte, qs, qe):
        by_label[lab] = dict(fte=f, start=s if it.start else None, end=e if it.end else None)
    for lab, d, it, parent in reversed(tree):              # children come after parents, so reverse rolls up
        node = by_label.setdefault(lab, dict(fte=np.zeros(3), start=None, end=None))
        if parent is not None:
            p = by_label.setdefault(parent, dict(fte=np.zeros(3), start=None, end=None))
            p['fte'] = p['fte'] + node['fte']
            if node['start'] is not None: p['start'] = node['start'] if p['start'] is None else min(p['start'], node['start'])
            if node['end'] is not None: p['end'] = node['end'] if p['end'] is None else max(p['end'], node['end'])
    for lab, d, it, parent in tree:
        n = by_label[lab]
        items[lab] = dict(title=it.title, depth=d, parent=parent, fte=n['fte'], start=year_week(n['start']), end=year_week(n['end']))
    return dict(ids=ids, person_year=person_year, person_total=person_total,
                project_total=np.round(person_total.sum(0), 10), items=items,
                leaf_labels=[lab for lab, _ in leaves], year_fraction=frac, weeks=W, unfunded_weeks=U, checks=checks)
