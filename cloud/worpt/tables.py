"""LaTeX tables for gooTeX, built from a Proposal with the repository's latexTableTemplates.

Ported from the Google Sheet version (Code.gs, Jan 2025) so that, given the same data, each table
matches the Sheet's output line for line, except for the deliberate corrections marked FIX:
  FIX-1 non-labor table: the Domestic travel line is the year's total, not the cost of one trip.
  FIX-2 schedule: "team" weeks are multiplied by the number of people it covers (unnamed members),
        and its color follows whether those weeks are unfunded or international.
  FIX-3 HST table: a missing Science/Admin PI falls back to the PI's full name, not its first letter.
  FIX-4 travel caption: trips are counted only within the grant years, and "1 trip" is singular.
  FIX-5 anonymous task list: "team" alongside named experts is shown as "team".
  FIX-6 FTE tables: a person whose unfunded (or total) effort is negligible gets the template's
        "minor" row instead of silently disappearing from that section.
New: subtasks (A1.1, A1.2 ...) appear as task rows; a task that has subtasks shows its rolled-up
timeline and FTE with no people of its own.
"""
import dataclasses, math, os, pathlib, re
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
from .effort import Check, compute, label_tree, TEAM, WEEKS_PER_YEAR, WEEKS_PER_QUARTER, week_index

TEMPLATE_DIR = pathlib.Path(os.environ.get('WORPT_TEMPLATES') or pathlib.Path(__file__).resolve().parents[2] / 'latexTableTemplates')
ROUND_DOLLARS = 5
TABLES = ('NOTANONteamSummaries', 'isANONteamSummaries', 'NOTANONtasks', 'NOTANONfte', 'NOTANONhst', 'isANONschedule',
          'isANONfte', 'isANONtasks', 'isANONtravel', 'isANONnonlabor', 'NOTANONworkEffort', 'isANONpapers')


# ------------------------------------------------ JavaScript-compatible text helpers
def _expand(repl, match, before, after):
    """JavaScript replacement patterns: $$ -> $, $& -> the match, $` -> text before, $' -> text after."""
    out, i = [], 0
    while i < len(repl):
        if repl[i] == '$' and i + 1 < len(repl) and repl[i + 1] in "$&`'":
            out.append({'$': '$', '&': match, '`': before, "'": after}[repl[i + 1]]); i += 2
        else:
            out.append(repl[i]); i += 1
    return ''.join(out)


def one_line(title):
    """A title for a table that keeps its rows to one line, where LaTeX may cut it short between words (worpt.sty's
    \\WorPTfitTitle): math ($...$ or \\(...\\)) is braced so it is never cut in the middle."""
    return re.sub(r'(\$[^$]*\$|\\\(.*?\\\))', r'{\1}', title)


def jrep(s, old, new):
    """JavaScript s.replace('old', new): first occurrence only."""
    i = s.find(old)
    return s if i < 0 else s[:i] + _expand(str(new), old, s[:i], s[i + len(old):]) + s[i + len(old):]


def jsub(s, pattern, new, flags=0, every=True):
    """JavaScript s.replace(/pattern/flags, new); every=True for the g flag."""
    out, pos, new = [], 0, str(new)
    for m in re.finditer(pattern, s, flags):
        out += [s[pos:m.start()], _expand(new, m.group(0), s[:m.start()], s[m.end():])]; pos = m.end()
        if not every: break
    return ''.join(out) + s[pos:]


def fixed(x, n):
    """JavaScript Number.toFixed(n)."""
    q = Decimal(float(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    return str(abs(q) if q == 0 else q)


def general(x):
    """A number with no trailing zeros: 2 -> "2", 1.2 -> "1.2"."""
    return f'{float(x):.10g}'


def dollars(v):
    """Round to the nearest $5 and add thousands commas (Code.gs formatCurrency)."""
    return f'{int(math.floor(v / ROUND_DOLLARS + 0.5) * ROUND_DOLLARS):,}'


def round5(v):
    return math.floor(v / ROUND_DOLLARS + 0.5) * ROUND_DOLLARS


def clean_up(s):
    """Code.gs basicCleanUp: drop % COMMENT lines and blank lines."""
    s = re.sub(r' *% *COMMENT[^\n]+\n', '', s)
    s = re.sub(r'\n *% *COMMENT[^\n]+\Z', '', s)
    s = re.sub(r'\n *\n', '\n', s)
    s = re.sub(r'\n *\Z', '', s, count=1)
    return re.sub(r'\} *\n *\}', '}} \n', s)


def extract(s, start, end):
    """Code.gs extractFormatting: cut the [START]...[END] block out of s; return (rest, block)."""
    block = re.split(r'\[' + start + r'\] *\n', s, flags=re.I)[1]
    block = clean_up(re.split(r' *\n *\[' + end + r'\]', block, flags=re.I)[0])
    first = re.split(r'\[' + start + r'\]', s, flags=re.I)[0]
    endre = r'\[' + end + r'\] *\n' if re.search(r'\[' + end + r'\] *\n', s) else r'\[' + end + r'\] *'
    return clean_up(first + re.split(endre, s)[-1]), block


def template(name):
    return clean_up((TEMPLATE_DIR / name / 'main.tex').read_text())


def style():
    """worpt.sty, the package every table needs (loaded once with \\usepackage{worpt})."""
    return (TEMPLATE_DIR / 'worpt.sty').read_text()


STYLE_BLOCK = '\\usepackage{worpt}   % the last package in the preamble\n'


def paste_in(name):
    """What a document puts where the table goes (its readme shows the same): \\input, the environment, a caption to edit.
    For 'worpt', the preamble line."""
    return STYLE_BLOCK if name == 'worpt' else (TEMPLATE_DIR / name / 'pastein.tex').read_text()


# ------------------------------------------------ everything the tables need, computed once
def full_role(role):
    for pat, full in ((r'admin', 'Administrative PI'), (r'sci', 'Science PI'), (r'pi', 'Principal Investigator'),
                      (r'princ', 'Principal Investigator'), (r'col', 'Collaborator'), (r'co\-I', 'co-Investigator'),
                      (r'gst', 'Graduate Student'), (r'ust', 'Undergraduate Student')):
        if re.search(pat, role, re.I): return full
    return ''


# The team's order, by kind of role (PI, Admin PI, Science PI, co-Is, postdocs, grad students, undergrads, anyone with
# another role, collaborators). A role's kind is its short form without a number (co-I(2) -> co-I): the one-person roles
# are matched whole (so a typed "Pipeline lead" is not the PI), the numbered ones by how they start.
SINGLE_RANKS = {'pi': 0, 'principal-investigator': 0, 'admin-pi': 1, 'administrative-pi': 1, 'sci-pi': 2, 'science-pi': 2}
NUMBERED_RANKS = (('co-i', 3), ('coi', 3), ('pd', 4), ('postdoc', 4), ('gst', 5), ('grad', 5), ('ust', 6), ('undergrad', 6), ('coll', 8))
OTHER_RANK = 7


def role_rank(role):
    base = re.sub(r'[\s_]+', '-', re.sub(r'\(\s*\d+\s*\)\s*$', '', role or '').strip().lower())
    if base in SINGLE_RANKS: return SINGLE_RANKS[base]
    return next((rank for start, rank in NUMBERED_RANKS if base.startswith(start)), OTHER_RANK)


def team_order(members):
    """The team in the tables' order: PI, Admin PI, Science PI, co-Is, postdocs, grad students, undergrads, anyone with
    another role, then collaborators; within each, by last name (ties keep their order). WorPT numbers co-Is and the
    rest in this same order, so co-I 1 comes before co-I 2. members: objects or dicts with role and last."""
    get = lambda m, k: m[k] if isinstance(m, dict) else getattr(m, k)
    return sorted(members, key=lambda m: (role_rank(get(m, 'role')), get(m, 'last')))


def numbered_roles(members):
    """Numbered roles (co-I(n), coll(n), gst(n), pd(n)...) numbered 1, 2, ... within each kind, in team_order, so the
    numbers never leave gaps. Returns the new role for each member, in team_order."""
    get = lambda m, k: m[k] if isinstance(m, dict) else getattr(m, k)
    labels, out = {}, []
    for m in team_order(members):
        new, hit = get(m, 'role'), re.search(r'\( *[0-9]+ *\)', get(m, 'role'))
        if hit:
            base = new.replace(hit.group(0), '', 1).strip()
            labels[base] = labels.get(base, 0) + 1
            new = f'{base}({labels[base]})'
        out.append((m, new))
    return out


def prepare(p):
    r = compute(p.members, p.goals, p.n_years, p.weeks_per_fte, p.rounding)
    n, M = p.n_years, p.members
    mi = {m.id: i for i, m in enumerate(M)}
    people = {}
    for m, new in numbered_roles(M):
        i = mi[m.id]
        trips = np.zeros((n, 2))
        given = np.array(m.trips, float).reshape(-1, 2)[:n] if m.trips else np.zeros((0, 2))
        trips[:len(given)] = given
        people[m.id] = dict(
            m=m, idx=i, newrole=new, full_role=full_role(m.role), us='US' if m.us else 'F',
            name=re.sub(r',\Z', '', f'{m.first} {m.middle} {m.last}, {m.suffix}'.strip()),
            year=[[fixed(v, 2) for v in yr] for yr in r['person_year'][i]], total=[fixed(v, 2) for v in r['person_total'][i]],
            funded_total=r['person_total'][i, 2], trips=trips)
    people[TEAM] = dict(m=None, newrole=TEAM, last=TEAM)
    leaf_idx = {lab: k for k, lab in enumerate(r['leaf_labels'])}
    rows = []
    for lab, depth, it, parent in label_tree(p.goals):
        row = dict(kind=('goal', 'task', 'subtask')[min(depth, 2)], label=lab, title=it.title, short=one_line(it.short_title or it.title),
                   has_children=bool(it.children),
                   start=r['items'][lab]['start'], end=r['items'][lab]['end'], fte=[fixed(v, 2) for v in r['items'][lab]['fte']],
                   lead=None, experts=[])
        if depth and not it.children:
            k = leaf_idx[lab]
            named = {a.person for a in it.assignments if a.person.lower() != TEAM}
            for a in it.assignments:
                if a.person.lower() == TEAM:
                    unnamed = [m for m in M if m.id not in named]
                    e = dict(id=TEAM, weeks=a.weeks, unnamed=unnamed,
                             international=any(not u.us for u in unnamed),
                             unfunded=any(r['unfunded_weeks'][mi[u.id], k] > 0 for u in unnamed))
                elif a.person in mi:
                    e = dict(id=a.person, weeks=a.weeks, international=not M[mi[a.person]].us,
                             unfunded=r['unfunded_weeks'][mi[a.person], k] > 0)
                else:
                    continue                                   # reported by the engine's checks
                if a.lead and row['lead'] is None: row['lead'] = e
                else: row['experts'].append(e)
        rows.append(row)
    return dict(p=p, r=r, n=n, order=[m.id for m in team_order(M)], people=people, rows=rows)


# ------------------------------------------------ the tables
def team_summaries(c):
    t = jsub(template('NOTANONteamSummaries'), r'\[INSERTFILENAME\]', 'NOTANONteamSummaries')
    t, para = extract(t, 'STARTSUMMARYTEMPLATE', 'ENDSUMMARYTEMPLATE')
    out = []
    for pid in c['order']:
        q = c['people'][pid]
        role = q['full_role'] if re.search('hst', c['p'].program, re.I) else q['newrole']
        s = jrep(para, '[INSERTPREFIX]', q['m'].prefix)
        s = jrep(s, '[INSERTNAME]', q['name'])
        s = jrep(s, '[INSERTROLE]', role)
        out.append(jrep(s, '[INSERTBIOSUMMARY]', q['m'].bio_summary))
    _summary_checks(c, False)
    return clean_up(jrep(t, '[INSERTSUMMARIES]', jsub('\n'.join(out), r'\\par *\Z', '', every=False)))


# The anonymous team summaries call each person by their role, spelled out, with the same numbers as the anonymous tables.
ANON_ONE = {'pi': 'The PI', 'sci-pi': 'The Science PI', 'admin-pi': 'The Admin-PI'}
ANON_NUMBERED = {'co-i': 'Co-I', 'coi': 'Co-I', 'pd': 'Postdoc', 'gst': 'Grad student', 'ust': 'Undergrad', 'coll': 'Collaborator'}
# Words after "her" that show it is not possessive ("with her and", "gave her the data"); before any other word it is.
NOT_A_NOUN = set('''a an the and or but nor so yet to in on at by for from of with about as into onto over under through during
    after before since until while when where that this these those which who whom whose will would can could shall should may
    might must is are was were be been being has have had do does did not also too then than if because although though via per
    within without across among between toward towards around up down out off back again both either neither each every all any
    some more most very well here there now already still'''.split())
TITLES = r'(?:(?:Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?[\s~]+)'


def anon_label(role):
    """How the anonymous team summaries call a person: PI -> The PI, co-I(2) -> Co-I 2, coll(1) -> Collaborator 1,
    ust(1) -> Undergrad 1; any other role as typed, after "The"."""
    m = re.fullmatch(r'\s*([A-Za-z][A-Za-z-]*)\s*\(\s*(\d+)\s*\)\s*', role or '')
    if m: return f'{ANON_NUMBERED.get(m.group(1).lower(), m.group(1))} {m.group(2)}'
    return ANON_ONE.get((role or '').strip().lower(), 'The ' + (role or '').strip())


def named_start(q, program):
    """What the named team summaries put in front of a person's text: "Dr. Jane Q. Doe, PI," (full role names for HST)."""
    role = q['full_role'] if re.search('hst', program, re.I) else q['newrole']
    return ' '.join(f"{q['m'].prefix} {q['name']}, {role},".split())


def summary_starts(p):
    """{member id: (named start, anonymous label)}, for the dashboard to show in front of each team summary."""
    c = dict(p=p, people={m.id: dict(m=m, newrole=new, full_role=full_role(m.role),
                                     name=re.sub(r',\Z', '', f'{m.first} {m.middle} {m.last}, {m.suffix}'.strip())) for m, new in numbered_roles(p.members)})
    return {mid: (named_start(q, p.program), anon_label(q['newrole'])) for mid, q in c['people'].items()}


def _name_forms(m):
    """The ways a person's name may be written, longest first: First Middle Last, First Last, Last."""
    forms = [' '.join(x for x in (m.first, m.middle, m.last) if x), ' '.join(x for x in (m.first, m.last) if x), m.last]
    return [f for f in dict.fromkeys(f.strip() for f in forms) if f]


def _sentence_start(before):
    return re.search(r'(\A|[.!?:]["\')\]}]*)\s*\Z', before) is not None


def anonymize(text, me, people):
    """A team summary without names or gendered pronouns. me: the paragraph's person; people: {member id: (Person, label)}.
    Team members' names (with any title such as Dr.) become their labels; she, he, him and the like become the paragraph's
    own label (her or his before a noun: the label's possessive); herself and himself become themself."""
    out, shared = text, {}
    for m, _ in people.values(): shared[m.last] = shared.get(m.last, 0) + 1
    forms = sorted(((f, lab) for m, lab in people.values() for f in _name_forms(m) if f != m.last or shared[m.last] == 1),
                   key=lambda x: -len(x[0]))
    def put(label, at_start, possessive=False):
        lab = label if at_start or not label.startswith('The ') else 'the' + label[3:]
        return lab + ("'s" if possessive else '')
    if forms:
        rx = re.compile(r'(?<![\\\w])' + TITLES + '?(' + '|'.join(re.escape(f) for f, _ in forms) + r')(?!\w)')
        label_of = dict(forms)
        out = rx.sub(lambda h: put(label_of[h.group(1)], _sentence_start(h.string[:h.start()])), out)
    label = people[me][1]
    def pronoun(h):
        word, low, after = h.group(0), h.group(0).lower(), h.string[h.end():]
        start = word[0].isupper()
        if word == 'He' and (not _sentence_start(h.string[:h.start()]) or re.match(r'[\s~]*(?:[IVX]+\b|\d|\+|\$|-)', after)):
            return word                                              # helium (a capital He inside a sentence, He II, He-3)
        if low in ('herself', 'himself'): return 'Themself' if start else 'themself'
        if low in ('his', 'hers'): return put(label, start, True)
        if low == 'her':                                             # possessive before a noun, a number or a LaTeX command
            nxt = re.match(r'[\s~]+(?:([A-Za-z][\w-]*)|[\d\\${])', after)
            return put(label, start, bool(nxt) and (nxt.group(1) is None or nxt.group(1).lower() not in NOT_A_NOUN))
        return put(label, start)                                     # she, he, him
    return re.sub(r"(?<![\\\w])(?:[Ss]he|[Hh]e|[Hh]im|[Hh]er|[Hh]is|[Hh]ers|[Hh]erself|[Hh]imself)(?![\w])", pronoun, out)


def _summary_checks(c, anonymous):
    """Warnings on the team summaries, added to the checks once per table kind."""
    key = 'anon_summary_checks' if anonymous else 'summary_checks'
    if c.get(key): return
    c[key] = True
    for pid in c['order']:
        q = c['people'][pid]; text = (q['m'].bio_summary or '').strip()
        if not anonymous:
            pre = re.escape(q['m'].prefix.strip())
            rest = re.sub(r'\A(?:' + TITLES + (r'|' + pre + r'[\s~]+' if pre else '') + ')', '', text)
            if any(re.match(re.escape(f) + r'(?!\w)', rest) for f in _name_forms(q['m'])):
                c['r']['checks'].append(Check('warn', pid, 'team summary starts with their name, which the table already puts in front of it', pid))
            continue
        anon = anonymize(text, pid, c['anon_people'])
        left = [f for m, _ in c['anon_people'].values() for f in (m.first, m.last) if f and re.search(r'(?<![\\\w])' + re.escape(f) + r'(?!\w)', anon)]
        left += [m.institution for m, _ in c['anon_people'].values() if m.institution.strip() and m.institution.strip().lower() in anon.lower()]
        if left:
            c['r']['checks'].append(Check('warn', pid, 'anonymous team summary still names ' + ', '.join(f'"{x}"' for x in dict.fromkeys(left)), pid))


def team_summaries_anonymous(c):
    t = jsub(template('isANONteamSummaries'), r'\[INSERTFILENAME\]', 'isANONteamSummaries')
    t, para = extract(t, 'STARTSUMMARYTEMPLATE', 'ENDSUMMARYTEMPLATE')
    c.setdefault('anon_people', {pid: (c['people'][pid]['m'], anon_label(c['people'][pid]['newrole'])) for pid in c['order']})
    _summary_checks(c, True)
    out = []
    for pid in c['order']:
        q = c['people'][pid]
        s = jrep(para, '[INSERTLABEL]', c['anon_people'][pid][1])
        out.append(jrep(s, '[INSERTBIOSUMMARY]', anonymize(q['m'].bio_summary, pid, c['anon_people'])))
    return clean_up(jrep(t, '[INSERTSUMMARIES]', jsub('\n'.join(out), r'\\par *\Z', '', every=False)))


def _lastname(c, e):
    return TEAM if e['id'] == TEAM else c['people'][e['id']]['m'].last


def tasks_named(c):
    t = jsub(template('NOTANONtasks'), r'\[INSERTFILENAME\]', 'NOTANONtasks')
    t, cat = extract(t, 'STARTCATEGORYENTRYTEMPLATE', 'ENDCATEGORYENTRYTEMPLATE')
    t, task = extract(t, 'STARTTASKENTRYTEMPLATE', 'ENDTASKENTRYTEMPLATE')
    out = []
    for row in c['rows']:
        if row['kind'] == 'goal':
            out.append(jsub(jsub(cat, r'\[INSERTID\]', row['label']), r'\[INSERTTITLE\]', row['short']))
        else:
            lead = _lastname(c, row['lead']) if row['lead'] else ''
            experts = ', '.join(_lastname(c, e) for e in row['experts'])
            s = jsub(task, r'\[INSERTID\]', row['label'])
            out.append(jsub(jsub(jsub(s, r'\[INSERTTITLE\]', row['short']), r'\[INSERTLEAD\]', lead), r'\[INSERTEXPERTS\]', experts))
    return jrep(t, '[INSERTTABLECONTENTS]', '\n'.join(out))


def _consolidate(roles):
    """co-I(1), co-I(3) -> co-I(1,3) (numbers sorted as text)."""
    merged, prefixes = [], []
    for role in roles:
        pre = role.split('(')[0]
        if pre in prefixes and '(' in role:
            k = prefixes.index(pre)
            nums = [x.strip() for x in merged[k].replace(pre, '', 1).replace('(', '', 1).replace(')', '', 1).split(',')]
            nums.append(role.replace(pre, '', 1).replace('(', '', 1).replace(')', '', 1).strip())
            nums = [general(float(x)) if x else '0' for x in nums]
            merged[k] = pre + '(' + ','.join(sorted(dict.fromkeys(nums))) + ')'
        else:
            merged.append(role); prefixes.append(pre)
    return ', '.join(merged)


def tasks_anonymous(c):
    t = jsub(template('isANONtasks'), r'\[INSERTFILENAME\]', 'isANONtasks')
    t, banner = extract(t, 'STARTBANNERTEMPLATE', 'ENDBANNERTEMPLATE')
    t, task = extract(t, 'STARTTASKTEMPLATE', 'ENDTASKTEMPLATE')
    out = []
    for row in c['rows']:
        if row['kind'] == 'goal':
            out.append(jrep(jrep(banner, '[INSERTCATEGORYID]', row['label']), '[INSERTCATEGORYTITLE]', row['title']))
            continue
        roles = [c['people'][e['id']]['newrole'] for e in row['experts']]          # FIX-5: team shows as "team"
        experts = TEAM if roles == [TEAM] else _consolidate(roles)
        lead = c['people'][row['lead']['id']]['newrole'] if row['lead'] else ''
        quarter = lambda yw: (yw[0], (yw[1] - 1) // WEEKS_PER_QUARTER + 1) if yw else ('', '')     # the quarter a week falls in
        (sy, sq), (fy, fq) = quarter(row['start']), quarter(row['end'])
        s = jrep(task, '[INSERTTASKID]', row['label'])
        for k, v in (('[INSERTTASKTITLE]', row['title']), ('[INSERTLEADROLE]', lead), ('[INSERTEXPERTISEROLE]', experts),
                     ('[INSERTSTARTYEAR]', sy), ('[INSERTSTARTQTR]', sq), ('[INSERTFINISHYEAR]', fy), ('[INSERTFINISHQTR]', fq)):
            s = jrep(s, k, v)
        out.append(s)
    return jrep(t, '[INSERTSUMMARIES]', '\n'.join(out))


def _fte_value(val, places, threshold):
    if val == 0: return '{\\FaintZeros{' + fixed(val, places) + '}}'
    if val <= threshold: return '{$\\leq$' + fixed(threshold, places) + '}'
    return fixed(val, places)


def _fte_section(t, col, c, tp, small_to_zero, label):
    n = c['n']
    per_year, grand, out = [0.0] * n, 0.0, []
    m = re.search(r'leq\$([0-9.]+)', tp['below'])
    minvalue, places0 = float(m.group(1)), len(m.group(1).strip().split('.')[1])
    def places(v):
        k = places0
        if not small_to_zero:
            while v > 0 and float(fixed(v, k)) == 0: k += 1
        return k
    for pid in c['order']:
        q = c['people'][pid]
        total = float(q['total'][col])
        if small_to_zero and 0 < total <= minvalue:
            out.append(jrep(jrep(tp['below'], '[INSERTNAME]', q['name']), '[INSERTROLE]', q['m'].role))   # FIX-6
            continue
        s = jrep(jrep(tp['above'], '[INSERTNAME]', q['name']), '[INSERTROLE]', q['m'].role)
        s = jrep(s, '[INSERTTOTAL]', _fte_value(total, places(total), minvalue))
        vals = []
        for y in range(n):
            v = float(q['year'][y][col])
            vals.append(jrep(tp['fte'], '[INSERTFTEVALUEFORTHISYEAR]', _fte_value(v, places(v), minvalue)))
            per_year[y] += v; grand += v
        out.append(jrep(s, '[INSERTLISTOFFTES]', ''.join(vals)))
    t = jrep(t, f'[INSERT{label}WORKEFFORTLIST]', '\n'.join(out))
    t = jrep(t, f'[INSERTLISTOFANNUAL{label}TOTALS]', ''.join(jrep(tp['total'], '[INSERTTOTALFTEPERYEAR]', _fte_value(v, places(v), minvalue)) for v in per_year))
    return jrep(t, f'[INSERT{label}TOTALOVERYEAR]', _fte_value(grand, places(grand), minvalue))


def fte(c, name):
    n = c['n']
    t = jsub(template(name), r'\[INSERTLATEXFILESUBDIRECTORY\]', c['p'].latex_subdir, every=False)
    for k, v in ((r'\[INSERTFILENAME\]', name), (r'\[INSERTLASTYEARPLUSTHREE\]', n + 3), (r'\[INSERTLASTYEARPLUSTWO\]', n + 2),
                 (r'\[INSERTLASTYEARPLUSONE\]', n + 1), (r'\[INSERTLASTYEAR\]', n)):
        t = jsub(t, k, v)
    tp = {}
    t, year = extract(t, 'STARTYEARLABELTEMPLATE', 'ENDYEARLABELTEMPLATE')
    for key, tag in (('above', 'ABOVETHRESHOLD'), ('below', 'BELOWTHRESHOLD'), ('fte', 'ANNUALFTE'), ('total', 'ANNUALTOTALFTE')):
        t, tp[key] = extract(t, f'START{tag}TEMPLATE', f'END{tag}TEMPLATE')
    t = jrep(t, '[INSERTLISTOFYEARLABELS]', ''.join(jrep(year, '[INSERTYEARNUMBER]', y) for y in range(1, n + 1)))
    t = _fte_section(t, 2, c, tp, False, 'FUNDED')
    t = _fte_section(t, 1, c, tp, True, 'UNFUNDED')
    return _fte_section(t, 0, c, tp, True, 'BOTH')


def hst(c):
    t = jsub(template('NOTANONhst'), r'\[INSERTFILENAME\]', 'NOTANONhst')
    t = clean_up(jsub(t, r'\[INSERTLATEXFILESUBDIRECTORY\]', c['p'].latex_subdir))
    t, rowt = extract(t, 'STARTROWTEMPLATE', 'ENDROWTEMPLATE')
    out, pis = [], {}
    for pid in c['order']:
        q = c['people'][pid]; m = q['m']
        pis[re.sub('[^a-z]', '', m.role.lower())] = q['name']
        s = jsub(rowt, r'\[INSERTNAME\]', q['name'] + ' \\newline{' + q['full_role'] + '}')
        s = jsub(s, r'\[INSERTJOB\]', m.position + ' \\newline{' + m.institution + '} \\newline{' + q['us'] + '}')
        s = jsub(s, r'\[INSERTDESC\]', m.task_summary)
        s = jsub(s, r'\[INSERTFUNDING\]', 'Y' if q['funded_total'] > 0 else 'N')
        out.append(jsub(s, r'\[INSERTFTE\]', q['total'][0]))
    t = jrep(t, '[INSERTTABLECONTENT]', '\n'.join(out))
    pi = pis.get('pi', '')                                                    # FIX-3: the full name
    t = jsub(t, r'\[INSERTADMINPINAME\]', pis.get('adminpi', pi), every=False)
    return jsub(t, r'\[INSERTSCIENCEPINAME\]', pis.get('scipi', pi), every=False)


def _assignment(tp, e, weeks):
    kind = 'international' if e['international'] else 'unfunded' if e['unfunded'] else 'funded'
    return jrep(jrep(tp[kind], '[TEAMID]', 'T' if e['id'] == TEAM else e['id']), '[NUMBERWEEKS]', weeks)


def schedule(c):
    """The resource-loaded schedule: each task's timeline, and a column per team member marking who leads the task and who
    works on it (funded, or partly or wholly unfunded), with each member's FTE over the grant at the foot. The Sheet
    version's template (used to check parity with it) lists assignments as "id weeks" instead; both are filled here."""
    t = template('isANONschedule')
    grid = '[STARTTEAMLEADCELLTEMPLATE]' in t
    m = re.search(r'\\def\\SlicesPerYear\{(\d+)\}', t)        # columns per year: the template says (12, months); the Sheet's had quarters
    n, slices, ntypes = c['n'], int(m.group(1)) if m else 4, 3
    order = c['order']
    t = jsub(t, r'\[INSERTLATEXFILESUBDIRECTORY\]', c['p'].latex_subdir, every=False)
    for k, v in (('FILENAME', 'isANONschedule'), ('NUMBERYEARSLICESPLUSFIVE', n * slices + 5), ('NUMBERYEARSLICESPLUSFOUR', n * slices + 4),
                 ('NUMBERYEARSLICESPLUSTHREE', n * slices + 3), ('NUMBERYEARSLICESPLUSTWO', n * slices + 2),
                 ('NUMBERYEARSLICESPLUSONE', n * slices + 1), ('NUMBERYEARSLICES', n * slices), ('NUMBERFTETYPES', ntypes),
                 ('NUMBERSLICESPERYEARMINUSTWO', slices - 2), ('NUMBERSLICESPERYEAR', slices), ('LASTYEARPLUSTWO', n + 2), ('LASTYEAR', n),
                 ('NUMBERTEAMMINUSONE', len(order) - 1), ('NUMBERTEAM', len(order)), ('LASTCOLUMN', n * slices + len(order) + 2)):
        t = jsub(t, r'\[INSERT' + k + r'\]', v)
    blocks = (('year', 'YEARLABEL'), ('slice', 'YEARSLICELABEL'), ('category', 'CATEGORYSECTION'), ('empty', 'UNCOLOREDTIMELINE'),
              ('task', 'TASKROW'), ('filled', 'COLOREDTIMELINE'), ('id2name', 'IDTONAME'))
    blocks += ((('parent', 'PARENTTASKROW'), ('subtask', 'SUBTASKROW'), ('parent_filled', 'PARENTCOLOREDTIMELINE'), ('lead', 'TEAMLEADCELL'), ('funded', 'TEAMFUNDEDCELL'), ('unfunded', 'TEAMUNFUNDEDCELL'), ('none', 'TEAMEMPTYCELL'),
                ('label_funded', 'FUNDEDUSTEAMLABEL'), ('label_unfunded', 'UNFUNDEDUSTEAMLABEL'), ('label_international', 'INTERNATIONALTEAMLABEL'),
                ('fte_funded', 'TEAMFUNDEDFTE'), ('fte_unfunded', 'TEAMUNFUNDEDFTE'), ('fte_zero', 'TEAMZEROFTE')) if grid else
               (('funded', 'FUNDEDUSTEAMASSIGNMENT'), ('unfunded', 'UNFUNDEDUSTEAMASSIGNMENT'), ('international', 'INTERNATIONALTEAMASSIGNMENT')))
    tp = {}
    for key, tag in blocks:
        t, tp[key] = extract(t, f'START{tag}TEMPLATE', f'END{tag}TEMPLATE')
    t = jrep(t, '[INSERTYEARLABELLIST]', ''.join(jrep(tp['year'], '[INSERTYEARNUMBER]', y) for y in range(1, n + 1)))
    m = re.search(r'\\def\\SlicesPerLabel\{(\d+)\}', t)        # a label may span several columns (a quarter over its months)
    span = int(m.group(1)) if m else 1
    def slice_label(k):
        out = jrep(jrep(tp['slice'], '[INSERTSLICENUMBER]', k), '[INSERTSLICESPERLABEL]', span)
        return jrep(out, '[INSERTLABELRULE]', '@{}|' if k == slices // span else '@{\\QuarterRule}')   # the year line ends a year
    t = jrep(t, '[INSERTYEARSLICELABELLIST]', ''.join(slice_label(k) for y in range(n) for k in range(1, slices // span + 1)))
    def timeline(row):
        if not row['start'] or not row['end']: return tp['empty'] * (n * slices)
        filled = tp['parent_filled'] if grid and row['has_children'] else tp['filled']   # a task with subtasks spans theirs
        slice_of = lambda w: (w // WEEKS_PER_YEAR) * slices + (w % WEEKS_PER_YEAR) * slices // WEEKS_PER_YEAR   # the slice a week falls in
        q0, q1 = slice_of(week_index(row['start'])), slice_of(week_index(row['end']))
        return ''.join(filled if q0 <= q <= q1 else tp['empty'] for q in range(n * slices))
    if grid:
        r, members = c['r'], {pid: c['people'][pid]['m'] for pid in order}
        leaf = {lab: k for k, lab in enumerate(r['leaf_labels'])}
        idx = {pid: c['people'][pid]['idx'] for pid in order}
        def kind(pid):
            return 'international' if not members[pid].us else 'unfunded' if members[pid].collaborator else 'funded'
        t = jrep(t, '[INSERTTEAMLABELLIST]', ''.join(jrep(tp['label_' + kind(pid)], '[TEAMID]', pid) for pid in order))
        def team_cells(row):
            """Lead, funded, unfunded (some or all of the person's weeks on it unfunded) or none, for each member in order."""
            on = set()
            for e in ([row['lead']] if row['lead'] else []) + row['experts']:
                on |= {u.id for u in e['unnamed']} if e['id'] == TEAM else {e['id']}
            lead = row['lead']['id'] if row['lead'] and row['lead']['id'] != TEAM else None
            k = leaf.get(row['label'])
            unfunded = lambda pid: members[pid].collaborator or (k is not None and r['unfunded_weeks'][idx[pid], k] > 0)
            return ''.join(tp['lead'] if pid == lead else tp['none'] if pid not in on else tp['unfunded'] if unfunded(pid) else tp['funded']
                           for pid in order)
        foot = {kind: [c['people'][pid]['total'][j] for pid in order] for kind, j in (('funded', 2), ('unfunded', 1))}
        for kind, values in foot.items():
            t = jrep(t, f'[INSERTTEAM{kind.upper()}FTELIST]',
                     ''.join(jrep(tp['fte_' + (kind if float(v) else 'zero')], '[INSERTFTE]', v) for v in values))
        t = jrep(jrep(t, '[INSERTFTEFUNDEDTOTAL]', fixed(r['project_total'][2], 2)), '[INSERTFTEUNFUNDEDTOTAL]', fixed(r['project_total'][1], 2))
        totals = [fixed(r['project_total'][j], 2) for j in (1, 2)] + [row['fte'][0] for row in c['rows']]
        t = jrep(t, '[INSERTWIDESTFTE]', max(totals, key=len))                    # (categories' totals are among the rows)
    sections, section, tasks = [], None, []
    def close():
        if section is not None and tasks: sections.append(jrep(section, '[INSERTTASKSUNDERTHISCATEGORY]', '\n'.join(tasks)))
    for row in c['rows']:
        if row['kind'] == 'goal':
            close(); tasks = []
            section = jrep(jrep(tp['category'], '[INSERTCATEGORYLABEL]', row['label']), '[INSERTCATEGORYTITLE]', row['short'])
            section = jrep(section, '[INSERTEMPTYYEARSLICESLIST]', tp['empty'] * (n * slices))
            if grid: section = jrep(jrep(section, '[INSERTEMPTYTEAMCELLSLIST]', tp['none'] * len(order)), '[INSERTCATEGORYFTE]', row['fte'][0])
            continue
        kind = 'parent' if grid and row['has_children'] else 'subtask' if grid and row['kind'] == 'subtask' else 'task'
        s = jrep(jrep(tp[kind], '[INSERTTASKLABEL]', row['label']), '[INSERTTASKTITLE]', row['short'])
        s = jrep(s, '[INSERTYEARSLICESLIST]', timeline(row))
        if grid:
            s = jrep(jrep(s, '[INSERTTEAMCELLSFORTHISTASK]', team_cells(row)), '[INSERTFTETOTAL]', row['fte'][0])
        else:
            people = ([_assignment(tp, row['lead'], general(row['lead']['weeks']))] if row['lead'] else []) + [
                _assignment(tp, e, general(e['weeks'] * len(e['unnamed']) if e['id'] == TEAM else e['weeks'])) for e in row['experts']]   # FIX-2
            s = jrep(s, '[INSERTASSIGNMENTLISTFORTHISTASK]', '\\TaskAssignmentDelimiter'.join(people))
            for k, v in zip(('[INSERTFTETOTAL]', '[INSERTFTEUNFUNDED]', '[INSERTFTEFUNDED]'), row['fte']):
                s = jrep(s, k, v)
        tasks.append(s)
    close()
    t = jrep(t, '[INSERTLISTOFCATEGORYSECTIONS]', '\n'.join(sections))
    names = [jrep(jrep(tp['id2name'], '[INSERTTEAMID]', pid), '[INSERTTEAMNAME]', c['people'][pid]['m'].first + '~' + c['people'][pid]['m'].last)
             for pid in order]
    return jrep(t, '[INSERTIDTONAMELIST]', ', '.join(names))


def _travel_costs(p, n):
    """Per-trip costs per year (index 0 = year 1), each component escalated by its own yearly increase."""
    tc, out = p.travel, {}
    grow = lambda base, inc: np.multiply.accumulate(np.r_[base, np.full(max(n - 1, 0), 1.0 + inc)])[:n]   # same order of operations as before
    for d, kind in ((0, 'dom'), (1, 'int')):
        days = tc.days[d]
        parts = dict(airfare=grow(tc.airfare[d], tc.airfare[2]), perdiem=grow(tc.perdiem[d] * days, tc.perdiem[2]),
                     conference=grow(tc.conference[d], tc.conference[2]), ground=grow(tc.ground[d] * days, tc.ground[2]))
        parts['trip'] = parts['airfare'] + parts['perdiem'] + parts['conference'] + parts['ground']
        out[kind] = parts
    return out


def travel_summary(p):
    """Per year: trips (domestic, international) summed over the team, the cost of one trip, and the year's travel cost."""
    n, cost = p.n_years, _travel_costs(p, p.n_years)
    trips = np.zeros((n, 2))
    for m in p.members:
        given = np.array(m.trips, float).reshape(-1, 2)[:n] if m.trips else np.zeros((0, 2))
        trips[:len(given)] += given
    return [dict(year=y + 1, dom_trips=float(trips[y, 0]), int_trips=float(trips[y, 1]),
                 dom_per_trip=float(cost['dom']['trip'][y]), int_per_trip=float(cost['int']['trip'][y]),
                 dom_total=float(cost['dom']['trip'][y] * trips[y, 0]), int_total=float(cost['int']['trip'][y] * trips[y, 1]))
            for y in range(n)]


def _trips_per_year(c):
    return np.sum([c['people'][pid]['trips'] for pid in c['order']], axis=0) if c['order'] else np.zeros((c['n'], 2))


def travel(c):
    p, n = c['p'], c['n']
    cost, trips = _travel_costs(p, n), _trips_per_year(c)
    t = jsub(template('isANONtravel'), r'\[INSERTFILENAME\]', 'isANONtravel')
    t = jsub(t, r'\[INSERTLATEXFILESUBDIRECTORY\]', p.latex_subdir, every=False)
    t = clean_up(t.split('Yr' + str(n + 1))[0])
    t, yeart = extract(t, 'STARTTRAVELYEARTEMPLATE', 'ENDTRAVELYEARTEMPLATE')
    years = []
    for y in range(n):
        s = jsub(yeart, r'\[INSERTYEARNUMBER\]', y + 1)
        for tag, kind, k in (('DOM', 'dom', 0), ('INT', 'int', 1)):
            s = jsub(s, r'\[NUMBER' + tag + r'TRIPS\]', general(trips[y, k]), every=False)
            for f, part in (('AIRFARE', 'airfare'), ('PERDIEM', 'perdiem'), ('CONFERENCE', 'conference'), ('GROUND', 'ground'), ('PERTRIP', 'trip')):
                s = jsub(s, r'\[' + tag + f + r'\]', dollars(cost[kind][part][y]), every=False)
            s = jsub(s, r'\[' + tag + r'ALLTRIPS\]', dollars(cost[kind]['trip'][y] * trips[y, k]), every=False)
        years.append(s)
    t = jrep(t, '[INSERTLISTOFYEARS]', '\n'.join(years))
    t, persont = extract(t, 'STARTPERPERSONNUMBERTRIPSTEMPLATE', 'ENDPERPERSONNUMBERTRIPSTEMPLATE')
    plural = lambda k: '' if k == 1 else 's'                                                          # FIX-4
    lines = []
    for pid in c['order']:
        dom, intl = c['people'][pid]['trips'].sum(0)                                                     # FIX-4: grant years only
        if dom + intl > 0:
            s = jsub(persont, r'\[TEAMROLE\]', c['people'][pid]['m'].role, every=False)
            for k, v in (('NUMDOMTRIPS', general(dom)), ('DOMPLURALITY', plural(dom)), ('NUMINTTRIPS', general(intl)), ('INTPLURALITY', plural(intl))):
                s = jsub(s, r'\[' + k + r'\]', v, every=False)
            lines.append(s)
    t = jrep(t, '[INSERTPERPERSONNUMBERTRIPS]', '\n'.join(lines))
    tc = p.travel
    for k, v in (('NDAYSDOMESTICTRIP', general(tc.days[0])), ('DOMESTICPERDIEMDOLLARS', dollars(tc.perdiem[0])),
                 ('DOMESTICGROUNDTRAVELDOLLARS', dollars(tc.ground[0])), ('NDAYSINTERNATIONALTRIP', general(tc.days[1])),
                 ('INTERNATIONALPERDIEMDOLLARS', dollars(tc.perdiem[1])), ('INTERNATIONALGROUNDTRAVELDOLLARS', dollars(tc.ground[1]))):
        t = jsub(t, r'\[INSERT' + k + r'\]', v, every=False)
    return jsub(t, r'\[INSERTNGRANTYEARS\]', n)


def nonlabor(c):
    p, n = c['p'], c['n']
    cost, trips = _travel_costs(p, n), _trips_per_year(c)
    t = jsub(template('isANONnonlabor'), r'\[INSERTLATEXFILESUBDIRECTORY\]', p.latex_subdir, every=False)
    t = jsub(jsub(jsub(t, r'\[INSERTFILENAME\]', 'isANONnonlabor'), r'\[INSERTLASTYEARPLUSTWO\]', n + 2, every=False), r'\[INSERTLASTYEARPLUSONE\]', n + 1, every=False)
    tp = {}
    for key, tag in (('year', 'YEARLABEL'), ('item', 'NONLABORITEM'), ('cost', 'PERYEARCOST'), ('travelsum', 'PERYEARTRAVELSUM'), ('domint', 'PERYEARDOMINT')):
        t, tp[key] = extract(t, f'START{tag}TEMPLATE', f'END{tag}TEMPLATE')
    t = jrep(t, '[INSERTYEARLABELLIST]', ''.join(jrep(tp['year'], '[INSERTYEARNUMBER]', y) for y in range(1, n + 1)))
    rows = []
    for item in p.nonlabor:
        amounts = (list(item.amounts) + [0.0] * n)[:n]
        if not item.item.strip() or sum(item.amounts) <= 0: continue        # as before: empty lines are left out
        s = jsub(tp['item'], r'\[ITEMDESC\]', item.item.strip(), every=False)
        s = jrep(s, '[INSERTANNUALCOSTLIST]', ''.join(jrep(tp['cost'], '[INSERTPERYEARCOST]', dollars(v)) for v in amounts))
        rows.append(jrep(s, '[SUMOVERYEARS]', dollars(sum(round5(v) for v in amounts))))
    t = jrep(t, '[INSERTNONLABORCOSTSLIST]', '\n'.join(rows))
    dom = cost['dom']['trip'] * trips[:, 0]                                  # FIX-1: the year's total, not one trip
    intl = cost['int']['trip'] * trips[:, 1]
    t = jrep(t, '[INSERTTRAVELSUMMARYLIST]', ''.join(jrep(tp['travelsum'], '[INSERTTRAVELSUMFORTHISYEAR]', dollars(d + i)) for d, i in zip(dom, intl)))
    t = jrep(t, '[TRAVELSUMALLYEARS]', dollars(sum(round5(d) + round5(i) for d, i in zip(dom, intl))))
    t = jrep(t, '[INSERTTRAVELDOMESTICLIST]', ''.join(jrep(tp['domint'], '[INSERTTRAVELFORTHISYEAR]', dollars(v)) for v in dom))
    t = jrep(t, '[DOMSUMALLYEARS]', dollars(sum(round5(v) for v in dom)))
    t = jrep(t, '[INSERTTRAVELINTERNATIONALLIST]', ''.join(jrep(tp['domint'], '[INSERTTRAVELFORTHISYEAR]', dollars(v)) for v in intl))
    return jrep(t, '[INTSUMALLYEARS]', dollars(sum(round5(v) for v in intl)))


# The roles as NASA's Table of Work Effort names them (no numbers): a role's kind is its short form without a number.
WORK_EFFORT_ROLES = {'pi': 'PI', 'principal-investigator': 'PI', 'sci-pi': 'Science PI', 'science-pi': 'Science PI',
                     'admin-pi': 'Admin PI', 'administrative-pi': 'Admin PI', 'co-i': 'Co-I', 'coi': 'Co-I', 'coll': 'Collaborator',
                     'pd': 'Postdoc', 'gst': 'Grad Student', 'ust': 'Undergrad Student'}


def work_effort_role(role):
    base = re.sub(r'[\s_]+', '-', re.sub(r'\(\s*\d+\s*\)\s*$', '', role or '').strip().lower())
    return WORK_EFFORT_ROLES.get(base, re.sub(r'\(\s*\d+\s*\)\s*$', '', role or '').strip())


def work_effort(c):
    """NASA's Table of Work Effort: for each team member and each year, the months funded by this proposal (NASA
    Support), all their months on this project (Total), and their months on other currently funded projects (as entered
    in WorPT); then the sums over the years, and over the team. Months are the FTE the other tables show, times 12, to
    one decimal; the sums add up the months shown."""
    name, n = 'NOTANONworkEffort', c['n']
    t = template(name)
    tp = {}
    for key, tag in (('cols', 'YEARCOLUMNS'), ('year', 'YEARHEADER'), ('project', 'THISPROJECTHEADER'), ('month', 'MONTHHEADER'),
                     ('person', 'PERSON'), ('months', 'MONTHS'), ('sums', 'SUMMONTHS')):
        t, tp[key] = extract(t, f'START{tag}TEMPLATE', f'END{tag}TEMPLATE')
    tenth = lambda v: Decimal(fixed(v, 1))
    shown = lambda v: '\\ZeroMonths' if v == 0 else str(v)
    colors = ['\\WorkEffortOddYearColor' if y % 2 == 0 else '\\WorkEffortEvenYearColor' for y in range(n)] + ['\\WorkEffortSumColor']
    labels = [f'\\YearLabel{{{y + 1}}}' for y in range(n)] + ['\\SumLabel']
    groups = lambda tpl: ''.join(tpl.replace('[INSERTYEARCOLOR]', col).replace('[INSERTYEARLABEL]', lab) for col, lab in zip(colors, labels))
    def cells(tpl, triples):
        return ''.join(jrep(jrep(jrep(tpl, '[INSERTNASASUPPORT]', shown(a)), '[INSERTTOTAL]', shown(b)), '[INSERTOTHERFUNDED]', shown(o)) for a, b, o in triples)
    rows, team, numbers = [], [[Decimal(0)] * 3 for _ in range(n + 1)], []
    for pid in c['order']:
        q = c['people'][pid]
        fte = c['r']['person_year'][q['idx']]
        other = list(q['m'].other_months or [])[:n] + [0] * max(0, n - len(q['m'].other_months or []))
        years = [(tenth(fte[y][2] * 12), tenth(fte[y][0] * 12), tenth(other[y])) for y in range(n)]
        triples = years + [tuple(sum((yr[k] for yr in years), Decimal(0)) for k in range(3))]
        for y, tr in enumerate(triples):
            team[y] = [a + b for a, b in zip(team[y], tr)]
        numbers += [v for tr in triples for v in tr]
        s = jrep(jrep(tp['person'], '[INSERTNAME]', q['name']), '[INSERTROLE]', work_effort_role(q['m'].role))
        rows.append(jrep(s, '[INSERTMONTHS]', cells(tp['months'], triples)))
    numbers += [v for tr in team for v in tr]
    for k, v in (('[INSERTFILENAME]', name), ('[INSERTLASTYEAR]', n), ('[INSERTLASTCOLUMN]', 2 + 3 * (n + 1)),
                 ('[INSERTNUMBERCOLUMNS]', 3 * (n + 1)), ('[INSERTWIDESTNUMBER]', max((str(v) for v in numbers if v), key=len, default='0')),
                 ('[INSERTYEARCOLUMNS]', groups(tp['cols'])), ('[INSERTYEARHEADERS]', groups(tp['year'])),
                 ('[INSERTTHISPROJECTHEADERS]', groups(tp['project'])), ('[INSERTMONTHHEADERS]', tp['month'] * (n + 1)),
                 ('[INSERTPERSONROWS]', '\n'.join(rows)), ('[INSERTSUMMONTHS]', cells(tp['sums'], team))):
        t = t.replace(k, str(v))
    return t


# ------------------------------------------------ planned papers
PAPER = re.compile(r'\s*paper\s*(\d+)\s*:\s*(.*?)\s*\Z', re.I | re.S)


def planned_papers(goals):
    """The work plan's papers: its categories, tasks and subtasks titled "Paper N: title" (any capitals, any spaces), as
    {N: (title, label, description)} in number order, and the checks: a number used more than once (the first in the plan keeps it)
    and a "Paper N:" with no title after it."""
    found, checks = {}, []
    for lab, depth, it, parent in label_tree(goals):
        m = PAPER.match(it.title or '')
        if not m: continue
        n, title = int(m.group(1)), m.group(2)
        if not title: checks.append(Check('warn', lab, f'is titled "Paper {n}:" with nothing after it, so Paper {n} has no title'))
        if n in found:
            checks.append(Check('warn', lab, f'is also titled "Paper {n}:", like {found[n][1]}; Paper {n} keeps {found[n][1]}\'s title'))
        else:
            found[n] = (title, lab, (it.description or '').strip())
    return dict(sorted(found.items())), checks


def papers(c):
    found, checks = planned_papers(c['p'].goals)
    c['r']['checks'].extend(checks)
    lines = ''.join(f'\\WorPTpaper{{{n}}}{{{title}}}{{{desc}}}   % {lab}\n' for n, (title, lab, desc) in found.items())
    return template('isANONpapers').replace('[INSERTFILENAME]', 'isANONpapers').replace('[INSERTPAPERS]', lines.rstrip('\n'))


PERSON_TEXT = ('last', 'first', 'middle', 'prefix', 'suffix', 'institution', 'position', 'bio_summary', 'task_summary')


def latex_text(s):
    """Typed text as LaTeX: a bare &, % or # (one without a backslash in front) is written \\&, \\%, \\#, so that
    "Validation & Scaling" or "50% of the time" print as typed instead of breaking the table (in LaTeX they would start
    a new column, comment out the rest of the line, or name a macro argument). Everything else is left as written,
    LaTeX included (\\&, $M_\\star$, \\textit{...})."""
    return re.sub(r'(?<!\\)([&%#])', r'\\\1', s) if s else s


def as_latex_text(p):
    """The proposal with the text people type (names, institutions, positions, summaries, titles, non-labor items) made
    LaTeX by latex_text."""
    def item(it): return dataclasses.replace(it, title=latex_text(it.title), short_title=latex_text(it.short_title), description=latex_text(it.description),
                                             children=[item(k) for k in it.children])
    def person(m): return dataclasses.replace(m, **{f: latex_text(getattr(m, f)) for f in PERSON_TEXT if hasattr(m, f)})
    return dataclasses.replace(p, members=[person(m) for m in p.members], goals=[item(g) for g in p.goals],
                               nonlabor=[dataclasses.replace(n, item=latex_text(n.item)) for n in p.nonlabor])


def build(proposal, names=TABLES):
    """Return {table name: LaTeX text} plus the engine's checks under '_checks'."""
    c = prepare(as_latex_text(proposal))
    make = dict(NOTANONteamSummaries=team_summaries, isANONteamSummaries=team_summaries_anonymous, NOTANONtasks=tasks_named, NOTANONhst=hst, isANONschedule=schedule,
                NOTANONfte=lambda c: fte(c, 'NOTANONfte'), isANONfte=lambda c: fte(c, 'isANONfte'), isANONtasks=tasks_anonymous,
                isANONtravel=travel, isANONnonlabor=nonlabor, NOTANONworkEffort=work_effort, isANONpapers=papers)
    out = {name: make[name](c) for name in names}
    out['_checks'] = c['r']['checks']
    return out
