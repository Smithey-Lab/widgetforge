# WidgetForge 3.5 — deployment guide

A desktop app that compiles ServiceNow Service Portal widgets. You arrange
cards on a 24-column grid; it emits the four fields of an `sp_widget` record —
server script, client controller, HTML template, CSS.

Everything runs locally. Nothing leaves your machine.

Changing the code rather than using it? `CLAUDE.md`, then `ARCHITECTURE.md` and
`CONTRIBUTING.md`.

---

## 1. Install on Windows

You need Python 3.10 or newer. Check with `py -V`. If that fails, install from
python.org and tick **Add python.exe to PATH**. 3.10 is the floor because
PySide6's wheels are `cp310-abi3` — 3.9 passes a naive version check and then
finds no wheel to install.

```
cd path\to\widgetforge
py install.py
```

The installer creates `venv\`, installs PySide6 into it, runs the test suite,
and writes `run.bat`. If the tests do not report `ALL PASS`, stop — do not
deploy anything from that install. Rerunning `install.py` is safe; it reuses
the venv.

Behind a corporate proxy, set `HTTPS_PROXY` first:

```
set HTTPS_PROXY=http://your.proxy:8080
py install.py
```

PySide6 ships `abi3` wheels built for cp310, which cover every Python from 3.10
upwards, so a new Python release does not usually mean waiting for a new wheel.
There is nothing to compile. If pip reports no matching distribution anyway,
PySide6 has not yet published for that interpreter — the installer says so.

If pip fails with an SSL or certificate error rather than a connection error,
the proxy is inspecting TLS and pip needs to trust its root certificate:
`set PIP_CERT=C:\path\to\corp-root.pem` before running the installer.

### Running it

```
run.bat
```

A window opens. There is no browser, no localhost and no port — the app is a Qt
window, and `run.bat` launches it with `pythonw.exe` so no console sits behind
it. Passing a board file works too: `run.bat boards\demo-stats.json`.

---

## 2. Using the app

**Left rail** — the card types. Drag one onto the canvas to place it exactly;
click it to drop it in the first free spot that fits. The search box filters by
name, blurb and id. Clear canvas and Import board JSON sit at the foot of this
rail.

**Canvas** — drag a card to move it, pull the bottom-right grip to resize. The
readout under the canvas shows live coordinates while you drag, and the ruler
along the top lights up the columns the card currently spans. Arrow keys nudge
the selection one cell.

**Right rail** — settings for the selected card. Fields marked `*` are
required; the build fails loudly if one is empty rather than emitting a card
that quietly returns nothing.

**Bottom drawer** — the compiled output, recompiled about a quarter second
after every change. The status line in the top bar says whether the board
compiles and how many warnings it has.

The menu bar carries everything the top bar does not: New, Open, Import board
JSON, Duplicate, Delete, and **Reload card types**. Everything in the menus that
you reach for daily is also a button.

| Shortcut | Action |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo. `Ctrl+Y` also redoes, since that is Windows' own standard |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / save as |
| `Ctrl+O` | Open a saved board |
| `Ctrl+N` | New board |
| `Ctrl+D` | Duplicate the selected card |
| `Ctrl+E` | Copy for ServiceNow |
| `Ctrl+R` | Reload card types from disk |
| `Ctrl+T` | Toggle the app theme |
| `Ctrl+Q` | Quit |
| `` Ctrl+` `` | Show or hide the output drawer |
| `Delete` | Remove the selection, except locked cards |
| `Esc` | Clear the selection |
| Arrows | Nudge one grid cell |
| `F1` | Shortcuts |

Your work is autosaved as a draft, so closing the window does not lose it.
**Save** writes a named copy to `boards\` on disk; **Export board JSON** writes
it wherever you choose, so you can commit it to Git.

Start from `examples\security-operations.json` — import it, then fix every
filter against your own tables.

### Where your files live

| What | Where |
|---|---|
| Saved boards | `boards\` beside the app |
| Draft, presets, theme, window size | `%APPDATA%\WidgetForge\state.json` |
| Card types | `modules\` beside the app |

State is kept out of the tree so a standalone build can sit somewhere
unwritable, and because none of it is work you would want to copy to another
machine. If neither location is writable the app still starts and says so in
the status bar — it just will not remember anything between runs.

On a first run, before you have chosen one, the app follows the desktop's own
light/dark setting. After that it remembers your choice.

### Boards that need repairing

A board file that has been hand-edited into a shape the app cannot lay out — a
card with no size, a size larger than the grid, two cards sharing an id — is
repaired on the way in, and a dialog lists exactly what was changed. Nothing is
written back until you save, so closing without saving keeps the original file
as it was.

---

## 3. Why 24 × 16

24 divides evenly by 2, 3, 4, 6, 8 and 12, so halves, thirds, quarters and
sixths all land on exact column boundaries. A 6-wide card is a quarter; an
8-wide is a third.

The canvas *is* the layout. Each card's x/y/w/h compiles into an explicit CSS
Grid coordinate — `.wf-c-donut_1 { grid-column: 1 / span 9; grid-row: 5 / span 6; }`.
What you arrange is what ships.

**The board fills the screen and does not scroll.** Sixteen rows is the whole
height, divided as fractions rather than fixed pixels, so the same board fills
a 1080p monitor and a laptop panel without reflowing. A card that would end
past row 16 is a build error, not a warning — there would be no way to reach
it. Cards still scroll their own contents: tables, lists and legends get an
internal scrollbar and the page around them stays put.

The widget measures how much portal chrome sits above it and sizes itself to
the remainder, rather than assuming a fixed header height. If it comes out
slightly short or tall on your portal, `c.fit()` in the client script is the
one place that decides it.

Below 900px this is suspended: sixteen bands cannot fit a phone, so the board
stacks to one card per row and the page scrolls normally.

---

## 4. Getting a board into ServiceNow

Two routes.

### 4a. Copy for ServiceNow — the normal route

Click **Copy for ServiceNow**. It lists the four fields in paste order with a
copy button and a save button each, and ticks them off as you go.

Paste **CSS first.** It is the field most likely to be rejected, and it fails
fastest, so you find out before spending effort on the other three. Then HTML
template, then client controller, then server script.

Use a scratch `sp_widget` the first time. Never paste over a widget you care
about, and never over an existing production widget, until you have seen the board render.

**Save all four** asks for a folder and writes them as separate files, which is
easier than the clipboard when you are committing the output to Git alongside
the board JSON.

### 4b. Update Set XML

Click **Update Set**. You are asked for a widget name and, optionally, an
existing `sys_id`:

- Leave the `sys_id` blank to create a new widget.
- Paste an existing `sys_id` to update that widget in place.

Choose where to write the file. In ServiceNow: **Retrieved Update Sets → Import
Update Set from XML**, pick the file, then **Preview** and **Commit**.

This is the route that creates the widget record for you, and the one to use
when the change crosses an instance boundary, because it goes through normal
update set review. It needs no credentials and no network.

---

## 5. The app never touches your instance

There is no push, no stored credentials, and no network call to ServiceNow
anywhere in WidgetForge. There is no HTTP client in the source at all, and the
test suite asserts that across every Python file under `wf/`, plus `main.py` —
if someone adds one, the suite fails. The same test now also fails if anything reintroduces a
server: no Flask, no sockets, no listening.

That means there is no drift detection, and none is needed: you are looking at
the field before you replace it. The tradeoff is that nothing warns you if
somebody hotfixed the widget in Studio, so check the record's **Updated** and
**Updated by** before you paste over it.

A read-only preview, where the app runs your filters as GET queries so the
canvas shows real numbers, would slot in without disturbing any of this. It is
not built.

## 5b. Board settings

**Board** in the top bar sets things that apply to every card.

**Default table.** Cards with no table of their own use it. New cards are
created with their table left blank so the default actually applies — a module
default would otherwise win silently and the board setting would do nothing.
The tick box clears the table on cards you already placed.

**Base filter.** ANDed in front of every card filter. A card asking for
`priority=1` on a board based on `active=true` queries `active=true^priority=1`.
A card with no filter of its own just gets the base.

**Board appearance.** Dark or light, for the compiled dashboard in the portal.
This is separate from the app's own light/dark toggle.

---

## 5c. Working on the canvas

Drag from the palette to place a card exactly; double-click one to drop it in
the first free spot. Shift-click adds to the selection, and dragging a
selection moves it all together. With two or more selected, the right rail
shows align, match-size and spread controls.

**Lock** stops a card being moved, resized or deleted by accident. Delete skips
locked cards and says so rather than doing nothing.

**Save as preset** stores a configured card — table, filter, columns and all —
under the Presets heading in the palette. Presets live in your app settings,
not in the board file, so they follow you across every board on this machine.

Warnings under the canvas are buttons. Clicking one selects the card it names.

---

## 6. Adding a card type

No compiler changes, and no application changes. Drop a folder into
`modules\<id>\`:

1. **`module.json`** — `name`, `blurb`, `icon`, `accent`, `size` `[w,h]`,
   `min` `[w,h]`, and `fields[]`.
2. **`server.js`** — exactly one top-level `function run<Name>(s)` returning a
   plain object. The loader finds the name itself, so there is no naming
   contract to get wrong.
3. **`template.html`** — one root element, guarded with
   `ng-if="card.kind === '<id>'"`.
4. **`style.css`** — flat CSS, appended after the shell styles.
5. **`client.js`** — usually empty. Spliced inside the controller with `c`,
   `$scope` and `$sce` in scope. Post-render DOM work goes in `c.onRender(fn)`.

Then run the suite. It checks the new module on its own and on a board with
every other card type, and it builds your module's inspector for every option
of every select field to prove the UI can render it.

The module cache is keyed on the modification time and size of every file under
`modules\` and `shell\`, so editing a fragment in an editor takes effect on the
next compile with no restart. A brand new folder appears in the palette after
**View → Reload card types** (`Ctrl+R`).

**Field types:** `text`, `number`, `select` (needs `options`), `toggle`,
`textarea`, `list` (one per line), `pairs` (`Label | value`), `query`.
A field can carry `showIf: {"otherKey": ["a","b"]}`; hidden fields are omitted
from the compiled output rather than carried through stale.

`icon` must name one of the glyphs in `wf/ui/icons.py`. A test fails if a
module asks for one that does not exist, because the palette would otherwise
silently fall back to a generic mark.

**Defaults in `module.json` are JSON strings.** A multi-line default for a
`pairs` or `list` field needs `\n`, not `\\n`. Writing `\\n` produces a literal
backslash-n, the whole default collapses into one entry with a nonsense field
name, and the card compiles cleanly and renders blank. Three modules shipped
with exactly that bug; there is now a test for it.

Shell helpers available to every runner: `wfCount`, `wfAgg`, `wfGroup`,
`wfTrend`, `wfTopKeys`, `wfArc`, `wfComma`, `wfPercent`, `wfTrim`, `wfColor`,
`wfNum`, `wfRound`, `wfPoint`.

---

## 7. Updating WidgetForge

```
update.bat                              apply everything in updates\ newer than VERSION
update.bat wf-update-3.6.0.zip          unpack an update pack and apply it
update.bat --check                      dry run, changes nothing
update.bat --rollback                   restore the last backup
```

Use `update.bat` rather than `py update.py`. The updater runs the test suite
after patching, and that suite needs PySide6, which lives in `venv\` and not in
your system Python. Launching with `py` meant the tests failed on a missing
dependency and rolled back a change that was actually fine. The updater
resolves the venv interpreter itself, and `update.bat` removes the question
entirely.

Every run backs the tree up to `.backup\` first, then runs the test suite
afterwards. A failed patch or a failed test restores the backup automatically —
you cannot end up on a half-applied version. `boards\` and `venv\` are never
touched.

See `updates\README.md` to write one.

---

## 8. Building a standalone exe

`widgetforge.spec` is a PyInstaller spec for a one-folder build:

```
venv\Scripts\python.exe -m pip install pyinstaller
venv\Scripts\pyinstaller.exe widgetforge.spec
```

**This has never been built or run.** It is written from the documented
behaviour of PyInstaller and PySide6 and is a starting point, not a finished
artefact. Two things to know before you try it:

- It is deliberately *not* a one-file build. One-file unpacks to a temp
  directory on each launch, which would move `modules\` somewhere different
  every run and break the whole point of dropping in a card type.
- Expect to trim `excludes` after the first successful build. PySide6 pulls in
  a great deal of Qt that a widget builder never touches; that list is the
  difference between roughly 200 MB and something reasonable.

`modules\`, `shell\` and `boards\` sit beside the exe, and the app finds its
root by looking for them rather than assuming a layout, so it works whether
PyInstaller puts data at the top level or under `_internal\`. `WF_HOME`
overrides the search if you ever want one exe pointed at a different set of
card types.

---

## 9. Guardrails, and why each exists

| Guard | The bug it prevents |
|---|---|
| A card with no `moduleId` fails the build | It used to be dropped while the build reported success |
| A card ending past row 16 fails the build | The board does not scroll, so it would be unreachable |
| `splice()` asserts its marker appears exactly once | A helper was once never inserted because the anchor text had drifted |
| `ctx.edit()` asserts its anchor exists | Same failure, in the updater |
| Generated code is parsed for ES5 violations | Rhino rejects arrows, `let`/`const`, template literals |
| The server script is wrapped in an IIFE | Top-level `return` is illegal outside a function, and loose `var`s collide with other widgets on the page |
| Templates are checked against what their runner returns | `card.foo` where the runner never sets `foo` renders blank and reports success |
| Generated CSS is asserted flat | Plain CSS, so nothing depends on ServiceNow's SCSS compiler |
| Settings are excluded from the ES5 scan | A filter containing a backtick is data, not code |
| Module defaults are parsed and checked | A double-escaped `\n` made a card compile clean and render blank |
| The query parser is replayed against a frozen corpus | The port from JavaScript must not drift from what it replaced |
| Board and state files are written atomically | A crash mid-write used to be able to truncate a saved board |

Warnings, not errors: overlapping cards, and cards resized below their
module's minimum.

---

## 10. What has never run inside ServiceNow

Being plain about this, because two versions ago the documentation was not.

All verification here is local and structural: the generated server and client
scripts are parsed for ES5 violations and bracket balance, the template's tags
are checked, the CSS braces are checked, and the runner/template contract is
asserted. **Nothing has executed against a live instance.** Specifically
unproven, in the order they are likely to bite:

1. **`wfTrend`'s use of `addTrendAggregate`.** The daily bucketing reads the
   `timeref` alias, with a fallback to the raw date field. This is the single
   most likely thing to need adjusting. If a trend line comes back flat or
   empty against a table that clearly has data, that function is where to look.
2. **Whether your filters return what you expect.** Validation checks that a
   filter *looks* like an encoded query, not that it is correct for the table.
   Every number is a guess until you check it against a list view.
3. **The Update Set XML.** It is well-formed and round-trips through a parser
   here, but no ServiceNow instance has imported it.
4. **Rendering.** No board has been pasted into a widget and looked at.

The Qt conversion changed none of this either way. The compiler produces
byte-identical output to 3.4.0 — that is asserted, not assumed — so a board
that would have rendered before will render now, and one that would not, still
will not.

Test protocol: scratch widget, CSS first, one card type at a time.

---

## 11. Troubleshooting on Windows

**`py` is not recognised** — Python is not on PATH. Reinstall with the PATH box
ticked, or use the full path to `python.exe`.

**Nothing happens when I run `run.bat`** — `pythonw.exe` shows no console, so a
startup error has nowhere to go. Run `venv\Scripts\python.exe main.py` instead
and read the message.

**"WidgetForge needs PySide6"** — you launched with the wrong interpreter. Use
`run.bat`, or `venv\Scripts\python.exe main.py`. `py main.py` gets system
Python, which has no PySide6.

**The palette is empty and the status bar shows an error** — a `module.json` is
malformed. The message names the file. Fix it and press `Ctrl+R`.

**The window is enormous / tiny / off-screen on a second monitor** — delete
`%APPDATA%\WidgetForge\state.json` and start again. That file holds the
remembered geometry along with presets and the draft.

**Stray `\r` in pasted fields** — the compiler emits `\n` only, and the files
written by **Save** and **Save all four** contain `\n` only. Windows' clipboard
is a different matter: Qt converts newlines to CRLF on the way out, because
that is the convention `CF_UNICODETEXT` expects, and there is no way to opt
out. It has never caused a problem in a `sp_widget` field, but if you ever
suspect it has, use **Save** instead of **Copy** and paste from the file.

**Terminal truncates long pastes** — do not paste generated code through a
terminal at all. Use the copy buttons or the Update Set XML.

**A card shows "Query failed" in the portal** — that is the error card doing
its job. The message is the actual exception from your runner; the usual cause
is a field name that does not exist on that table.
