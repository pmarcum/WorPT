"""The versions in the dashboard's hover text: the server's own commit, and the latest on GitHub (never asked here)."""
import subprocess
import pytest
from worpt import about as A


def head():
    return subprocess.run(['git', '-C', str(A.REPO), 'log', '-1', '--format=%H %cI'], capture_output=True, text=True).stdout.split()


def test_the_server_knows_the_commit_it_started_from():
    sha, date = head()
    assert A.RUNNING == dict(commit=sha[:7], sha=sha, date=date)


def test_page_and_server_versions_from_github(monkeypatch):
    sha, date = head()
    gh = {'Index.html': dict(commit='abc1234', sha='abc1234' + '0' * 33, date='2026-11-09T01:48:00Z'), 'cloud': dict(commit=sha[:7], sha=sha, date=date)}
    asked = []
    monkeypatch.setattr(A, 'latest_commit', lambda owner, repo, path: asked.append((owner, repo, path)) or gh[path])
    monkeypatch.setattr(A, '_github_repo', lambda: ('someone', 'WorPT'))
    assert A.about() == dict(server=dict(commit=sha[:7], date=date), page=dict(commit='abc1234', date='2026-11-09T01:48:00Z'), server_update=False)
    assert asked == [('someone', 'WorPT', 'Index.html'), ('someone', 'WorPT', 'cloud')]
    A.about(); assert len(asked) == 2                                     # asked again only after 10 minutes


def test_server_changes_waiting_on_github(monkeypatch):
    newer = dict(commit='fffffff', sha='f' * 40, date='2026-11-09')       # a commit this checkout doesn't have
    monkeypatch.setattr(A, 'latest_commit', lambda owner, repo, path: newer)
    monkeypatch.setattr(A, '_github_repo', lambda: ('someone', 'WorPT'))
    assert A.about()['server_update'] is True


def test_github_not_reachable(monkeypatch):
    def down(*a): raise OSError('no route to GitHub')
    monkeypatch.setattr(A, 'latest_commit', down)
    monkeypatch.setattr(A, '_github_repo', lambda: ('someone', 'WorPT'))
    v = A.about()
    assert v['server'] == dict(commit=A.RUNNING['commit'], date=A.RUNNING['date']) and v['page'] is None and v['server_update'] is None


def test_the_dashboard_gets_it_with_me(client):
    from test_server import Api
    r = Api(client, 'ann@x.org', 'core').ok('get', '/api/me')
    assert r['about']['server']['commit'] == A.RUNNING['commit']


@pytest.fixture
def client(tmp_path):
    from test_server import create_app, KEY, READ
    return create_app(str(tmp_path / 'worpt.db'), KEY, READ).test_client()
