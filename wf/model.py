"""The board model and every grid operation, with no Qt in sight.

Keeping this Qt-free is deliberate. Placement, collision, alignment and undo
are where the interesting bugs live, and they are far easier to test as plain
functions than through a widget. The UI layer holds one BoardModel and asks it
questions; it never manipulates card dicts directly.

A board is the same JSON shape the compiler already accepts, so what is edited
here and what is compiled are literally the same object.
"""

import copy
import json
import re

from .compiler import GRID_COLS, GRID_ROWS

ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')

UNDO_DEPTH = 60


# --------------------------------------------------------------------------
# Sanitising what comes off disk
# --------------------------------------------------------------------------
#
# Everything below this point assumes a card is a dict with integer x, y, w, h
# and a dict of settings. The compiler validates that too, but it validates in
# order to refuse - the UI has to paint the board first, and painting a card
# whose `w` is the string "6", or 6000, or missing, is how a malformed file
# turns into a traceback inside paintEvent and then a hard crash on the next
# repaint. So a board is repaired on the way in, and the user is told what was
# repaired rather than left wondering why their file looks different.
#
# The repairs are deliberately narrow. Sizes are clamped to the grid because an
# unclamped size is unbounded work in `occupied`; positions are clamped to the
# grid for the same reason. A card that still ends past the right or bottom
# edge is left that way, so the compiler's bounds error - which exists because
# the board does not scroll - still fires and still says so.

def _int(value, default, low, high):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def sanitise_board(raw, cols=GRID_COLS, rows=GRID_ROWS):
    """Return (board, repairs). Never raises, whatever `raw` is."""
    repairs = []

    if not isinstance(raw, dict):
        return ({'title': '', 'subtitle': '', 'cards': []},
                ['That file is not a board object, so an empty board was opened instead.'])

    board = dict(raw)
    for key in ('title', 'subtitle'):
        if key in board and not isinstance(board[key], str):
            board[key] = '' if board[key] is None else str(board[key])
            repairs.append('The board %s was not text and has been converted.' % key)

    defaults = board.get('defaults')
    if defaults is not None and not isinstance(defaults, dict):
        board.pop('defaults')
        repairs.append('The board defaults were not an object and have been dropped.')

    raw_cards = board.get('cards')
    if not isinstance(raw_cards, list):
        board['cards'] = []
        repairs.append('This board has no card list, so it opened empty.')
        return board, repairs

    cards = []
    seen = set()
    dropped = 0
    for entry in raw_cards:
        if not isinstance(entry, dict):
            dropped += 1
            continue

        module_id = entry.get('moduleId')
        if not isinstance(module_id, str) or not module_id:
            dropped += 1
            continue

        card = dict(entry)
        card['moduleId'] = module_id

        cid = card.get('id')
        if not isinstance(cid, str) or not ID_RE.match(cid) or cid in seen:
            fixed = next_id(cards, module_id)
            if isinstance(cid, str) and cid in seen:
                repairs.append('Two cards shared the id "%s"; the second is now "%s".'
                               % (cid, fixed))
            else:
                repairs.append('A card had no usable id and is now "%s".' % fixed)
            cid = fixed
        card['id'] = cid
        seen.add(cid)

        before = (card.get('x'), card.get('y'), card.get('w'), card.get('h'))
        card['w'] = _int(card.get('w'), 1, 1, cols)
        card['h'] = _int(card.get('h'), 1, 1, rows)
        card['x'] = _int(card.get('x'), 0, 0, cols - 1)
        card['y'] = _int(card.get('y'), 0, 0, rows - 1)
        if before != (card['x'], card['y'], card['w'], card['h']):
            repairs.append('Card "%s" had a position or size that is not on this grid '
                           'and has been brought back onto it.' % cid)

        settings = card.get('settings')
        if not isinstance(settings, dict):
            card['settings'] = {}
            if settings is not None:
                repairs.append('Card "%s" had settings that were not an object; '
                               'they have been cleared.' % cid)
        card['locked'] = bool(card.get('locked'))
        cards.append(card)

    if dropped:
        repairs.append('%d entr%s in the card list %s not a card and %s dropped.'
                       % (dropped, 'y' if dropped == 1 else 'ies',
                          'was' if dropped == 1 else 'were',
                          'has been' if dropped == 1 else 'have been'))

    board['cards'] = cards
    return board, repairs


# --------------------------------------------------------------------------
# Pure grid helpers
# --------------------------------------------------------------------------

def occupied(cards, skip_id=None, cols=GRID_COLS, rows=GRID_ROWS):
    """Set of (x, y) cells covered by cards, ignoring one id.

    Clamped to the grid. A card claiming 6000 columns is a malformed file, not
    a reason to build a set of 36 million tuples and freeze the window - which
    is exactly what an unclamped version did.
    """
    taken = set()
    for c in cards:
        if not isinstance(c, dict) or c.get('id') == skip_id:
            continue
        x = _int(c.get('x'), 0, 0, cols)
        y = _int(c.get('y'), 0, 0, rows)
        w = _int(c.get('w'), 1, 0, cols)
        h = _int(c.get('h'), 1, 0, rows)
        for cy in range(y, min(rows, y + h)):
            for cx in range(x, min(cols, x + w)):
                taken.add((cx, cy))
    return taken


def fits(cards, x, y, w, h, skip_id=None, cols=GRID_COLS, rows=GRID_ROWS):
    """Is a w x h card at (x, y) on the grid and clear of everything else?"""
    if x < 0 or y < 0 or x + w > cols or y + h > rows:
        return False
    taken = occupied(cards, skip_id, cols, rows)
    for cy in range(y, y + h):
        for cx in range(x, x + w):
            if (cx, cy) in taken:
                return False
    return True


def find_spot(cards, w, h, cols=GRID_COLS, rows=GRID_ROWS):
    """First free w x h slot scanning left to right, top to bottom. None if full."""
    taken = occupied(cards, None, cols, rows)
    for y in range(0, rows - h + 1):
        for x in range(0, cols - w + 1):
            free = True
            for dy in range(h):
                for dx in range(w):
                    if (x + dx, y + dy) in taken:
                        free = False
                        break
                if not free:
                    break
            if free:
                return x, y
    return None


def next_id(cards, module_id):
    """module_id_1, _2, ... skipping any already taken."""
    existing = set(c.get('id') for c in cards if isinstance(c, dict))
    n = 1
    while True:
        cid = '%s_%d' % (module_id, n)
        if cid not in existing:
            return cid
        n += 1


# --------------------------------------------------------------------------
# Board model
# --------------------------------------------------------------------------

class BoardModel(object):
    """One board plus its undo history.

    Callers wrap a mutation in `begin()` before changing anything. That pushes
    the current state; undo restores it. Mutating without begin() is a bug, not
    a shortcut - it silently makes the change unundoable.
    """

    def __init__(self, board=None, cols=GRID_COLS, rows=GRID_ROWS):
        self.cols = cols
        self.rows = rows
        self.board, self.repairs = sanitise_board(
            board if board is not None else {'title': '', 'subtitle': '', 'cards': []},
            cols, rows)
        self._undo = []
        self._redo = []

    # -- state -------------------------------------------------------------

    @property
    def cards(self):
        return self.board['cards']

    def card(self, cid):
        for c in self.cards:
            if c.get('id') == cid:
                return c
        return None

    def snapshot(self):
        return json.dumps(self.board, sort_keys=False)

    def begin(self):
        """Record the current state so the next change can be undone."""
        self._undo.append(self.snapshot())
        if len(self._undo) > UNDO_DEPTH:
            self._undo.pop(0)
        self._redo = []

    def push_state(self, state_json):
        """Record a specific earlier state - used by drag, which mutates live."""
        self._undo.append(state_json)
        if len(self._undo) > UNDO_DEPTH:
            self._undo.pop(0)
        self._redo = []

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self.board, _ = sanitise_board(json.loads(self._undo.pop()), self.cols, self.rows)
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.board, _ = sanitise_board(json.loads(self._redo.pop()), self.cols, self.rows)
        return True

    def replace(self, board, keep_history=True):
        """Swap in a whole board, e.g. after opening a file.

        Returns the list of repairs sanitise_board had to make. Everything that
        loads a board goes through here, so there is one place that guarantees
        the rest of the app is looking at a well-formed board.
        """
        clean, repairs = sanitise_board(board, self.cols, self.rows)
        if keep_history:
            self.begin()
        else:
            self._undo = []
            self._redo = []
        self.board = clean
        return repairs

    # -- grid --------------------------------------------------------------

    def occupied(self, skip_id=None):
        return occupied(self.cards, skip_id, self.cols, self.rows)

    def fits(self, x, y, w, h, skip_id=None):
        return fits(self.cards, x, y, w, h, skip_id, self.cols, self.rows)

    def find_spot(self, w, h):
        return find_spot(self.cards, w, h, self.cols, self.rows)

    def card_at(self, x, y):
        """Topmost card covering a cell. Later cards win, matching paint order."""
        hit = None
        for c in self.cards:
            cx, cy = int(c.get('x', 0)), int(c.get('y', 0))
            cw, ch = int(c.get('w', 1)), int(c.get('h', 1))
            if cx <= x < cx + cw and cy <= y < cy + ch:
                hit = c
        return hit

    # -- cards -------------------------------------------------------------

    def add_card(self, module_id, meta, at=None, board_default_table=''):
        """Place a new card. Returns the card, or None if there is no room."""
        w, h = int(meta['size'][0]), int(meta['size'][1])
        if at is None:
            spot = self.find_spot(w, h)
            if spot is None:
                return None
            x, y = spot
        else:
            x, y = at

        settings = {}
        for f in meta.get('fields', []):
            if f.get('default') is None:
                continue
            # With a board default set, leaving table blank is the point -
            # otherwise the module's own default silently wins and the board
            # default can never apply to anything.
            if f['key'] == 'table' and board_default_table:
                continue
            settings[f['key']] = f['default']

        self.begin()
        card = {'id': next_id(self.cards, module_id), 'moduleId': module_id,
                'x': x, 'y': y, 'w': w, 'h': h, 'settings': settings}
        self.cards.append(card)
        return card

    def add_preset(self, preset):
        """Place a saved preset. Returns the card, or None if there is no room."""
        w, h = int(preset['w']), int(preset['h'])
        spot = self.find_spot(w, h)
        if spot is None:
            return None
        self.begin()
        card = {'id': next_id(self.cards, preset['moduleId']), 'moduleId': preset['moduleId'],
                'x': spot[0], 'y': spot[1], 'w': w, 'h': h,
                'settings': copy.deepcopy(preset.get('settings') or {})}
        self.cards.append(card)
        return card

    def duplicate(self, cid):
        src = self.card(cid)
        if not src:
            return None
        spot = self.find_spot(int(src['w']), int(src['h']))
        if spot is None:
            return None
        self.begin()
        copy_ = copy.deepcopy(src)
        copy_['id'] = next_id(self.cards, src['moduleId'])
        copy_['x'], copy_['y'] = spot
        copy_.pop('locked', None)
        self.cards.append(copy_)
        return copy_

    def remove(self, ids):
        """Delete cards by id. Returns how many went. Locked cards stay."""
        doomed = [i for i in ids if (self.card(i) and not self.card(i).get('locked'))]
        if not doomed:
            return 0
        self.begin()
        self.board['cards'] = [c for c in self.cards if c.get('id') not in doomed]
        return len(doomed)

    def clear(self):
        if not self.cards:
            return False
        self.begin()
        self.board['cards'] = []
        return True

    # -- alignment ---------------------------------------------------------

    def align(self, ids, how):
        """Align, match size or spread. Locked cards are left out entirely."""
        cs = [self.card(i) for i in ids]
        cs = [c for c in cs if c and not c.get('locked')]
        if len(cs) < 2:
            return False
        self.begin()
        cols, rows = self.cols, self.rows

        if how == 'left':
            edge = min(c['x'] for c in cs)
            for c in cs:
                c['x'] = min(edge, cols - c['w'])
        elif how == 'right':
            edge = max(c['x'] + c['w'] for c in cs)
            for c in cs:
                c['x'] = max(0, edge - c['w'])
        elif how == 'top':
            edge = min(c['y'] for c in cs)
            for c in cs:
                c['y'] = min(edge, rows - c['h'])
        elif how == 'bottom':
            edge = max(c['y'] + c['h'] for c in cs)
            for c in cs:
                c['y'] = max(0, edge - c['h'])
        elif how == 'width':
            wmax = max(c['w'] for c in cs)
            for c in cs:
                c['w'] = min(wmax, cols - c['x'])
        elif how == 'height':
            hmax = max(c['h'] for c in cs)
            for c in cs:
                c['h'] = min(hmax, rows - c['y'])
        elif how == 'spread':
            cs.sort(key=lambda c: c['x'])
            first, last = cs[0], cs[-1]
            span = (last['x'] + last['w']) - first['x']
            used = sum(c['w'] for c in cs)
            gap = (span - used) // (len(cs) - 1) if len(cs) > 1 else 0
            if gap < 0:
                gap = 0
            at = first['x']
            for c in cs:
                c['x'] = min(at, cols - c['w'])
                at = c['x'] + c['w'] + gap
        else:
            return False
        return True

    def nudge(self, ids, dx, dy):
        """Move a selection by whole cells, clamped to the grid.

        The whole selection moves by the same amount or not at all, so a card
        against the edge does not slide out from under its neighbours.
        """
        cs = [self.card(i) for i in ids]
        cs = [c for c in cs if c and not c.get('locked')]
        if not cs:
            return False
        if dx < 0:
            dx = max(dx, -min(c['x'] for c in cs))
        if dx > 0:
            dx = min(dx, min(self.cols - (c['x'] + c['w']) for c in cs))
        if dy < 0:
            dy = max(dy, -min(c['y'] for c in cs))
        if dy > 0:
            dy = min(dy, min(self.rows - (c['y'] + c['h']) for c in cs))
        if not dx and not dy:
            return False
        self.begin()
        for c in cs:
            c['x'] += dx
            c['y'] += dy
        return True
