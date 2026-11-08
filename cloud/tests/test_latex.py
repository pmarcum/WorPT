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
CLASSES = ['article', 'report', '[twocolumn]{aastex631}', '{aastex631}', 'revtex4-2']
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


@pytest.mark.parametrize('path', TEMPLATES, ids=[p.parent.name for p in TEMPLATES])
def test_templates_leave_the_document_alone(path):
    """No column types of their own (they would replace the document's), no long tables inside floats."""
    s = path.read_text()
    if path.parent.name not in TABLES: pytest.skip('not made by the server')
    assert '\\newcolumntype' not in s and 'longtable' not in s and 'TaskAddCounter' not in s
