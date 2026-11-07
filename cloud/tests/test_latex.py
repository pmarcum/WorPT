"""The tables compile cleanly with worpt.sty and nothing else, in the document classes WorPT users write in.

Every table of every fixture is put in one document, each on its own page, the way a table's readme says to
(\\usepackage{worpt} last in the preamble, then \\input and the table's environment). The document must compile
with no LaTeX errors, in each class installed here. Skipped where pdflatex is not installed (the VM).
"""
import pathlib, re, shutil, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from worpt.tables import build, TABLES, TEMPLATE_DIR
from test_parity_tables import load, CASES

TEMPLATES = sorted(TEMPLATE_DIR.glob('*/main.tex'))
CLASSES = ['article', 'report', '[twocolumn]{aastex631}', '{aastex631}', 'revtex4-2']
pytestmark = pytest.mark.skipif(not shutil.which('pdflatex'), reason='pdflatex is not installed')


def paste_in(name):
    """The paste-in block from the table's readme, as a user copies it."""
    block = re.search(r'(%:+ *start .*?%:+ *end [^\n]*)', (TEMPLATE_DIR / name / 'readme.md').read_text(), re.S).group(1)
    return re.sub(r'<[^>]+>', '', block).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def installed(cls):
    name = re.sub(r'.*\{|\}|\[.*\]', '', cls)
    return subprocess.run(['kpsewhich', name + '.cls'], capture_output=True, text=True).stdout.strip() != ''


@pytest.mark.parametrize('folder', CASES, ids=[c.name for c in CASES])
@pytest.mark.parametrize('cls', CLASSES)
def test_tables_compile_with_worpt_sty_alone(folder, cls, tmp_path):
    if not installed(cls): pytest.skip(f'{cls} is not installed')
    out = build(load(folder))
    shutil.copy(TEMPLATE_DIR / 'worpt.sty', tmp_path)
    body = []
    for name in TABLES:
        (tmp_path / f'{name}.tex').write_text(out[name])
        block = paste_in(name)
        assert f'\\input{{{name}}}' in block, f'{name}: the readme should bring the file in with \\input{{{name}}}'
        body.append('\\clearpage\n' + block)
    macros = r'\newcommand\Chandra{Chandra}\newcommand\Hubble{Hubble}\newcommand\Spitzer{Spitzer}\newcommand\RST{RST}'  # used in sample captions
    doc = '\\documentclass' + (cls if cls[0] in '[{' else '{' + cls + '}') + '\n\\usepackage{worpt}\n' + macros + \
          '\n\\begin{document}\n\\section{Tables}\\label{Subsec:tmeline}\\label{Sec:Baseline}\\label{Sec:Sample}\n' + '\n\n'.join(body) + '\n\\end{document}\n'
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
