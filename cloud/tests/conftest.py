import pytest
from worpt import about


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Tests never ask GitHub for the latest versions (tests that need an answer give their own)."""
    def offline(*a): raise OSError('tests do not ask GitHub')
    monkeypatch.setattr(about, 'latest_commit', offline)
    monkeypatch.setattr(about, '_cache', dict(at=-about.TTL, value=None))


@pytest.fixture(autouse=True)
def no_previews(request, monkeypatch):
    """Only the preview tests compile previews: elsewhere a table request would compile one, which on a small server
    takes a second or more per table and adds nothing to what those tests check."""
    from worpt import preview
    if request.module.__name__ != 'test_preview':
        monkeypatch.setattr(preview, 'render', lambda name, latex: dict(error='Previews are not made in these tests.'))
