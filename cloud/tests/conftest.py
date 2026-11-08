import pytest
from worpt import about


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Tests never ask GitHub for the latest versions (tests that need an answer give their own)."""
    def offline(*a): raise OSError('tests do not ask GitHub')
    monkeypatch.setattr(about, 'latest_commit', offline)
    monkeypatch.setattr(about, '_cache', dict(at=-about.TTL, value=None))
