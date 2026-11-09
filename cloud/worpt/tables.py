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
import math, os, pathlib, re
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
from .effort import compute, label_tree, TEAM, WEEKS_PER_YEAR, WEEKS_PER_QUARTER, week_index

TEMPLATE_DIR = pathlib.Path(os.environ.get('WORPT_TEMPLATES') or pathlib.Path(__file__).resolve().parents[2] / 'latexTableTemplates')
ROUND_DOLLARS = 5
TABLES = ('NOTANONteamSummaries', 'NOTANONtasks', 'NOTANONfte', 'NOTANONhst', 'NOTANONschedule',
          'isANONfte', 'isANONtasks', 'isANONtravel', 'isANONnonlabor')


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


def team_order(members):
    """The team in the tables' order: PI, Science PI, Admin PI, then by last name (ties keep their order).
    members: objects or dicts with role and last."""
    get = lambda m, k: m[k] if isinstance(m, dict) else getattr(m, k)
    key = lambda m: ('AAAA' if get(m, 'role').lower().startswith('pi') else 'AAAB' if get(m, 'role').lower().startswith('sci')
                     else 'AAAC' if get(m, 'role').lower().startswith('admin') else '') + get(m, 'last')
    return sorted(members, key=key)


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
    t = template('NOTANONschedule')
    grid = '[STARTTEAMLEADCELLTEMPLATE]' in t
    m = re.search(r'\\def\\SlicesPerYear\{(\d+)\}', t)        # columns per year: the template says (12, months); the Sheet's had quarters
    n, slices, ntypes = c['n'], int(m.group(1)) if m else 4, 3
    order = c['order']
    t = jsub(t, r'\[INSERTLATEXFILESUBDIRECTORY\]', c['p'].latex_subdir, every=False)
    for k, v in (('FILENAME', 'NOTANONschedule'), ('NUMBERYEARSLICESPLUSFIVE', n * slices + 5), ('NUMBERYEARSLICESPLUSFOUR', n * slices + 4),
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


def build(proposal, names=TABLES):
    """Return {table name: LaTeX text} plus the engine's checks under '_checks'."""
    c = prepare(proposal)
    make = dict(NOTANONteamSummaries=team_summaries, NOTANONtasks=tasks_named, NOTANONhst=hst, NOTANONschedule=schedule,
                NOTANONfte=lambda c: fte(c, 'NOTANONfte'), isANONfte=lambda c: fte(c, 'isANONfte'), isANONtasks=tasks_anonymous,
                isANONtravel=travel, isANONnonlabor=nonlabor)
    out = {name: make[name](c) for name in names}
    out['_checks'] = c['r']['checks']
    return out
