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


# Writes the text block's left edges (odd and even pages) and width to the log, in points.
EDGES = ('\\makeatletter\\AtEndDocument{\\typeout{WORPT EDGES \\strip@pt\\dimexpr1in+\\hoffset+\\oddsidemargin\\relax\\space'
         '\\strip@pt\\dimexpr1in+\\hoffset+\\evensidemargin\\relax\\space\\strip@pt\\textwidth}}\\makeatother\n')


def outside_text(folder, pdf):
    """Words printed left or right of the text block (the log has its edges), on pages not turned sideways (a table
    in landscape mode runs along the page, and its words stand on end)."""
    log = pdf.with_suffix('.log').read_text(errors='replace')
    odd, even, width = map(float, re.search(r'WORPT EDGES ([\d.]+) ([\d.]+) ([\d.]+)', log).groups())
    lo, hi = min(odd, even) * 72 / 72.27 - 1, (max(odd, even) + width) * 72 / 72.27 + 1         # TeX points to PDF points
    xml = subprocess.run(['pdftotext', '-bbox', pdf.name, '-'], cwd=folder, capture_output=True, text=True).stdout
    return [w for sideways, words in pages(xml) if not sideways for x0, y0, x1, y1, w in words if x0 < lo or x1 > hi]


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
@pytest.mark.parametrize('name', ['NOTANONschedule', 'NOTANONtasks'])
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
