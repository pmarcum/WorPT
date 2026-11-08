"""What WorPT is running, for the dashboard's version hover text.

- The server: the commit of the git checkout it was started from (read once, at startup: a later `git pull` changes
  nothing until the restart, so neither does this).
- The page: the dashboard loads Index.html from GitHub each time, so its version is the latest commit on GitHub that
  changed Index.html.
- Whether GitHub has server changes this server isn't running yet (pulled and restarted on the VM).

GitHub is asked at most once every 10 minutes, with a short timeout; if it can't be reached, only the server's own
commit is given.
"""
import json, logging, re, subprocess, threading, time, urllib.request
from pathlib import Path

log = logging.getLogger('worpt')
REPO = Path(__file__).resolve().parents[2]       # the checkout: cloud/worpt/about.py -> the repository's top folder
TTL, TIMEOUT = 600, 3


def _git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, timeout=5)


def _running():
    try:
        r = _git('log', '-1', '--format=%H %cs')
        sha, date = r.stdout.split() if r.returncode == 0 else (None, None)
    except (OSError, subprocess.SubprocessError, ValueError):
        sha, date = None, None
    return dict(commit=sha[:7], sha=sha, date=date) if sha else None


RUNNING = _running()
_cache, _lock = dict(at=-TTL, value=None), threading.Lock()


def _github_repo():
    """owner and name of the GitHub repository this checkout came from."""
    m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$', _git('config', '--get', 'remote.origin.url').stdout.strip())
    return (m[1], m[2]) if m else None


def latest_commit(owner, repo, path):
    """The latest commit on the default branch that changed path: {commit, sha, date}."""
    req = urllib.request.Request(f'https://api.github.com/repos/{owner}/{repo}/commits?path={path}&per_page=1',
                                 headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'WorPT'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as f: c = json.load(f)[0]
    return dict(commit=c['sha'][:7], sha=c['sha'], date=c['commit']['committer']['date'][:10])


def _has(sha):
    """Is that commit part of what this server is running?"""
    return _git('merge-base', '--is-ancestor', sha, RUNNING['sha']).returncode == 0


def about():
    """{server: {commit, date} or None, page: {commit, date} or None, server_update: True/False/None}."""
    with _lock:
        if time.monotonic() - _cache['at'] < TTL: return _cache['value']
        value = dict(server=RUNNING and dict(commit=RUNNING['commit'], date=RUNNING['date']), page=None, server_update=None)
        try:
            gh = _github_repo()
            if gh:
                page, server = latest_commit(*gh, 'Index.html'), latest_commit(*gh, 'cloud')
                value['page'] = dict(commit=page['commit'], date=page['date'])
                if RUNNING: value['server_update'] = not _has(server['sha'])
        except Exception as e:                       # GitHub not reachable, or not answering as expected: say less
            log.info('Could not ask GitHub for the latest versions: %s', e)
        _cache.update(at=time.monotonic(), value=value)
        return value
