"""Nightly copy of the WorPT database, keeping the newest 14 copies.

Runs from the bibman user's crontab (crontab -e as bibman), for example at 03:17 every night:
  17 3 * * * /home/bibman/worpt/venv/bin/python /home/bibman/worpt/cloud/worpt_backup.py
"""
import datetime, os, pathlib, sqlite3, sys

KEEP = 14
db = pathlib.Path(os.environ.get('WORPT_DB', '/home/bibman/worpt_data/worpt.db'))
folder = pathlib.Path(os.environ.get('WORPT_BACKUPS', '/home/bibman/worpt_backups'))


def backup(db=db, folder=folder, keep=KEEP, stamp=None):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'worpt-{stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}.db'
    src, dst = sqlite3.connect(db), sqlite3.connect(target)
    with dst: src.backup(dst)                     # a consistent copy even while the server is running
    src.close(); dst.close()
    for old in sorted(folder.glob('worpt-*.db'))[:-keep]: old.unlink()
    return target


if __name__ == '__main__':
    if not db.exists(): sys.exit(f'WorPT backup: no database at {db}')
    print('WorPT backup written:', backup())
