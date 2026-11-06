# Running your own WorPT server

WorPT's server keeps your proposals (team, goals, tasks, effort, budget) and makes their LaTeX tables.
It is built to sit on the same small Linux VM as [BibMan](https://github.com/pmarcum/BibMan) and
[gooTeX](https://github.com/pmarcum/gooTeX), beside them and without touching them, but it also runs
on its own.

This guide covers the server. The WorPT dashboard (Google Apps Script) comes in a later release,
with its own part of this guide.

## How the pieces fit

```
Browser ──► WorPT dashboard (Apps Script, Google's side) ──► nginx (443) /worpt/ ──► gunicorn/Flask 127.0.0.1:8083 ──► SQLite
gooTeX compile server (same VM) ─────────────── localhost:8083 (read-only key, tables only) ──┘
```

- Browsers never talk to the server. Only the dashboard's Apps Script code does, so the server's
  key never reaches a browser.
- The server listens only on `127.0.0.1:8083`; nginx is the only way in from outside.
- It runs as the `bibman` user (the same user as BibMan and gooTeX on a shared VM), with a memory
  cap so it can never starve the other two.

| What | Where |
|---|---|
| Code (a clone of this repository) | `/home/bibman/worpt/` |
| Python environment | `/home/bibman/worpt/venv/` |
| Database | `/home/bibman/worpt_data/worpt.db` (outside the code folder, so updating code never touches data) |
| Nightly backups (newest 14 kept) | `/home/bibman/worpt_backups/` |
| Service | `/etc/systemd/system/worpt.service` |
| **Secrets** | `/etc/systemd/system/worpt.service.d/credential.conf`, readable only by root |
| nginx | a `location /worpt/` block in `/etc/nginx/sites-available/proxy-router` |

## What you need

- An always-on Linux VM with nginx and HTTPS already working, and a `bibman` user. If BibMan or
  gooTeX already run on the VM, you have all of this. Otherwise follow BibMan's
  [DEPLOY.md](https://github.com/pmarcum/BibMan/blob/main/DEPLOY.md), Part 1, steps 1, 2 and 6
  (swap, system packages and the `bibman` user, nginx with HTTPS).
- Python 3.11 or newer (Debian 12's `python3` is 3.11).

---

## Part 1: the server

All commands run on the VM, from your own account unless a step says otherwise.

**1. Check the VM is ready.**

```bash
python3 --version                  # Python 3.11 or newer
ss -ltn | grep 8083                # prints nothing: port 8083 is free
free -m                            # note the "available" figure; WorPT needs about 100 MB
```

**2. Install the code** (as `bibman`):

```bash
sudo -iu bibman
git clone https://github.com/pmarcum/WorPT.git ~/worpt
cd ~/worpt && python3 -m venv venv && venv/bin/pip install -r cloud/requirements.txt
```

**3. Run the tests on the VM.** They check the effort rules, every table against the old Sheet
version's output, and the whole server, using a throw-away database (your real data is never touched):

```bash
cd ~/worpt/cloud && ../venv/bin/python -m pytest -q tests     # → "62 passed"
exit                                                          # back to your own account
```

**4. Install the service and its key.** The key is the password the dashboard uses to reach the
server. It goes in a small file of its own, readable only by root:

```bash
sudo cp /home/bibman/worpt/cloud/systemd/worpt.service.example /etc/systemd/system/worpt.service
NEWKEY=$(openssl rand -hex 16); echo "$NEWKEY"
sudo mkdir -p /etc/systemd/system/worpt.service.d
printf '[Service]\nEnvironment=WORPT_CREDENTIAL=%s\n' "$NEWKEY" | sudo tee /etc/systemd/system/worpt.service.d/credential.conf >/dev/null
sudo chmod 600 /etc/systemd/system/worpt.service.d/credential.conf
sudo ls -l /etc/systemd/system/worpt.service.d/credential.conf      # → -rw------- 1 root root ...
```

Keep the printed key somewhere safe (where you keep your other keys): the dashboard's
`WORPT_CREDENTIAL` Script Property needs it. Don't put it in an email, a chat, a Google Doc or a
repository. If you lose it, make a new one by repeating this step and restarting the service.

**5. Start it and check it.** Use the same terminal as step 4, so `$NEWKEY` is still set:

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now worpt
systemctl status worpt --no-pager | head -5                       # → "active (running)"
curl -s http://127.0.0.1:8083/health                              # → {"service":"worpt","status":"ok"}
curl -s -H "X-WorPT-Credential: $NEWKEY" -H "X-WorPT-User: test@example.org" http://127.0.0.1:8083/api/me
#   → {"access":"code","email":"test@example.org","profile":null,"proposals":[],"status":"ok"}
sudo ls -l /home/bibman/worpt_data/                              # → worpt.db owned by bibman
```

If the service is not running, `journalctl -u worpt -n 30 --no-pager` says why. A missing or short key
gives "refusing to start" and the service stops after one try (it does not restart in a loop).

**6. Add WorPT to nginx.** First note how BibMan and gooTeX answer now, so you can check afterwards
that nothing changed for them (use your own address in `HOST`):

```bash
HOST=yourname.duckdns.org
for p in health bibman/health gootex/health; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' https://$HOST/$p)"; done
```

Then add the block. Keep a copy of the current file in your home folder (not in an nginx folder,
where nginx would load it):

```bash
sudo cp /etc/nginx/sites-available/proxy-router ~/proxy-router.before-worpt
sudo nano /etc/nginx/sites-available/proxy-router
```

Paste the block from [`cloud/nginx/worpt-location.conf`](cloud/nginx/worpt-location.conf) inside the
`server` block that has `listen 443 ssl`, just above the line `location /gootex/ {` (or above the
final `}` if there is no gooTeX block). Save (Ctrl+O, Enter) and exit (Ctrl+X). Then:

```bash
sudo nginx -t && sudo systemctl reload nginx                      # nginx -t must say "test is successful"
curl -s https://$HOST/worpt/health                                # → {"service":"worpt","status":"ok"}
for p in health bibman/health gootex/health; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' https://$HOST/$p)"; done
```

The last command must print the same numbers as before. If `nginx -t` fails, nginx keeps running with
the old settings; put the copy back with `sudo cp ~/proxy-router.before-worpt /etc/nginx/sites-available/proxy-router`.
Once everything checks out, delete the copy: `rm ~/proxy-router.before-worpt`.

**7. Nightly backups** (as `bibman`):

```bash
sudo -iu bibman
~/worpt/venv/bin/python ~/worpt/cloud/worpt_backup.py              # → "WorPT backup written: ..."
crontab -e
```

Add this line at the end (it runs at 03:17 every night, VM time), save and exit:

```
17 3 * * * /home/bibman/worpt/venv/bin/python /home/bibman/worpt/cloud/worpt_backup.py >> /home/bibman/worpt_backup.log 2>&1
```

Then `crontab -l` to check it is there, and `exit`.

---

## Updating WorPT

```bash
sudo -iu bibman
cd ~/worpt && git pull && venv/bin/pip install -r cloud/requirements.txt
cd cloud && ../venv/bin/python -m pytest -q tests                 # all must pass before restarting
exit
sudo systemctl restart worpt && curl -s http://127.0.0.1:8083/health
```

If a test fails, don't restart: the running server keeps using the code it started with.

## Restoring a backup

```bash
sudo systemctl stop worpt
sudo -iu bibman
ls ~/worpt_backups/                                               # pick one, e.g. worpt-20261106-031700.db
mv ~/worpt_data/worpt.db ~/worpt_data/worpt.db.replaced
rm -f ~/worpt_data/worpt.db-wal ~/worpt_data/worpt.db-shm
cp ~/worpt_backups/worpt-20261106-031700.db ~/worpt_data/worpt.db
exit
sudo systemctl start worpt
```

For undoing a single change, use the dashboard's history instead: every change is recorded with who,
when, and the before and after.

## Removing WorPT

```bash
sudo systemctl disable --now worpt
sudo rm -r /etc/systemd/system/worpt.service /etc/systemd/system/worpt.service.d && sudo systemctl daemon-reload
```

Remove the `location /worpt/` block from nginx (then `sudo nginx -t && sudo systemctl reload nginx`),
the backup line from `bibman`'s crontab, and, only if you no longer want the data,
`/home/bibman/worpt`, `/home/bibman/worpt_data` and `/home/bibman/worpt_backups`.

## Security notes

- The key file `worpt.service.d/credential.conf` must stay readable only by root: `sudo ls -l` shows `-rw-------`.
- The key never goes in a Google Doc, a web page, a link or a repository. The dashboard keeps it in its
  Script Properties and uses it only on Google's side.
- gooTeX gets its own **read-only** key (`WORPT_READ_CREDENTIAL`), which can only read tables. It
  belongs in gooTeX's own systemd drop-in on the VM, never in a Doc's `Config.gs`. It is set up with
  the gooTeX link.
- Never commit `worpt.db`, a backup, or a filled-in drop-in.
