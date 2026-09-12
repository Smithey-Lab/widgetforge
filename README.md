# WidgetForge 3.5

A desktop app that compiles ServiceNow Service Portal widgets. Arrange cards on
a 24-column grid; it emits the four fields of an `sp_widget` record.

```
py install.py      once
run.bat            every time
```

No browser, no localhost, no server. It is a Qt window.

Full instructions, deployment routes and the list of what has never been tested
against a live instance: **[DEPLOY.md](DEPLOY.md)**.

## Documentation

| Document | What it is for |
|---|---|
| **[CLAUDE.md](CLAUDE.md)** | Start here if you are changing the code — the rules, how to run it, and the traps that have already bitten. Written for an agent picking this up cold. |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | How it works: the compile pipeline, every data shape, the module map, the signal graph. |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Recipes: add a card type, add a field type, change the grid, write a test, ship a version. |
| **[HANDOFF.md](HANDOFF.md)** | Why it is the way it is. Decisions made, decisions rejected, and what is still unverified. |
| **[DEPLOY.md](DEPLOY.md)** | Install, run, get a board into ServiceNow, troubleshoot on Windows. |

The builder is entirely offline. It never contacts a ServiceNow instance — you
copy the four compiled fields, or export an update set.

## Development and GitHub checks

Use a short-lived feature branch and a pull request into `dev` for development,
then promote tested changes from `dev` to `main` through a pull request.
Keep both long-lived branches; use a merge commit when promoting `dev` to `main`
so their shared history stays intact.

Install development tools after running the normal installer:

```powershell
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m ruff check .
$env:QT_QPA_PLATFORM = 'offscreen'
venv\Scripts\python.exe tests.py
venv\Scripts\python.exe -m bandit -r wf main.py install.py update.py -ll
venv\Scripts\python.exe -m pip_audit --progress-spinner off
$files = @(git ls-files)
venv\Scripts\detect-secrets-hook.exe --no-verify --baseline .secrets.baseline @files
```

GitHub Actions runs lint and the full Qt test suite on Windows/Python 3.14 and
Linux/Python 3.10 and 3.14. Security checks run on PRs, pushes to `main`/`dev`, and
weekly on `main`. Dependabot proposes weekly Python and GitHub Actions updates
against `main`; merge accepted updates back into `dev`. Actions use read-only
permissions by default and pinned action commits. CodeQL has only the additional
permission needed to upload security findings. See [SECURITY.md](SECURITY.md)
for scanning coverage and reviewed exceptions.

Both `main` and `dev` require pull requests, passing checks, an up-to-date branch,
and resolved review conversations. Force pushes and branch deletion are blocked,
including for administrators. Reviewer approval is optional for solo development.

## Layout

```
main.py                the app entry point
wf/
  compiler.py          board JSON in, four sp_widget fields out
  model.py             the board, the grid, undo - no Qt, so it is testable
  query.py             the encoded-query parser and its round-trip guard
  boards.py            board files and app state, written atomically
  ui/                  the Qt interface
modules/<id>/          one folder per card type - module.json + 4 fragments
shell/                 fragments included on every board
tests.py               773 assertions
install.py             venv + PySide6 + test run + launchers
update.py, updates/    updater with backup and automatic rollback
widgetforge.spec       PyInstaller spec for a standalone exe (never built)
examples/              two working boards
boards/                your saved boards (not in Git)
```

Adding a card type still means adding a folder under `modules/` and nothing
else. The compiler did not change in the conversion — it produces byte-identical
output to 3.4.0.

## Commands

| Command | What it does |
|---|---|
| `py install.py` | Set up venv, install PySide6, run tests, write launchers |
| `run.bat` | Start the app |
| `venv\Scripts\python.exe tests.py` | Run the suite. Must say `ALL PASS` before you deploy anything |
| `update.bat` | Apply pending updates, with rollback on failure |
| `update.bat --check` | Dry run |
| `update.bat --rollback` | Restore the last backup |

`py tests.py` on its own gets the system interpreter and fails on a missing
PySide6. Use the venv.

## Shortcuts

| Key | What |
|---|---|
| Drag from the palette | Place a card exactly where you want it |
| Click a palette card | Drop it in the first free spot |
| Shift-click | Add a card to the selection |
| Arrow keys | Nudge the selection one cell |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo (Ctrl+Y also redoes) |
| Ctrl+D | Duplicate |
| Ctrl+N | New board |
| Ctrl+S / Ctrl+Shift+S | Save / save as |
| Ctrl+O | Open a board |
| Ctrl+E | Copy for ServiceNow |
| Ctrl+R | Reload card types from disk |
| Ctrl+T | Toggle the app theme |
| Ctrl+` | Show or hide the output drawer |
| F1 | Shortcuts |
| Ctrl+Q | Quit |
| Delete | Remove the selection, except locked cards |
| Esc | Clear the selection |
