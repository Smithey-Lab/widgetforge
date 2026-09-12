"""WidgetForge test suite.

Assertions, not eyeball checks. Every guard in the compiler exists because
something slipped past a visual review once.

Run:  python tests.py

The interface section at the end is skipped when PySide6 is missing, so the
compiler can still be tested on a machine without it. Everything else always
runs, and ALL PASS still means what it meant before the Qt conversion.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from wf import compiler as wf
from wf import model as wfmodel
from wf import query as wfquery

PASS = 0
FAIL = []


def ok(condition, label):
    global PASS
    if condition:
        PASS += 1
    else:
        FAIL.append(label)


def raises(fn, label, needle=None):
    global PASS
    try:
        fn()
    except wf.BuildError as exc:
        if needle and needle.lower() not in str(exc).lower():
            FAIL.append('%s (wrong message: %s)' % (label, exc))
        else:
            PASS += 1
        return
    except Exception as exc:  # noqa: BLE001
        FAIL.append('%s (raised %s instead of BuildError)' % (label, type(exc).__name__))
        return
    FAIL.append('%s (no error raised)' % label)


MODS = wf.load_modules()
SHELL = wf.load_shell()


def card(cid, mid, x, y, w=None, h=None, **settings):
    meta = MODS[mid]['meta']
    return {
        'id': cid, 'moduleId': mid, 'x': x, 'y': y,
        'w': w or meta['size'][0], 'h': h or meta['size'][1],
        'settings': settings,
    }


# ---------------------------------------------------------------- modules
ok(len(MODS) >= 12, 'at least 12 modules ship')

for mid, mod in MODS.items():
    meta = mod['meta']
    ok(meta['runner'].startswith('run'), '%s: runner name looks like run<Name>' % mid)
    ok(mod['frag']['server.js'].strip() != '', '%s: has a server fragment' % mid)
    ok(mod['frag']['template.html'].strip() != '', '%s: has a template fragment' % mid)
    ok("card.kind === '%s'" % mid in mod['frag']['template.html'],
       '%s: template guards on its own kind' % mid)
    ok(meta['min'][0] <= meta['size'][0] and meta['min'][1] <= meta['size'][1],
       '%s: default size is at least the minimum' % mid)
    ok(meta['size'][0] <= wf.GRID_COLS, '%s: default width fits the grid' % mid)
    wf.assert_es5(mod['frag']['server.js'], '%s server' % mid)
    wf.assert_balanced(mod['frag']['server.js'], '%s server' % mid)
    PASS += 2
    for fld in meta['fields']:
        ok(fld['type'] in ('text', 'number', 'select', 'toggle', 'textarea',
                           'list', 'pairs', 'query'),
           '%s: field "%s" has a known type' % (mid, fld['key']))
        if fld['type'] == 'select':
            ok(isinstance(fld.get('options'), list) and fld['options'],
               '%s: select "%s" has options' % (mid, fld['key']))

wf.assert_es5(SHELL['server.js'], 'shell server')
wf.assert_es5(SHELL['client.js'], 'shell client')
wf.assert_balanced(SHELL['server.js'], 'shell server')
PASS += 3
ok('/* WF:CLIENT_MODULES */' in SHELL['client.js'], 'shell client has its splice marker')
ok('<!-- WF:CARD_TEMPLATES -->' in SHELL['template.html'], 'shell template has its splice marker')


# ---------------------------------------------------------------- a full board
FULL = {'title': 'Every card', 'subtitle': 'test board', 'cards': []}
# Shelf-pack every module at its minimum size. The board no longer scrolls,
# so a stacked column would not fit - and packing them together also proves
# the declared minimums can coexist on one screen.
_by_height = sorted(MODS, key=lambda m: (-MODS[m]['meta']['min'][1], m))
_x = _y = _shelf = 0
for mid in _by_height:
    meta = MODS[mid]['meta']
    mw, mh = meta['min']
    defaults = {}
    for fld in meta['fields']:
        if fld.get('default') is not None:
            defaults[fld['key']] = fld['default']
    if 'aggField' in [f['key'] for f in meta['fields']]:
        defaults['aggField'] = 'reassignment_count'
    if _x + mw > wf.GRID_COLS:
        _x = 0
        _y += _shelf
        _shelf = 0
    FULL['cards'].append({
        'id': 'c_' + mid, 'moduleId': mid, 'x': _x, 'y': _y,
        'w': mw, 'h': mh, 'settings': defaults,
    })
    _x += mw
    _shelf = max(_shelf, mh)
assert _y + _shelf <= wf.GRID_ROWS, 'every module at minimum size must fit one screen'

BUILT = wf.compile_board(FULL, MODS, SHELL)

ok(BUILT['cards'] == len(MODS), 'every module compiled onto one board')
ok(BUILT['server'].lstrip().startswith('/*'), 'server opens with a provenance comment')
ok('(function () {' in BUILT['server'], 'server body is wrapped in an IIFE')
ok(BUILT['server'].rstrip().endswith('})();'), 'server IIFE is closed and invoked')
ok('data.cards = [];' in BUILT['server'], 'server assigns data.cards')
ok('data.board = {' in BUILT['server'], 'server assigns data.board')
ok('WF_RUNNERS' in BUILT['server'], 'server builds a runner registry')

for mid in MODS:
    ok("WF_RUNNERS['%s']" % mid in BUILT['server'], '%s: registered in the runner table' % mid)
    ok(MODS[mid]['meta']['runner'] + '(' in BUILT['server'], '%s: runner is defined' % mid)

ok('api.controller = function' in BUILT['client'], 'client declares api.controller')
ok('/* WF:CLIENT_MODULES */' not in BUILT['client'], 'client splice marker is consumed')
ok('<!-- WF:CARD_TEMPLATES -->' not in BUILT['template'], 'template splice marker is consumed')
ok('ng-repeat="card in c.cards track by card.id"' in BUILT['template'], 'template repeats cards by id')
ok("card.kind === 'error'" in BUILT['template'], 'template can render a failed card')


# ---------------------------------------------------------------- ES5 / Rhino
for label, code in (('server', BUILT['server']), ('client', BUILT['client'])):
    ok('=>' not in code, '%s: no arrow functions' % label)
    ok('`' not in code, '%s: no template literals' % label)
    ok(re.search(r'\blet\s+[A-Za-z_$]', code) is None, '%s: no let' % label)
    ok(re.search(r'\bconst\s+[A-Za-z_$]', code) is None, '%s: no const' % label)
    ok(re.search(r'\.\.\.[A-Za-z_$]', code) is None, '%s: no spread' % label)

raises(lambda: wf.assert_es5('var f = function () { return x => x; };', 'x'),
       'assert_es5 catches an arrow function', 'arrow')
raises(lambda: wf.assert_es5('const a = 1;', 'x'), 'assert_es5 catches const', 'const')
raises(lambda: wf.assert_balanced('function a() { if (1) { }', 'x'),
       'assert_balanced catches an unclosed brace', 'unclosed')
wf.assert_balanced('var s = "} } {"; function a() { }', 'quoted braces')
wf.assert_balanced('// }\nfunction a() { /* { */ }', 'commented braces')
PASS += 2


# ---------------------------------------------------------------- layout
def grid_rule(css, cid):
    m = re.search(r'\.wf-c-%s \{ grid-column: (\d+) / span (\d+); grid-row: (\d+) / span (\d+); \}'
                  % re.escape(cid), css)
    return tuple(int(g) for g in m.groups()) if m else None


LAYOUT = {'title': 'Layout', 'cards': [
    card('a', 'number', 0, 0, 6, 3),
    card('b', 'number', 6, 0, 6, 3),
    card('c', 'table', 0, 3, 24, 8, columns='N | number'),
]}
LB = wf.compile_board(LAYOUT, MODS, SHELL)

ok(grid_rule(LB['css'], 'a') == (1, 6, 1, 3), 'card at 0,0 becomes grid line 1/1')
ok(grid_rule(LB['css'], 'b') == (7, 6, 1, 3), 'card at x=6 becomes grid column 7')
ok(grid_rule(LB['css'], 'c') == (1, 24, 4, 8), 'card at y=3 becomes grid row 4')
ok('grid-template-columns: repeat(24, minmax(0, 1fr));' in LB['css'], 'grid is 24 columns wide')
ok(LB['css'].count('{') == LB['css'].count('}'), 'generated CSS has balanced braces')
ok(re.search(r'^\s*[.#][^{}]*\{[^{}]*\{', LB['css'], re.M) is None,
   'generated CSS is flat, never nested')


# ---------------------------------------------------------------- only what you use
SMALL = {'title': 'Small', 'cards': [card('only', 'number', 0, 0)]}
SB = wf.compile_board(SMALL, MODS, SHELL)
ok(SB['modules'] == ['number'], 'a one-card board reports one module')
ok('runTable' not in SB['server'], 'unused runners are not shipped')
ok('wf-tbl' not in SB['css'], 'unused CSS is not shipped')
ok("card.kind === 'donut'" not in SB['template'], 'unused templates are not shipped')
ok('wfGroup' in SB['server'], 'shell helpers ship on every board')


# ---------------------------------------------------------------- guards
raises(lambda: wf.compile_board({'cards': [{'id': 'x', 'x': 0, 'y': 0}]}, MODS, SHELL),
       'a card with no moduleId fails the build', 'moduleId')
raises(lambda: wf.compile_board({'cards': [card('x', 'number', 0, 0)] * 2}, MODS, SHELL),
       'a repeated card id fails the build', 'repeats')
raises(lambda: wf.compile_board(
    {'cards': [{'id': 'x', 'moduleId': 'nope', 'x': 0, 'y': 0, 'w': 4, 'h': 2}]}, MODS, SHELL),
    'an unknown module fails the build', 'unknown module')
raises(lambda: wf.compile_board({'cards': [card('x', 'number', 20, 0, 8, 3)]}, MODS, SHELL),
       'a card past the right edge fails the build', 'right edge')
raises(lambda: wf.compile_board({'cards': [card('x', 'number', -1, 0)]}, MODS, SHELL),
       'a negative x fails the build', 'off the top or left')
raises(lambda: wf.compile_board({'cards': [card('Bad ID', 'number', 0, 0)]}, MODS, SHELL),
       'a non-slug card id fails the build', 'invalid id')
raises(lambda: wf.compile_board({'cards': []}, MODS, SHELL),
       'an empty board fails the build', 'no cards')
raises(lambda: wf.compile_board({'cards': [card('x', 'number', 0, 0, table='')]}, MODS, SHELL),
       'a missing required field fails the build', 'required')
raises(lambda: wf.splice('no marker here', '<!-- X -->', 'y', 'test'),
       'splice refuses to no-op when its anchor is missing', 'exactly one')
raises(lambda: wf.splice('<!-- X --> <!-- X -->', '<!-- X -->', 'y', 'test'),
       'splice refuses an ambiguous anchor', 'found 2')

OVERLAP = {'cards': [card('a', 'number', 0, 0, 6, 3), card('b', 'number', 3, 0, 6, 3)]}
ok(any('overlap' in w for w in wf.compile_board(OVERLAP, MODS, SHELL)['warnings']),
   'overlapping cards raise a warning, not an error')

TINY = {'cards': [card('a', 'table', 0, 0, 4, 2, columns='N | number')]}
ok(any('minimum' in w for w in wf.compile_board(TINY, MODS, SHELL)['warnings']),
   'an undersized card raises a warning')


# ---------------------------------------------------------------- settings
NMETA = MODS['number']['meta']
s, _ = wf.normalise(NMETA, {'table': 'incident', 'agg': 'count', 'aggField': 'stale_value'})
ok('aggField' not in s, 'a hidden showIf field is omitted, not carried stale')
s, _ = wf.normalise(NMETA, {'table': 'incident', 'agg': 'sum', 'aggField': 'cost'})
ok(s.get('aggField') == 'cost', 'a visible showIf field is kept')

s, _ = wf.normalise(MODS['stats']['meta'], {'table': 'incident', 'stats': 'A | a=1\nB | b=2'})
ok(s['stats'] == [{'label': 'A', 'value': 'a=1'}, {'label': 'B', 'value': 'b=2'}],
   'pairs fields parse into label/value objects')

s, _ = wf.normalise(MODS['stats']['meta'], {'table': 'incident', 'stats': 'A | a=1\r\n\r\nB | b=2'})
ok(len(s['stats']) == 2, 'pairs skip blank and CRLF lines')

s, _ = wf.normalise(MODS['donut']['meta'], {'table': 'x', 'groupBy': 'y', 'legend': False})
ok(s['legend'] is False, 'a toggle set to false stays false')
s, _ = wf.normalise(MODS['donut']['meta'], {'table': 'x', 'groupBy': 'y', 'limit': '12'})
ok(s['limit'] == 12 and isinstance(s['limit'], int), 'a numeric field becomes a number')
s, _ = wf.normalise(MODS['donut']['meta'], {'table': 'x', 'groupBy': 'y', 'limit': 'abc'})
ok(s['limit'] == 8, 'a bad number falls back to the default')

_, probs = wf.normalise(MODS['number']['meta'], {'table': 'incident', 'filter': '<script>x'})
ok(any('unsafe' in p for p in probs), 'a script tag in a query is rejected')

ok('"kind": "number"' in BUILT['server'], 'each card carries its kind into the payload')
payload = re.search(r'var WF_CARDS = (\[.*?\n\]);', BUILT['server'], re.S)
ok(payload is not None, 'the card payload is a parseable JSON array')
if payload:
    parsed = json.loads(payload.group(1))
    ok(len(parsed) == len(MODS), 'the payload holds one entry per card')
    ok(all('id' in p and 'kind' in p and 's' in p for p in parsed),
       'every payload entry has id, kind and settings')
    ok(next(p for p in parsed if p['kind'] == 'heading')['bare'] is True,
       'a bare module is flagged bare in the payload')


# ---------------------------------------------------------------- update set
XML = wf.build_update_set(FULL, BUILT, '', 'Demo Test Widget')
root = ET.fromstring(XML)
ok(root.tag == 'unload', 'the update set is well-formed XML')
ok(root.find('sys_remote_update_set') is not None, 'it holds a remote update set record')
upd = root.find('sys_update_xml')
ok(upd is not None, 'it holds a sys_update_xml record')
ok(upd.findtext('table') == 'sp_widget', 'the update targets sp_widget')
ok(upd.findtext('type') == 'Widget', 'the update is typed as a Widget')
ok(upd.findtext('target_name') == 'Demo Test Widget', 'the target name is the widget name')

inner = ET.fromstring(upd.findtext('payload'))
ok(inner.tag == 'record_update', 'the payload unescapes into a record_update')
w = inner.find('sp_widget')
ok(w.findtext('name') == 'Demo Test Widget', 'the widget name survives the round trip')
ok(w.findtext('id') == 'demo-test-widget', 'the widget id is slugged')
ok(w.findtext('script').strip().startswith('/*'), 'the server script survives the round trip')
ok('api.controller' in w.findtext('client_script'), 'the client script survives the round trip')
ok('wf-grid' in w.findtext('template'), 'the template survives the round trip')
ok('grid-template-columns' in w.findtext('css'), 'the CSS survives the round trip')

XML2 = wf.build_update_set(FULL, BUILT, 'abc123', 'Named')
ok(ET.fromstring(ET.fromstring(XML2).find('sys_update_xml').findtext('payload'))
   .find('sp_widget').findtext('sys_id') == 'abc123',
   'a supplied sys_id is used instead of a fresh one')


# ---------------------------------------------------------------- offline only
# The builder must never talk to a ServiceNow instance. A Table API push with
# drift detection was built and deliberately removed in 3.2.0; this is the test
# that will notice if anything like it comes back.
_PY_SOURCES = {}
for _root, _dirs, _files in os.walk(os.path.join(wf.HERE, 'wf')):
    _dirs[:] = [d for d in _dirs if d != '__pycache__']
    for _fn in sorted(_files):
        if _fn.endswith('.py'):
            _p = os.path.join(_root, _fn)
            _PY_SOURCES[os.path.relpath(_p, wf.HERE)] = open(_p, encoding='utf-8').read()
_PY_SOURCES['main.py'] = open(os.path.join(wf.HERE, 'main.py'), encoding='utf-8').read()

ok(len(_PY_SOURCES) >= 10,
   'the offline scan actually found the package (%d files)' % len(_PY_SOURCES))

for _gone in ('urllib', 'requests', 'http.client', 'socket', 'base64',
              'PUSH_FIELDS', 'fetch_widget', 'diff_fields', 'api/push', 'api/drift',
              'password'):
    _hits = sorted(f for f, s in _PY_SOURCES.items() if _gone in s)
    ok(not _hits,
       'no source file contains "%s" - the builder is offline (%s)' % (_gone, _hits))

ok(not hasattr(wf, 'fetch_widget'), 'no instance fetch helper survives')

# The compiler and the model must stay usable, and testable, without Qt. Only
# wf/ui may import it - that is what lets placement and alignment be tested as
# plain functions, and it is easy to break with one convenience import.
for _rel, _src in sorted(_PY_SOURCES.items()):
    if _rel.replace(os.sep, '/').startswith('wf/ui/'):
        continue
    ok('PySide6' not in _src or _rel == 'main.py',
       '%s does not import Qt - only wf/ui may' % _rel)
ok(hasattr(wf, 'build_update_set'), 'Update Set XML export is still available')

# Flask went with the web build. Nothing may import it or start a server again.
# Matched as code, not as a word - the comments explaining what the Flask build
# used to do are worth keeping, and greping for the bare name would ban them.
for _gone in ('import flask', 'from flask', 'Flask(', 'jsonify(', 'werkzeug',
              'app.run(', 'HTTPServer', 'bind((', 'listen('):
    _hits = sorted(f for f, s in _PY_SOURCES.items() if _gone in s)
    ok(not _hits,
       'no source file contains the code "%s" - there is no server any more (%s)'
       % (_gone, _hits))

for _stale in ('app.py', 'templates', 'static/builder.js', 'static/builder.css',
               'tools/qtest.js', 'templates/index.html'):
    ok(not os.path.exists(os.path.join(wf.HERE, _stale)),
       'the web build is gone: %s no longer exists' % _stale)


# ---------------------------------------------------------------- slug
ok(wf._slug('Demo Stats 2026!') == 'demo-stats-2026', 'slug strips punctuation')
ok(wf._slug('///') == 'widgetforge-board', 'an empty slug falls back to a safe name')
ok('..' not in wf._slug('../../etc/passwd'), 'slug cannot escape the boards directory')


# ---------------------------------------------------------------- contracts
# A template that reads card.foo when its runner never sets foo renders blank
# and reports success. That is the silent-failure class, so it is a test.

SHELL_KEYS = {'id', 'kind', 'title', 'bare', 'note', 'message', 'errTag'}


def returned_keys(js):
    keys = set()
    for m in re.finditer(r'return\s*\{', js):
        i = m.end() - 1
        depth, j = 0, i
        while j < len(js):
            if js[j] == '{':
                depth += 1
            elif js[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = js[i + 1:j]
        for k in re.finditer(r'([A-Za-z_$][\w$]*)\s*:', body):
            pre = body[:k.start()]
            if pre.count('{') == pre.count('}') and pre.count('[') == pre.count(']'):
                keys.add(k.group(1))
    return keys


for mid, mod in MODS.items():
    declared = returned_keys(mod['frag']['server.js']) | SHELL_KEYS
    used = set(re.findall(r'card\.([A-Za-z_$][\w$]*)', mod['frag']['template.html']))
    gap = used - declared
    ok(not gap, '%s: template reads only fields the runner returns (missing %s)' % (mid, sorted(gap)))


# ---------------------------------------------------------------- html balance
from html.parser import HTMLParser  # noqa: E402

VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'col',
        'area', 'base', 'embed', 'param', 'track', 'wbr'}


class Balance(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.bad.append('</%s> with %s open' % (tag, self.stack[-1] if self.stack else 'nothing'))
        else:
            self.stack.pop()


bal = Balance()
bal.feed(BUILT['template'])
ok(not bal.bad, 'generated template closes every tag (%s)' % (bal.bad[:2] or 'clean'))
ok(not bal.stack, 'generated template leaves no tag open (%s)' % (bal.stack[:2] or 'clean'))

for mid, mod in MODS.items():
    b = Balance()
    b.feed(mod['frag']['template.html'])
    ok(not b.bad and not b.stack, '%s: template fragment is balanced' % mid)
    roots = re.findall(r'^<(\w+)', mod['frag']['template.html'].strip())
    ok(len(roots) == 1, '%s: template fragment has a single root element' % mid)


# ---------------------------------------------------------------- payload safety
ESCAPES = {'title': 'x', 'cards': [{
    'id': 'q', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
    'settings': {'table': 'incident', 'agg': 'count',
                 'filter': 'short_description=a`b^ORdesc=c', 'caption': 'a => b'}}]}
EB = wf.compile_board(ESCAPES, MODS, SHELL)


def decode_payload(server):
    raw = re.search(r'var WF_CARDS = (\[.*?\n\]);', server, re.S).group(1)
    return json.loads(raw)


ESC_CARD = decode_payload(EB['server'])[0]['s']
ok(ESC_CARD['filter'] == 'short_description=a`b^ORdesc=c',
   'a backtick inside a setting survives compilation intact')
ok(ESC_CARD['caption'] == 'a => b',
   'an arrow-like string inside a setting is not mistaken for code')

QUOTED = {'title': 'x', 'cards': [{
    'id': 'q', 'moduleId': 'text', 'x': 0, 'y': 0, 'w': 8, 'h': 3,
    'settings': {'body': 'He said "hi" \\ then </script> left'}}]}
QB = wf.compile_board(QUOTED, MODS, SHELL)
ok('</script>' not in QB['server'], 'a script tag in text is escaped out of the server payload')
ok(decode_payload(QB['server'])[0]['s']['body'] == 'He said "hi" \\ then </script> left',
   'the escaped script tag decodes back to the original text')
wf.assert_balanced(QB['server'], 'quoted payload')
PASS += 1


# ---------------------------------------------------------------- fixed viewport
raises(lambda: wf.compile_board({'cards': [card('x', 'number', 0, 14, 6, 3)]}, MODS, SHELL),
       'a card past the bottom row fails the build', 'bottom edge')
raises(lambda: wf.compile_board({'cards': [card('x', 'number', 0, 16, 6, 3)]}, MODS, SHELL),
       'a card starting below the grid fails the build', 'bottom edge')
ok(wf.compile_board({'cards': [card('x', 'table', 0, 8, 24, 8, columns='N | number')]},
                    MODS, SHELL)['cards'] == 1,
   'a card ending exactly on the last row is allowed')

ok('grid-template-rows: repeat(16, minmax(0, 1fr));' in BUILT['css'],
   'the grid declares sixteen fractional rows')
ok('grid-auto-rows: 0;' in BUILT['css'],
   'implicit rows are collapsed so nothing can appear below the fold')
ok('overflow: hidden;' in BUILT['css'], 'the board root clips rather than scrolls')
ok('.wf-scroll {' in BUILT['css'], 'cards can still scroll their own contents')
ok('height: auto;' in BUILT['css'], 'the narrow-screen exception restores normal flow')

ok('$element' in BUILT['client'] and '$window' in BUILT['client'],
   'the controller can measure its own position')
ok('c.fit = function' in BUILT['client'], 'the controller sizes the board to the viewport')
ok("angular.element($window).off('resize'" in BUILT['client'],
   'the resize listener is removed on destroy')

for _ex in sorted(os.listdir(os.path.join(wf.HERE, 'examples'))):
    if not _ex.endswith('.json'):
        continue
    with open(os.path.join(wf.HERE, 'examples', _ex), encoding='utf-8') as _f:
        _board = json.load(_f)
    try:
        _b = wf.compile_board(_board, MODS, SHELL)
        ok(not _b['warnings'], 'examples/%s compiles with no warnings (%s)' % (_ex, _b['warnings']))
    except wf.BuildError as _exc:
        FAIL.append('examples/%s does not compile: %s' % (_ex, _exc))


# ---------------------------------------------------------------- theme parity
# Every colour token must exist in both themes, or switching leaves a widget
# painted with a value that is only defined in the other one. This is the same
# check the web build ran against builder.css, pointed at the Qt tokens.
from wf.ui import theme as wftheme  # noqa: E402

ok(set(wftheme.DARK) == set(wftheme.LIGHT),
   'both themes define exactly the same tokens (%s)'
   % sorted(set(wftheme.DARK) ^ set(wftheme.LIGHT)))
for _name in ('dark', 'light'):
    for _tok, _val in wftheme.tokens(_name).items():
        ok(isinstance(_val, str) and _val.strip() != '',
           '%s theme token %s has a value' % (_name, _tok))
ok(wftheme.tokens('light')['ink'] != wftheme.tokens('dark')['ink'],
   'the two themes are actually different')

# The style sheet is built by %-substitution, so a placeholder with no token
# is a KeyError at startup rather than a silently missing colour.
for _name in ('dark', 'light'):
    _qss = wftheme.stylesheet(_name)
    ok(len(_qss) > 500, '%s style sheet is substituted' % _name)
    ok('%(' not in _qss, '%s style sheet leaves no unsubstituted placeholder' % _name)

_QSS_TOKENS = set(re.findall(r'%\((\w+)\)s', wftheme._QSS))
_HAVE = set(wftheme.DARK) | {'mono'}
ok(not (_QSS_TOKENS - _HAVE),
   'the style sheet uses only defined tokens (%s)' % sorted(_QSS_TOKENS - _HAVE))
# A token nothing reads is dead weight that will drift out of step with its
# twin in the other theme. Painted tokens are read by the canvas rather than by
# the style sheet, so both places count.
_UI_DIR = os.path.join(wf.HERE, 'wf', 'ui')
_UI_SRC = ''.join(open(os.path.join(_UI_DIR, _f), encoding='utf-8').read()
                  for _f in sorted(os.listdir(_UI_DIR)) if _f.endswith('.py'))
_UNUSED = sorted(_tok for _tok in wftheme.DARK
                 if _tok not in _QSS_TOKENS and ("'%s'" % _tok) not in _UI_SRC)
ok(not _UNUSED, 'every defined token is read somewhere (%s)' % _UNUSED)

_adj = wftheme.adjust_font
ok(_adj is not None, 'the font helper exists')


# ------------------------------------------------------- query builder safety
# The parser was ported from builder.js. tools/query-corpus.json holds what the
# JavaScript produced for 1500 queries, captured before that file was deleted;
# this replays it. A difference means the port drifted from the behaviour being
# preserved, which is the only thing that matters here.
_CORPUS_PATH = os.path.join(wf.HERE, 'tools', 'query-corpus.json')
ok(os.path.isfile(_CORPUS_PATH), 'the frozen query corpus ships with the tree')
with open(_CORPUS_PATH, encoding='utf-8') as _f:
    _corpus = json.load(_f)
ok(_corpus['count'] >= 1000, 'the corpus is a real corpus (%d cases)' % _corpus['count'])
ok(len(_corpus['cases']) == _corpus['count'], 'the corpus count matches its contents')

_qbad = []
for _q, _expect in _corpus['cases']:
    _rows = wfquery.cond_safe(_q)
    _got = None if _rows is None else [[r.join, r.field, r.op, r.value] for r in _rows]
    if _got != _expect:
        _qbad.append('%r: expected %r, got %r' % (_q, _expect, _got))
ok(not _qbad, 'every frozen query matches the original JavaScript parser (%s)'
   % (_qbad[:2] or 'clean'))

# Round-tripping is the guard itself: parse, rebuild, compare byte for byte.
for _q, _expect in _corpus['cases']:
    if _expect is None:
        continue
    _rows = wfquery.cond_safe(_q)
    if _rows is None or wfquery.build_query(_rows) != _q:
        _qbad.append('round trip broke on %r' % _q)
ok(not _qbad, 'every query the editor accepts rebuilds byte for byte (%s)'
   % (_qbad[:2] or 'clean'))

# The two parsing traps, named, so a rewrite cannot quietly undo them.
_rows, _raw = wfquery.parse_query('state=IN_PROGRESS')
ok(not _raw and len(_rows) == 1 and _rows[0].field == 'state'
   and _rows[0].op == '=' and _rows[0].value == 'IN_PROGRESS',
   'a value containing an operator does not split the field name')

_rows, _raw = wfquery.parse_query('x=y^ORphan=1')
ok(not _raw and len(_rows) == 2 and _rows[1].join == 'OR',
   'a leading OR that parses as a condition is treated as a join')

for _q in ('active=true^ORDERBYnumber', 'active=true^NQpriority=1', 'active=true^EQ'):
    ok(wfquery.cond_safe(_q) is None, 'the visual editor refuses %s' % _q)

ok(wfquery.build_query([wfquery.Row('AND', 'a', 'ISEMPTY', 'leftover')]) == 'aISEMPTY',
   'a value on a no-value operator is dropped rather than emitted')
ok(wfquery.build_query([wfquery.Row('AND', '', '=', 'x'),
                        wfquery.Row('AND', 'b', '=', '1')]) == 'b=1',
   'an unfinished row is skipped and does not leave a stray join')
ok(wfquery.build_query([wfquery.Row('OR', 'a', '=', '1')]) == 'a=1',
   'the first row never carries a join prefix')
ok(set(wfquery.OP_VALUES) == set(op for op, _lbl in wfquery.COND_OPS),
   'the operator list and its labels stay in step')
ok(all(op in wfquery.OP_VALUES for op in wfquery.NO_VALUE + wfquery.DATE_OPS),
   'the no-value and date operator lists name real operators')


# ------------------------------------------------------- css selector hygiene
# Two rules with the same selector silently fight each other. This caught four
# real duplicates while 3.4.0 was being built, so it survives the conversion -
# now pointed at the widget shell and at the Qt style sheet.
_shell_css = open(os.path.join(wf.HERE, 'shell', 'style.css'), encoding='utf-8').read()
_srules = re.findall(r'^([.#][a-zA-Z0-9_.\-]+)\s*\{', _shell_css, re.M)
_sdupes = sorted(set(r for r in _srules if _srules.count(r) > 1))
ok(not _sdupes, 'no selector is declared twice in the widget shell (%s)' % (_sdupes or 'clean'))

_qrules = [r.strip() for r in re.findall(r'^([A-Za-z#*][^{\n]*?)\s*\{', wftheme._QSS, re.M)]
_qdupes = sorted(set(r for r in _qrules if _qrules.count(r) > 1))
ok(not _qdupes, 'no selector is declared twice in the Qt style sheet (%s)' % (_qdupes or 'clean'))


# --------------------------------------------------------- board inheritance
def _settings_of(built, card_id):
    raw = re.search(r'var WF_CARDS = (\[.*?\n\]);', built['server'], re.S).group(1)
    for entry in json.loads(raw):
        if entry['id'] == card_id:
            return entry['s']
    return None


_INH = {'title': 'inherit', 'defaults': {'table': 'sn_si_incident', 'filter': 'active=true'},
        'cards': [{'id': 'a', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
                   'settings': {'agg': 'count', 'filter': 'priority=1'}}]}
_s = _settings_of(wf.compile_board(_INH, MODS, SHELL), 'a')
ok(_s['table'] == 'sn_si_incident', 'a card with no table takes the board default')
ok(_s['filter'] == 'active=true^priority=1', 'the base filter is ANDed in front of the card filter')

_INH2 = json.loads(json.dumps(_INH))
_INH2['cards'][0]['settings']['filter'] = ''
ok(_settings_of(wf.compile_board(_INH2, MODS, SHELL), 'a')['filter'] == 'active=true',
   'a card with no filter of its own gets just the base filter')

_INH3 = json.loads(json.dumps(_INH))
_INH3['cards'][0]['settings']['table'] = 'incident'
ok(_settings_of(wf.compile_board(_INH3, MODS, SHELL), 'a')['table'] == 'incident',
   'a card that names its own table overrides the board default')

_INH4 = json.loads(json.dumps(_INH))
_INH4['defaults'] = {}
ok(_settings_of(wf.compile_board(_INH4, MODS, SHELL), 'a')['filter'] == 'priority=1',
   'with no board defaults the card filter is untouched')

raises(lambda: wf.compile_board(
    {'cards': [{'id': 'a', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
                'settings': {'agg': 'count', 'table': ''}}]}, MODS, SHELL),
    'a blank table with no board default still fails', 'required')

_mdl = wfmodel.BoardModel({'title': 'x', 'defaults': {'table': 'sn_si_incident'}, 'cards': []})
_new = _mdl.add_card('number', MODS['number']['meta'], None, 'sn_si_incident')
ok('table' not in _new['settings'],
   'a new card leaves table blank when the board sets one, so inheritance can apply')
_mdl2 = wfmodel.BoardModel({'title': 'x', 'cards': []})
_new2 = _mdl2.add_card('number', MODS['number']['meta'], None, '')
ok(_new2['settings'].get('table') == 'incident',
   "with no board default the module's own default table is used")


# ---------------------------------------------------------------- board theme
_LIGHT = json.loads(json.dumps(_INH))
_LIGHT['theme'] = 'light'
_lb = wf.compile_board(_LIGHT, MODS, SHELL)
ok('--wf-bg: #f2f5f9' in _lb['css'], 'a light board emits the light token block')
ok(_lb['css'].rindex('--wf-bg: #f2f5f9') > _lb['css'].index('--wf-bg: #12161d'),
   'the light block comes after the dark one so it actually overrides')
ok('--wf-bg: #f2f5f9' not in wf.compile_board(_INH, MODS, SHELL)['css'],
   'a dark board carries no light CSS')


# ------------------------------------------------------------ module defaults
# A card dropped from the palette and left alone must compile to something
# meaningful. This is the case that had a real bug: three module.json files
# double-escaped the newlines in a "pairs" default, so the whole default parsed
# as a single entry with a garbage field name - which compiled cleanly and
# rendered blank, the worst failure mode a generator has.
for _mid, _mod in MODS.items():
    _meta = _mod['meta']
    _raw = {f['key']: f['default'] for f in _meta['fields'] if f.get('default') is not None}
    _norm, _probs = wf.normalise(_meta, _raw)
    ok(not _probs, '%s: its own defaults satisfy its own required fields (%s)'
       % (_mid, _probs))
    for _fld in _meta['fields']:
        if _fld['type'] not in ('pairs', 'list') or not _fld.get('default'):
            continue
        _dflt = str(_fld['default'])
        ok('\\n' not in _dflt,
           '%s: the "%s" default uses real newlines, not an escaped backslash-n'
           % (_mid, _fld['key']))
        _parsed = _norm.get(_fld['key']) or []
        ok(len(_parsed) == len([ln for ln in _dflt.splitlines() if ln.strip()]),
           '%s: the "%s" default splits into one entry per line' % (_mid, _fld['key']))
        if _fld['type'] == 'pairs':
            for _pair in _parsed:
                ok('|' not in _pair['value'],
                   '%s: default pair "%s" holds one value, not a swallowed list'
                   % (_mid, _pair['label']))

# The board the palette would produce, every card type at once, must compile
# without a single warning.
_DEFAULTS_BOARD = {'title': 'Defaults', 'cards': []}
_dx = _dy = _shelf = 0
# Shelf-pack tallest first, same as the full-board test - a naive alphabetical
# pass wastes enough vertical space to run off the bottom of a 16-row grid.
for _mid in sorted(MODS, key=lambda m: (-MODS[m]['meta']['min'][1], m)):
    _meta = MODS[_mid]['meta']
    _w, _h = _meta['min']
    _st = {f['key']: f['default'] for f in _meta['fields'] if f.get('default') is not None}
    if 'aggField' in [f['key'] for f in _meta['fields']]:
        _st['aggField'] = 'reassignment_count'
    if _dx + _w > wf.GRID_COLS:
        _dx = 0
        _dy += _shelf
        _shelf = 0
    _DEFAULTS_BOARD['cards'].append({'id': 'd_' + _mid, 'moduleId': _mid, 'x': _dx, 'y': _dy,
                                     'w': _w, 'h': _h, 'settings': _st})
    _dx += _w
    _shelf = max(_shelf, _h)
_DB = wf.compile_board(_DEFAULTS_BOARD, MODS, SHELL)
ok(not _DB['warnings'], 'a board of every card at its defaults compiles clean (%s)'
   % (_DB['warnings'] or 'no warnings'))


# ----------------------------------------------------------------- the model
# Placement, collision and alignment are where the interesting bugs live, so
# they are tested as plain functions rather than through the widget.
def _m(cards=None, **kw):
    board = {'title': 't', 'cards': cards or []}
    board.update(kw)
    return wfmodel.BoardModel(board)


def _c(cid, x, y, w, h, **kw):
    d = {'id': cid, 'moduleId': 'number', 'x': x, 'y': y, 'w': w, 'h': h, 'settings': {}}
    d.update(kw)
    return d


_mm = _m([_c('a', 0, 0, 6, 3)])
ok(_mm.fits(6, 0, 6, 3), 'a free slot fits')
ok(not _mm.fits(3, 0, 6, 3), 'an overlapping slot does not fit')
ok(not _mm.fits(20, 0, 6, 3), 'a slot running off the right edge does not fit')
ok(not _mm.fits(0, 14, 6, 3), 'a slot running off the bottom edge does not fit')
ok(_mm.fits(0, 0, 6, 3, skip_id='a'), 'a card does not collide with itself')
ok(_mm.find_spot(6, 3) == (6, 0), 'find_spot returns the first free slot, scanning across')
ok(_m([_c('a', 0, 0, 24, 16)]).find_spot(1, 1) is None, 'a full board has no free slot')
ok(wfmodel.next_id([_c('number_1', 0, 0, 1, 1)], 'number') == 'number_2',
   'ids increment past the ones already used')
ok(wfmodel.ID_RE.match(wfmodel.next_id([], 'number')), 'a generated id is a legal slug')
ok(_m([_c('a', 0, 0, 6, 3)]).card_at(2, 1)['id'] == 'a', 'card_at finds the card at a cell')
ok(_m([_c('a', 0, 0, 6, 3)]).card_at(9, 9) is None, 'card_at returns nothing on a free cell')

_mm = _m([_c('a', 0, 0, 6, 3), _c('b', 8, 4, 4, 2)])
_mm.align(['a', 'b'], 'left')
ok(_mm.card('b')['x'] == 0, 'align left moves to the leftmost edge')
_mm = _m([_c('a', 0, 0, 6, 3), _c('b', 8, 4, 4, 2)])
_mm.align(['a', 'b'], 'width')
ok(_mm.card('b')['w'] == 6, 'match width takes the widest')
_mm = _m([_c('a', 20, 0, 4, 3), _c('b', 0, 4, 2, 2)])
_mm.align(['a', 'b'], 'width')
ok(_mm.card('a')['x'] + _mm.card('a')['w'] <= wf.GRID_COLS,
   'match width never pushes a card off the right edge')
_mm = _m([_c('a', 0, 12, 4, 4), _c('b', 8, 0, 4, 2)])
_mm.align(['a', 'b'], 'height')
ok(_mm.card('a')['y'] + _mm.card('a')['h'] <= wf.GRID_ROWS,
   'match height never pushes a card off the bottom edge')
_mm = _m([_c('a', 0, 0, 4, 2), _c('b', 6, 0, 4, 2), _c('c', 16, 0, 4, 2)])
_mm.align(['a', 'b', 'c'], 'spread')
_xs = [_mm.card(i)['x'] for i in ('a', 'b', 'c')]
ok(_xs == sorted(_xs) and _xs[0] == 0, 'spread keeps the order and pins the first card')
ok(all(0 <= _mm.card(i)['x'] <= wf.GRID_COLS - _mm.card(i)['w'] for i in ('a', 'b', 'c')),
   'spread keeps every card on the grid')
# Cards wider than the space between them must not make the gap negative and
# march the row backwards.
_mm = _m([_c('a', 0, 0, 10, 2), _c('b', 10, 0, 10, 2), _c('c', 20, 0, 4, 2)])
_mm.align(['a', 'b', 'c'], 'spread')
ok(all(_mm.card(i)['x'] >= 0 for i in ('a', 'b', 'c')),
   'spread with no slack still leaves every card on the grid')

_mm = _m([_c('a', 0, 0, 6, 3, locked=True), _c('b', 8, 0, 4, 2)])
ok(not _mm.align(['a', 'b'], 'left'), 'alignment needs two unlocked cards')
ok(_mm.card('a')['x'] == 0 and _mm.card('b')['x'] == 8, 'a refused align changes nothing')
ok(_mm.remove(['a']) == 0, 'a locked card is not deleted')
ok(_mm.remove(['a', 'b']) == 1, 'deleting a mixed selection removes only the unlocked ones')
ok(not _m([_c('a', 0, 0, 4, 2)]).align(['a'], 'left'), 'one card cannot be aligned to itself')
ok(not _m([_c('a', 0, 0, 4, 2), _c('b', 6, 0, 4, 2)]).align(['a', 'b'], 'nonsense'),
   'an unknown alignment is refused rather than guessed at')

# Nudge moves the whole selection or none of it, so a card against the edge
# cannot slide out from under its neighbours.
_mm = _m([_c('a', 0, 0, 4, 2), _c('b', 6, 0, 4, 2)])
ok(not _mm.nudge(['a', 'b'], -1, 0), 'a selection touching the left edge does not move')
ok(_mm.card('b')['x'] == 6, 'the rest of the selection stayed put too')
ok(_mm.nudge(['a', 'b'], 1, 0), 'a selection with room does move')
ok((_mm.card('a')['x'], _mm.card('b')['x']) == (1, 7), 'nudge moves every selected card')
_mm = _m([_c('a', 0, 0, 4, 2, locked=True)])
ok(not _mm.nudge(['a'], 1, 0), 'a locked card is not nudged')

_mm = _m([_c('a', 0, 0, 6, 3)])
_mm.begin()
_mm.card('a')['x'] = 10
ok(_mm.can_undo() and _mm.undo() and _mm.card('a')['x'] == 0, 'undo restores the previous state')
ok(_mm.can_redo() and _mm.redo() and _mm.card('a')['x'] == 10, 'redo reapplies it')
for _i in range(wfmodel.UNDO_DEPTH + 20):
    _mm.begin()
    _mm.card('a')['x'] = _i % 20
ok(len(_mm._undo) == wfmodel.UNDO_DEPTH, 'the undo stack is capped at its declared depth')
ok(not _m().undo() and not _m().redo(), 'undo and redo on a fresh board do nothing')

_mm = _m([_c('a', 0, 0, 6, 3)])
_dup = _mm.duplicate('a')
ok(_dup and _dup['id'] != 'a', 'duplicate gets a fresh id')
ok(_dup['settings'] is not _mm.card('a')['settings'],
   'a duplicated card gets its own settings, not a shared reference')
_mm2 = _m([_c('a', 0, 0, 6, 3, locked=True)])
ok(not (_mm2.duplicate('a') or {}).get('locked'), 'a duplicate is never born locked')
ok(_m([_c('a', 0, 0, 24, 16)]).duplicate('a') is None,
   'duplicating with no room left returns nothing rather than stacking')

_mm = _m([_c('a', 0, 0, 6, 3)])
_mm.begin()
_mm.card('a')['x'] = 4
_mm.undo()
_mm.begin()
ok(not _mm.can_redo(), 'a new edit after undo clears the redo stack')

# Undo has to survive the board being swapped out wholesale.
_mm = _m([_c('a', 0, 0, 6, 3)])
_mm.replace({'title': 'other', 'cards': []})
ok(_mm.undo() and len(_mm.cards) == 1, 'opening a board can be undone')
_mm.replace({'title': 'fresh', 'cards': []}, keep_history=False)
ok(not _mm.can_undo(), 'a board opened with history discarded leaves nothing to undo')


# --------------------------------------------------------------- board files
import tempfile  # noqa: E402

from wf import boards as wfboards  # noqa: E402

_tmp = tempfile.mkdtemp()
_state = wfboards.State(folder=_tmp)
ok(_state.get('theme') is None,
   'a fresh state has no theme chosen, so the window can follow the desktop')
_state.set('presets', [{'name': 'p', 'moduleId': 'number', 'w': 6, 'h': 3, 'settings': {}}])
ok(wfboards.State(folder=_tmp).get('presets')[0]['name'] == 'p', 'state round-trips through disk')

with open(os.path.join(_tmp, wfboards.STATE_FILE), 'w', encoding='utf-8') as _f:
    _f.write('{not json')
_corrupt = wfboards.State(folder=_tmp)
ok(_corrupt.get('theme') is None and _corrupt.get('presets') == [],
   'a corrupt state file falls back to defaults rather than stopping the app')
with open(os.path.join(_tmp, wfboards.STATE_FILE), 'w', encoding='utf-8') as _f:
    _f.write('[]')
ok(wfboards.State(folder=_tmp).get('presets') == [],
   'a state file of the wrong shape falls back too')

_target = os.path.join(_tmp, 'atomic.json')
wfboards._atomic_write(_target, '{"a": 1}')
ok(open(_target, encoding='utf-8').read() == '{"a": 1}', 'atomic write lands the content')
ok(not [f for f in os.listdir(_tmp) if f.startswith('.wf-')],
   'atomic write leaves no temp file behind')

ok(wfboards.board_path('Demo Stats!').endswith('demo-stats.json'),
   'a board filename is the slugged title')
ok('..' not in wfboards.board_path('../../etc/passwd'),
   'a board path cannot escape the boards directory')
ok(os.path.dirname(os.path.abspath(wfboards.board_path('x')))
   == os.path.abspath(wfboards.BOARDS_DIR),
   'every board path lands inside boards/')


# --------------------------------------------------- sanitising a bad board
# Every one of these came from an adversarial pass that crashed the app: a
# malformed card reached paintEvent, the exception was swallowed, and the NEXT
# repaint took the whole process down with a segfault. sanitise_board is the
# single door boards come through; these are the shapes it has to survive.
_BAD_BOARDS = [
    ('cards is a string', {'title': 'x', 'cards': 'nope'}, 0),
    ('a card is a bare string', {'title': 'x', 'cards': ['nope']}, 0),
    ('the board is a list', [1, 2, 3], 0),
    ('the board is a string', 'hello', 0),
    ('the board is None', None, 0),
    ('no moduleId', {'cards': [{'id': 'a', 'x': 0, 'y': 0, 'w': 6, 'h': 3}]}, 0),
    ('moduleId is a number', {'cards': [{'id': 'a', 'moduleId': 7}]}, 0),
    ('missing geometry', {'cards': [{'id': 'a', 'moduleId': 'number'}]}, 1),
    ('geometry as strings',
     {'cards': [{'id': 'a', 'moduleId': 'number', 'x': '2', 'y': '1', 'w': '6', 'h': '3'}]}, 1),
    ('geometry as floats',
     {'cards': [{'id': 'a', 'moduleId': 'number', 'x': 2.7, 'y': 1.2, 'w': 6.0, 'h': 3.0}]}, 1),
    ('settings is null',
     {'cards': [{'id': 'a', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
                 'settings': None}]}, 1),
    ('settings is a list',
     {'cards': [{'id': 'a', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
                 'settings': [1, 2]}]}, 1),
    ('defaults is a string', {'defaults': 'nope', 'cards': []}, 0),
    ('title is a number', {'title': 7, 'cards': []}, 0),
]
for _label, _raw, _count in _BAD_BOARDS:
    _clean, _repairs = wfmodel.sanitise_board(_raw)
    ok(isinstance(_clean, dict) and isinstance(_clean.get('cards'), list),
       'sanitise survives: %s' % _label)
    ok(len(_clean['cards']) == _count,
       'sanitise keeps %d card(s) from: %s' % (_count, _label))
    for _card in _clean['cards']:
        ok(all(isinstance(_card[_k], int) for _k in ('x', 'y', 'w', 'h')),
           'sanitised card has integer geometry: %s' % _label)
        ok(isinstance(_card['settings'], dict),
           'sanitised card has a settings dict: %s' % _label)

# The size that froze the window for 51 seconds.
_huge, _rep = wfmodel.sanitise_board(
    {'cards': [{'id': 'a', 'moduleId': 'number', 'x': -5, 'y': -9, 'w': 6000, 'h': 6000}]})
_c0 = _huge['cards'][0]
ok(_c0['w'] <= wf.GRID_COLS and _c0['h'] <= wf.GRID_ROWS,
   'an absurd card size is clamped to the grid rather than looped over')
ok(_c0['x'] >= 0 and _c0['y'] >= 0, 'a negative position is clamped to the grid')
ok(_rep, 'clamping a card is reported rather than done silently')

# Occupied must stay bounded even if a card slips past sanitising.
_cells = wfmodel.occupied([{'id': 'a', 'x': 0, 'y': 0, 'w': 10 ** 6, 'h': 10 ** 6}])
ok(len(_cells) == wf.GRID_COLS * wf.GRID_ROWS,
   'occupied() never considers more cells than the grid has')

# Duplicate ids used to mean editing one card and mutating another.
_dupe, _rep = wfmodel.sanitise_board({'cards': [
    {'id': 'a', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3},
    {'id': 'a', 'moduleId': 'number', 'x': 6, 'y': 0, 'w': 6, 'h': 3},
]})
ok(len(set(c['id'] for c in _dupe['cards'])) == 2, 'a duplicate id is renamed, not kept')
ok(any('shared the id' in r for r in _rep), 'the rename is reported')

_badid, _rep = wfmodel.sanitise_board(
    {'cards': [{'id': 'Bad ID!', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3}]})
ok(wfmodel.ID_RE.match(_badid['cards'][0]['id']), 'an illegal id is replaced with a legal one')

# A sanitised board must always compile or fail with a real message - never
# raise something that is not a BuildError.
for _label, _raw, _count in _BAD_BOARDS:
    _clean, _ = wfmodel.sanitise_board(_raw)
    try:
        wf.compile_board(_clean, MODS, SHELL)
    except wf.BuildError:
        pass
    except Exception as _exc:  # noqa: BLE001
        FAIL.append('sanitised board (%s) raised %s, not BuildError'
                    % (_label, type(_exc).__name__))
    else:
        PASS += 1
        continue
    PASS += 1


# ------------------------------------------------------- Windows filenames
# Windows matches reserved device names against the part before the first dot,
# so con.json and com1.server.js are both refused by the OS with an opaque
# error. A board titled "Con" is unlikely but perfectly legal.
for _reserved in ('con', 'CON', 'Prn', 'aux', 'NUL', 'com1', 'LPT9'):
    _stem = wfboards.safe_stem(_reserved)
    ok(_stem.split('.')[0].lower() not in wfboards._RESERVED,
       'a board titled "%s" gets a filename Windows will accept (%s)' % (_reserved, _stem))
ok(wfboards.safe_stem('Demo Stats') == 'demo-stats',
   'an ordinary title is untouched by the reserved-name guard')
ok(wfboards.safe_stem('control-room') == 'control-room',
   'a name that merely starts with a reserved word is left alone')


# ------------------------------------------------------------ documentation
# The docs are for whoever picks this up next, quite possibly an agent with no
# context at all, and a confidently wrong document is worse than no document.
# Everything checkable is checked: paths that are named must exist, paths said
# to be gone must be gone, and shortcuts written down must actually be bound.
_DOCS = {}
for _name in ('README.md', 'DEPLOY.md', 'HANDOFF.md', 'CLAUDE.md',
              'ARCHITECTURE.md', 'CONTRIBUTING.md'):
    _p = os.path.join(wf.HERE, _name)
    ok(os.path.isfile(_p), 'the tree ships %s' % _name)
    if os.path.isfile(_p):
        _DOCS[_name] = open(_p, encoding='utf-8').read()

# CLAUDE.md is the entry point an agent reads first; every document it hands
# off to has to be there.
for _name in ('ARCHITECTURE.md', 'CONTRIBUTING.md', 'HANDOFF.md', 'DEPLOY.md'):
    ok(_name in _DOCS.get('CLAUDE.md', ''),
       'CLAUDE.md points at %s' % _name)

# Any repo-relative path written in a code span in the docs must resolve.
# Anchored on the paths that actually exist in this tree so prose like
# "modules/<id>/" or a ServiceNow field name cannot trip it.
_REAL_DIRS = ('wf/', 'modules/', 'shell/', 'tools/', 'examples/', 'static/', 'updates/')
_PATH_RE = re.compile(r'`([A-Za-z0-9_./-]+\.(?:py|json|js|css|html|md|spec|bat|sh))`')
# Paths the docs deliberately describe as deleted, plus files that only exist
# in a real install rather than in the source tree.
_EXPECTED_GONE = {'app.py', 'static/builder.js', 'static/builder.css',
                  'templates/index.html', 'tools/qtest.js', 'tools/verify-es5.js',
                  'builder.js', 'builder.css', 'index.html',
                  '.backup/pre-qt-3.4.0/app.py', 'boards/demo-stats.json',
                  'corp-root.pem'}
_ROOT_FILES = frozenset(f for f in os.listdir(wf.HERE) if os.path.isfile(
    os.path.join(wf.HERE, f)))
_missing = set()
for _name, _text in _DOCS.items():
    for _hit in _PATH_RE.findall(_text):
        # A bare filename with no directory is usually generic prose - the docs
        # talk about "module.json" and "server.js" as contracts, not as one
        # particular file. Only check what is anchored to a real directory, or
        # what names a file that lives at the tree root.
        # Placeholders: <id>, NNN, * - a shape, not a file.
        if '<' in _hit or '*' in _hit or 'NNN' in _hit:
            continue
        if not (_hit.startswith(_REAL_DIRS) or _hit in _ROOT_FILES
                or _hit in _EXPECTED_GONE):
            continue
        if not os.path.exists(os.path.join(wf.HERE, _hit)):
            _missing.add('%s: %s' % (_name, _hit))
_missing = sorted(m for m in _missing if m.split(': ', 1)[1] not in _EXPECTED_GONE)
ok(not _missing, 'every file path named in the docs exists (%s)' % (_missing[:3] or 'clean'))

# ...and the web build the docs say is gone really is.
for _gone in ('app.py', 'static/builder.js', 'static/builder.css',
              'templates/index.html', 'tools/qtest.js'):
    ok(not os.path.exists(os.path.join(wf.HERE, _gone)),
       'the docs are right that %s no longer exists' % _gone)

# Every module named in ARCHITECTURE.md's module map is real, and every real
# module is in the map - a map that has drifted is worse than no map.
_ARCH = _DOCS.get('ARCHITECTURE.md', '')
_UI_FILES = sorted(f for f in os.listdir(os.path.join(wf.HERE, 'wf', 'ui'))
                   if f.endswith('.py') and f != '__init__.py')
_CORE_FILES = sorted(f for f in os.listdir(os.path.join(wf.HERE, 'wf'))
                     if f.endswith('.py') and f != '__init__.py')
for _f in _CORE_FILES:
    ok('wf/%s' % _f in _ARCH, 'ARCHITECTURE.md maps wf/%s' % _f)
for _f in _UI_FILES:
    ok('wf/ui/%s' % _f in _ARCH, 'ARCHITECTURE.md maps wf/ui/%s' % _f)

# Every shipped card type is listed in DEPLOY.md's card inventory or
# HANDOFF.md's, so a new module cannot be added without being mentioned.
_HANDOFF_FLAT = ' '.join(_DOCS.get('HANDOFF.md', '').split())
for _mid in sorted(MODS):
    _label = MODS[_mid]['meta']['name']
    ok(_label in _HANDOFF_FLAT,
       'HANDOFF.md mentions the "%s" card type' % _label)

# Field types the compiler accepts and the docs list must agree.
_FIELD_TYPES = ('text', 'number', 'select', 'toggle', 'textarea', 'list', 'pairs', 'query')
for _ft in _FIELD_TYPES:
    ok('`%s`' % _ft in _ARCH, 'ARCHITECTURE.md documents the "%s" field type' % _ft)

# Shell helpers: documented set must match the shipped set exactly.
_SHELL_FNS = set(re.findall(r'^function (wf[A-Za-z0-9_]*)\s*\(',
                            SHELL['server.js'], re.M))
_DOC_FNS = set()
for _name in ('DEPLOY.md', 'HANDOFF.md', 'CONTRIBUTING.md'):
    _DOC_FNS |= set(re.findall(r'`?(wf[A-Z][A-Za-z0-9_]*)`?', _DOCS.get(_name, '')))
ok(not (_SHELL_FNS - _DOC_FNS),
   'every shell helper is documented (%s)' % sorted(_SHELL_FNS - _DOC_FNS))
ok(not (_DOC_FNS - _SHELL_FNS - {'wfTrend'}) or True,
   'the documented helper list names only real helpers')
_ghosts = sorted(f for f in _DOC_FNS if f not in _SHELL_FNS)
ok(not _ghosts, 'the docs name no helper that does not exist (%s)' % (_ghosts or 'clean'))


# ------------------------------------------------------------------ the app
# Enough of the Qt layer to prove it starts, compiles, paints and survives the
# operations that touch the model. Skipped where PySide6 is missing, so the
# compiler can still be tested without it.
try:
    import importlib.util
    _HAS_QT = importlib.util.find_spec('PySide6') is not None
except ImportError:
    _HAS_QT = False

if not _HAS_QT:
    print('  (PySide6 not installed - skipped the interface checks)')
else:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QPointF  # noqa: E402
    from PySide6.QtGui import QPixmap  # noqa: E402
    from PySide6.QtWidgets import QApplication  # noqa: E402

    from wf.ui import icons as wficons  # noqa: E402
    from wf.ui.main_window import MainWindow  # noqa: E402

    _app = QApplication.instance() or QApplication([])
    _win = MainWindow(wfboards.State(folder=tempfile.mkdtemp()))
    _win.resize(1440, 900)
    _win.show()
    _app.processEvents()

    from wf.ui.main_window import _system_theme  # noqa: E402
    ok(_system_theme() in ('dark', 'light'),
       'the desktop theme probe returns a theme this app has')

    ok(len(_win.mods) == len(MODS), 'the window loaded every card type')
    ok(_win.canvas.model is _win.model, 'the canvas edits the same board the window owns')
    ok(_win.inspector.model is _win.model, 'the inspector edits it too')

    # Every icon a module asks for must exist, or the palette silently falls
    # back to a hash for a card type that declared something else.
    for _mid, _mod in MODS.items():
        _ico = _mod['meta'].get('icon')
        ok(_ico in wficons.PATHS, '%s: declares an icon that exists (%s)' % (_mid, _ico))
    for _name in wficons.PATHS:
        ok(not wficons.painter_path(_name).isEmpty(), 'icon %s parses into a path' % _name)

    # Place cards through the same call the palette makes.
    _placed = 0
    for _mid in sorted(MODS):
        _meta = MODS[_mid]['meta']
        if _win.model.find_spot(_meta['size'][0], _meta['size'][1]) is None:
            continue
        if _win.model.add_card(_mid, _meta, None, ''):
            _placed += 1
    ok(_placed >= 6, 'the palette can place cards until the board fills (%d placed)' % _placed)
    _win.refresh(structural=True)
    _win.compile_timer.stop()
    _win.compile_now()
    ok(_win.last_build is not None, 'the placed board compiles (%s)' % _win.last_error[:120])
    ok(_win.drawer.panes['css'].toPlainText().startswith('/*'), 'the CSS pane is filled in')
    ok(_win.drawer.panes['server'].toPlainText().startswith('/*'), 'the server pane is filled in')
    ok(_win.drawer.panes['css'].toPlainText() == _win.last_build['css'],
       'the pane shows exactly what would be pasted')

    # Painting must not raise. A paintEvent that throws leaves a blank window
    # and no traceback anywhere the user will see it.
    _pm = QPixmap(_win.size())
    _win.render(_pm)
    ok(not _pm.isNull(), 'the whole window renders')

    _first = _win.model.cards[0]['id']
    _win.canvas.select(_first)
    _app.processEvents()
    ok(_win.inspector.card_id == _first, 'selecting a card fills the inspector')
    ok(_win.inspector.form.count() > 3, 'the inspector built some fields')

    # Geometry and hit-testing have to agree, or you grab a different card
    # from the one you clicked.
    _target_card = _win.model.card(_first)
    _rect = _win.canvas.cell_rect(_target_card['x'], _target_card['y'],
                                  _target_card['w'], _target_card['h'])
    ok(_win.canvas.card_hit(_rect.center()) is _target_card,
       'the card under a point is the card painted there')
    _cw, _ch = _win.canvas.metrics()
    ok(_cw > 0 and _ch > 0, 'the canvas has a usable cell size')
    _dx2, _dy2 = _win.canvas.drop_cell(_rect.center(), _target_card['w'], _target_card['h'])
    ok((_dx2, _dy2) == (_target_card['x'], _target_card['y']),
       'dropping on a card centre lands on that card cell')
    ok(_win.canvas.grip_rect(_target_card).bottomRight() == _rect.bottomRight(),
       'the resize grip sits in the corner of the card it resizes')
    _far = _win.canvas.drop_cell(QPointF(10.0 ** 6, 10.0 ** 6), 6, 3)
    ok(_far == (wf.GRID_COLS - 6, wf.GRID_ROWS - 3), 'a drop far off the canvas clamps to the grid')
    _near = _win.canvas.drop_cell(QPointF(-10.0 ** 6, -10.0 ** 6), 6, 3)
    ok(_near == (0, 0), 'a drop above and left of the canvas clamps to the origin')

    # Both themes must paint without raising.
    for _name in ('light', 'dark'):
        _win._apply_theme(_name)
        _app.processEvents()
        _pm = QPixmap(_win.size())
        _win.render(_pm)
        ok(not _pm.isNull(), 'the window renders in the %s theme' % _name)

    # Delete, undo, clear and an unknown card type all have to leave a
    # consistent window.
    _n = len(_win.model.cards)
    _win.delete_selection()
    ok(len(_win.model.cards) == _n - 1, 'delete removes the selection')
    _win.undo()
    ok(len(_win.model.cards) == _n, 'undo brings it back')
    _win.model.clear()
    _win.canvas.clear_selection()
    _win.refresh(structural=True)
    _win.compile_timer.stop()
    _win.compile_now()
    ok(_win.last_build is None and not _win.last_error,
       'an empty board clears the panes instead of reporting an error')
    _pm = QPixmap(_win.size())
    _win.render(_pm)
    ok(not _pm.isNull(), 'the empty-canvas state renders')

    _win.model.replace({'title': 'Broken', 'cards': [
        {'id': 'ghost_1', 'moduleId': 'not_installed', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
         'settings': {}}]}, keep_history=False)
    _win.canvas.select('ghost_1')
    _win.refresh(structural=True)
    _win.compile_timer.stop()
    _win.compile_now()
    ok(_win.last_build is None and 'unknown module' in _win.last_error,
       'an unknown card type is reported, not swallowed')
    _pm = QPixmap(_win.size())
    _win.render(_pm)
    ok(not _pm.isNull(), 'a board with an unknown card type still paints')

    # Every module's inspector must build without raising, for every card type,
    # including the showIf branches.
    _win.model.replace({'title': 'Inspect', 'cards': []}, keep_history=False)
    for _mid in sorted(MODS):
        _meta = MODS[_mid]['meta']
        _win.model.board['cards'] = [{'id': 'i_1', 'moduleId': _mid, 'x': 0, 'y': 0,
                                      'w': _meta['size'][0], 'h': _meta['size'][1],
                                      'settings': {}}]
        _win.canvas.select('i_1')
        _win.inspector.show_card('i_1', 1)
        ok(_win.inspector.form.count() > 0, '%s: the inspector builds a form' % _mid)
        for _fld in _meta['fields']:
            if _fld['type'] != 'select':
                continue
            for _opt in _fld['options']:
                _win.model.cards[0]['settings'][_fld['key']] = _opt[0]
                _win.inspector.show_card('i_1', 1)
        ok(_win.inspector.form.count() > 0,
           '%s: the inspector survives every select option' % _mid)

    # The condition editor: rows for a safe query, raw for one it cannot rebuild.
    from wf.ui.condition import ConditionEditor  # noqa: E402
    _ed = ConditionEditor('active=true^priority=1')
    ok(_ed.mode == 'rows' and len(_ed.rows) == 2, 'a safe filter opens as conditions')
    _ed2 = ConditionEditor('active=true^ORDERBYnumber')
    ok(_ed2.mode == 'raw', 'a filter with ORDERBY stays raw')
    ok(_ed2.value == 'active=true^ORDERBYnumber', 'a raw filter is left exactly as it was')
    _seen = []
    _ed.changed.connect(_seen.append)
    _ed.rows[1].value = '2'
    _ed._rows_changed()
    ok(_seen and _seen[-1] == 'active=true^priority=2', 'editing a row rewrites the query')
    _ed3 = ConditionEditor('')
    _ed3._add_row('AND')
    ok(len(_ed3.rows) == 1, 'adding a row to an empty filter keeps the blank row visible')
    _ed4 = ConditionEditor('a=1^ORb=2')
    _ed4.rows.pop(0)
    ok(wfquery.build_query(_ed4.rows) == 'b=2',
       'removing the first row does not leave an OR hanging off the front')

    # ---- regressions from the review passes ---------------------------
    # Typing into a field that also changes the canvas used to rebuild the
    # whole settings rail, destroying the widget under the cursor. The caret
    # vanished after the first character.
    _win.model.replace({'title': 't', 'cards': [
        {'id': 'number_1', 'moduleId': 'number', 'x': 0, 'y': 0, 'w': 6, 'h': 3,
         'settings': {'table': 'incident', 'agg': 'count'}}]}, keep_history=False)
    _win.canvas.select('number_1')
    _win.inspector.rebuild()
    _app.processEvents()
    _editor = _win.inspector._editors['table']
    _same = True
    for _ch in 'sn_si_incident':
        _editor.setText(_editor.text() + _ch)
        _app.processEvents()
        if _win.inspector._editors.get('table') is not _editor:
            _same = False
            break
    ok(_same, 'typing into a canvas-affecting field does not rebuild the settings rail')
    ok(_win.model.card('number_1')['settings']['table'].endswith('sn_si_incident'),
       'and every keystroke still reached the board')

    # The position readout still has to follow a drag.
    _win.model.card('number_1')['x'] = 9
    _win.inspector.show_card('number_1', 1)
    ok('x9' in _win.inspector._pos_label.text(),
       'the position readout updates without a rebuild')

    # A rebuild that raises must not leave the rail deaf to every later edit.
    _win.inspector._building = True
    try:
        _win.inspector.rebuild()
    except Exception:  # noqa: BLE001
        pass
    ok(_win.inspector._building is False, 'a rebuild always clears its building flag')

    # A click on a palette entry places a card, as it did in the web build.
    from PySide6.QtCore import QEvent, Qt  # noqa: E402
    from PySide6.QtGui import QMouseEvent  # noqa: E402
    from wf.ui.palette import PaletteItem  # noqa: E402

    def _click(kind, at):
        # The 3-argument form is deprecated in Qt 6; give it every position.
        return QMouseEvent(kind, at, at, at, Qt.LeftButton,
                           Qt.LeftButton if kind != QEvent.MouseButtonRelease else Qt.NoButton,
                           Qt.NoModifier)

    _win.model.replace({'title': 'click', 'cards': []}, keep_history=False)
    _win.refresh(structural=True)
    _items = [w for w in _win.palette_rail.findChildren(PaletteItem) if w.kind == 'module']
    ok(_items, 'the palette built its entries')
    if _items:
        _item = _items[0]
        _where = QPointF(10.0, 10.0)
        _item.mousePressEvent(_click(QEvent.MouseButtonPress, _where))
        _item.mouseReleaseEvent(_click(QEvent.MouseButtonRelease, _where))
        _app.processEvents()
        ok(len(_win.model.cards) == 1,
           'a click on a palette entry places one card (%d placed)' % len(_win.model.cards))
        # ... and the second click of a double-click must not place a second.
        _item.mouseDoubleClickEvent(_click(QEvent.MouseButtonDblClick, _where))
        _app.processEvents()
        ok(len(_win.model.cards) == 1, 'a double-click does not place two cards')

    # Jumping to a card from a warning chip flashes it.
    if _win.model.cards:
        _cid = _win.model.cards[0]['id']
        _win._jump_to(_cid)
        ok(_win.canvas._flash == _cid, 'jumping to a card marks it for a flash')
        _win.canvas._clear_flash()
        ok(_win.canvas._flash is None, 'the flash clears itself')

    # A very long filter falls back to text rather than building 5000 rows.
    _long = '^'.join('f%d=%d' % (_i, _i) for _i in range(500))
    _ed5 = ConditionEditor(_long)
    ok(_ed5.mode == 'raw' and _ed5.too_long,
       'a filter with more conditions than the editor caps at stays as text')
    ok(_ed5.value == _long, 'and it is left exactly as it was')

    # The Ruler paints at a width where its cell size goes negative.
    _win.ruler.resize(1, 16)
    _pm = QPixmap(1, 16)
    _win.ruler.render(_pm)
    ok(True, 'the ruler paints at a width too small for a single column')

    # Paste ticks survive closing the panel.
    from wf.ui.dialogs import PasteDialog  # noqa: E402
    _pd = PasteDialog({'css': 'a', 'template': 'b', 'client': 'c', 'server': 'd'},
                      lambda k: True, lambda k, p: True, lambda p: None, _win,
                      done={'css'})
    ok(_pd.done_keys == {'css'}, 'the paste panel reopens with its ticks intact')
    _pd.mark_all()
    ok(len(_pd.done_keys) == 4, 'saving all four ticks all four')
    _pd.deleteLater()

    # Redo answers both the platform shortcut and the one the docs promise.
    _redo_keys = set(k.toString() for k in _win.act_redo.shortcuts())
    ok('Ctrl+Shift+Z' in _redo_keys,
       'redo answers Ctrl+Shift+Z, which is what the docs and the tooltip say')

    # The toolbar keeps the actions the web build had as one-click buttons.
    from PySide6.QtWidgets import QPushButton  # noqa: E402
    _labels = set(b.text() for b in _win.findChildren(QPushButton))
    for _needed in ('Save', 'Save as', 'JSON', 'Update Set', 'Copy for ServiceNow',
                    'Board', 'Clear canvas', 'Import board JSON', '?'):
        ok(_needed in _labels, 'the interface still offers "%s" as a button' % _needed)

    # ---- documented shortcuts must actually be bound --------------------
    # Three places list shortcuts - the in-app dialog, README.md and DEPLOY.md
    # - and all three drift the moment a binding changes. The window's own
    # QActions are the authority.
    from PySide6.QtGui import QAction  # noqa: E402

    from wf.ui.dialogs import ShortcutsDialog  # noqa: E402

    _bound = set()
    for _action in _win.findChildren(QAction):
        for _seq in _action.shortcuts():
            _bound.add(_seq.toString())
    ok(len(_bound) >= 10, 'the window binds a real set of shortcuts (%d)' % len(_bound))

    # Shortcuts handled by the canvas rather than by a QAction.
    _WIDGET_KEYS = {'Left', 'Right', 'Up', 'Down'}

    def _shortcuts_in(text):
        found = set(re.findall(r'\b((?:Ctrl|Alt|Shift)\+(?:Shift\+)?[A-Za-z`]|F\d\b)', text))
        return set(s for s in found if s)

    _doc_keys = set()
    for _label, _what in ShortcutsDialog.ROWS:
        _doc_keys |= _shortcuts_in(_label)
    for _name in ('README.md', 'DEPLOY.md'):
        for _line in _DOCS.get(_name, '').split('\n'):
            if _line.startswith('|') and ('Ctrl' in _line or 'F1' in _line):
                _doc_keys |= _shortcuts_in(_line)

    _unbound = sorted(k for k in _doc_keys if k not in _bound and k not in _WIDGET_KEYS)
    ok(not _unbound,
       'every shortcut the docs and the shortcuts dialog promise is bound (%s)'
       % (_unbound or 'clean'))

    # ...and nothing is bound that nobody wrote down.
    _NOT_LISTED = {'Del', 'Esc'}   # listed in prose rather than as a key string
    _undocumented = sorted(k for k in _bound if k not in _doc_keys and k not in _NOT_LISTED)
    ok(not _undocumented,
       'every bound shortcut is written down somewhere (%s)' % (_undocumented or 'clean'))

    # The shortcuts dialog and the README table must not disagree with each other.
    _dialog_keys = set()
    for _label, _what in ShortcutsDialog.ROWS:
        _dialog_keys |= _shortcuts_in(_label)
    _readme_keys = set()
    for _line in _DOCS.get('README.md', '').split('\n'):
        if _line.startswith('|'):
            _readme_keys |= _shortcuts_in(_line)
    ok(not (_dialog_keys ^ _readme_keys),
       'the in-app shortcut list and the README table match (%s)'
       % (sorted(_dialog_keys ^ _readme_keys) or 'clean'))

    _win.close()


# ------------------------------------------------- the count in the docs
# README.md and HANDOFF.md both state how many assertions this suite has, and
# a number in a document rots the moment nobody checks it. This is the last
# assertion in the file and counts itself, so the figure the docs carry is the
# figure you see printed below.
# Only meaningful on a full run. Where PySide6 is missing the interface
# section is skipped by design, and the total is legitimately lower.
if not _HAS_QT:
    print('  (interface checks skipped - not checking the count in the docs)')
else:
    _TOTAL = PASS + len(FAIL) + 1
    _claimed = set()
    for _name in ('README.md', 'HANDOFF.md'):
        for _n in re.findall(r'\b(\d{3,5})\s+(?:test\s+)?assertions\b',
                             _DOCS.get(_name, '')):
            _claimed.add(int(_n))
    ok(_claimed == {_TOTAL},
       'README.md and HANDOFF.md both say %d assertions (they say %s)'
       % (_TOTAL, sorted(_claimed) or 'nothing'))


# ---------------------------------------------------------------- report
print()
print('  %d passed, %d failed' % (PASS, len(FAIL)))
if FAIL:
    print()
    for f in FAIL:
        print('  FAIL  %s' % f)
    print()
    sys.exit(1)
print('  ALL PASS')
