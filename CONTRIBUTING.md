# WidgetForge — how to change it

Recipes for the things people actually need to do. Read `CLAUDE.md` for the
rules and `ARCHITECTURE.md` for how the pieces fit; this is the how-to.

Every recipe here ends the same way, so it is stated once:

```
venv\Scripts\python.exe tests.py          # must print ALL PASS
python3 -m pyflakes main.py wf/*.py wf/ui/*.py tests.py
```

On anything but Windows, or over a remote shell, prefix with
`QT_QPA_PLATFORM=offscreen`.

---

## Contents

1. [Add a card type](#1-add-a-card-type)
2. [Add a field type](#2-add-a-field-type)
3. [Add an icon](#3-add-an-icon)
4. [Add a shell helper](#4-add-a-shell-helper)
5. [Change the grid size](#5-change-the-grid-size)
6. [Add a panel, dialog or button](#6-add-a-panel-dialog-or-button)
7. [Change a colour](#7-change-a-colour)
8. [Write a test](#8-write-a-test)
9. [Prove the compiler did not change](#9-prove-the-compiler-did-not-change)
10. [Look at the UI without a screen](#10-look-at-the-ui-without-a-screen)
11. [Debug the usual failures](#11-debug-the-usual-failures)
12. [Ship a version](#12-ship-a-version)

---

## 1. Add a card type

**No Python changes. None.** If you think you need one, stop and read step 6 of
this recipe first.

Create `modules/<id>/` where `<id>` is lowercase, matches
`^[a-z0-9][a-z0-9_-]*$`, and is not already taken.

### 1. `module.json`

```json
{
  "name": "Sparkline",
  "blurb": "A tiny trend, no axes.",
  "icon": "line",
  "accent": "#63c98a",
  "size": [6, 3],
  "min": [4, 2],
  "fields": [
    { "key": "title", "label": "Title", "type": "text", "default": "" },
    { "key": "table", "label": "Table", "type": "text",
      "required": true, "default": "incident" },
    { "key": "filter", "label": "Filter", "type": "query",
      "help": "Encoded query, e.g. active=true^priority=1" },
    { "key": "dateField", "label": "Date field", "type": "text",
      "required": true, "default": "opened_at" },
    { "key": "days", "label": "Days back", "type": "number", "default": 14 }
  ]
}
```

`icon` must be a key in `wf/ui/icons.py`'s `PATHS` — a test fails otherwise,
because the palette would silently fall back to a generic mark. See recipe 3 to
add a new one.

**A multi-line default needs `\n`, not `\\n`.** This is JSON. Writing `\\n`
produces a literal backslash-n, the whole default collapses into one entry, and
the card compiles clean and renders blank. Three modules shipped with exactly
that bug. There is now a test, and it will catch you.

### 2. `server.js`

Exactly one top-level function, named `run<Anything>`, taking the normalised
settings and returning a plain object. The loader finds the name by scanning, so
there is no naming contract to get wrong — but zero or two matches is a
`BuildError`.

```javascript
function runSparkline(s) {
  var t = wfTrend(s.table, s.filter, s.dateField, s.days);
  var pts = t.points, n = pts.length;
  var max = t.max > 0 ? t.max : 1;
  var line = '';
  for (var i = 0; i < n; i++) {
    var x = n > 1 ? (i / (n - 1)) * 100 : 50;
    var y = 30 - (pts[i].value / max) * 28;
    line += (i ? ' ' : '') + (Math.round(x * 10) / 10) + ',' + (Math.round(y * 10) / 10);
  }
  return { points: line, total: wfComma(t.total), empty: n === 0 };
}
```

ES5 only. No arrow functions, no `let`/`const`, no template literals, no spread,
no classes — Rhino rejects all of it and `assert_es5` will stop the build.

Helpers available to every runner:

| Helper | Returns |
|---|---|
| `wfCount(table, filter)` | a row count |
| `wfAgg(table, filter, agg, field)` | `count` / `sum` / `avg` / `max` / `min` |
| `wfGroup(table, filter, field, limit)` | `[{label, value, color, pct}]`, biggest first, remainder folded into `Other` |
| `wfTrend(table, filter, dateField, days)` | `{points: [{key, label, value}], total, max}` |
| `wfTopKeys(map, limit)` | keys of a `{label: count}` map, biggest first |
| `wfArc(cx, cy, rOuter, rInner, a0, a1)` | an SVG donut-segment path |
| `wfPoint(cx, cy, r, deg)` | `{x, y}` on a circle, 0° = 12 o'clock |
| `wfColor(i)` | the *i*th palette colour, wrapping |
| `wfNum(v)` / `wfRound(n)` / `wfComma(n)` | number coercion and formatting |
| `wfPercent(part, total)` | one decimal place |
| `wfTrim(s, n)` | truncate with an ellipsis |

### 3. `template.html`

**One root element**, guarded on your own kind.

```html
<div class="wf-spark" ng-if="card.kind === 'sparkline'">
  <div class="wf-empty" ng-if="card.empty">No data in range</div>
  <svg viewBox="0 0 100 30" preserveAspectRatio="none" ng-if="!card.empty">
    <polyline ng-attr-points="{{card.points}}" class="wf-spark-line"></polyline>
  </svg>
  <div class="wf-spark-total" ng-if="!card.empty">{{card.total}}</div>
</div>
```

Every `card.<name>` you read here must be something your runner returns.
`card.id`, `card.kind`, `card.title`, `card.bare`, `card.note`, `card.message`
and `card.errTag` come from the shell and are always available. **A test checks
this** — a template reading a field the runner never sets renders blank and
reports success, which is the worst failure mode a generator has.

### 4. `style.css`

Flat CSS. No nesting, no `&`. Prefix classes with `wf-`, and do not reuse a
selector another module already defines — a test fails on duplicates.

```css
.wf-spark { display: flex; flex-direction: column; height: 100%; }
.wf-spark-line { fill: none; stroke: var(--wf-accent); stroke-width: 2; }
.wf-spark-total { font-size: 20px; font-weight: 600; }
```

### 5. `client.js`

Usually empty — create it as an empty file. If you need post-render DOM work,
register it:

```javascript
c.onRender(function () { /* the DOM exists by now */ });
```

`c`, `$scope`, `$sce`, `$element`, `$timeout` and `$window` are all in scope.

### 6. Check it

```
QT_QPA_PLATFORM=offscreen python3 tests.py
```

The suite picks the new module up automatically — roughly twenty assertions
appear the moment the folder exists. It checks the fragments, the ES5, the
template contract, the CSS, the defaults, and builds your inspector for every
option of every select field. In the running app, **Ctrl+R** reloads card types
without a restart.

Two of those new assertions will fail, on purpose:

```
FAIL  HANDOFF.md mentions the "Sparkline" card type
FAIL  README.md and HANDOFF.md both say 796 assertions (they say [773])
```

That is the documentation guard, not a bug in your module. Add the card type to
the list in `HANDOFF.md` §1 and update the assertion count in `README.md` and
`HANDOFF.md` to the number the suite now prints. A card type nobody wrote down
is a card type the next person will not know exists.

**If the recipe needed a Python change, that is a finding.** The module contract
is missing something, and the right move is to say so rather than special-case
the new type.

---

## 2. Add a field type

Rarer, and it touches two files that must agree.

1. **`wf/compiler.py`, `normalise()`** — add a branch that turns the raw UI
   value into the shape runners should receive. This decides what ends up in the
   compiled payload.
2. **`wf/ui/inspector.py`, `_add_field()`** — add a branch that builds the
   editor and connects it to `self._set(key, value)`.
3. **`tests.py`** — the "modules" section asserts every field type is known;
   add yours to that tuple, and add a `normalise` case to the "settings"
   section.

Keep the two branches symmetric. If `normalise` produces a list of dicts, the
inspector has to render a list of dicts back into text — `_as_text()` in
`inspector.py` is where that already happens for `pairs`.

---

## 3. Add an icon

`wf/ui/icons.py`, the `PATHS` dict. The value is an SVG path string in a 16 × 16
viewbox.

```python
'spark': 'M2 11l3-3 3 2 6-6',
```

The parser handles `M`, `L`, `H`, `V`, `A` and `Z`, absolute and relative, and
raises on anything else. Curves (`C`, `Q`, `S`, `T`) are **not** supported —
approximate them with line segments or add the command to `painter_path()`.

Check it by rendering a contact sheet:

```python
import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import QRectF
app = QApplication([])
from wf.ui import icons
names = list(icons.PATHS)
sheet = QPixmap(64 * len(names), 64); sheet.fill(QColor('#161c25'))
p = QPainter(sheet)
for i, n in enumerate(names):
    icons.draw(p, n, QRectF(i * 64 + 8, 8, 48, 48), '#3fb9b0', 1.6)
p.end(); sheet.save('/tmp/icons.png')
```

Then open the PNG. Do not skip this — the arc code is the part most likely to be
subtly wrong, and it is invisible until you look.

---

## 4. Add a shell helper

`shell/server.js`, ES5, `wf`-prefixed camelCase. It ships on **every** board, so
keep it small and general — a helper only one card type needs belongs in that
module's `server.js`.

Document it in the table in recipe 1 and in `DEPLOY.md` §6.

---

## 5. Change the grid size

Four places, and they must agree:

1. `wf/compiler.py` — `GRID_COLS` / `GRID_ROWS`.
2. `shell/style.css` — `grid-template-columns: repeat(24, …)` and
   `grid-template-rows: repeat(16, …)`.
3. `tests.py` — the "fixed viewport" section asserts both CSS rules literally.
4. Every `module.json` whose `size` or `min` no longer fits.

`wf/model.py` and the canvas take the dimensions from the compiler, so they
follow automatically.

Consider whether you actually want this. 24 was chosen because it divides by 2,
3, 4, 6, 8 and 12; a number that does not will make thirds and sixths land
off-boundary forever after.

---

## 6. Add a panel, dialog or button

- **A dialog** goes in `wf/ui/dialogs.py` as a `QDialog` subclass with a
  `values()` method returning a plain dict. Keep Qt out of the caller's decision
  making: the dialog collects, the window decides.
- **A rail or panel** gets its own module under `wf/ui/`, exposes signals rather
  than reaching into `MainWindow`, and is wired up in `MainWindow._build_ui`.
- **A toolbar button** goes in `MainWindow._top_bar`. If it duplicates a menu
  item, connect both to the same method — never to two copies of the logic.
- **A menu item and shortcut** go in `MainWindow._build_menus` via `self._act`.
  Add it to `ShortcutsDialog.ROWS`, the `README.md` table and the `DEPLOY.md`
  table in the same commit; there is a test that the docs and the bindings agree.

Rules that keep this layer from rotting:

- **Rebuilding a form destroys the widget under the cursor.** If a panel rebuilds
  in response to editing, gate it the way `InspectorRail.show_card` does.
- **`setParent(None)` before `deleteLater()`** when clearing a layout.
- **`p.end()` on every early return** in a `paintEvent`.
- **`style().unpolish()` / `polish()`** after changing an object name at runtime.
- Read colours from `theme.tokens(name)`, never as literals.

---

## 7. Change a colour

`wf/ui/theme.py`. Add the token to **both** `DARK` and `LIGHT` — a test asserts
the key sets are identical — then reference it as `%(yourToken)s` in `_QSS`, or
read it from `tokens(self.theme)` in a widget that paints itself.

A token defined but never read fails a test too, so remove it if you change your
mind.

The compiled *dashboard's* colours are a different thing entirely:
`shell/style.css` for dark and `_LIGHT_THEME` in `wf/compiler.py` for light.

---

## 8. Write a test

`tests.py` is one flat script. `ok(condition, label)` and
`raises(fn, label, needle)`. Put it in the section it belongs to; add a section
with a `# ---- name` banner if none fits.

Two habits that make the suite worth having:

**Write the test before the fix.** If you are fixing a bug, add the assertion
that fails, watch it fail, then fix it. A test written afterwards tends to
assert the fix rather than the bug.

**Name the failure, not the behaviour.** `'a card with no moduleId fails the
build'` tells the next reader what it is protecting. `'test_validate_3'` does
not.

For UI behaviour, drive the real window offscreen — the suite already builds one
in the "the app" section, so add to it rather than starting another. Synthetic
input works:

```python
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
at = QPointF(10.0, 10.0)
widget.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, at, at, at,
                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
```

And "it painted" is a real assertion — a `paintEvent` that raises leaves a blank
window and no traceback anywhere a user sees:

```python
pm = QPixmap(win.size()); win.render(pm)
ok(not pm.isNull(), 'the window renders with a board that has no cards')
```

---

## 9. Prove the compiler did not change

Run this after touching `compile_board`, `normalise`, `inherit`, `validate` or
anything in `shell/`. It compares against 3.4.0 and normalises only the
generation timestamp and the version string.

The 3.4.0 tree lives at `.backup/pre-qt-3.4.0/` **in a real install** — it was
put there when 3.5.0 was unpacked over it, and it is not in the source zip. If
you are working from a fresh extract you will need to fetch that copy first, or
this recipe has nothing to compare against. Point the path below at wherever it
actually is.

```python
import sys, os, re, json, types, importlib.util
sys.path.insert(0, '.')

fake = types.ModuleType('flask')            # 3.4.0 was a Flask app
class _A:
    def __init__(s, *a, **k): pass
    def after_request(s, f): return f
    def route(s, *a, **k):
        def d(f): return f
        return d
fake.Flask = _A
fake.jsonify = fake.request = fake.send_from_directory = None
sys.modules['flask'] = fake

spec = importlib.util.spec_from_file_location(
    'oldapp', '.backup/pre-qt-3.4.0/app.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
from wf import compiler as new

TS  = re.compile(r'on \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC')
VER = re.compile(r'WidgetForge \d+\.\d+\.\d+')
def norm(s): return VER.sub('WidgetForge <v>', TS.sub('on <ts>', s))

om, osh = old.load_modules(), old.load_shell()
nm, nsh = new.load_modules(), new.load_shell()
bad = []
for fn in sorted(os.listdir('examples')):
    b = json.load(open('examples/' + fn, encoding='utf-8'))
    a, c = old.compile_board(b, om, osh), new.compile_board(b, nm, nsh)
    for k in ('server', 'client', 'template', 'css'):
        if norm(a[k]) != norm(c[k]):
            bad.append('%s:%s' % (fn, k))
print('differences:', bad or 'NONE')
```

If it reports differences and you intended them, say so out loud — the
byte-identity claim appears in `README.md`, `DEPLOY.md` and `HANDOFF.md` and all
three need updating together.

---

## 10. Look at the UI without a screen

```python
import os, tempfile, json
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from wf import boards as bs
from wf.ui.main_window import MainWindow

app = QApplication([])
win = MainWindow(bs.State(folder=tempfile.mkdtemp()))   # NEVER the real state dir
win.model.replace(json.load(open('examples/security-operations.json')),
                  keep_history=False)
win._sync_title_fields(); win.inspector.rebuild(); win.refresh(structural=True)
win.compile_timer.stop(); win.compile_now()             # skip the debounce
win.resize(1500, 940); win.show(); app.processEvents()
win.grab().save('/tmp/shot.png')
print(win.status.text())
```

Then open the PNG. Notes that save time:

- `compile_timer.stop()` then `compile_now()` — otherwise nothing has compiled
  yet when you grab.
- `app.processEvents()` after anything that changes layout.
- Check both themes: `win._apply_theme('light')` / `'dark'`.
- Check a narrow window: the top bar sheds its subtitle below 1240px and two
  buttons below 1120px, and that logic only runs on a real resize.
- Dialogs: construct, `show()`, `adjustSize()`, `processEvents()`, then
  `render(QPixmap(dlg.size()))`.

---

## 11. Debug the usual failures

**"Card types could not be loaded"** — a `module.json` is malformed, or a
`server.js` has zero or two top-level `run…` functions. The message names the
folder. `Ctrl+R` after fixing.

**A card renders blank in ServiceNow but compiles clean** — the template is
reading a field the runner does not return, or a `pairs` default is
double-escaped. Both have tests; run the suite first, then check the runner's
return keys against the `card.*` reads in the template.

**A trend line is flat or empty against a table with data** — `wfTrend`'s use of
`GlideAggregate.addTrendAggregate` and the `timeref` alias. This is the single
most likely thing in the project to need adjusting against a real instance. Add
a test for whatever it turns out to be *before* changing it.

**The window opens blank** — a `paintEvent` raised. Run the suite; the "the app"
section renders the whole window and would have caught it. If not, add the case.

**Typing loses the caret** — something rebuilt the form. See recipe 6.

**Palette rows draw twice** — a layout was cleared with `deleteLater()` and no
`setParent(None)`.

**`ModuleNotFoundError: PySide6`** — you used the system interpreter. Use
`venv\Scripts\python.exe`.

**Tests pass locally but the app fails to start on Windows** — `run.bat` uses
`pythonw.exe`, which has no console, so a startup error has nowhere to print.
Run `venv\Scripts\python.exe main.py` and read the message.

**A board opens with things moved** — `sanitise_board` repaired it and the
dialog said what it changed. Nothing is written back until you save.

---

## 12. Ship a version

1. `VERSION` — one line, `major.minor.patch`. It appears in the generated
   server-script header and in the update-set description.
2. `tests.py` prints `ALL PASS`.
3. pyflakes is silent.
4. If the compiler changed, run recipe 9 and update every doc that claims
   byte-identity.
5. Update `HANDOFF.md`: what changed, what you decided and rejected, and
   anything a future reader would otherwise have to reverse-engineer. This is
   the document that makes the next session cheap.
6. Update the assertion count wherever it appears — `README.md`, `HANDOFF.md`.
   A test checks the count in the docs matches the suite.
7. If you are handing files to the user: **whole files, not diffs**, and as
   downloads rather than inline code. His terminal truncates pastes around 700
   lines.

The updater (`update.bat`) still works and still gives you a full-tree backup,
anchor assertions, a test run and automatic rollback. If you edit files directly
instead, preserve the equivalent: run the suite after every change, and be able
to get back.
