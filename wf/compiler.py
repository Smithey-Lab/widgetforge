"""WidgetForge - the compiler.

The compiler is deliberately small. Everything that describes a card type
lives in modules/<id>/ as data, so adding a card type never means editing
this file.
"""

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone


def _find_root():
    """The tree root: the folder holding VERSION, modules/ and shell/.

    Running from source this is simply the parent of this file. Running from a
    PyInstaller build it is not: the package is frozen into an archive, and
    where the bundled data lands next to the executable has moved between
    PyInstaller versions. Rather than encode one layout and discover it was the
    wrong one only after a build, each candidate is checked for the files that
    actually have to be there.

    WF_HOME overrides everything, which is also what makes it possible to point
    a build at a different set of card types.
    """
    candidates = []
    env = os.environ.get('WF_HOME')
    if env:
        candidates.append(env)
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(meipass)
            candidates.append(os.path.join(meipass, '_internal'))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(here)
    candidates.append(os.path.join(here, '_internal'))

    for path in candidates:
        if (os.path.isfile(os.path.join(path, 'VERSION'))
                and os.path.isdir(os.path.join(path, 'modules'))
                and os.path.isdir(os.path.join(path, 'shell'))):
            return os.path.abspath(path)
    # Nothing matched. Fall back to the source layout so the error that follows
    # names a real missing path rather than something invented.
    return here


HERE = _find_root()
MODULES_DIR = os.path.join(HERE, 'modules')
SHELL_DIR = os.path.join(HERE, 'shell')

# Where the user's own files go. Beside the executable for a build, and the
# tree root from source - never inside a bundle, where they would be invisible
# and would vanish on the next install.
USER_ROOT = (os.path.dirname(os.path.abspath(sys.executable))
             if getattr(sys, 'frozen', False) else HERE)

GRID_COLS = 24
GRID_ROWS = 16

with open(os.path.join(HERE, 'VERSION'), encoding='utf-8') as _f:
    VERSION = _f.read().strip()


class BuildError(Exception):
    """Raised when a board cannot be compiled. Never swallowed."""


# --------------------------------------------------------------------------
# Module loading
# --------------------------------------------------------------------------

FRAGMENTS = ('server.js', 'client.js', 'template.html', 'style.css')
RUNNER_RE = re.compile(r'^function\s+(run[A-Za-z0-9_]*)\s*\(', re.M)


def load_modules():
    """Read every modules/<id>/ folder into a dict. Fails loudly on a bad one."""
    mods = {}
    if not os.path.isdir(MODULES_DIR):
        raise BuildError('modules/ directory is missing')

    for mid in sorted(os.listdir(MODULES_DIR)):
        path = os.path.join(MODULES_DIR, mid)
        if not os.path.isdir(path) or mid.startswith('.'):
            continue

        meta_path = os.path.join(path, 'module.json')
        if not os.path.isfile(meta_path):
            raise BuildError('modules/%s has no module.json' % mid)

        with open(meta_path, encoding='utf-8') as f:
            try:
                meta = json.load(f)
            except ValueError as exc:
                raise BuildError('modules/%s/module.json is not valid JSON: %s' % (mid, exc))

        frags = {}
        for name in FRAGMENTS:
            fp = os.path.join(path, name)
            frags[name] = open(fp, encoding='utf-8').read() if os.path.isfile(fp) else ''

        found = RUNNER_RE.findall(frags['server.js'])
        if len(found) != 1:
            raise BuildError(
                'modules/%s/server.js must declare exactly one top-level '
                'run<Name>(s) function, found %d' % (mid, len(found)))

        for key in ('name', 'size', 'min', 'fields'):
            if key not in meta:
                raise BuildError('modules/%s/module.json is missing "%s"' % (mid, key))

        seen = set()
        for fld in meta['fields']:
            if 'key' not in fld or 'type' not in fld:
                raise BuildError('modules/%s has a field with no key or type' % mid)
            if fld['key'] in seen:
                raise BuildError('modules/%s repeats the field "%s"' % (mid, fld['key']))
            seen.add(fld['key'])

        meta['id'] = mid
        meta['runner'] = found[0]
        mods[mid] = {'meta': meta, 'frag': frags}

    if not mods:
        raise BuildError('no modules found in modules/')
    return mods


def load_shell():
    shell = {}
    for name in FRAGMENTS:
        fp = os.path.join(SHELL_DIR, name)
        if not os.path.isfile(fp):
            raise BuildError('shell/%s is missing' % name)
        shell[name] = open(fp, encoding='utf-8').read()
    return shell


# --------------------------------------------------------------------------
# Settings normalisation
# --------------------------------------------------------------------------

def _lines(raw):
    return [ln.strip() for ln in str(raw or '').replace('\r\n', '\n').split('\n') if ln.strip()]


def _pairs(raw):
    out = []
    for ln in _lines(raw):
        if '|' in ln:
            label, value = ln.split('|', 1)
            out.append({'label': label.strip(), 'value': value.strip()})
        else:
            out.append({'label': ln, 'value': ''})
    return out


def _visible(field, settings):
    """showIf: {key: [allowed values]}. Hidden fields are omitted, not carried stale."""
    cond = field.get('showIf')
    if not cond:
        return True
    for key, allowed in cond.items():
        if str(settings.get(key, '')) not in [str(a) for a in allowed]:
            return False
    return True


def inherit(board, meta, raw_settings):
    """Fold the board's defaults into one card's raw settings.

    A blank table takes the board's. A base filter is ANDed in front of the
    card's own. Applied before validation and before compilation, from the same
    function, so the two can never disagree about what a card actually queries.
    """
    defaults = (board or {}).get('defaults') or {}
    raw = dict(raw_settings or {})
    keys = [f['key'] for f in meta['fields']]

    base_table = str(defaults.get('table', '') or '').strip()
    if base_table and 'table' in keys and not str(raw.get('table', '') or '').strip():
        raw['table'] = base_table

    base_filter = str(defaults.get('filter', '') or '').strip()
    if base_filter and 'filter' in keys:
        own = str(raw.get('filter', '') or '').strip()
        raw['filter'] = (base_filter + '^' + own) if own else base_filter

    return raw


def normalise(meta, raw_settings):
    """Turn raw UI values into the exact shapes the runner expects."""
    raw_settings = raw_settings or {}
    out = {}
    problems = []

    for field in meta['fields']:
        key = field['key']
        if not _visible(field, raw_settings):
            continue

        val = raw_settings.get(key, field.get('default'))
        ftype = field['type']

        if ftype == 'toggle':
            val = bool(val) if val not in ('false', 'False') else False
        elif ftype == 'number':
            try:
                val = float(val)
                val = int(val) if val == int(val) else val
            except (TypeError, ValueError):
                val = field.get('default', 0)
        elif ftype == 'list':
            val = _lines(val)
        elif ftype == 'pairs':
            val = _pairs(val)
        else:
            val = '' if val is None else str(val).strip()

        if field.get('required'):
            empty = val in ('', None, []) or (ftype == 'number' and val in (None, ''))
            if empty:
                problems.append('%s is required' % field.get('label', key))

        if ftype == 'query' and val:
            if re.search(r'[<>]\s*script', str(val), re.I):
                problems.append('%s looks unsafe' % field.get('label', key))

        out[key] = val

    return out, problems


# --------------------------------------------------------------------------
# Board validation
# --------------------------------------------------------------------------

ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


def validate(board, mods):
    """Return (errors, warnings). Errors stop the build."""
    errors = []
    warnings = []

    if not isinstance(board, dict):
        return ['board must be an object'], []

    cards = board.get('cards')
    if not isinstance(cards, list):
        return ['board.cards must be a list'], []
    if not cards:
        return ['board has no cards'], []

    seen_ids = set()
    occupied = {}

    for idx, card in enumerate(cards):
        where = 'card %d' % (idx + 1)

        cid = card.get('id')
        if not cid or not ID_RE.match(str(cid)):
            errors.append('%s has an invalid id (lowercase letters, digits, - and _ only)' % where)
            continue
        if cid in seen_ids:
            errors.append('%s repeats the id "%s"' % (where, cid))
            continue
        seen_ids.add(cid)

        mid = card.get('moduleId')
        if not mid:
            errors.append('%s ("%s") has no moduleId' % (where, cid))
            continue
        if mid not in mods:
            errors.append('%s uses unknown module "%s"' % (where, mid))
            continue

        meta = mods[mid]['meta']
        try:
            x = int(card.get('x', 0))
            y = int(card.get('y', 0))
            w = int(card.get('w', meta['size'][0]))
            h = int(card.get('h', meta['size'][1]))
        except (TypeError, ValueError):
            errors.append('%s has non-numeric position or size' % where)
            continue

        if w < 1 or h < 1:
            errors.append('%s has zero width or height' % where)
            continue
        if x < 0 or y < 0:
            errors.append('%s sits off the top or left of the grid' % where)
            continue
        if x + w > GRID_COLS:
            errors.append('%s runs past the right edge (x %d + w %d > %d)' % (where, x, w, GRID_COLS))
            continue
        if y + h > GRID_ROWS:
            errors.append('%s runs past the bottom edge (y %d + h %d > %d). The board fills '
                          'the screen and does not scroll, so there is nowhere for it to go.'
                          % (where, y, h, GRID_ROWS))
            continue
        if w < meta['min'][0] or h < meta['min'][1]:
            warnings.append('%s ("%s") is smaller than the %dx%d minimum for %s and may clip'
                            % (where, cid, meta['min'][0], meta['min'][1], meta['name']))

        for cy in range(y, y + h):
            for cx in range(x, x + w):
                key = (cx, cy)
                if key in occupied:
                    warnings.append('%s ("%s") overlaps "%s"' % (where, cid, occupied[key]))
                    break
                occupied[key] = cid
            else:
                continue
            break

        _, problems = normalise(meta, inherit(board, meta, card.get('settings')))
        for p in problems:
            errors.append('%s ("%s"): %s' % (where, cid, p))

    return errors, warnings


# --------------------------------------------------------------------------
# Output guards
# --------------------------------------------------------------------------

ES5_BANNED = [
    (re.compile(r'=>'), 'arrow function'),
    (re.compile(r'\blet\s+[A-Za-z_$]'), 'let'),
    (re.compile(r'\bconst\s+[A-Za-z_$]'), 'const'),
    (re.compile(r'`'), 'template literal'),
    (re.compile(r'\bclass\s+[A-Za-z_$]+\s*\{'), 'class declaration'),
    (re.compile(r'\.\.\.[A-Za-z_$]'), 'spread operator'),
    (re.compile(r'\basync\s+function\b'), 'async function'),
]


def assert_es5(code, label):
    for pattern, name in ES5_BANNED:
        m = pattern.search(code)
        if m:
            line = code[:m.start()].count('\n') + 1
            raise BuildError("%s uses %s on line %d - ServiceNow's Rhino engine rejects it"
                             % (label, name, line))


def assert_balanced(code, label):
    pairs = {'}': '{', ')': '(', ']': '['}
    stack = []
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch in '"\'':
            quote = ch
            i += 1
            while i < n and code[i] != quote:
                i += 2 if code[i] == '\\' else 1
        elif ch == '/' and i + 1 < n and code[i + 1] == '/':
            while i < n and code[i] != '\n':
                i += 1
        elif ch == '/' and i + 1 < n and code[i + 1] == '*':
            i += 2
            while i + 1 < n and not (code[i] == '*' and code[i + 1] == '/'):
                i += 1
            i += 1
        elif ch in '{([':
            stack.append(ch)
        elif ch in '})]':
            if not stack or stack.pop() != pairs[ch]:
                raise BuildError('%s has an unbalanced "%s" near line %d'
                                 % (label, ch, code[:i].count('\n') + 1))
        i += 1
    if stack:
        raise BuildError('%s leaves %d bracket(s) unclosed' % (label, len(stack)))


def splice(text, marker, payload, label):
    """Replace a marker, asserting it exists exactly once. Never a silent no-op."""
    count = text.count(marker)
    if count != 1:
        raise BuildError('%s: expected exactly one "%s" marker, found %d' % (label, marker, count))
    return text.replace(marker, payload)


# --------------------------------------------------------------------------
# Compile
# --------------------------------------------------------------------------

def compile_board(board, mods=None, shell=None):
    mods = mods or load_modules()
    shell = shell or load_shell()

    errors, warnings = validate(board, mods)
    if errors:
        raise BuildError('; '.join(errors))

    cards = board['cards']
    used = []
    for card in cards:
        if card['moduleId'] not in used:
            used.append(card['moduleId'])
    used.sort()

    # ---- card payload -----------------------------------------------------
    payload = []
    positions = []
    for card in cards:
        meta = mods[card['moduleId']]['meta']
        settings, _ = normalise(meta, inherit(board, meta, card.get('settings')))
        x = int(card.get('x', 0))
        y = int(card.get('y', 0))
        w = int(card.get('w', meta['size'][0]))
        h = int(card.get('h', meta['size'][1]))
        entry = {
            'id': str(card['id']),
            'kind': card['moduleId'],
            'title': settings.get('title', ''),
            'bare': bool(meta.get('bare')),
            's': settings,
        }
        payload.append(entry)
        positions.append((str(card['id']), x, y, w, h))

    # ---- server script ----------------------------------------------------
    parts = [
        '/* Generated by WidgetForge %s on %s. Edit the board, not this file. */'
        % (VERSION, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')),
        '(function () {',
        shell['server.js'].rstrip(),
        '',
        '// --- card runners ---',
    ]
    for mid in used:
        parts.append(mods[mid]['frag']['server.js'].rstrip())
        parts.append('')

    parts.append('var WF_RUNNERS = {};')
    for mid in used:
        parts.append("WF_RUNNERS['%s'] = %s;" % (mid, mods[mid]['meta']['runner']))

    parts.append('')
    # Angle brackets are escaped so the payload stays inert if this script is
    # ever pasted inside an HTML <script> block while debugging a portal page.
    payload_json = (json.dumps(payload, indent=2)
                    .replace('<', '\\u003c').replace('>', '\\u003e'))
    payload_line = 'var WF_CARDS = %s;' % payload_json
    parts.append(payload_line)
    parts.append('')
    parts.append(_BUILD_LOOP)
    parts.append(_BOARD_META % (
        json.dumps(str(board.get('title', ''))),
        json.dumps(str(board.get('subtitle', ''))),
    ))
    parts.append('})();')
    server = '\n'.join(parts) + '\n'

    # ---- client script ----------------------------------------------------
    client_mods = []
    for mid in used:
        frag = mods[mid]['frag']['client.js'].strip()
        if frag:
            client_mods.append('  // --- %s ---\n%s' % (mid, frag))
    client = splice(shell['client.js'], '/* WF:CLIENT_MODULES */',
                    ('\n'.join(client_mods) if client_mods else '// no module client code'),
                    'client script')

    # ---- template ---------------------------------------------------------
    tpl_parts = []
    for mid in used:
        frag = mods[mid]['frag']['template.html'].strip()
        if not frag:
            raise BuildError('modules/%s/template.html is empty' % mid)
        tpl_parts.append('        <!-- %s -->\n%s' % (mid, _indent(frag, 8)))
    template = splice(shell['template.html'], '<!-- WF:CARD_TEMPLATES -->',
                      '\n'.join(tpl_parts).strip(), 'template')

    # ---- css --------------------------------------------------------------
    css_parts = [shell['style.css'].rstrip()]
    for mid in used:
        frag = mods[mid]['frag']['style.css'].strip()
        if frag:
            css_parts.append('\n/* --- %s --- */\n%s' % (mid, frag))

    grid_rules = ['\n/* --- layout: the canvas is the layout --- */']
    for cid, x, y, w, h in positions:
        grid_rules.append('.wf-c-%s { grid-column: %d / span %d; grid-row: %d / span %d; }'
                          % (cid, x + 1, w, y + 1, h))
    css_parts.append('\n'.join(grid_rules))
    if str(board.get('theme', 'dark')).lower() == 'light':
        css_parts.append(_LIGHT_THEME)
    css = '\n'.join(css_parts) + '\n'

    # ---- guards -----------------------------------------------------------
    # The ES5 scan is about generated *code*. The settings payload is user data
    # inside JSON string literals - a filter containing a backtick or "=>" is
    # legal there and must not trip the guard.
    assert_es5(server.replace(payload_line, ''), 'server script')
    assert_es5(client, 'client script')
    assert_balanced(server, 'server script')
    assert_balanced(client, 'client script')
    if css.count('{') != css.count('}'):
        raise BuildError('generated CSS has unbalanced braces')
    if re.search(r'^\s*[.#&][^{}]*\{[^{}]*\{', css, re.M):
        raise BuildError('generated CSS contains nesting - ServiceNow SCSS is not assumed')
    if template.count('<div') < 1:
        raise BuildError('generated template is empty')

    return {
        'server': server,
        'client': client,
        'template': template,
        'css': css,
        'warnings': warnings,
        'modules': used,
        'cards': len(cards),
        'version': VERSION,
    }


_LIGHT_THEME = """
/* --- light board --- */
.wf-root {
  --wf-bg: #f2f5f9;
  --wf-card: #ffffff;
  --wf-card-2: #eef2f7;
  --wf-line: #dbe2ec;
  --wf-text: #1b2530;
  --wf-dim: #5c6a7b;
  --wf-accent: #0f8f88;
  --wf-warn: #9a6f18;
  --wf-bad: #c0444b;
}
.wf-card { box-shadow: 0 1px 2px rgba(27, 37, 48, 0.06); }
.wf-line-area { fill: rgba(15, 143, 136, 0.14); }
"""


def _indent(text, spaces):
    pad = ' ' * spaces
    return '\n'.join(pad + ln if ln.strip() else ln for ln in text.split('\n'))


_BUILD_LOOP = """data.cards = [];
for (var wfi = 0; wfi < WF_CARDS.length; wfi++) {
  var wfc = WF_CARDS[wfi];
  var wfOut;
  var wfFn = WF_RUNNERS[wfc.kind];
  if (!wfFn) {
    wfOut = { kind: 'error', errTag: 'Unknown card type', message: wfc.kind };
  } else {
    try {
      wfOut = wfFn(wfc.s);
      if (!wfOut) { wfOut = { kind: 'error', errTag: 'No data', message: wfc.kind }; }
      else { wfOut.kind = wfc.kind; }
    } catch (wfE) {
      wfOut = { kind: 'error', errTag: 'Query failed', message: '' + wfE };
    }
  }
  wfOut.id = wfc.id;
  wfOut.title = wfc.title;
  wfOut.bare = wfc.bare;
  data.cards.push(wfOut);
}
"""

_BOARD_META = """data.board = { title: %s, subtitle: %s };"""


# --------------------------------------------------------------------------
# Update Set XML
# --------------------------------------------------------------------------

def _esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def build_update_set(board, built, widget_id, widget_name):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    set_id = uuid.uuid4().hex
    sys_id = widget_id or uuid.uuid4().hex
    set_name = 'WidgetForge - %s' % (board.get('title') or widget_name)

    record = (
        '<record_update table="sp_widget">'
        '<sp_widget action="INSERT_OR_UPDATE">'
        '<client_script><![CDATA[%s]]></client_script>'
        '<css><![CDATA[%s]]></css>'
        '<demo_data/>'
        '<description>Generated by WidgetForge %s</description>'
        '<docs/>'
        '<field_list/>'
        '<has_preview>false</has_preview>'
        '<id>%s</id>'
        '<internal>false</internal>'
        '<link/>'
        '<name>%s</name>'
        '<option_schema/>'
        '<public>false</public>'
        '<roles/>'
        '<script><![CDATA[%s]]></script>'
        '<servicenow>false</servicenow>'
        '<sys_class_name>sp_widget</sys_class_name>'
        '<sys_id>%s</sys_id>'
        '<sys_name>%s</sys_name>'
        '<sys_policy/>'
        '<template><![CDATA[%s]]></template>'
        '</sp_widget>'
        '</record_update>'
    ) % (built['client'], built['css'], VERSION,
         _esc(_slug(widget_name)), _esc(widget_name), built['server'],
         sys_id, _esc(widget_name), built['template'])

    return _UPDATE_SET_XML % {
        'now': now,
        'set_id': set_id,
        'set_name': _esc(set_name),
        'sys_id': sys_id,
        'widget_name': _esc(widget_name),
        'payload': _esc(record),
        'update_guid': uuid.uuid4().hex,
        'version': VERSION,
    }


_UPDATE_SET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<unload unload_date="%(now)s">
<sys_remote_update_set action="INSERT_OR_UPDATE">
<application display_value="Global">global</application>
<application_name>Global</application_name>
<application_scope>global</application_scope>
<application_version/>
<collisions/>
<commit_date/>
<deleted/>
<description>Generated by WidgetForge %(version)s</description>
<inserted/>
<name>%(set_name)s</name>
<origin_sys_id/>
<parent/>
<release_date/>
<remote_sys_id>%(set_id)s</remote_sys_id>
<state>loaded</state>
<summary/>
<sys_created_by>widgetforge</sys_created_by>
<sys_created_on>%(now)s</sys_created_on>
<sys_id>%(set_id)s</sys_id>
<sys_mod_count>0</sys_mod_count>
<sys_updated_by>widgetforge</sys_updated_by>
<sys_updated_on>%(now)s</sys_updated_on>
<update_set/>
<update_source/>
</sys_remote_update_set>
<sys_update_xml action="INSERT_OR_UPDATE">
<action>INSERT_OR_UPDATE</action>
<application display_value="Global">global</application>
<category>customer</category>
<comments/>
<name>sp_widget_%(sys_id)s</name>
<payload>%(payload)s</payload>
<payload_hash/>
<remote_update_set display_value="%(set_name)s">%(set_id)s</remote_update_set>
<replace_on_upgrade>false</replace_on_upgrade>
<sys_created_by>widgetforge</sys_created_by>
<sys_created_on>%(now)s</sys_created_on>
<sys_id>%(update_guid)s</sys_id>
<sys_mod_count>0</sys_mod_count>
<sys_updated_by>widgetforge</sys_updated_by>
<sys_updated_on>%(now)s</sys_updated_on>
<table>sp_widget</table>
<target_name>%(widget_name)s</target_name>
<type>Widget</type>
<update_domain>global</update_domain>
<update_guid>%(update_guid)s</update_guid>
<update_guid_history/>
<view/>
</sys_update_xml>
</unload>
"""


def _slug(name):
    s = re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')
    return s or 'widgetforge-board'


# --------------------------------------------------------------------------
# Cached loading
# --------------------------------------------------------------------------
#
# The Flask build reloaded every module folder on each request, which is what
# made a newly dropped modules/<id>/ appear after a browser refresh with no
# restart. A desktop app has no request boundary to hang that off, so the cache
# is keyed on the mtime and size of every file the loader reads. Dropping in a
# folder, or editing a fragment in an editor, invalidates it on the next
# compile - the same behaviour, without re-reading 65 files per keystroke.

_CACHE = {'stamp': None, 'mods': None, 'shell': None}


def _stamp():
    """A cheap fingerprint of everything load_modules and load_shell read."""
    marks = []
    for root in (MODULES_DIR, SHELL_DIR):
        if not os.path.isdir(root):
            marks.append((root, None))
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for fn in sorted(filenames):
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                marks.append((os.path.relpath(fp, HERE), st.st_mtime_ns, st.st_size))
    return tuple(marks)


def load_cached():
    """Return (mods, shell), reloading only when a file on disk has changed."""
    stamp = _stamp()
    if _CACHE['stamp'] != stamp or _CACHE['mods'] is None:
        mods = load_modules()
        shell = load_shell()
        _CACHE['stamp'] = stamp
        _CACHE['mods'] = mods
        _CACHE['shell'] = shell
    return _CACHE['mods'], _CACHE['shell']


def invalidate_cache():
    _CACHE['stamp'] = None


def slug(name):
    """Public name for the slug helper. The UI needs it for filenames."""
    return _slug(name)
