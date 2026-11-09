"""A picture of one table, for the dashboard: the table compiled on its own, with its default settings, in the newest
AASTeX this machine has (or article, if none compiles), and each page turned into a PNG.

Limits (agreed for a small, shared VM):
- one compile at a time, across the whole server (a second request waits for the first);
- 60 seconds at most per compile, then it is stopped and the dashboard says so;
- the last 5 pictures are kept in memory, so a table that hasn't changed comes back at once; a restart forgets them.
Needs pdflatex and pdftocairo; without them, the dashboard says the preview isn't available here.
"""
import base64, collections, fcntl, hashlib, os, pathlib, re, shutil, subprocess, tempfile, threading, time
from .tables import paste_in, style

LIMIT_SECONDS, KEEP, DPI = 60, 5, 192            # DPI: twice a screen's 96, so the picture is sharp on high-density screens
LOCK_FILE = pathlib.Path(tempfile.gettempdir()) / 'worpt-preview.lock'
_kept, _kept_lock = collections.OrderedDict(), threading.Lock()
_cls = []                                        # the class found, once per run of the server


def available():
    return bool(shutil.which('pdflatex') and shutil.which('pdftocairo'))


def _compiles(cls):
    """Does an empty document in this class compile here?"""
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)
        (p / 'empty.tex').write_text('\\documentclass{%s}\n\\begin{document}\nx\n\\end{document}\n' % cls)
        try: subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 'empty.tex'], cwd=d, capture_output=True, timeout=LIMIT_SECONDS)
        except subprocess.TimeoutExpired: return False
        return (p / 'empty.pdf').exists()


def _version(name):
    """aastex702 -> (7, 0, 2); aastex631 -> (6, 3, 1); aastex7 -> (7, 0, 0); aastex63 -> (6, 3, 0)."""
    digits = [int(c) for c in name[len('aastex'):]]
    return tuple(digits + [0] * (3 - len(digits)))


def _aastex_classes():
    """Every aastex<digits>.cls that TeX can see here: in its trees (TEXMFHOME, TEXMFLOCAL, TEXMFDIST...) and TEXINPUTS."""
    roots = set()
    for var in ('TEXMFHOME', 'TEXMFLOCAL', 'TEXMFDIST', 'TEXMFMAIN'):
        r = subprocess.run(['kpsewhich', '-var-value=' + var], capture_output=True, text=True)
        roots.update(pathlib.Path(x.strip('!{}')) / 'tex' for x in re.split(r'[:;,]', r.stdout.strip()) if x.strip('!{}'))
    roots.update(pathlib.Path(x.rstrip('/')) for x in os.environ.get('TEXINPUTS', '').split(':') if x.strip('/'))
    found = {f.stem for root in roots if root.is_dir() for f in root.rglob('aastex*.cls') if re.fullmatch(r'aastex\d+', f.stem)}
    return sorted(found, key=_version, reverse=True)


def document_class():
    """The newest AASTeX that compiles here, else article. Found once per run (a newly installed class needs a restart)."""
    if not _cls:
        _cls.append(next((c for c in _aastex_classes() if _compiles(c)), 'article'))
    return _cls[0]


def render(name, latex):
    """{'pages': [base64 PNG, ...], 'document_class': ..., 'seconds': ...}, or {'error': message for people}."""
    if not available(): return dict(error='Previews need pdflatex and pdftocairo on the WorPT server, and this one has not got them.')
    cls = document_class()
    key = hashlib.sha256('\0'.join((cls, name, latex, style())).encode()).hexdigest()
    with _kept_lock:
        if key in _kept: _kept.move_to_end(key); return _kept[key]
    with open(LOCK_FILE, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)                       # one compile at a time, server-wide
        with _kept_lock:                                       # it may have been made while this request waited
            if key in _kept: return _kept[key]
        out = _compile(cls, name, latex)
    if 'pages' in out:
        with _kept_lock:
            _kept[key] = out
            while len(_kept) > KEEP: _kept.popitem(last=False)
    return out


def _compile(cls, name, latex):
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)
        (p / f'{name}.tex').write_text(latex); (p / 'worpt.sty').write_text(style())
        (p / 'preview.tex').write_text('\\documentclass{%s}\n%s\\pagestyle{empty}\n\\begin{document}\n%s\n\\end{document}\n' % (cls, paste_in('worpt'), paste_in(name)))
        try:
            subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', 'preview.tex'], cwd=d, capture_output=True, timeout=LIMIT_SECONDS)
            left = LIMIT_SECONDS - (time.monotonic() - start)
            if (p / 'preview.pdf').exists() and left > 0:
                subprocess.run(['pdftocairo', '-png', '-r', str(DPI), 'preview.pdf', 'page'], cwd=d, capture_output=True, timeout=left)
        except subprocess.TimeoutExpired:
            return dict(error=f'The preview took longer than {LIMIT_SECONDS} seconds, so it was stopped.')
        if not (p / 'preview.pdf').exists():
            log = (p / 'preview.log').read_text(errors='replace') if (p / 'preview.log').exists() else ''
            first = next((l for l in log.splitlines() if l.startswith('!')), 'no PDF was made')
            return dict(error=f'LaTeX could not compile this table ({cls}): {first.lstrip("! ")}')
        pngs = sorted(p.glob('page*.png'), key=lambda f: int(re.search(r'(\d+)\.png$', f.name)[1]))
        return dict(pages=[base64.b64encode(f.read_bytes()).decode() for f in pngs], document_class=cls,
                    seconds=round(time.monotonic() - start, 1))
