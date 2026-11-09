# Bringing WorPT tables into gooTeX

This is for whoever builds the gooTeX side of the link. It says what WorPT offers, how to ask for it,
and what a document needs in order to use it. WorPT's side is finished and tested.

## What the link does

A WorPT work plan produces nine LaTeX tables (team, tasks, effort, schedule, travel, budget) and one
package file, `worpt.sty`, that every table needs. gooTeX fetches those ten files from WorPT for the
work plan a document names, writes them where the document's LaTeX can find them, and compiles as
usual. The document itself only loads `worpt.sty` once and has a short paste-in block per table, which
WorPT also hands out, so gooTeX can insert and update those too.

## Where WorPT is

Both run on the same VM. Call WorPT directly on the VM:

```
http://127.0.0.1:8083
```

Don't go through nginx's public `https://<host>/worpt/` path: the local address never leaves the
machine, needs no TLS, and does not depend on the public hostname.

## The read-only key

Every request (except `/health`) carries a key in the `X-WorPT-Credential` header. gooTeX uses
WorPT's **read-only key**, which WorPT accepts only for reading tables (`GET` requests whose path
contains `/tables`); with it, nothing in WorPT can be changed. It is not the dashboard's key.

- The key lives only on the VM, in two systemd drop-ins: WorPT's and gooTeX's. It never goes in a
  Google Doc, a Doc's `Config.gs`, a web page, a chat, an email or a repository.
- WorPT reads it from `WORPT_READ_CREDENTIAL`. It must be at least 16 characters; a shorter one is
  ignored, with a warning in WorPT's log.
- Anyone holding the key and a work plan's ID can read that work plan's tables, which include
  people's names. The ID is a 12-character random string, so the key is what has to stay private.

Setting it up, one time (each line on its own, in the VM's SSH window):

1. Make a key and note it for step 3 (it is printed once):
   ```bash
   READKEY=$(openssl rand -hex 16); echo "$READKEY"
   ```
2. Add it to WorPT's drop-in, next to the dashboard key already there, and restart WorPT:
   ```bash
   echo "Environment=WORPT_READ_CREDENTIAL=$READKEY" | sudo tee -a /etc/systemd/system/worpt.service.d/credential.conf >/dev/null
   sudo systemctl daemon-reload && sudo systemctl restart worpt
   sudo cat /etc/systemd/system/worpt.service.d/credential.conf     # → [Service] and two Environment= lines
   ```
3. Put the same value in gooTeX's own systemd drop-in, under whatever name gooTeX reads
   (`WORPT_READ_CREDENTIAL` keeps it recognizable), and restart gooTeX.
4. Check it from the VM (use a real work plan ID, see below):
   ```bash
   curl -s -H "X-WorPT-Credential: $READKEY" "http://127.0.0.1:8083/api/proposals/<ID>/tables" ; echo
   # → {"status":"ok","style":"worpt","tables":[...]}
   ```

## Which work plan: the work plan ID

Each work plan has an ID such as `kM3vQ9x_T2bA` (12 characters: letters, digits, `-` and `_`).
People find it in the WorPT dashboard: open the work plan, **Settings** tab, **Work plan ID**, then
**Copy**. A gooTeX document needs a place to hold that ID (one work plan per document is the
expected case); how a person enters it is up to gooTeX.

## The request

One request returns everything a document needs:

```
GET /api/proposals/<ID>/tables?files=1
X-WorPT-Credential: <read-only key>
```

Answer (always HTTP 200; look at `status`):

```json
{
  "status": "ok",
  "work_plan": {"id": "kM3vQ9x_T2bA", "title": "Mapping faint halos"},
  "files": {
    "NOTANONfte.tex": "...", "NOTANONhst.tex": "...", "NOTANONschedule.tex": "...",
    "NOTANONtasks.tex": "...", "NOTANONteamSummaries.tex": "...", "isANONfte.tex": "...",
    "isANONnonlabor.tex": "...", "isANONtasks.tex": "...", "isANONtravel.tex": "...",
    "worpt.sty": "..."
  },
  "blocks": {
    "NOTANONfte": "%::: start NOTANONfte :::\n\\input{NOTANONfte} ...\n\\begin{NOTANONfte}\n\\caption{...}\n\\label{tab:NOTANONfte}\n\\end{NOTANONfte}\n%::: end NOTANONfte :::\n",
    "...": "... one per table ...",
    "worpt": "\\usepackage{worpt}   % the last package in the preamble\n"
  },
  "digest": "3f1c…(64 hex characters)",
  "checks": [{"level": "fix", "item": "B2", "message": "has no timeline, so its weeks are not counted in any year"}]
}
```

- `files`: file name → contents (UTF-8 text). Write each one as is, overwriting any older copy.
- `blocks`: table name → its paste-in block, the LaTeX that goes in the document where the table
  appears: the `\input`, the table's environment, and a default caption and label. Each block starts
  with a `%::: start <name> :::` line and ends with a `%::: end <name> :::` line, so a block already in
  a document can be found and replaced. Captions have parts meant to be rewritten for each proposal,
  in red and in square brackets (`{\color{red}[Describe ...]}`); once a person has edited a caption,
  replacing their block would undo the edit, so how and when gooTeX refreshes a block is gooTeX's choice.
  `blocks["worpt"]` is the preamble line, `\usepackage{worpt}`, which goes after all other packages.
  These are the same blocks the readmes show, and every one compiles with `worpt.sty` alone.
- `digest`: a fingerprint of all ten files and the blocks together. It changes whenever any of them
  changes: an edit to the plan, to a person's profile (names and institutions appear in the tables), or
  a WorPT update to the table templates. gooTeX can keep the last digest and skip rewriting the files
  when it is the same. Don't use anything else (such as a time) to decide whether the files are current.
- `checks`: problems WorPT found in the plan. `level` is `fix` (needs attention: some effort is not
  counted) or `warn`; `item` is a task label such as `B2`, or a team member's label; `message` is
  written for people. The tables are still made; these are worth showing the person, in gooTeX's own way.

The request builds the tables fresh each time and takes a fraction of a second, so fetching at every
compile is fine.

Other read-only requests, if useful:

| Request | Answer |
|---|---|
| `GET /health` (no key) | `{"service":"worpt","status":"ok"}` when WorPT is up |
| `GET /api/proposals/<ID>/tables` | `{"tables": [nine names], "style": "worpt"}` |
| `GET /api/proposals/<ID>/tables/<name>` | `{"name", "latex", "block", "checks"}` for one table; `<name>` = `worpt` gives `worpt.sty` and its preamble line |

## When something is wrong

Refusals are HTTP 200 too, with `"status": "error"`, a `code` and a `message` written for people:

| `code` | Meaning |
|---|---|
| `credential` | the key is missing or wrong (or the read-only key was used on something other than reading tables) |
| `not_found` | no work plan has that ID (mistyped, or the work plan was deleted) |
| `unknown_table` | a table name WorPT doesn't make |
| `unknown` | a path or method WorPT doesn't have |
| `internal` | WorPT hit an unexpected problem; details are in WorPT's log (`journalctl -u worpt`) |

If WorPT doesn't answer at all (the connection is refused), WorPT isn't running:
`sudo systemctl status worpt`. A compile can then go ahead with the files from the last successful
fetch, if gooTeX kept them, and tell the person the tables may be out of date.

## Where to put the files

LaTeX has to find `worpt.sty` for `\usepackage{worpt}` and each table for `\input{<table>}`. The
readmes' paste-in blocks use bare names, so the simplest arrangement is the same folder as the
document's main `.tex` file during the compile. If gooTeX prefers a subfolder, add it to the search
path (for example `TEXINPUTS=./worpt//:` in the compile's environment) rather than changing the names.

The files are WorPT's output: people should change a table's look with the settings lines described
in its readme, placed in their own document, never by editing the files (the next fetch replaces them).

## What a document needs

1. In the preamble, as the **last** package loaded (after aastex, xcolor, hyperref and the rest):
   ```latex
   \usepackage{worpt}
   ```
2. Where a table goes, its paste-in block (from `blocks` above, or that table's readme), for example:
   ```latex
   %:::::::::::::::::::: start isANONfte ::::::::::::::::::::::
   \input{isANONfte}   % reset file parameters

   \begin{isANONfte}
   \caption{Details of work efforts per member to be funded for the present proposal; {\color{red}[Say where ...]}}
   \label{tab:isANONfte}
   \end{isANONfte}
   %::::::::::::::::::::: end isANONfte :::::::::::::::::::::::
   ```
   The readmes, one per table with a picture of it and its settings:
   https://github.com/pmarcum/WorPT/tree/main/latexTableTemplates
   (`worpt.sty` itself: https://github.com/pmarcum/WorPT/tree/main/latexTableTemplates/WorPTpackages)

The tables compile in article, report, revtex4-2, aastex631 and aastex702 (AASTeX 7.0.2; one or two columns), and alongside the
older FU style files. aastex631 needs the revtex4-1 class installed with TeX; without it aastex631
can't compile anything, WorPT or not.

## Compatibility

WorPT may add fields to these answers; it won't remove or rename the ones above without saying so in
this file. New tables would appear as new entries in `files` and `blocks`.

Added after the first version of this file: `blocks` in the all-files answer, and `block` in each
table's answer.
