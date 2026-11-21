"""The table preview: newest AASTeX that works, one compile at a time, 60 seconds at most, kept on disk for 30 days."""
import base64, os, shutil, threading, time
import pytest
from worpt import preview as P
from test_server import Api, create_app, KEY, READ

needs_tex = pytest.mark.skipif(not P.available(), reason='pdflatex or pdftocairo is not installed')


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(P, 'CACHE_DIR', tmp_path / 'previews'); monkeypatch.setattr(P, '_cls', [])
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
    """A compile that would never end is stopped. (Only the answer is checked, not the time it took: a small shared
    server can be slow to start and stop programs; without the limit this test would never end.)"""
    monkeypatch.setattr(P, 'LIMIT_SECONDS', 3); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    out = P.render('isANONfte', '\\def\\forever{\\forever}\\forever\n')
    assert out == dict(error='The preview took longer than 3 seconds, so it was stopped.')


def fake_compiles(monkeypatch):
    made = []
    monkeypatch.setattr(P, 'available', lambda: True); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    monkeypatch.setattr(P, '_compile', lambda cls, name, latex: made.append(latex) or dict(pages=[latex], document_class=cls, seconds=0))
    return made


def test_a_table_that_has_not_changed_is_not_drawn_again(monkeypatch, tmp_path):
    made = fake_compiles(monkeypatch)
    for latex in ('v0', 'v1', 'v0', 'v1', 'v0'): assert P.render('isANONfte', latex)['pages'] == [latex]
    assert made == ['v0', 'v1'] and len(list((tmp_path / 'previews').glob('*.json'))) == 2
    assert P.render('isANONtravel', 'v0') and made == ['v0', 'v1', 'v0']          # another table with the same text is another picture
    monkeypatch.setattr(P, '_cls', [])                                  # a restart: the pictures are still there
    P.render('isANONfte', 'v1'); assert made == ['v0', 'v1', 'v0']


def test_a_picture_not_looked_at_for_30_days_is_deleted(monkeypatch, tmp_path):
    made = fake_compiles(monkeypatch)
    P.render('isANONfte', 'old'); P.render('isANONfte', 'used')
    files = {f.read_text(): f for f in (tmp_path / 'previews').glob('*.json')}
    long_ago = time.time() - 31 * 86400
    for f in files.values(): os.utime(f, (long_ago, long_ago))
    P.render('isANONfte', 'used')                                               # looked at: its 30 days start again
    P.render('isANONfte', 'new')                                                # keeping a new picture clears the old ones
    left = sorted(f.read_text() for f in (tmp_path / 'previews').glob('*.json'))
    assert [('used' in t, 'new' in t) for t in left] == [(False, True), (True, False)] and made == ['old', 'used', 'new']


def test_a_failed_picture_is_not_kept(monkeypatch, tmp_path):
    tries = []
    monkeypatch.setattr(P, 'available', lambda: True); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    monkeypatch.setattr(P, '_compile', lambda cls, name, latex: tries.append(1) or dict(error='no'))
    P.render('isANONfte', 'x'); P.render('isANONfte', 'x')
    assert len(tries) == 2 and not list((tmp_path / 'previews').glob('*.json'))


def test_one_compile_at_a_time(monkeypatch):
    running, most = [0], [0]
    def slow(cls, name, latex):
        running[0] += 1; most[0] = max(most[0], running[0]); time.sleep(0.3); running[0] -= 1
        return dict(pages=[latex], document_class=cls, seconds=0.3)
    monkeypatch.setattr(P, 'available', lambda: True); monkeypatch.setattr(P, 'document_class', lambda: 'article')
    monkeypatch.setattr(P, '_compile', slow)
    threads = [threading.Thread(target=P.render, args=('isANONfte', f'v{i}')) for i in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert most[0] == 1


def test_the_dashboard_always_gets_a_preview_and_gootex_when_it_asks(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'render', lambda name, latex: dict(pages=['x'], document_class='article', seconds=0))
    client = create_app(str(tmp_path / 'w.db'), KEY, READ).test_client()
    ann = Api(client, 'ann@x.org', 'core')
    p = ann.ok('post', '/api/people', dict(first='Ann', last='Annson', email='ann@x.org'))['person']
    pid = ann.ok('post', '/api/proposals', dict(title='T', program='NASA/ADAP', n_years=1, leads=[dict(person_id=p['id'], short_id='AA', role='PI')]))['proposal']['id']
    assert ann.ok('get', f'/api/proposals/{pid}/tables/isANONfte')['preview']['pages'] == ['x']
    gootex = Api(client, 'gootex', key=READ)
    assert 'preview' not in gootex.ok('get', f'/api/proposals/{pid}/tables/isANONfte')
    assert gootex.ok('get', f'/api/proposals/{pid}/tables/isANONfte?preview=1')['preview']['pages'] == ['x']
    assert 'preview' not in ann.ok('get', f'/api/proposals/{pid}/tables/worpt')
