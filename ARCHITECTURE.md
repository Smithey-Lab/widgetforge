# WidgetForge — architecture

How the program actually works. `HANDOFF.md` says *why* each decision was made;
this says *what* the code does and where. `CONTRIBUTING.md` turns it into
recipes.

---

## 1. The shape of the problem

ServiceNow Service Portal widgets are records in the `sp_widget` table. Four
fields hold all the code:

| Field | What goes in it |
|---|---|
| **Server script** | ES5 JavaScript run by Rhino on the instance. Queries tables, fills a `data` object. |
| **Client controller** | AngularJS 1.x controller function. Receives `data` as `c.data`. |
| **HTML template** | Angular template. Renders `c.cards`. |
| **CSS** | Stylesheet, scoped by convention rather than by the platform. |

There is no build step on the instance and no module system. Everything for one
widget lives in those four fields, and you paste them in by hand.

WidgetForge's job is to let you arrange cards on a grid and get those four
fields out, correct by construction. That is the whole product.

```
        boards/*.json                 modules/<id>/                shell/
      (what you arranged)          (what a card type is)      (what every board gets)
              \                            |                        /
               \                           |                       /
                +--------------------------+----------------------+
                                           |
                                  wf/compiler.py
                                           |
                            +--------------+--------------+
                            |              |              |
                     server script   client + template   CSS
                            |              |              |
                            +--------------+--------------+
                                           |
                            paste into an sp_widget record
                                    (by hand, always)
```

---

## 2. The grid, and why it is the layout

24 columns by 16 rows. 24 divides by 2, 3, 4, 6, 8 and 12, so halves, thirds,
quarters and sixths all land on exact column boundaries.

Each card's `x`, `y`, `w`, `h` compiles into one explicit CSS Grid rule:

```css
.wf-c-donut_1 { grid-column: 1 / span 9; grid-row: 5 / span 6; }
```

There is no layout algorithm at runtime — what you arranged is literally what
ships. Rows are `repeat(16, minmax(0, 1fr))`, fractions rather than pixels, so
one board fills any monitor without reflowing.

**The board does not scroll.** Sixteen rows is the whole viewport height, so a
card ending past row 16 would be unreachable; that is a build error rather than
a warning. Cards scroll their own contents (`.wf-scroll`), the page does not.
Below 900px the scheme is suspended entirely and the board stacks.

---

## 3. Data shapes

Everything in this program is one of five shapes. Learn these and the code
follows.

### 3.1 A board

The document the user edits and saves. Also exactly what `compile_board` takes.

```json
{
  "title": "Security operations",
  "subtitle": "Starter board - every filter is a guess",
  "theme": "dark",
  "defaults": { "table": "sn_si_incident", "filter": "" },
  "cards": [
    {
      "id": "number_1",
      "moduleId": "number",
      "x": 0, "y": 1, "w": 6, "h": 3,
      "locked": false,
      "settings": { "title": "Open incidents", "table": "", "filter": "active=true",
                    "agg": "count" }
    }
  ]
}
```

- `theme` is the **compiled dashboard's** appearance in the portal, not the
  app's own light/dark. `"light"` appends an extra token block to the CSS.
- `defaults.table` is used by any card that leaves `table` blank.
- `defaults.filter` is ANDed in *front* of each card's own filter.
- `id` must match `^[a-z0-9][a-z0-9_-]*$` — it becomes a CSS class name.
- `settings` keys are whatever that card type's `module.json` declares.

### 3.2 A card type — `modules/<id>/`

```
modules/donut/
  module.json      metadata and the field list
  server.js        exactly one top-level function run<Name>(s)
  template.html    ONE root element, guarded by ng-if="card.kind === 'donut'"
  style.css        flat CSS, appended after the shell styles
  client.js        usually empty; spliced into the controller
```

`module.json`:

```json
{
  "name": "Donut chart",
  "blurb": "Share of a total, by group.",
  "icon": "donut",
  "accent": "#d9b26a",
  "size": [8, 6],
  "min": [6, 5],
  "bare": false,
  "fields": [
    { "key": "table", "label": "Table", "type": "text",
      "required": true, "default": "incident" },
    { "key": "agg", "label": "Calculate", "type": "select", "default": "count",
      "options": [["count", "Count of records"], ["sum", "Sum of a field"]] },
    { "key": "aggField", "label": "Field", "type": "text",
      "showIf": { "agg": ["sum", "avg", "max", "min"] },
      "help": "Numeric field name to aggregate." }
  ]
}
```

| Key | Meaning |
|---|---|
| `name`, `blurb` | Shown in the palette. Searchable along with the folder id. |
| `icon` | Must be a key in `wf/ui/icons.py`'s `PATHS`. A test enforces this. |
| `accent` | Hex colour for this card's icon chip and selection border. |
| `size` | `[w, h]` the card is created at. |
| `min` | `[w, h]` below which a warning is raised. Not an error. |
| `bare` | Optional. A bare card renders with no header chrome (`heading` uses it). |
| `fields[]` | Drives both the inspector and `normalise`. |

Field keys: `key`, `label`, `type`, and optionally `default`, `required`,
`help`, `options` (select only), `showIf`.

Field types — eight supported, seven currently used by shipped modules:

| Type | Editor | Compiles to |
|---|---|---|
| `text` | `QLineEdit` | trimmed string |
| `number` | `QLineEdit` with a numeric validator | int, or float, or the default |
| `select` | `QComboBox` | the chosen option's value |
| `toggle` | `QCheckBox` | bool |
| `textarea` | `QPlainTextEdit` | trimmed string |
| `list` | `QPlainTextEdit`, one per line | `["a", "b"]` — supported, unused so far |
| `pairs` | `QPlainTextEdit`, `Label \| value` per line | `[{"label": …, "value": …}]` |
| `query` | `ConditionEditor` | encoded-query string |

`showIf: {"otherKey": ["a", "b"]}` hides a field unless `otherKey` currently
holds one of those values. **A hidden field is omitted from the compiled
output, not carried through stale** — that rule lives in `normalise`, not the
UI.

### 3.3 The build result

`compile_board` returns:

```python
{
  'server':   str,    # the whole server script
  'client':   str,    # the whole client controller
  'template': str,    # the whole HTML template
  'css':      str,    # the whole stylesheet
  'warnings': [str],  # non-fatal: overlaps, undersized cards
  'modules':  [str],  # the card type ids actually used, sorted
  'cards':    int,
  'version':  str,
}
```

Errors are not in this dict. A board that cannot compile raises `BuildError`
with every problem joined by `; `.

### 3.4 The compiled server script

```javascript
/* Generated by WidgetForge 3.5.0 on <date> UTC. Edit the board, not this file. */
(function () {                       // IIFE: top-level return is illegal, and
  … shell/server.js …                // loose vars collide with other widgets
  // --- card runners ---
  function runDonut(s) { … }         // only the types this board uses
  var WF_RUNNERS = {};
  WF_RUNNERS['donut'] = runDonut;
  var WF_CARDS = [ … ];              // the settings payload, as JSON
  data.cards = [];                   // the build loop: run each card, catch each
  data.board = { title: …, subtitle: … };
})();
```

The build loop wraps every runner in a `try`, so one card whose query throws
becomes an error card on the dashboard instead of an empty widget.

### 3.5 App state — `%APPDATA%\WidgetForge\state.json`

`theme`, `presets`, `draft`, `lastSysId`, `geometry`, `windowState`,
`drawerHidden`. Deliberately **not** in the tree: a packaged build may sit
somewhere unwritable, and none of it is work worth copying to another machine.
`theme` is `null` until the user picks one, which is what lets a first run
follow the desktop's own light/dark setting.

---

## 4. The compile pipeline

`wf/compiler.py`, top to bottom. This is the only file whose output reaches a
production instance, and it is deliberately small.

**1. `load_modules()`** walks `modules/*/`, reads `module.json` and the four
fragments, and finds the runner by scanning `server.js` for exactly one
top-level `function run<Name>(s)`. Exactly one — zero or two is a `BuildError`.
Scanning rather than deriving the name from the folder removes a contract that
could be got wrong silently.

**2. `load_shell()`** reads the four `shell/` fragments included on every board.

**3. `validate(board, mods)`** returns `(errors, warnings)`. Errors: missing or
duplicate id, an id that is not a slug, unknown `moduleId`, non-numeric or
zero-size geometry, running off any edge, a required field left empty. Warnings:
overlap, and a card smaller than its module's `min`.

**4. `inherit(board, meta, raw)`** folds the board's defaults into one card's
raw settings — blank table takes the board's, base filter is ANDed in front.
Called from both `validate` and `compile_board`, from the same function, so the
two can never disagree about what a card actually queries.

**5. `normalise(meta, raw)`** turns raw UI values into the exact shapes each
runner expects, and drops fields hidden by `showIf`.

**6. Assembly.** Server script: shell helpers, then only the runners this board
uses, then the runner registry, then the settings payload, then the build loop,
all inside one IIFE. Client: `shell/client.js` with each used module's
`client.js` spliced at `/* WF:CLIENT_MODULES */`. Template: `shell/template.html`
with each used module's fragment spliced at `<!-- WF:CARD_TEMPLATES -->`. CSS:
shell styles, each used module's styles, then one grid rule per card, then the
light block if the board asked for it.

**7. Guards.** Every one of these exists because something got through a review:

| Guard | The bug it prevents |
|---|---|
| `assert_es5` | Rhino rejects arrows, `let`/`const`, template literals, spread |
| `assert_balanced` | An unclosed brace that a regex would not notice |
| `splice` asserts its marker appears exactly once | A helper silently never inserted because the anchor drifted |
| CSS brace balance and a flat-CSS check | Removes the dependency on ServiceNow's SCSS compiler |
| Template non-empty | An empty template compiles and renders nothing |

**The settings payload is excluded from the ES5 scan.** A filter containing a
backtick or `=>` is data inside a JSON string literal, not code. Scanning it
produced false build failures on legitimate boards.

**Angle brackets in the payload are escaped** (`<`), so the script stays
inert if it is ever pasted inside an HTML `<script>` block while debugging.

### Caching

`load_cached()` returns `(mods, shell)`, reloading only when the mtime or size
of any file under `modules/` or `shell/` has changed. The Flask build reloaded
all 65 files on every request, which is what made a newly dropped card type
appear on a browser refresh; the cache keeps that property without re-reading
the tree on every keystroke. The stamp costs about 0.7 ms; a full compile of an
11-card board costs about 6 ms.

### Finding the tree

`_find_root()` looks for the directory containing `VERSION`, `modules/` and
`shell/`, trying `WF_HOME`, then the executable's folder and `sys._MEIPASS` when
frozen, then the source layout. Checking for the files rather than assuming a
layout is what makes the PyInstaller build work whether data lands at the top
level or under `_internal/`. `USER_ROOT` — where `boards/` goes — is the
executable's folder when frozen, so a user's boards never end up inside a
bundle.

---

## 5. Module map

Nothing in `wf/` outside `wf/ui/` imports PySide6. That is enforced by a test.

```
main.py                72   entry point; a readable message if PySide6 is missing
wf/compiler.py        747   board JSON in, four sp_widget fields out
wf/model.py           452   board, grid, collision, alignment, undo, sanitising
wf/query.py           132   encoded-query parse / build / round-trip guard
wf/boards.py          229   board files and app state, written atomically
wf/ui/theme.py        263   colour tokens and the Qt style sheet
wf/ui/icons.py        249   an SVG path parser and the glyph set
wf/ui/canvas.py       599   the grid canvas and the column ruler
wf/ui/palette.py      299   card types and presets
wf/ui/inspector.py    361   the settings rail, generated from module.json
wf/ui/condition.py    299   the condition builder widget
wf/ui/output.py       119   the four-pane output drawer
wf/ui/dialogs.py      279   board settings, shortcuts, paste panel, update set
wf/ui/main_window.py 1053   assembles everything and owns the board
tests.py             1409   773 assertions
```

### `wf/model.py` — the board, Qt-free

`BoardModel` owns one board dict and its undo history.

```
sanitise_board(raw)  -> (board, repairs)   never raises, whatever raw is
occupied(cards, …)   -> {(x, y), …}        clamped to the grid
fits(cards, x,y,w,h) -> bool
find_spot(cards,w,h) -> (x, y) | None      first free slot, scanning across
next_id(cards, mid)  -> "mid_3"

BoardModel:
  cards / card(id) / card_at(x, y)
  begin() push_state(json) undo() redo() can_undo() can_redo() snapshot()
  replace(board, keep_history=True) -> repairs
  add_card(module_id, meta, at, board_default_table)
  add_preset(preset) / duplicate(id) / remove(ids) / clear()
  align(ids, how) / nudge(ids, dx, dy)
  occupied() / fits() / find_spot()
```

**The undo contract:** call `begin()` *before* mutating. Mutating without it
silently makes the change unundoable. Drag is the exception — it mutates live,
so it captures `snapshot()` at mouse-down and hands it to `push_state()` on
release.

**`sanitise_board` is the single door every board comes through.** It repairs
rather than refuses, and returns a list of what it changed so the user can be
told. It coerces geometry to ints, clamps sizes to the grid, renames duplicate
ids, replaces illegal ids, drops entries that are not cards, and forces
`settings` to a dict. It does *not* pull a card back inside the right or bottom
edge — that stays a compiler error, because the "does not scroll" rule should
stay visible.

**`nudge` moves the whole selection or none of it,** so a card against an edge
cannot slide out from under its neighbours.

### `wf/query.py` — encoded queries

ServiceNow encoded queries look like `active=true^priority=1^ORpriority=2`.

```
parse_query(q) -> (rows, raw)   raw=True means "do not touch this"
build_query(rows) -> str
cond_safe(q) -> rows | None     None means "leave the text box alone"
```

The governing rule: **a builder that quietly rewrites a working filter is worse
than a text box.** `cond_safe` parses, re-serialises and compares byte for byte;
anything that does not come back identical stays raw and untouched. `^ORDERBY`,
`^NQ` and `^EQ` all fall back this way.

Two parsing traps, both fixed, both easy to reintroduce:

1. **Searching for the operator breaks on values that contain one.**
   `state=IN_PROGRESS` would parse as field `state=`, operator `IN`. `OP_RE`
   anchors on a field-name pattern (`[a-z0-9_.]+`) *first*, then the operator,
   with the alternation ordered longest-first so `ISNOTEMPTY` beats `ISEMPTY`
   and `>=` beats `>`.
2. **`^OR` can prefix a genuine field name.** The OR branch only fires when
   what follows also parses as a condition.

This module was ported from the JavaScript it replaced. Both were run against
6,016 generated queries and agreed on every one; 1,500 of those, with the
answers the *JavaScript* gave, are frozen in `tools/query-corpus.json` and
replayed by the suite. That file is the only surviving record of the original
behaviour.

### `wf/boards.py` — files and state

Every write goes through `_atomic_write`: a temp file **in the same directory**,
then `os.replace`. Same directory matters — `os.replace` is only atomic within
one filesystem, and `%TEMP%` is often a different volume from the Desktop.

`safe_stem` appends `-board` when a slugged title collides with a Windows
reserved device name (`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`),
which Windows refuses as a filename with an opaque error.

`State` is forgiving on read: a corrupt or wrongly-shaped state file degrades to
defaults rather than stopping the app from starting.

---

## 6. The UI layer

### Composition

```
MainWindow (QMainWindow)
├─ menu bar                      File / Edit / View / Help
└─ central widget
   ├─ top bar                    brand, title, subtitle, status, board picker,
   │                             undo/redo, Board, Save, Save as, JSON,
   │                             Update Set, Copy for ServiceNow, ?, theme
   └─ QSplitter (vertical)
      ├─ QSplitter (horizontal)
      │  ├─ PaletteRail          search, card types, presets, Clear / Import
      │  ├─ stage
      │  │  ├─ Ruler             24 column ticks, lit during a drag
      │  │  ├─ GridCanvas        the board
      │  │  └─ HUD + issue chips
      │  └─ InspectorRail        actions, then one editor per module field
      └─ OutputDrawer            four read-only panes, in paste order
```

### The canvas is custom-painted

One `paintEvent`, not a `QGraphicsScene`. A scene graph would introduce a second
coordinate system to keep in step with the one the compiler emits, and that is
exactly the sync that would drift. Instead there is **one function, `cell_rect`,
and painting, hit-testing and drop targeting all go through it**, so they cannot
disagree.

```python
def cell_rect(self, x, y, w=1, h=1) -> QRectF   # grid cell -> pixels
def cell_at(self, pos)              -> (x, y)   # pixels -> grid cell
def drop_cell(self, pos, w, h)      -> (x, y)   # centred on the pointer, clamped
def card_hit(self, pos)             -> card     # later cards win, matching paint order
def grip_rect(self, card)           -> QRectF   # the resize corner
```

Drag-and-drop from the palette uses real Qt DnD with two private MIME types,
`application/x-widgetforge-module` and `…-preset`.

### Signals

| Emitter | Signal | Handled by | Meaning |
|---|---|---|---|
| `GridCanvas` | `selectionChanged` | `_selection_changed` | repoint the inspector |
| | `boardChanged` | `refresh(structural=True)` | recompile and repaint |
| | `liveMoved` | `_live_moved` | mid-drag: position readout only |
| | `hudChanged(str)` | `_hud` | the coordinate readout |
| | `statusMessage(str, str)` | `set_status` | text, kind |
| | `placeModule(str,int,int)` | `_drop_module` | a drop landed |
| | `placePreset(str,int,int)` | `_drop_preset` | |
| `PaletteRail` | `place(kind, name)` | `_place_from_palette` | click: first free spot |
| | `forgetPreset(str)` | `_forget_preset` | |
| | `clearCanvas` / `importBoard` | `clear_canvas` / `import_json` | |
| `InspectorRail` | `settingsChanged` | `refresh(structural=False)` | recompile only |
| | `structureChanged` | `refresh(structural=True)` | also repaint the canvas |
| | `action(str)` | `_card_action` | `dup` / `lock` / `del` / `preset` |
| | `alignRequested(str)` | `_align` | |
| `ConditionEditor` | `changed(str)` | the inspector's field setter | |
| | `aboutToRemoveRow` | `model.begin` | deleting a row is an undo step |
| `OutputDrawer` | `copyRequested(str)` | `_copy_pane` | |
| | `toggled(bool)` | `_drawer_toggled` | |

### `refresh(structural)` — and the bug it encodes

`structural=True` prunes the selection, repaints the canvas and re-points the
inspector. `structural=False` only schedules a recompile.

`InspectorRail.show_card` **rebuilds only when the card id or the selection size
actually changes.** Typing into a field that also affects the canvas (title,
table, filter, group-by, date field) fires `structureChanged` on every
keystroke, and an unconditional rebuild destroyed the widget under the cursor —
the caret vanished after the first character. A position readout is one label,
not a reason to tear down a form. There is a test that types fourteen
characters and asserts the editor is the same object at the end.

### Compilation

In-process, on a 240 ms single-shot `QTimer`. No server, no port, no thread —
`compile_board` is called directly, the same call the test suite makes, and a
`BuildError` becomes a status message rather than a 400.

Status messages fade after six seconds; the compile readout does not. It is a
state indicator, not an event — a board that has not changed for a minute is
still compiling fine.

### Theming

`wf/ui/theme.py` holds two token dictionaries with identical key sets (asserted)
and one Qt style sheet built by `%`-substitution — so a placeholder with no
token is a `KeyError` at startup rather than a silently missing colour. Qt style
sheets are not CSS: no variables, no nesting, a narrow property set.

Widgets that paint themselves (`GridCanvas`, `Ruler`, `Swatch`) read tokens
directly rather than through the style sheet. Changing an object name at runtime
needs `style().unpolish()` / `polish()` to take effect.

### Icons

The card glyphs are the same SVG paths the web build used, parsed into
`QPainterPath`s once and stroked at whatever size and colour is asked for —
which is how a module's own `accent` reaches its icon. The path parser handles
`M`, `L`, `H`, `V`, `A` and `Z`, absolute and relative, and raises on anything
else rather than silently drawing nothing. The arc conversion is the standard
W3C endpoint-to-centre formula, because Qt has no endpoint arc.

The UI glyphs (undo, redo, sun, moon, lock) are drawn for a different reason:
the obvious characters for them are not in every Windows UI font, and a missing
glyph renders as a tofu box.

---

## 7. The test suite

`tests.py` is one flat script, not a framework. `ok(condition, label)` and
`raises(fn, label, needle)`; it prints `N passed, M failed` and exits non-zero
on any failure. 773 assertions in 28 sections.

Run it with `QT_QPA_PLATFORM=offscreen`. The interface section skips cleanly
when PySide6 is missing, so the compiler can still be tested without it — that
path is real, and gives 657 of the 773.

Sections, in file order: modules · a full board · ES5/Rhino · layout · only
what you use · guards · settings · update set · offline only · slug · contracts
· html balance · payload safety · fixed viewport · theme parity · query builder
safety · css selector hygiene · board inheritance · board theme · module
defaults · the model · board files · sanitising a bad board · Windows filenames
· documentation · the app · the count in the docs · report.

Six of these catch whole classes of bug rather than one instance:

- **Runner/template contract.** Every `card.foo` in a template is checked
  against what that module's runner actually returns. A template reading a
  field the runner never sets renders blank and reports success — the worst
  failure mode a generator has.
- **Module defaults.** Every module's own defaults are normalised and checked.
  This is what would have caught the `\\n` bug.
- **The frozen query corpus.** 1,500 queries with the answers the original
  JavaScript gave.
- **The window renders.** The suite builds the real window offscreen, places a
  card of every type, compiles, and renders the whole thing to a pixmap in both
  themes — plus the empty canvas and a board naming a card type that is not
  installed. A `paintEvent` that raises leaves a blank window and no traceback
  anywhere a user would see it, so "it painted" is an assertion.
- **Duplicate selectors**, in both the widget shell CSS and the Qt style sheet.
  Two rules with the same selector silently fight.
- **The documentation.** Every file path the docs name must exist, every path
  they say is deleted must be gone, every module must appear in the map above,
  every shell helper must be documented and every documented helper must exist,
  every shortcut the docs or the in-app list promise must actually be bound and
  every bound shortcut must be written down somewhere — and the assertion count
  quoted in `README.md` and `HANDOFF.md` must equal the number this suite
  prints. A confidently wrong document is worse than no document.

---

## 8. What is not here

- **No instance connection.** No HTTP client, no credentials. A Table API push
  with drift detection was built and deliberately removed in 3.2.0. Asserted by
  a grep across every Python file under `wf/` plus `main.py`.
- **No true OR groups.** A mixed and/or list compiles to a flat `^`/`^OR` chain,
  which ServiceNow evaluates left to right. Real `^NQ` clauses are a feature,
  not a tweak, and no dashboard has needed one yet.
- **No tabs inside one widget.** One board = one screen = one widget; navigate
  with the portal menu.
- **No maps, modals or typeahead.** Complex custom dashboards stay hand-written. The
  rule is the author's: *if it needs to be that custom, it can be hard coded.*
- **No verification against a live instance.** See `DEPLOY.md` §10 for exactly
  what is unproven. This is the largest open risk in the project and it has not
  moved.
