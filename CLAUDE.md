# WidgetForge — instructions for an agent working in this repo

You are looking at a local desktop app that compiles ServiceNow Service Portal
widgets. It is not a web app, it has no server, and it never contacts a
ServiceNow instance. Read this file first, then the one that matches your task.

| If you are about to… | Read |
|---|---|
| do anything at all | this file, all of it — it is short |
| understand how it works | `ARCHITECTURE.md` |
| add a card type, a field type, a panel, a test | `CONTRIBUTING.md` |
| understand *why* something is the way it is | `HANDOFF.md` |
| install, run, deploy, or troubleshoot on Windows | `DEPLOY.md` |

`HANDOFF.md` is the project's memory. Almost every guard in this codebase
exists because something slipped past a review once, and §2 of that document
records which decisions were made deliberately and what was rejected. **Do not
reopen a decision listed there without a reason that is not already in it.**

---

## The one-paragraph version

A *board* is a JSON document: a title and a list of *cards*, each card being a
position and size on a 24 × 16 grid plus a bag of settings. A *card type* is a
folder under `modules/` containing `module.json` and four code fragments. The
compiler (`wf/compiler.py`) turns a board plus its card types into the four
fields of an `sp_widget` record — server script, client controller, HTML
template, CSS — which you paste into ServiceNow by hand. The Qt app is a visual
editor for the board JSON, and nothing more.

---

## Hard rules

These are not style preferences. Breaking one of them either ships broken
output to a production ServiceNow instance or removes a guard that was added
after a real failure.

**1. Nothing in `wf/` outside `wf/ui/` may import PySide6.**
`compiler.py`, `model.py`, `query.py` and `boards.py` are Qt-free so that
placement, collision, alignment, undo and compilation can be tested as plain
functions instead of through a widget. A test asserts this. If you find
yourself wanting Qt in the model, the logic belongs in the UI layer instead.

**2. The compiler's output must stay byte-identical to version 3.4.0.**
This has been verified across 202 boards and every error message. It is the
reason a board that worked before the Qt conversion still works. If you change
`compile_board`, `normalise`, `inherit`, `validate` or the shell fragments, you
are changing what gets pasted into a live instance — say so explicitly, and
re-run the identity check in `CONTRIBUTING.md`.

**3. The app never contacts ServiceNow.**
No HTTP client, no sockets, no credentials, no `urllib`, no `requests`. A Table
API push existed and was deliberately removed in 3.2.0. `tests.py` greps every
Python file under `wf/` plus `main.py` and fails if any of that comes back —
including anything that would reintroduce a *server* (`import flask`,
`listen(`, `bind((`).

**4. `tests.py` must say `ALL PASS` before anything ships.**
Assertions, not eyeball checks. A missing IIFE once survived several rounds of
"verified" because it was checked by wrapping the file before syntax-checking
it. If you fix a bug, add the test that would have caught it *before* you fix
it.

**5. Adding a card type never means editing Python.**
Not the compiler, not the UI. A card type is a folder of data and fragments.
The inspector is generated from `module.json`. If a new card type seems to
require a code change, that is a signal the module contract is missing
something — say so rather than special-casing.

**6. Generated code is ES5 and the CSS is flat.**
ServiceNow's server-side engine is Rhino: no arrow functions, no `let`/`const`,
no template literals, no spread, no classes. The CSS field does compile SCSS,
but relying on that was the single most likely failure point in an earlier
design, so the output is plain CSS with no nesting. Both are asserted.

**7. A card ending past row 16 is a build error, not a warning.**
The compiled board fills the screen and does not scroll, so an off-screen card
would be unreachable. Do not "helpfully" downgrade this to a warning.

---

## Running it

```
py install.py                      # once: venv + PySide6 + tests + launchers
run.bat                            # Windows
./run.sh                           # anything else
venv\Scripts\python.exe tests.py   # the suite
```

`py tests.py` gets the *system* interpreter, which has no PySide6, and fails on
a missing dependency. Always use the venv. This has caused a good update to be
rolled back before.

**Headless.** Set `QT_QPA_PLATFORM=offscreen` and the whole app runs with no
display — including the interface section of the test suite. This is how the UI
was actually developed and reviewed:

```
QT_QPA_PLATFORM=offscreen python3 tests.py
```

**Looking at the UI without a screen.** `window.grab()` returns a `QPixmap`;
save it and open the PNG. Do this rather than guessing whether a layout worked
— several real layout bugs in this app were found no other way.

```python
import os, tempfile
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from wf import boards as bs
from wf.ui.main_window import MainWindow
app = QApplication([])
w = MainWindow(bs.State(folder=tempfile.mkdtemp()))   # a throwaway state dir
w.resize(1500, 940); w.show(); app.processEvents()
w.grab().save('/tmp/shot.png')
```

Always pass a temporary folder to `State`. The default writes to the real
`%APPDATA%\WidgetForge\state.json` and will clobber the user's presets, draft
and window geometry.

---

## What "done" looks like

- `tests.py` prints `ALL PASS`.
- `python3 -m pyflakes main.py wf/*.py wf/ui/*.py tests.py` is silent.
- Any behaviour you changed has a test naming what it prevents.
- If you touched the compiler, the byte-identity check still passes.
- If you touched the UI, you have looked at a screenshot of it.
- `HANDOFF.md` reflects any decision you made that a future reader would
  otherwise have to reverse-engineer.

---

## Traps that have already bitten

Each of these cost real debugging time. They are listed so they cost none.

**`module.json` is JSON, so a multi-line default needs `\n`, not `\\n`.**
Three modules shipped with `\\n`. The default decoded to a literal backslash-n,
the whole thing parsed as one entry with a nonsense field name, and the card
compiled with zero errors and rendered blank. There is now a test.

**A widget removed from a layout keeps painting until the event loop deletes
it.** `deleteLater()` is queued. Call `setParent(None)` first. Skipping this
drew every palette row twice.

**Rebuilding a form while someone is typing in it destroys the widget under the
cursor.** `InspectorRail.show_card` rebuilds only when the card or selection
size actually changes, for exactly this reason. Do not "simplify" it into an
unconditional rebuild.

**A `QPainter` abandoned by an early `return` leaves the paint device
unterminated.** Every `paintEvent` guard clause must `p.end()` before returning.

**Boards from disk cannot be trusted.** A card whose `w` is `"6"` or `6000` or
missing used to reach `paintEvent`, raise, get swallowed, and segfault the
process on the *next* repaint. Everything loaded goes through
`model.sanitise_board`, which repairs and reports. Do not add a load path that
bypasses it.

**`tools/query-corpus.json` cannot be regenerated.** It holds 1,500 encoded
queries with the answers produced by the JavaScript parser this app replaced,
captured before that file was deleted. It is the only record of that behaviour.
Never edit it by hand.

**Do not write to `boards/` or `%APPDATA%\WidgetForge\` during development.**
Those are the user's real work.

---

## Project conventions

- Card ids match `^[a-z0-9][a-z0-9_-]*$` — they become CSS class names.
- Widget CSS classes are `wf-` prefixed; shell server helpers are `wf`-prefixed
  camelCase (`wfCount`, `wfGroup`, `wfTrend`).
- Qt object names used for styling are `CamelCase` (`#RailHead`,
  `#PaletteItem`).
- Board files are `boards/<slugged-title>.json`.
- Comments explain *why*, not *what*. The code says what it does; the comment
  says which failure it is preventing.
- Full file replacements over partial diffs when handing work to the user — he
  copies whole files.

---

## The thing that actually matters

**Nothing this tool produces has ever run inside ServiceNow.** All verification
is local and structural: the generated scripts are checked for ES5 violations
and bracket balance, the templates for tag balance and against what their
runners return, the CSS for flatness. That is a high bar and it still proves
nothing about behaviour in the instance.

Do not describe any of this as verified, working or tested against ServiceNow.
`DEPLOY.md` §10 lists exactly what is unproven and in what order it is likely
to bite. Keep that list honest — an earlier version of this project's
documentation was not, and it cost trust.
