"""The table preview: newest AASTeX that works, one compile at a time, 60 seconds at most, the last 5 kept."""
import base64, shutil, threading, time
import pytest
from worpt import preview as P
from test_server import Api, create_app, KEY, READ

needs_tex = pytest.mark.skipif(not P.available(), reason='pdflatex or pdftocairo is not installed')


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(P, '_kept', type(P._kept)()); monkeypatch.setattr(P, '_cls', [])
    monkeypatch.setattr(P, 'LOCK_FILE', tmp_path / 'preview.lock')


def test_versions_sort_newest_first():
    names = ['aastex631', 'aastex7', 'aastex62', 'aastex702', 'aastex63', 'aastex701']
    assert sorted(names, key=P._version, reverse=True) == ['aastex702', 'aastex701', 'aastex7', 'aastex631', 'aastex63', 'aastex62']


def test_the_newest_aastex_that_compiles_else_article(monkeypatch):
    monkeypatch.setattr(P, '_aastex_classes', lambda: ['aastex702', 'aastex631'])
    monkeypatch.setattr(P, '_compiles', lambda c: c == 'aastex631')              # 7.0.2 present but not working here
    assert P.document_class() == 'aastex631'
    monkeypatch.setattr(P, '_cls', []); monkeypatch.setattr(P, '_compiles', lambda c: False)
    assert P.document_class() == 'article'


@needs_tex
def test_a_table_comes_back_as_png_pages():
    out = P.render('isANONfte', '\\newenvironment{isANONfte}{\\begin{table}\\centering\\begin{tabular}{|l|}\\hline x\\\\\\hline\\end{tabular}}{\\end{table}}\n')
    assert 'error' not in out, out
    assert len(out['pages']) == 1 and base64.b64decode(out['pages'][0])[:8] == b'\x89PNG\r\n\x1a\n'
    assert out['document_class'] == P.document_class()


@needs_tex
def test_latex_problems_are_reported():
    out = P.render('isANONfte', '\\newenvironment{isANONfte}{\\undefinedcommandhere}{}\n')
    assert out['error'].startswith('LaTeX could not compile this table') and 'Undefined control sequence' in out['error']


@needs_tex
def test_a_compile_is_stopped_after_the_limit(monkeypatch):
    monkeypatch.setattr(P, 'LIMIT_SECONDS', 3)
    t = time.monotonic(); out = P.render('isANONfte', '\\def\\forever{\\forever}\\forever\n')
    assert out == dict(error='The preview took longer than 3 seconds, so it was stopped.') and time.monotonic() - t < 10


def test_the_last_five_are_kept(monkeypatch):
    made = []
    monkeypatch.setattr(P, 'available', lambda: True); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    monkeypatch.setattr(P, '_compile', lambda cls, name, latex: made.append(latex) or dict(pages=[latex], document_class=cls, seconds=0))
    for i in range(6): P.render('t', f'v{i}')
    P.render('t', 'v5'); P.render('t', 'v1')                     # v5 kept; v1 kept (v0 was dropped, the oldest)
    P.render('t', 'v0')
    assert made == ['v0', 'v1', 'v2', 'v3', 'v4', 'v5', 'v0'] and len(P._kept) == 5


def test_one_compile_at_a_time(monkeypatch):
    running, most = [0], [0]
    def slow(cls, name, latex):
        running[0] += 1; most[0] = max(most[0], running[0]); time.sleep(0.3); running[0] -= 1
        return dict(pages=[latex], document_class=cls, seconds=0.3)
    monkeypatch.setattr(P, 'available', lambda: True); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    monkeypatch.setattr(P, '_compile', slow)
    threads = [threading.Thread(target=P.render, args=('t', f'v{i}')) for i in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert most[0] == 1


def test_only_the_dashboard_gets_a_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'render', lambda name, latex: dict(pages=['x'], document_class='article', seconds=0))
    client = create_app(str(tmp_path / 'w.db'), KEY, READ).test_client()
    ann = Api(client, 'ann@x.org', 'core')
    p = ann.ok('post', '/api/people', dict(first='Ann', last='Annson', email='ann@x.org'))['person']
    pid = ann.ok('post', '/api/proposals', dict(title='T', program='NASA/ADAP', n_years=1, leads=[dict(person_id=p['id'], short_id='AA', role='PI')]))['proposal']['id']
    assert ann.ok('get', f'/api/proposals/{pid}/tables/isANONfte')['preview']['pages'] == ['x']
    assert 'preview' not in Api(client, 'gootex', key=READ).ok('get', f'/api/proposals/{pid}/tables/isANONfte')
    assert 'preview' not in ann.ok('get', f'/api/proposals/{pid}/tables/worpt')
