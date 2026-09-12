"""The 24 x 16 grid canvas.

Custom-painted rather than built from QGraphicsItems. The board is a fixed
grid of at most a few dozen rectangles that must fill the available space
exactly; a scene graph would add a coordinate system to keep in sync with the
one the compiler emits, and that is precisely the sync that would drift. Here
there is one function, `cell_rect`, and both painting and hit-testing go
through it, so they cannot disagree.

The grid is the layout. What you see here is what `.wf-c-<id>` will say.
"""

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QDrag, QFontMetrics, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

from . import icons
from .theme import adjust_font, tokens

MIME_MODULE = 'application/x-widgetforge-module'
MIME_PRESET = 'application/x-widgetforge-preset'

GAP = 6
MARGIN = 2
GRIP = 14


class Ruler(QWidget):
    """Column numbers above the canvas, with the dragged span lit."""

    def __init__(self, cols, parent=None):
        super().__init__(parent)
        self.cols = cols
        self.theme = 'dark'
        self._from = None
        self._to = None
        self.setFixedHeight(16)

    def set_theme(self, name):
        self.theme = name
        self.update()

    def highlight(self, start=None, end=None):
        if (start, end) != (self._from, self._to):
            self._from, self._to = start, end
            self.update()

    def paintEvent(self, event):
        t = tokens(self.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(t['ink']))
        w = self.width() - MARGIN * 2
        if w <= 0 or not self.cols:
            p.end()
            return
        cell = (w - GAP * (self.cols - 1)) / float(self.cols)
        p.setFont(adjust_font(self.font(), -3))
        for i in range(self.cols):
            x = MARGIN + i * (cell + GAP)
            lit = self._from is not None and self._from <= i < self._to
            p.setPen(QPen(QColor(t['signal'] if lit else t['dim'])))
            rect = QRectF(x, 0, cell, self.height())
            if lit:
                p.fillRect(rect, icons.tint(t['signal'], 0.16))
            if i % 2 == 0:
                p.drawText(rect, Qt.AlignCenter, str(i))
        p.end()


class GridCanvas(QWidget):
    """Places, moves, resizes and selects cards on the grid."""

    selectionChanged = Signal()
    boardChanged = Signal()          # something that must be recompiled
    liveMoved = Signal()             # mid-drag; repaint only, no recompile
    hudChanged = Signal(str)
    statusMessage = Signal(str, str)  # text, kind ('ok' | 'bad' | '')
    placeModule = Signal(str, int, int)
    placePreset = Signal(str, int, int)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.mods = {}
        self.presets = []
        self.theme = 'dark'
        self.selected = None
        self.extra = set()
        self.ruler = None

        self._drag = None       # in-progress move/resize
        self._ghost = None      # (x, y, w, h, ok) while a drop hovers
        self._flash = None      # card id briefly outlined after a jump

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(420, 280)

    # -- wiring ------------------------------------------------------------

    def set_modules(self, mods):
        self.mods = mods
        self.update()

    def set_theme(self, name):
        self.theme = name
        self.update()

    def selection(self):
        """Selected ids that still exist, primary first."""
        out = []
        if self.selected and self.model.card(self.selected):
            out.append(self.selected)
        for cid in self.extra:
            if cid != self.selected and self.model.card(cid):
                out.append(cid)
        return out

    def select(self, cid, additive=False):
        if additive and self.selected and cid != self.selected:
            self.extra.add(cid)
        elif not additive:
            self.extra.clear()
        self.selected = cid
        self.update()
        self.selectionChanged.emit()

    def clear_selection(self):
        self.selected = None
        self.extra.clear()
        self.update()
        self.selectionChanged.emit()

    def prune_selection(self):
        """Drop ids that no longer exist, e.g. after undo."""
        if self.selected and not self.model.card(self.selected):
            self.selected = None
        self.extra = set(c for c in self.extra if self.model.card(c))
        self.update()

    # -- geometry ----------------------------------------------------------

    def metrics(self):
        cols, rows = self.model.cols, self.model.rows
        w = self.width() - MARGIN * 2
        h = self.height() - MARGIN * 2
        cw = (w - GAP * (cols - 1)) / float(cols) if cols else 0
        ch = (h - GAP * (rows - 1)) / float(rows) if rows else 0
        return cw, ch

    def cell_rect(self, x, y, w=1, h=1):
        cw, ch = self.metrics()
        left = MARGIN + x * (cw + GAP)
        top = MARGIN + y * (ch + GAP)
        return QRectF(left, top, w * cw + (w - 1) * GAP, h * ch + (h - 1) * GAP)

    def cell_at(self, pos):
        """Grid cell under a pixel position, unclamped."""
        cw, ch = self.metrics()
        if cw <= 0 or ch <= 0:
            return 0, 0
        x = int((pos.x() - MARGIN) // (cw + GAP))
        y = int((pos.y() - MARGIN) // (ch + GAP))
        return x, y

    def drop_cell(self, pos, w, h):
        """Top-left cell for a w x h card centred on the pointer, clamped."""
        cw, ch = self.metrics()
        if cw <= 0 or ch <= 0:
            return 0, 0
        fx = (pos.x() - MARGIN) / (cw + GAP) - w / 2.0
        fy = (pos.y() - MARGIN) / (ch + GAP) - h / 2.0
        x = int(round(fx))
        y = int(round(fy))
        x = max(0, min(self.model.cols - w, x))
        y = max(0, min(self.model.rows - h, y))
        return x, y

    @staticmethod
    def paintable(card):
        """Is this card safe to lay out? See sanitise_board - this is the net."""
        return (isinstance(card, dict)
                and all(isinstance(card.get(k), int) for k in ('x', 'y', 'w', 'h')))

    def card_hit(self, pos):
        """Card under a point, honouring paint order (later cards win)."""
        hit = None
        for c in self.model.cards:
            if not self.paintable(c):
                continue
            if self.cell_rect(c['x'], c['y'], c['w'], c['h']).contains(pos):
                hit = c
        return hit

    def grip_rect(self, card):
        r = self.cell_rect(card['x'], card['y'], card['w'], card['h'])
        return QRectF(r.right() - GRIP, r.bottom() - GRIP, GRIP, GRIP)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event):
        t = tokens(self.theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(t['ink']))

        cw, ch = self.metrics()
        if cw <= 0 or ch <= 0:
            p.end()
            return

        # empty cells, so the grid reads as a grid even with nothing on it
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t['gridline']))
        for gy in range(self.model.rows):
            for gx in range(self.model.cols):
                p.drawRoundedRect(self.cell_rect(gx, gy), 2, 2)

        if not self.model.cards and not self._ghost:
            self._paint_empty(p, t)

        sel = set(self.selection())
        for c in self.model.cards:
            if not self.paintable(c):
                continue
            self._paint_card(p, t, c, c['id'] in sel)

        if self._ghost:
            gx, gy, gw, gh, ok = self._ghost
            r = self.cell_rect(gx, gy, gw, gh)
            colour = QColor(t['signal'] if ok else t['bad'])
            p.setBrush(icons.tint(colour.name(), 0.16))
            pen = QPen(colour)
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)

        p.end()

    def _paint_empty(self, p, t):
        p.setPen(QPen(QColor(t['dim'])))
        p.setFont(adjust_font(self.font(), 2, bold=True))
        r = QRectF(self.rect())
        top = QRectF(r.x(), r.y() + r.height() / 2 - 26, r.width(), 24)
        p.drawText(top, Qt.AlignCenter, 'Nothing on the canvas yet')
        p.setFont(self.font())
        bottom = QRectF(r.x(), r.y() + r.height() / 2, r.width(), 22)
        p.drawText(bottom, Qt.AlignCenter,
                   'Drag a card from the left, or click one to drop it '
                   'in the first free spot.')

    def _paint_card(self, p, t, c, is_selected):
        meta = self.mods.get(c.get('moduleId'))
        r = self.cell_rect(c['x'], c['y'], c['w'], c['h'])
        accent = (meta.get('accent') or t['signal']) if meta else t['bad']
        locked = bool(c.get('locked'))

        flashing = self._flash == c.get('id')
        p.setBrush(QColor(t['nodeFill']))
        pen = QPen(QColor(t['sand'] if flashing
                          else (accent if is_selected else t['nodeLine'])))
        pen.setWidth(3 if flashing else (2 if is_selected else 1))
        p.setPen(pen)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)

        if is_selected:
            p.setPen(Qt.NoPen)
            p.setBrush(icons.tint(accent, 0.08))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)

        inner = r.adjusted(7, 5, -7, -5)
        if inner.width() < 12 or inner.height() < 10:
            return

        # icon chip
        chip = QRectF(inner.x(), inner.y() + 1, 16, 16)
        if inner.height() >= 16 and inner.width() > 40:
            p.setPen(Qt.NoPen)
            p.setBrush(icons.tint(accent, 0.18))
            p.drawRoundedRect(chip, 4, 4)
            icons.draw(p, (meta.get('icon') if meta else 'hash') or 'hash',
                       chip.adjusted(3, 3, -3, -3), accent, 1.7)
            text_left = chip.right() + 6
        else:
            text_left = inner.x()

        title = ''
        if c.get('settings'):
            title = str(c['settings'].get('title') or '')
        if not title:
            title = meta['name'] if meta else str(c.get('moduleId', '?'))

        fm = QFontMetrics(self.font())
        kind = str(c.get('moduleId', ''))
        kind_w = fm.horizontalAdvance(kind) + 8
        avail = inner.right() - text_left - (kind_w if inner.width() > 150 else 0)

        p.setPen(QPen(QColor(t['text'])))
        p.setFont(adjust_font(self.font(), 0, bold=True))
        name_rect = QRectF(text_left, inner.y(), max(10, avail - (18 if locked else 0)), 18)
        p.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(title, Qt.ElideRight, int(name_rect.width())))
        p.setFont(self.font())

        if locked:
            icons.draw(p, 'lock', QRectF(name_rect.right() + 2, inner.y() + 2, 13, 13),
                       t['sand'], 1.6)

        if inner.width() > 150:
            p.setPen(QPen(QColor(t['dim'])))
            p.drawText(QRectF(inner.right() - kind_w, inner.y(), kind_w, 18),
                       Qt.AlignRight | Qt.AlignVCenter, kind)

        # summary and position, only when the card is tall enough to hold them
        y = inner.y() + 19
        if c['h'] > 1 and y + 14 <= inner.bottom():
            p.setPen(QPen(QColor(t['dim'])))
            summary = self.summarise(c)
            if summary:
                p.drawText(QRectF(inner.x(), y, inner.width(), 14),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(summary, Qt.ElideRight, int(inner.width())))
            y += 15
        if c['h'] > 2 and y + 13 <= inner.bottom():
            p.setPen(QPen(QColor(t['dim'])))
            p.drawText(QRectF(inner.x(), y, inner.width(), 13),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       'x%d y%d · %d×%d' % (c['x'], c['y'], c['w'], c['h']))

        # resize grip
        if not locked and r.width() > 34 and r.height() > 26:
            g = self.grip_rect(c)
            p.setPen(QPen(QColor(t['dim'] if not is_selected else accent), 1.4))
            for off in (3, 7):
                p.drawLine(int(g.right() - off), int(g.bottom() - 3),
                           int(g.right() - 3), int(g.bottom() - off))

    def summarise(self, c):
        s = c.get('settings') or {}
        bits = []
        if s.get('table'):
            bits.append(str(s['table']))
        if s.get('groupBy'):
            bits.append('by ' + str(s['groupBy']))
        if s.get('dateField'):
            bits.append('%s / %sd' % (s['dateField'], s.get('days', 30)))
        if s.get('filter'):
            bits.append(str(s['filter'])[:28])
        if not bits and c.get('moduleId') == 'text':
            bits.append(str(s.get('body', ''))[:30])
        if not bits and c.get('moduleId') == 'heading':
            bits.append(str(s.get('text', '')))
        return ' · '.join(b for b in bits if b)

    # -- mouse -------------------------------------------------------------

    def flash(self, cid, msec=700):
        """Outline a card briefly, so a jump to it is visible on a full board."""
        from PySide6.QtCore import QTimer
        self._flash = cid
        self.update()
        QTimer.singleShot(msec, self._clear_flash)

    def _clear_flash(self):
        if self._flash is not None:
            self._flash = None
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            # Not ours. Say so, rather than leaving the event marked accepted
            # and swallowing a right-click a parent might want.
            event.ignore()
            return
        pos = event.position()
        card = self.card_hit(pos)
        if not card:
            self.clear_selection()
            return

        additive = bool(event.modifiers() & Qt.ShiftModifier)
        if not additive and card['id'] not in self.extra:
            self.extra.clear()
        self.select(card['id'], additive)

        if card.get('locked'):
            self.hudChanged.emit('that card is locked')
            return

        resizing = self.grip_rect(card).contains(pos)
        others = [i for i in self.selection() if i != card['id']]
        self._drag = {
            'id': card['id'],
            'resize': resizing,
            'origin': pos,
            'x': card['x'], 'y': card['y'], 'w': card['w'], 'h': card['h'],
            'before': self.model.snapshot(),
            'moved': False,
            'group': None if resizing else [
                (i, self.model.card(i)['x'], self.model.card(i)['y']) for i in others
            ],
        }

    def mouseMoveEvent(self, event):
        pos = event.position()
        if not self._drag:
            card = self.card_hit(pos)
            cursor = Qt.ArrowCursor
            if card and not card.get('locked'):
                cursor = (Qt.SizeFDiagCursor if self.grip_rect(card).contains(pos)
                          else Qt.OpenHandCursor)
            self.setCursor(cursor)
            return

        cw, ch = self.metrics()
        if cw <= 0 or ch <= 0:
            return
        d = self._drag
        c = self.model.card(d['id'])
        if not c:
            self._drag = None
            return
        meta = self.mods.get(c['moduleId'])
        dx = int(round((pos.x() - d['origin'].x()) / (cw + GAP)))
        dy = int(round((pos.y() - d['origin'].y()) / (ch + GAP)))
        if dx or dy:
            d['moved'] = True

        if d['resize']:
            min_w = meta['min'][0] if meta else 2
            min_h = meta['min'][1] if meta else 1
            c['w'] = max(min_w, min(self.model.cols - c['x'], d['w'] + dx))
            c['h'] = max(min_h, min(self.model.rows - c['y'], d['h'] + dy))
        else:
            nx = max(0, min(self.model.cols - c['w'], d['x'] + dx))
            ny = max(0, min(self.model.rows - c['h'], d['y'] + dy))
            c['x'], c['y'] = nx, ny
            for cid, ox, oy in (d['group'] or []):
                o = self.model.card(cid)
                if not o or o.get('locked'):
                    continue
                o['x'] = max(0, min(self.model.cols - o['w'], ox + (nx - d['x'])))
                o['y'] = max(0, min(self.model.rows - o['h'], oy + (ny - d['y'])))

        self.hudChanged.emit('x%02d y%02d  ·  %d×%d' % (c['x'], c['y'], c['w'], c['h']))
        if self.ruler:
            self.ruler.highlight(c['x'], c['x'] + c['w'])
        self.update()
        self.liveMoved.emit()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._drag:
            event.ignore()
            return
        d = self._drag
        self._drag = None
        self.setCursor(Qt.ArrowCursor)
        if self.ruler:
            self.ruler.highlight()
        self.hudChanged.emit('')
        if d['moved']:
            # The drag mutated the live board, so the state to undo back to is
            # the one captured at mousePressEvent, not the current one.
            self.model.push_state(d['before'])
            self.boardChanged.emit()
        self.update()

    def mouseDoubleClickEvent(self, event):
        card = self.card_hit(event.position())
        if card:
            self.select(card['id'])

    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    # -- drag and drop from the palette ------------------------------------

    def _payload(self, mime):
        if mime.hasFormat(MIME_MODULE):
            return 'module', bytes(mime.data(MIME_MODULE)).decode('utf-8')
        if mime.hasFormat(MIME_PRESET):
            return 'preset', bytes(mime.data(MIME_PRESET)).decode('utf-8')
        return None, None

    def _drop_size(self, kind, name):
        if kind == 'module':
            meta = self.mods.get(name)
            return (meta['size'][0], meta['size'][1]) if meta else None
        for p in self.presets or []:
            if p.get('name') == name:
                return int(p['w']), int(p['h'])
        return None

    def dragEnterEvent(self, event):
        kind, name = self._payload(event.mimeData())
        if kind and self._drop_size(kind, name):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        kind, name = self._payload(event.mimeData())
        size = self._drop_size(kind, name) if kind else None
        if not size:
            event.ignore()
            return
        w, h = size
        x, y = self.drop_cell(event.position(), w, h)
        ok = self.model.fits(x, y, w, h)
        self._ghost = (x, y, w, h, ok)
        self.hudChanged.emit('x%02d y%02d  ·  %d×%d' % (x, y, w, h)
                             if ok else 'no room there')
        if self.ruler:
            self.ruler.highlight(x, x + w)
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._ghost = None
        self.hudChanged.emit('')
        if self.ruler:
            self.ruler.highlight()
        self.update()

    def dropEvent(self, event):
        kind, name = self._payload(event.mimeData())
        size = self._drop_size(kind, name) if kind else None
        self._ghost = None
        if self.ruler:
            self.ruler.highlight()
        self.hudChanged.emit('')
        if not size:
            event.ignore()
            return
        w, h = size
        x, y = self.drop_cell(event.position(), w, h)
        if not self.model.fits(x, y, w, h):
            self.statusMessage.emit('That spot is taken or off the grid.', 'bad')
            self.update()
            event.ignore()
            return
        event.acceptProposedAction()
        if kind == 'module':
            self.placeModule.emit(name, x, y)
        else:
            self.placePreset.emit(name, x, y)

    # -- keyboard ----------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        step = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0),
                Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}.get(key)
        if step and self.selection():
            if self.model.nudge(self.selection(), step[0], step[1]):
                self.update()
                self.boardChanged.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def make_drag(source, kind, name, label, accent, icon_name):
    """Build the QDrag used when a palette entry is dragged onto the canvas."""
    from PySide6.QtGui import QPixmap

    mime = QMimeData()
    mime.setData(MIME_MODULE if kind == 'module' else MIME_PRESET, name.encode('utf-8'))
    mime.setText(label)

    dpr = source.devicePixelRatioF() if hasattr(source, 'devicePixelRatioF') else 1.0
    fm = QFontMetrics(source.font())
    w = min(240, 44 + fm.horizontalAdvance(label))
    h = 28
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 6, 6)
    p.fillPath(path, QColor(30, 39, 51, 235))
    p.setPen(QPen(QColor(accent)))
    p.drawPath(path)
    icons.draw(p, icon_name or 'hash', QRectF(7, 7, 14, 14), accent, 1.7)
    p.setPen(QPen(QColor('#dde5ef')))
    p.drawText(QRectF(27, 0, w - 32, h), Qt.AlignLeft | Qt.AlignVCenter,
               fm.elidedText(label, Qt.ElideRight, int(w - 34)))
    p.end()

    drag = QDrag(source)
    drag.setMimeData(mime)
    drag.setPixmap(pm)
    drag.setHotSpot(QPoint(int(w / 2), int(h / 2)))
    return drag
