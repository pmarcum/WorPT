"""WorPT effort engine: turns weeks assigned on work-plan items into FTE.

Rules (see the WorPT design decisions):
  * Effort, people and timelines live only on lowest-level items (goal > task > subtask).
  * An item's weeks are split across years in proportion to its quarters that fall in each year.
  * Person FTE per year = weeks that year / weeks_per_fte, rounded to a step: 0.01 below 0.1 FTE,
    otherwise the person's FTE accuracy (default 0.05); rounding='nearest' (default) or 'up'.
  * Funded = rounded total - rounded unfunded. All-years figures are sums of rounded yearly values.
  * "team" gives its weeks to every team member not named on that item.
  * Collaborators (role "coll..." or a non-US institution) are always 100% unfunded.
  * Parents roll up from their children: FTE is summed, the timeline spans the children.
Nothing is dropped silently: anything incomplete is reported in `checks`.
"""
from dataclasses import dataclass, field
import numpy as np

TEAM = 'team'
SMALL_FTE, SMALL_STEP, DEFAULT_STEP = 0.1, 0.01, 0.05


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
    start: tuple | None = None   # (year, quarter), both counted from 1
    end: tuple | None = None
    assignments: list = field(default_factory=list)


@dataclass
class Check:
    level: str           # "fix" (needs attention) or "warn"
    item: str            # label such as "A1.2", or a member id
    message: str


def mround(x, step, mode='nearest'):
    """Round to a multiple of `step`: 'nearest' (halves go up, like Google Sheets' MROUND) or 'up' (ceiling)."""
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

    # Year fractions per leaf, from quarter spans.
    n_q = 4 * n_years
    qs = np.array([(it.start[0] - 1) * 4 + it.start[1] - 1 if it.start else -1 for _, it in leaves])
    qe = np.array([(it.end[0] - 1) * 4 + it.end[1] - 1 if it.end else -2 for _, it in leaves])
    qq = np.arange(n_q)
    inside = (qq >= qs[:, None]) & (qq <= qe[:, None])
    span = inside.sum(1)
    frac = np.divide(inside.reshape(len(leaves), n_years, 4).sum(2), span[:, None], out=np.zeros((len(leaves), n_years)), where=span[:, None] > 0)
    for (lab, it), s, e in zip(leaves, qs, qe):
        if it.start is None or it.end is None: checks.append(Check('fix', lab, 'has no timeline, so its weeks are not counted in any year'))
        elif e < s: checks.append(Check('fix', lab, 'ends before it starts'))
        elif e >= n_q: checks.append(Check('fix', lab, f'runs past year {n_years}; weeks after that are not counted'))

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

    # Person FTE per year: raw, then rounded; funded = total - unfunded.
    raw_t, raw_u = W @ frac / weeks_per_fte, U @ frac / weeks_per_fte
    rnd = lambda x: mround(x, np.where(x < SMALL_FTE, SMALL_STEP, step[:, None]), rounding)
    fte_t, fte_u = rnd(raw_t), rnd(raw_u)
    person_year = np.stack([fte_t, fte_u, np.round(fte_t - fte_u, 10)], axis=2)        # (P, Y, [total, unfunded, funded])
    person_total = np.round(person_year.sum(1), 10)                                       # (P, 3)
    for m, t in zip(members, person_total[:, 0]):
        if t == 0: checks.append(Check('fix', m.id, 'is on no item, so no effort is counted for them'))

    # Item FTE (unrounded, as in the Sheet's task columns) and roll-ups up the tree.
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
        q2yq = lambda q: None if q is None else (int(q) // 4 + 1, int(q) % 4 + 1)
        items[lab] = dict(title=it.title, depth=d, parent=parent, fte=n['fte'], start=q2yq(n['start']), end=q2yq(n['end']))
    return dict(ids=ids, person_year=person_year, person_total=person_total,
                project_total=np.round(person_total.sum(0), 10), items=items,
                leaf_labels=[lab for lab, _ in leaves], year_fraction=frac, weeks=W, unfunded_weeks=U, checks=checks)
