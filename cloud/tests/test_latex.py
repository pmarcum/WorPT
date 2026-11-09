"""The tables compile cleanly with worpt.sty and nothing else, in the document classes WorPT users write in.

Every table of every fixture is put in one document, each on its own page, the way a table's readme says to
(\\usepackage{worpt} last in the preamble, then \\input and the table's environment). The document must compile
with no LaTeX errors, in each class that works here (a class whose own empty document does not compile, such as
aastex631 without the revtex4-1 class it is built on, is skipped). Skipped where pdflatex is not installed.
"""
import functools, pathlib, re, shutil, subprocess, sys, tempfile
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
    doc = documentclass(cls) + '\n' + paste_in('worpt') + '\\begin{document}\n' + '\n\n'.join(body) + '\n\\end{document}\n'
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


@pytest.mark.parametrize('path', TEMPLATES, ids=[p.parent.name for p in TEMPLATES])
def test_templates_leave_the_document_alone(path):
    """No column types of their own (they would replace the document's), no long tables inside floats."""
    s = path.read_text()
    if path.parent.name not in TABLES: pytest.skip('not made by the server')
    assert '\\newcolumntype' not in s and 'longtable' not in s and 'TaskAddCounter' not in s


@pytest.mark.parametrize('years', [1, 5])
@pytest.mark.parametrize('cls', ['article', '{aastex631}', '{aastex702}', 'revtex4-2'])
def test_schedule_fits_the_page_with_one_line_rows(cls, years, tmp_path):
    """The schedule is as wide as the text (in landscape mode when it must be), long titles are cut short with "...",
    and nothing runs past the edge."""
    if not works(cls): pytest.skip(f'{cls} does not work on this machine, even without WorPT')
    import dataclasses
    P = load(CASES[0])
    for g in P.goals:
        g.title = 'A rather long task category title that goes on and on ' + g.title
        for t in g.children: t.title = 'Calibrate the photometric zero points of every field against the reference catalog and more'
    P = dataclasses.replace(P, n_years=years)
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    (tmp_path / 'NOTANONschedule.tex').write_text(build(P, ['NOTANONschedule'])['NOTANONschedule'])
    (tmp_path / 'doc.tex').write_text(documentclass(cls) + '\n' + paste_in('worpt') + '\\begin{document}\n' + paste_in('NOTANONschedule') + '\n\\end{document}\n')
    subprocess.run(['pdflatex', '-interaction=nonstopmode', 'doc.tex'], cwd=tmp_path, capture_output=True, timeout=300)
    log = (tmp_path / 'doc.log').read_text(errors='replace')
    assert not [l for l in log.splitlines() if l.startswith('!')], cls
    assert 'Overfull \\hbox' not in log and 'worpt Warning' not in log, (cls, years)
    if shutil.which('pdftotext'):
        text = subprocess.run(['pdftotext', 'doc.pdf', '-'], cwd=tmp_path, capture_output=True, text=True).stdout
        assert 'Calibrate' in text and 'reference catalog and more' not in text      # cut short
