"""Board files on disk, and the small amount of app state the UI remembers.

Two separate places, deliberately:

  boards/            saved boards, beside the app, gitignored, yours to copy
                     around. Named by slug, exactly as the Flask build named
                     them, so boards written by 3.4.0 open unchanged.

  <user config>/     theme, presets, the autosaved draft, window geometry.
                     Not in the tree, because a standalone exe may sit
                     somewhere unwritable and because none of it is work you
                     would ever want to copy to another machine.

Every write goes through _atomic_write. A half-written board is worse than no
board, and Windows will happily leave one behind if the process dies between
truncate and flush.
"""

import json
import os
import sys
import tempfile

from . import compiler

HERE = compiler.HERE
# Beside the executable for a packaged build, beside the tree from source.
# Never inside a bundle: a board written there would be invisible to the user
# and would be deleted by the next install.
BOARDS_DIR = os.path.join(compiler.USER_ROOT, 'boards')

APP_DIR_NAME = 'WidgetForge'
STATE_FILE = 'state.json'

_DEFAULT_STATE = {
    # None means "never chosen" - the window then follows the desktop's own
    # light/dark setting, the way the web build followed prefers-color-scheme.
    'theme': None,
    'presets': [],
    'draft': None,
    'lastSysId': '',
    'geometry': None,
    'windowState': None,
    'drawerHidden': False,
}


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------

def state_dir():
    """Where app state lives. Falls back into the tree if nothing else works."""
    base = None
    if sys.platform.startswith('win'):
        base = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
    elif sys.platform == 'darwin':
        home = os.path.expanduser('~')
        base = os.path.join(home, 'Library', 'Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')

    candidates = []
    if base:
        candidates.append(os.path.join(base, APP_DIR_NAME))
    candidates.append(os.path.join(compiler.USER_ROOT, '.wfstate'))

    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, '.writable')
            with open(probe, 'w') as f:
                f.write('')
            os.remove(probe)
            return path
        except OSError:
            continue
    # Nothing is writable. The caller degrades to in-memory state.
    return None


# Windows refuses these as filenames, matching on the part before the first
# dot, so `con.json` and `com1.server.js` are both rejected - with an opaque
# WinError rather than anything a user could act on. A board titled "Con" is
# unlikely but entirely legal, so the stem is checked rather than hoped about.
_RESERVED = frozenset(
    ['con', 'prn', 'aux', 'nul']
    + ['com%d' % i for i in range(1, 10)]
    + ['lpt%d' % i for i in range(1, 10)]
)


def safe_stem(name):
    """A slug that is also a legal filename stem on Windows."""
    stem = compiler.slug(name)
    if stem.split('.')[0] in _RESERVED:
        stem += '-board'
    return stem


def board_path(name, suffix='.json'):
    os.makedirs(BOARDS_DIR, exist_ok=True)
    return os.path.join(BOARDS_DIR, safe_stem(name) + suffix)


# --------------------------------------------------------------------------
# Atomic writes
# --------------------------------------------------------------------------

def _atomic_write(path, text):
    """Write via a temp file in the same directory, then replace.

    Same directory matters: os.replace is only atomic within one filesystem,
    and %TEMP% is often a different volume from the user's Desktop.
    """
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.wf-', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Boards
# --------------------------------------------------------------------------

def list_boards():
    """[(title, filename)] for every saved board, sorted by title."""
    os.makedirs(BOARDS_DIR, exist_ok=True)
    out = []
    for fn in sorted(os.listdir(BOARDS_DIR)):
        if not fn.endswith('.json') or fn.endswith('.deploy.json'):
            continue
        path = os.path.join(BOARDS_DIR, fn)
        try:
            with open(path, encoding='utf-8') as f:
                title = json.load(f).get('title') or fn
        except (ValueError, OSError):
            title = fn + ' (unreadable)'
        out.append((str(title), fn))
    out.sort(key=lambda pair: pair[0].lower())
    return out


def load_board(name):
    path = board_path(name)
    if not os.path.isfile(path):
        raise FileNotFoundError('No board saved as "%s"' % name)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_board_file(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_board(name, board):
    path = board_path(name)
    _atomic_write(path, json.dumps(board, indent=2))
    return path


def delete_board(name):
    path = board_path(name)
    if os.path.isfile(path):
        os.remove(path)


# --------------------------------------------------------------------------
# App state
# --------------------------------------------------------------------------

class State(object):
    """Theme, presets and the autosaved draft.

    Reads are forgiving: a corrupt or unreadable state file degrades to
    defaults rather than stopping the app from starting. Losing the last
    theme choice is not worth a crash on launch.
    """

    def __init__(self, folder=None):
        self.folder = folder if folder is not None else state_dir()
        self.path = os.path.join(self.folder, STATE_FILE) if self.folder else None
        self.data = dict(_DEFAULT_STATE)
        self.readonly = self.path is None
        self.load()

    def load(self):
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                merged = dict(_DEFAULT_STATE)
                merged.update(raw)
                self.data = merged
        except (ValueError, OSError):
            pass
        if not isinstance(self.data.get('presets'), list):
            self.data['presets'] = []

    def save(self):
        if not self.path:
            return False
        try:
            _atomic_write(self.path, json.dumps(self.data, indent=2))
            return True
        except OSError:
            self.readonly = True
            return False

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return self.save()
