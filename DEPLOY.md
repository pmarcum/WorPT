# Running your own WorPT server

WorPT's server keeps your proposals (team, goals, tasks, effort, budget) and makes their LaTeX tables.
It is built to sit on the same small Linux VM as [BibMan](https://github.com/pmarcum/BibMan) and
[gooTeX](https://github.com/pmarcum/gooTeX), beside them and without touching them, but it also runs
on its own.

Part 1 installs the server on the VM; Part 2 sets up the dashboard people use (two Google Apps Script
projects). Run VM commands **one line at a time**: when a line switches user (`sudo -iu bibman`), lines
pasted after it in the same paste can end up running as the wrong user.

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

**2. Install the code** (as `bibman`). Run the first line on its own; your prompt changes to `bibman@…`:

```bash
sudo -iu bibman
```

then:

```bash
git clone https://github.com/pmarcum/WorPT.git ~/worpt
cd ~/worpt && python3 -m venv venv && venv/bin/pip install -r cloud/requirements.txt
```

**3. Run the tests on the VM.** They check the effort rules, every table against the old Sheet
version's output, and the whole server, using a throw-away database (your real data is never touched):

```bash
cd ~/worpt/cloud && ../venv/bin/python -m pytest -q tests     # → "… passed", none failed
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

**6. Add WorPT to nginx.** First note how BibMan and gooTeX answer now, so you can check afterward
that nothing changed for them (use your own address in `HOST`):

```bash
HOST=yourname.duckdns.org
for p in health bibman/health gootex/health; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' https://$HOST/$p)"; done
```

Then add the block. Keep a copy of the current file in your home folder (not in an nginx folder,
where nginx would load it), and look at where the blocks are:

```bash
sudo cp /etc/nginx/sites-available/proxy-router ~/proxy-router.before-worpt
grep -n -E 'server \{|listen|location|^\}' /etc/nginx/sites-available/proxy-router
```

WorPT's block goes inside the `server` block that has `listen 443 ssl`, just above the line
`location /gootex/ {` (or, with no gooTeX block, just above that server block's final `}`). If that line
is number N in the list, insert the block after line N−1; for example, with `location /gootex/ {` on
line 37:

```bash
sudo sed -i '36r /home/bibman/worpt/cloud/nginx/worpt-location.conf' /etc/nginx/sites-available/proxy-router
sed -n '28,70p' /etc/nginx/sites-available/proxy-router            # look: /bibman/, then /worpt/, then /gootex/
```

Then:

```bash
sudo nginx -t && sudo systemctl reload nginx                      # nginx -t must say "test is successful"
curl -s https://$HOST/worpt/health                                # → {"service":"worpt","status":"ok"}
for p in health bibman/health gootex/health; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' https://$HOST/$p)"; done
```

The last command must print the same numbers as before. If `nginx -t` fails, nginx keeps running with
the old settings; put the copy back with `sudo cp ~/proxy-router.before-worpt /etc/nginx/sites-available/proxy-router`.
Once everything checks out, delete the copy: `rm ~/proxy-router.before-worpt`.

**7. Nightly backups** (as `bibman`; `sudo -iu bibman` on its own first). Make the first backup by hand,
then add the nightly job to `bibman`'s schedule, keeping the jobs already there:

```bash
~/worpt/venv/bin/python ~/worpt/cloud/worpt_backup.py              # → "WorPT backup written: ..."
(crontab -l; echo '17 11 * * * /home/bibman/worpt/venv/bin/python /home/bibman/worpt/cloud/worpt_backup.py >> /home/bibman/worpt_backup.log 2>&1') | crontab -
crontab -l | tail -3                                               # the new line is last
exit
```

Cron uses the VM's clock, which on Google Cloud is usually UTC (`date` shows it): 11:17 UTC is 3:17 am
in California. Pick a quiet time for your own time zone.

---

## Part 2: the dashboard

The dashboard is two Google Apps Script projects, made in the Google account that will look after WorPT
(script.google.com → **New project**). In each, open **Project Settings** and tick **Show "appsscript.json"
manifest file in editor**, then paste the files from the matching `apps_script/` folder of this repository.
Script Properties are under **Project Settings → Script Properties**.

- **WorPT Core library** (`apps_script/WorPT_Core_Library/`): everything the dashboard does in Apps Script.
- **WorPT Dashboard** (`apps_script/WorPT_Dashboard_WebApp/`): a thin web app holding your settings.
- The page itself, `Index.html`, is not pasted anywhere: the web app fetches it live from this repository,
  so page improvements reach everyone at once.

**1. The Core library.** New project, named *WorPT Core library* → paste `Code.gs` and `appsscript.json`
→ **Deploy → New deployment → Library** (description e.g. "Core 1") → **Deploy**. Then copy its
**Script ID** (Project Settings → IDs).

**2. The web app.** New project, named *WorPT Dashboard* → paste `Code.gs` and `appsscript.json`. In
`appsscript.json`, replace `REPLACE_WITH_YOUR_CORE_LIBRARY_SCRIPT_ID` with the Script ID from step 1, and
keep `"version": "1"` (the library's deployment number). Save. Then add the Script Properties:

| Property | Value |
|---|---|
| `WORPT_CREDENTIAL` | the key from Part 1, step 4 |
| `WORPT_URL` | `https://yourname.duckdns.org/worpt` (no trailing slash) |
| `WORPT_ACCESS_CODE` | the access code you give to people who are not core members (it can be the same as BibMan's) |
| `ADMIN_EMAILS` | admins' Google emails, separated by commas: they see every proposal |
| `CORE_MEMBERS` | core members' Google emails, separated by commas: they create proposals and never need the access code |
| `WORPT_DASHBOARD_WEBAPP_VERSION` | `1` (`worpt_dashboard_webapp_version` in `version.json`) |

**3. Allow it.** In the web app's editor, choose the function `authorize` and click **Run**. Google asks
for permission (it may warn that the app is unverified: **Advanced → Go to WorPT Dashboard**); allow it.

**4. Deploy it.** **Deploy → New deployment → Web app**: *Execute as: User accessing the web app*; *Who has
access: Anyone with a Google account* → **Deploy**. The web app URL is your group's WorPT link. Each person
allows it once, the first time they open it.

**5. Try it.** Open the link. Admins and core members go straight in; everyone else types the access code
once. Then, in **People & profiles**, make a profile for each person (with the Google email they sign in
with: that is how WorPT recognizes them), and in **Proposal Work Plans**, **New proposal work plan**.

### Updating the dashboard

- **The page** updates by itself. To try a page change first, put it on a branch of the repository and
  open your WorPT link with `?branch=NAME` added.
- **The Core library**: when a new Core is released, the dashboard shows a banner. Paste the new `Code.gs`
  into the Core project → **Deploy → Manage deployments → Edit → New version**. Then, in the WorPT Dashboard
  project: **Libraries → WorPTCore →** choose the new version → **Save**, and **Deploy → Manage deployments →
  Edit → New version** (the link stays the same).
- **The web app's `Code.gs`** rarely changes; when it does, the banner says so: paste it, update
  `WORPT_DASHBOARD_WEBAPP_VERSION`, and make a new version as above.

Always use **Manage deployments → Edit → New version**, never a new deployment, so everyone's link keeps working.

---

## Updating WorPT

`sudo -iu bibman` on its own first, then:

```bash
cd ~/worpt && git pull && venv/bin/pip install -r cloud/requirements.txt
cd cloud && ../venv/bin/python -m pytest -q tests                 # all must pass before restarting
exit
sudo systemctl restart worpt && curl -s http://127.0.0.1:8083/health
```

If a test fails, don't restart: the running server keeps using the code it started with.

## Restoring a backup

```bash
sudo systemctl stop worpt
```

`sudo -iu bibman` on its own, then:

```bash
ls ~/worpt_backups/                                               # pick one, e.g. worpt-20261106-031700.db
mv ~/worpt_data/worpt.db ~/worpt_data/worpt.db.replaced
rm -f ~/worpt_data/worpt.db-wal ~/worpt_data/worpt.db-shm
cp ~/worpt_backups/worpt-20261106-031700.db ~/worpt_data/worpt.db
exit
sudo systemctl start worpt
```

A backup restores every work plan at once. To put back just one work plan, use its **Snapshots** tab in the
dashboard instead: WorPT saves a snapshot at the first change of each day and before anything drastic,
and anyone can save a named one.

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
