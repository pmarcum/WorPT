"""The tables compile cleanly with worpt.sty and nothing else, in the document classes WorPT users write in.

Every table of every fixture is put in one document, each on its own page, the way a table's readme says to
(\\usepackage{worpt} last in the preamble, then \\input and the table's environment). The document must compile
with no LaTeX errors, in each class that works here (a class whose own empty document does not compile, such as
aastex631 without the revtex4-1 class it is built on, is skipped), and no table may run past the edges of the text. Skipped where pdflatex is not installed.
"""
import functools, html, pathlib, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from worpt.tables import build, paste_in, TABLES, TEMPLATE_DIR
from test_parity_tables import load, CASES

TEMPLATES = sorted(TEMPLATE_DIR.glob('*/main.tex'))
CLASSES = ['article', 'report', '[twocolumn]{aastex631}', '{aastex631}', '[twocolumn]{aastex702}', '{aastex702}', 'revtex4-2']
pytestmark = pytest.mark.skipif(not shutil.which('pdflatex'), reason='pdflatex is not installed')


@pytest.mark.parametrize('name', TABLES)
def test_readme_shows_the_paste_in_block(name):
    """The block a person copies from the readme is the one gooTeX fetches."""
    assert paste_in(name).rstrip('\n') in (TEMPLATE_DIR / name / 'readme.md').read_text()


def documentclass(cls):
    return '\\documentclass' + (cls if cls[0] in '[{' else '{' + cls + '}')


def front(cls):
    """A title, author and abstract, as a paper has: aastex 7 switches to two columns only after them."""
    return ('\\title{A paper}\n\\author{Someone}\n\\affiliation{Somewhere}\n\\email{someone@example.org}\n'
            '\\begin{abstract}An abstract.\\end{abstract}\n\\section{Text}Some text.\n\n') if 'aastex' in cls else ''


# Writes the text block's left edges (odd and even pages) and width to the log, in points; then its top, its height
# and the depth the last line on a page may have below it (\maxdepth).
EDGES = ('\\makeatletter\\AtEndDocument{\\typeout{WORPT EDGES \\strip@pt\\dimexpr1in+\\hoffset+\\oddsidemargin\\relax\\space'
         '\\strip@pt\\dimexpr1in+\\hoffset+\\evensidemargin\\relax\\space\\strip@pt\\textwidth}'
         '\\typeout{WORPT TOP \\strip@pt\\dimexpr1in+\\voffset+\\topmargin+\\headheight+\\headsep\\relax\\space\\strip@pt\\textheight\\space\\strip@pt\\maxdepth}}\\makeatother\n')


def outside_text(folder, pdf):
    """Words printed left or right of the text block (the log has its edges), on pages not turned sideways (a table
    in landscape mode runs along the page, and its words stand on end)."""
    log = pdf.with_suffix('.log').read_text(errors='replace')
    odd, even, width = map(float, re.search(r'WORPT EDGES ([\d.]+) ([\d.]+) ([\d.]+)', log).groups())
    lo, hi = min(odd, even) * 72 / 72.27 - 1, (max(odd, even) + width) * 72 / 72.27 + 1         # TeX points to PDF points
    xml = subprocess.run(['pdftotext', '-bbox', pdf.name, '-'], cwd=folder, capture_output=True, text=True).stdout
    return [w for sideways, words in pages(xml) if not sideways for x0, y0, x1, y1, w in words if x0 < lo or x1 > hi]


def outside_block(folder, pdf):
    """Words printed outside the text block (left, right, above or below), on every page, sideways or not. As on any
    page of text, the last line may reach below the block by \\maxdepth (on a page turned sideways, the block's right
    side is the page's bottom). Left out: page numbers, and the lines the class prints in the margins of the first
    page ("Draft version ..." and "Typeset using ..." in aastex)."""
    log = pdf.with_suffix('.log').read_text(errors='replace')
    odd, even, width = map(float, re.search(r'WORPT EDGES ([\d.]+) ([\d.]+) ([\d.]+)', log).groups())
    top, height, depth = map(float, re.search(r'WORPT TOP ([\d.]+) ([\d.]+) ([\d.]+)', log).groups())
    bp = 72 / 72.27                                                                                  # TeX points to PDF points
    lo, hi, up, down = min(odd, even) * bp - 1, (max(odd, even) + width) * bp + 1, top * bp - 1, (top + height) * bp + 1
    xml = subprocess.run(['pdftotext', '-bbox', pdf.name, '-'], cwd=folder, capture_output=True, text=True).stdout
    out = []
    for k, (sideways, words) in enumerate(pages(xml)):
        margin_lines = [y0 for x0, y0, x1, y1, w in words if w in ('Draft', 'Typeset') and (y0 < up or y0 > down)]
        right, bottom = (hi + depth * bp, down) if sideways else (hi, down + depth * bp)
        out += [(k + 1, w) for x0, y0, x1, y1, w in words
                if (x0 < lo or x1 > right or y0 < up or y1 > bottom) and not ((y0 > down or y1 < up) and w.isdigit())
                and not any(abs(y0 - y) < 2 for y in margin_lines)]
    return out


def pages(xml):
    """(sideways?, words with their boxes) for each page of `pdftotext -bbox` output; on a sideways page most words
    are taller than they are wide."""
    out = []
    for page in xml.split('<page ')[1:]:
        words = [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in
                 re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', page)]
        wide = [(x1 - x0) > (y1 - y0) for x0, y0, x1, y1, w in words if len(w) > 2]
        out.append((bool(wide) and sum(wide) < len(wide) / 2, words))
    return out


@functools.lru_cache(maxsize=None)
def works(cls):
    """Whether an empty document in this class compiles here, without WorPT."""
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / 'empty.tex').write_text(documentclass(cls) + '\n\\begin{document}\nx\n\\end{document}\n')
        subprocess.run(['pdflatex', '-interaction=nonstopmode', 'empty.tex'], cwd=d, capture_output=True, timeout=120)
        log = pathlib.Path(d) / 'empty.log'
        return (pathlib.Path(d) / 'empty.pdf').exists() and log.exists() and not any(
            l.startswith('!') for l in log.read_text(errors='replace').splitlines())


@pytest.mark.parametrize('folder', CASES, ids=[c.name for c in CASES])
@pytest.mark.parametrize('cls', CLASSES)
def test_tables_compile_with_worpt_sty_alone(folder, cls, tmp_path):
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    out = build(load(folder))
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    body = []
    for name in TABLES:
        (tmp_path / f'{name}.tex').write_text(out[name])
        block = paste_in(name)
        assert f'\\input{{{name}}}' in block, f'{name}: the readme should bring the file in with \\input{{{name}}}'
        body.append('\\clearpage\n' + block)
    doc = documentclass(cls) + '\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) + '\n\n'.join(body) + '\n\\end{document}\n'
    (tmp_path / 'doc.tex').write_text(doc)
    for _ in range(2): subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=300)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    errors = [l for l in log.splitlines() if l.startswith('!')]
    assert not errors and (tmp_path / 'doc.pdf').exists(), f'{cls}: {errors[:5]}'
    # a color begun in a box that was measured and thrown away, and ended on the page, upsets pdfTeX's color stack
    assert not re.findall(r'pdfTeX warning.*color', log), f'{cls}: {re.findall(r"pdfTeX warning.*color.*", log)[:3]}'
    # A class can take a column specification it doesn't understand without an error and print parts of it instead
    # (aastex and revtex can't repeat inside a repeat): no such text may show in the tables.
    if shutil.which('pdftotext'):
        text = subprocess.run(['pdftotext', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
        leaked = re.findall(r'\S*(?:\d(?:ex|pt|in|mm|cm)@|@[pcl]\d|\*\d+p)\S*', text)
        assert not leaked, f'{cls}: column specification printed in the table: {leaked[:5]}'
        outside = outside_text(tmp_path, tmp_path / 'doc.pdf')
        assert not outside, f'{cls}: tables run past the edge of the text: {outside[:8]}'


@pytest.mark.parametrize('path', TEMPLATES, ids=[p.parent.name for p in TEMPLATES])
def test_templates_leave_the_document_alone(path):
    """No column types of their own (they would replace the document's), no long tables inside floats."""
    s = path.read_text()
    if path.parent.name not in TABLES: pytest.skip('not made by the server')
    assert '\\newcolumntype' not in s and 'longtable' not in s and 'TaskAddCounter' not in s


@pytest.mark.parametrize('years', [1, 5])
@pytest.mark.parametrize('cls', ['article', '{aastex631}', '{aastex702}', '[twocolumn]{aastex702}', 'revtex4-2'])
@pytest.mark.parametrize('name', ['isANONschedule', 'NOTANONtasks'])
def test_wide_tables_fit_the_page_with_one_line_titles(name, cls, years, tmp_path):
    """The schedule and the tasks table are as wide as the text (in landscape mode when they must be; across both
    columns of a two-column document), long titles are cut short with "...", and nothing runs past the edge."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    import dataclasses
    P = load(CASES[0])
    for g in P.goals:
        g.title = 'A rather long task category title that goes on and on ' + g.title
        for t in g.children: t.title = ('Calibrate the photometric zero points of every field against the reference catalog, then '
                                        'check them night by night and more')
    P = dataclasses.replace(P, n_years=years)
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / f'{name}.tex').write_text(build(P, [name])[name])
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + '\\begin{document}\n' + front(cls) + paste_in(name) + '\n\\end{document}\n')
    subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=300)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    assert not [l for l in log.splitlines() if l.startswith('!')], cls
    assert 'Overfull \\hbox' not in log and 'worpt Warning' not in log, (cls, years)
    if shutil.which('pdftotext'):
        text = subprocess.run(['pdftotext', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
        assert 'Calibrate' in text and 'night by night and more' not in text         # cut short


@pytest.mark.parametrize('cls', ['article', '{aastex631}', '{aastex702}', 'revtex4-2'])
def test_colored_cells_reach_their_lines(cls, tmp_path):
    """colortbl colors a cell \\col@sep beyond its text on each side; in the WorPT tables that is the cell's padding,
    \\tabcolsep, in every class (aastex's tables otherwise leave it at zero, and the color stops short of the lines)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    show = '\\makeatletter\\def\\showpadding{\\typeout{PADDING \\the\\col@sep}}\\makeatother\n\\def\\cols{|l|l|}\n'
    tables = '\\setlength{\\tabcolsep}{4pt}\n' + ''.join(
        f'\\begin{{{env}}}{{\\cols}}\\showpadding a & b\\\\\\end{{{env}}}\n\n' for env in ('WorPTtabular', 'WorPTinlineTabular'))
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + show + '\\begin{document}\n' + tables + '\\end{document}\n')
    subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=120)
    assert re.findall(r'PADDING (\S+)', (tmp_path / 'doc.log').read_text(errors='replace')) == ['4.0pt', '4.0pt'], cls


@pytest.mark.parametrize('name', ['isANONtasks', 'NOTANONhst', 'isANONtravel'])
def test_tables_turn_sideways_on_a_page_too_narrow_for_them(name, tmp_path):
    """On a page 3 inches wide these tables don't fit even when their Task or Role column (or, for travel, the spacing
    between columns) is as small as it may be, so they are set in landscape mode, and fit there."""
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / f'{name}.tex').write_text(build(load(CASES[1]), [name])[name])
    (tmp_path / 'doc.tex').write_text('\\documentclass{article}\n\\setlength{\\textwidth}{3in}\n' + paste_in('worpt') + '\\begin{document}\n'
                                      + paste_in(name) + '\n\\end{document}\n')
    subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=120)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log and 'worpt Warning' not in log
    xml = subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
    assert [sideways for sideways, words in pages(xml) if words] == [True], name


@pytest.mark.parametrize('years', [1, 2, 3])
@pytest.mark.parametrize('cls', ['article', '{aastex702}', '[twocolumn]{aastex702}', 'revtex4-2'])
def test_task_timeline_header_takes_one_line_from_two_years_on(cls, years, tmp_path):
    """Over a timeline of two years or more, "TASK TIMELINE" fits on one line (a header row saved); over one year it
    takes two (TASK, then TIMELINE)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    import dataclasses
    P = dataclasses.replace(load(CASES[0]), n_years=years)
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'isANONschedule.tex').write_text(build(P, ['isANONschedule'])['isANONschedule'])
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) + paste_in('isANONschedule') + '\n\\end{document}\n')
    subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=300)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log
    lines = subprocess.run(['pdftotext', '-layout', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout.splitlines()
    assert any('TASK TIMELINE' in l for l in lines) == (years > 1), (cls, years)
    assert not outside_text(tmp_path, tmp_path / 'doc.pdf')


# ------------------------------------------------ a schedule too tall for one page
def tall_plan(categories=5, tasks=9):
    from worpt.model import Item
    from test_tables import proposal, task, person
    team = [person('a', 'PI', 'Alpha'), person('b', 'co-I(1)', 'Beta'), person('c', 'pd(1)', 'Gamma')]
    return proposal([Item(f'Category {g}', children=[
        Item(f'Task {g}.{t}', children=[task(f'Subtask {g}.{t}.{k}', [('a', 2, 0), ('c', 1, 1)], (1, 5 * k), (2, 10)) for k in (1, 2)])
        if t % 3 == 0 else task(f'Task {g}.{t} doing something useful', [('a', 4, 0), ('b', 2, 0)], (1, t), (2, 20)) for t in range(1, tasks + 1)])
        for g in range(1, categories + 1)], team, n_years=3)


def schedule_doc(tmp_path, cls, P, extra=''):
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'isANONschedule.tex').write_text(build(P, ['isANONschedule'])['isANONschedule'])
    block = paste_in('isANONschedule').replace('\\input{isANONschedule} % reset file parameters', '\\input{isANONschedule}\n' + extra)
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) +
                                      'Before the table, see Table~\\ref{tab:isANONschedule}.\n\n' + block + '\nAfter the table.\n\\end{document}\n')


def compile_doc(tmp_path, runs=2):
    for _ in range(runs): subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=300)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    text = subprocess.run(['pdftotext', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
    return log, text


@pytest.mark.parametrize('cls', ['article', '{aastex702}', '{aastex631}', 'revtex4-2'])
def test_a_schedule_too_tall_for_a_page_runs_over_several(cls, tmp_path):
    """Set where it is written, its headings on every page, "continued" notes at the breaks, the caption once at the end;
    nothing runs past the edges, and \\ref finds it."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    schedule_doc(tmp_path, cls, tall_plan())
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log and 'Float too large' not in log, cls
    parts = text.count('TASK TITLES')
    assert parts >= 2 and text.count('continued on next page') == parts - 1 and text.count('(continued)') == parts - 1, (cls, parts)
    assert text.count('Resource-loaded project schedule') == 1 and 'Table ??' not in text and 'Table~??' not in text
    on = lambda words: next(k for k, page in enumerate(text.split('\f')) if words in page)        # the page it is on
    assert on('Before the table') == on('TASK TITLES') and on('Resource-loaded') <= on('After the table')   # set where it is written
    assert on('Funded FTE') == on('Unfunded FTE') == on('Resource-loaded'), 'the foot and the caption on one page'
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), cls


@pytest.mark.parametrize('cls', ['article', '{aastex702}', '{aastex631}', 'revtex4-2'])
def test_a_landscape_schedule_too_tall_for_a_page_runs_over_sideways_pages(cls, tmp_path):
    """In landscape mode, a schedule too tall for its sideways page runs on over more sideways pages, from a page of its
    own: the text before it and after it stays upright (aastex and revtex turn every page if lscape is loaded, so
    WorPT turns its own pages)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    schedule_doc(tmp_path, cls, tall_plan(6), '\\LandScapetrue')
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log and 'Float too large' not in log, cls
    parts = text.count('TASK TITLES')
    assert parts >= 2 and text.count('continued on next page') == parts - 1 and text.count('(continued)') == parts - 1, (cls, parts)
    assert text.count('Resource-loaded project schedule') == 1 and 'Table ??' not in text
    sideways = [s for s, words in pages(subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout)]
    on = lambda words: next(k for k, page in enumerate(text.split('\f')) if words in page)
    table = range(on('TASK TITLES'), on('Resource-loaded') + 1)
    assert len(table) == parts and all(sideways[k] for k in table), sideways
    assert not sideways[on('Before the table')] and not sideways[on('After the table')] and on('Before the table') < table[0] < table[-1] < on('After the table'), sideways
    assert on('Funded FTE') == on('Unfunded FTE') == on('Resource-loaded'), 'the foot and the caption on one page'
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), cls


@pytest.mark.parametrize('cls, landscape', [('article', ''), ('{aastex702}', ''), ('revtex4-2', ''), ('article', '\\LandScapetrue'), ('{aastex702}', '\\LandScapetrue')])
def test_a_schedule_across_pages_is_right_on_the_first_run(cls, landscape, tmp_path):
    """longtable usually needs reruns to line up its headings with its rows; every heading and foot here has a hidden row
    giving each column its width, so the first run already looks like the last (gooTeX runs pdflatex once)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    schedule_doc(tmp_path, cls, tall_plan(), landscape)
    where = lambda: [(round(x0, 1), round(y0, 1), w) for sideways, words in pages(subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout)
                     for x0, y0, x1, y1, w in words if w in ('TASK', 'TIMELINE', 'YR1', 'YR2', 'YR3', 'TEAM', 'Funded', '4.60')]
    compile_doc(tmp_path, 1); first = where()
    compile_doc(tmp_path, 2); assert first == where() and len(first) > 8


@pytest.mark.parametrize('cls', ['article', '{aastex702}', '{aastex631}', 'revtex4-2'])
def test_a_schedule_across_pages_does_not_break_under_a_title(cls, tmp_path):
    """No page ends right under a category's title, or between a task and its first subtask (aastex and revtex end every
    row with a mark allowing a break; the schedule's own "no break here" has to take its place)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    ends = []
    for categories in (4, 5, 6, 7):
        schedule_doc(tmp_path, cls, tall_plan(categories))
        compile_doc(tmp_path, 1)
        text = subprocess.run(['pdftotext', '-layout', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
        ends += [[l for l in page.splitlines() if re.search(r'Category \d|Task \d|Subtask \d', l)][-1].strip() for page in text.split('\f') if 'continued on next page' in page]
    assert len(ends) >= 3, ends
    assert not [e for e in ends if re.search(r'Category \d|Task \d+\.\d+(\s|$)', e) and 'doing something' not in e], ends


@pytest.mark.parametrize('landscape', ['', '\\LandScapetrue'], ids=['portrait', 'landscape'])
@pytest.mark.parametrize('cls', ['[twocolumn]{aastex702}', '[twocolumn]{aastex631}', '[reprint]{revtex4-2}', '[twocolumn]{article}'])
def test_a_schedule_across_pages_in_two_columns(cls, landscape, tmp_path):
    """In a two-column document, a schedule too tall for a page runs over pages across both columns. aastex and revtex
    start it below the text before it and resume the two columns under it; other classes give it pages of its own. In
    landscape mode its pages are turned sideways, and the pages before and after are not."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    schedule_doc(tmp_path, cls, tall_plan(6), landscape)
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log and 'Float too large' not in log, cls
    parts = text.count('TASK TITLES')
    assert parts >= 2 and text.count('continued on next page') == parts - 1 and text.count('(continued)') == parts - 1, (cls, parts)
    assert text.count('Resource-loaded project schedule') == 1 and '??' not in text
    on = lambda words: next(k for k, page in enumerate(text.split('\f')) if words in page)
    assert on('Funded FTE') == on('Unfunded FTE') == on('Resource-loaded'), 'the foot and the caption on one page'
    sideways = [s for s, words in pages(subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout)]
    table = range(on('TASK TITLES'), on('Resource-loaded') + 1)
    assert all(sideways[k] for k in table) == bool(landscape) and not sideways[on('Before the table')] and not sideways[on('After the table')]
    same_page = 'article' not in cls and not landscape                     # aastex and revtex switch columns within a page
    assert (on('Before the table') == table[0]) == same_page and (on('After the table') == table[-1]) == same_page, (cls, landscape)
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), cls


@pytest.mark.parametrize('name', ['isANONschedule', 'isANONtasks', 'NOTANONtasks', 'NOTANONhst', 'isANONtravel'])
@pytest.mark.parametrize('cls', ['[twocolumn]{aastex702}', '[twocolumn]{aastex631}', '[reprint]{revtex4-2}', '[twocolumn]{article}'])
def test_a_sideways_table_in_two_columns_stays_inside_the_text(cls, name, tmp_path):
    """rotating sets a sideways table across both columns only when \\if@twocolumn is true; aastex631 and revtex4-2 leave
    it false in a two-column document, so there WorPT sets the table on its own sideways page; either way, nothing of
    it runs past the edges of the text."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / f'{name}.tex').write_text(build(load(CASES[0]), [name])[name])
    block = re.sub(r'(\\input\{' + name + r'\}[^\n]*\n)', lambda m: m.group(1) + '\\LandScapetrue\n', paste_in(name), count=1)
    assert '\\LandScapetrue' in block
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) +
                                      'Before the table.\n\n' + block + '\nAfter the table.\n\\end{document}\n')
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log, cls
    sideways = [s for s, words in pages(subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout)]
    assert True in sideways and not sideways[0], sideways
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), (cls, name)


@pytest.mark.parametrize('setting, tall, parts', [('', False, 1), ('always', False, 1), ('never', True, 1), ('always', True, 2)])
def test_the_switch_for_a_schedule_across_pages(setting, tall, parts, tmp_path):
    """auto (the default): one page when it fits; always: set where it is written, across pages if need be; never: one page."""
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    schedule_doc(tmp_path, 'article', tall_plan() if tall else tall_plan(2, 4), f'\\def\\ScheduleAcrossPages{{{setting}}}' if setting else '')
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')]
    assert text.count('TASK TITLES') == parts and text.count('continued on next page') == parts - 1
    assert ('Float too large' in log) == (setting == 'never'), 'never keeps a tall schedule on one page, as before'
    assert ('longtable' in log.split('\\begin{document}')[-1] and 'LT@' in (tmp_path / 'doc.aux').read_text()) == (setting == 'always')


# ------------------------------------------------ the work-effort table (NASA's Table of Work Effort)
def work_effort_doc(tmp_path, cls, P, extra=''):
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'NOTANONworkEffort.tex').write_text(build(P, ['NOTANONworkEffort'])['NOTANONworkEffort'])
    block = paste_in('NOTANONworkEffort').replace('\\input{NOTANONworkEffort} % reset file parameters', '\\input{NOTANONworkEffort}\n' + extra)
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) +
                                      'Before the table, see Table~\\ref{tab:NOTANONworkEffort}.\n\n' + block + '\nAfter the table.\n\\end{document}\n')


def work_effort_plan(years, people=0):
    """A real plan over `years` years, with months on other funded projects; or `people` copies of its team, no tasks."""
    import copy, dataclasses
    P = dataclasses.replace(load(CASES[1]), n_years=years)
    for m in P.members: m.other_months = [1.5] * years
    if not people: return P
    team = []
    for k in range(people):
        m = copy.deepcopy(P.members[k % len(P.members)]); m.id, m.last, m.role = f'x{k}', f'Person{k:02d}', 'co-I(1)' if k else 'PI'
        team.append(m)
    return dataclasses.replace(P, members=team, goals=[])


@pytest.mark.parametrize('years', [1, 3, 5])
@pytest.mark.parametrize('cls', ['article', '{aastex702}', '{aastex631}', 'revtex4-2', '[twocolumn]{aastex702}', '[reprint]{revtex4-2}'])
def test_the_work_effort_table_fits_the_page(cls, years, tmp_path):
    """As wide as the text, upright or sideways (narrower spacing, then landscape mode, then smaller headings over the
    months, as needed), with nothing past the edges; five years fit in aastex and revtex (not in plain article, whose
    text is narrow: there WorPT warns)."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    work_effort_doc(tmp_path, cls, work_effort_plan(years))
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')], cls
    if cls == 'article' and years == 5:
        assert 'The work effort table is wider than the page' in log    # (the log wraps the rest of the line)
        return
    assert 'Overfull \\hbox' not in log and 'worpt Warning' not in log, (cls, years)
    assert text.count('Commitment (months per year)') == 1 and 'Sum of work effort' in text and '??' not in text
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), (cls, years)


@pytest.mark.parametrize('landscape', ['', '\\LandScapetrue'], ids=['portrait', 'landscape'])
@pytest.mark.parametrize('cls', ['article', '{aastex702}', '[twocolumn]{aastex702}', 'revtex4-2'])
def test_a_work_effort_table_for_a_large_team_runs_over_pages(cls, landscape, tmp_path):
    """Its headings repeated on each page, "continued" notes at the breaks; the sums, the Comments row and the caption
    together at the end; right on the first run; nothing past the edges."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    work_effort_doc(tmp_path, cls, work_effort_plan(1, people=70), landscape)
    where = lambda: [(round(x0, 1), round(y0, 1), w) for sideways, words in pages(subprocess.run(['pdftotext', '-bbox', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout)
                     for x0, y0, x1, y1, w in words if w in ('Name', 'Role', 'Commitment', 'Year', 'Sum', 'Comments:', 'Person00', 'Person69')]
    log, text = compile_doc(tmp_path, 1); first = where()
    log, text = compile_doc(tmp_path, 2)
    assert first == where(), 'the first run already looks like the last'
    assert not [l for l in log.splitlines() if l.startswith('!')] and 'Overfull \\hbox' not in log, cls
    parts = text.count('Commitment (months per year)')
    assert parts >= 2 and text.count('continued on next page') == parts - 1 and text.count('(continued)') == parts - 1, (cls, parts)
    on = lambda words: next(k for k, page in enumerate(text.split('\f')) if words in page)
    assert on('Sum of work effort') == on('Comments:') == on('Table of work effort'), 'the end of the table on one page'
    assert text.count('Table of work effort') == 1 and '??' not in text
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), cls


def test_a_work_plan_with_no_papers_says_so_where_the_list_goes(tmp_path):
    from worpt.model import Item, Person, Proposal
    out = build(Proposal('T', 'NASA', 1, [Person('PI', 'PI', True, last='Doe')], [Item('Goal')]), ['isANONpapers'])
    (tmp_path / 'isANONpapers.tex').write_text(out['isANONpapers']); shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'doc.tex').write_text('\\documentclass{article}\n' + paste_in('worpt') + '\\begin{document}\n' + paste_in('isANONpapers') + '\\end{document}\n')
    log, text = compile_doc(tmp_path, runs=1)
    assert not [l for l in log.splitlines() if l.startswith('!')]
    assert 'no planned papers: the work plan has no tasks titled' in ' '.join(text.split()) and 'there are no planned papers to list' in ''.join(log.splitlines())


def test_typed_ampersand_percent_and_hash_compile_in_every_table(tmp_path):
    """A title, name, institution, summary or non-labor item typed with a bare &, % or # compiles in every table and
    prints as typed (task B1.3 "Astrophysical Validation & Scaling" stopped a whole document)."""
    if not works('{aastex702}'): pytest.skip('aastex702 does not work on this machine')
    from worpt.model import Item, NonlaborItem, Person, Proposal
    from test_tables import task
    pi = Person('PI', 'PI', True, last='Doe & Roe', first='Jane', institution='Lab #3 & Co', position='50% PI',
                bio_summary='will lead A1 & A2 (50%).', task_summary='#1 & #2', trips=[[1, 0]])
    goals = [Item('Science & Tests', children=[task('Validation & Scaling', [('PI', 4, 0)]), task('Paper 1: Halos & 100% #1', [('PI', 2, 0)])])]
    out = build(Proposal('T', 'NASA', 1, [pi], goals, nonlabor=[NonlaborItem('Materials & Supplies', [100])]))
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    for name in TABLES: (tmp_path / f'{name}.tex').write_text(out[name])
    (tmp_path / 'doc.tex').write_text(documentclass('{aastex702}') + '\n' + paste_in('worpt') + '\\begin{document}\n' +
                                      '\n'.join('\\clearpage\n' + paste_in(n) for n in TABLES) + '\n\\end{document}\n')
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')], [l for l in log.splitlines() if l.startswith('!')][:3]
    flat = ' '.join(text.split())
    for typed in ('Validation & Scaling', 'Science & Tests', 'Halos & 100% #1', 'A1 & A2 (50%)', 'Lab #3 & Co', 'Materials & Supplies', 'Doe & Roe'):
        assert typed in flat, typed


@pytest.mark.parametrize('cls', ['article', '{aastex702}', '[twocolumn]{aastex702}', '{aastex631}', 'revtex4-2'])
def test_planned_papers_list(cls, tmp_path):
    """\\listplannedpapers gives each paper as a paragraph: its label and finish (Paper 1 (Year 1, Q2):), the title in
    italics, the description (paragraphs kept, your own macros and references working); a paper with no timeline has no
    date. Later lines are indented, and everything stays inside the margins. The settings switch the dates and
    descriptions off and make "Publication I" labels; the file being read twice lists each paper once."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    if not shutil.which('pdftotext'): pytest.skip('pdftotext is not installed')
    from worpt.model import Item, Person, Proposal
    from test_tables import task
    goals = [Item('Science', children=[
        task('Paper: Streams', [('PI', 2, 0)], start=(2, 1), end=(2, 30)),
        Item('Paper 5: Exploring the LSB universe', description='we will explore \\RST/WFI & more, as in Sec.~\\ref{sec:m}. ' + 'And more words to wrap. ' * 6 + '\n\nA second paragraph.',
             children=[task('Imaging', [('PI', 2, 0)], start=(1, 1), end=(1, 20))]),
        Item('Paper: Undated')])]
    out = build(Proposal('T', 'NASA', 2, [Person('PI', 'PI', True, last='Doe')], goals), ['isANONpapers'])
    (tmp_path / 'isANONpapers.tex').write_text(out['isANONpapers']); shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n\\newcommand\\RST{Roman}\n' + paste_in('worpt') + EDGES + '\\begin{document}\n' + front(cls) +
        '\\section{Methods}\\label{sec:m}\nText.\n\n' + paste_in('isANONpapers') +
        '\nShort:\n\\PlannedPaperDatesfalse\\PlannedPaperDescriptionsfalse\\def\\PlannedPaperLabel#1{\\textbf{Publication~\\WorPTRoman{#1}}}\\listplannedpapers\n\\end{document}\n')
    log, text = compile_doc(tmp_path)
    assert not [l for l in log.splitlines() if l.startswith('!')], cls
    flat = re.sub(r'Sec\. \w+\.', 'Sec. N.', ' '.join(text.split()).replace('- ', ''))       # whatever the class numbers it
    assert re.search(r'Paper 1 \(Year 1, Q2\): Exploring the LSB universe we will explore Roman/WFI & more, as in Sec\. N\. (And more words to wrap\. ){6}A second paragraph\. '
                     r'Paper 2 \(Year 2, Q3\): Streams Paper 3: Undated Short:', flat), flat
    assert 'Publication I: Exploring the LSB universe Publication II: Streams Publication III: Undated' in flat, flat
    assert flat.count('Paper 1 (Year 1, Q2)') == 1
    assert not outside_block(tmp_path, tmp_path / 'doc.pdf'), cls
