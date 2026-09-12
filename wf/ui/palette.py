"""The card palette: searchable card types, plus saved presets.

Entries are real widgets rather than list rows so each one can carry its own
accent colour and start a drag with a matching chip. Double-click drops a card
in the first free spot; dragging places it exactly.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import icons
from .canvas import make_drag
from .theme import tokens


class Swatch(QWidget):
    """The little tinted square with the card-type glyph in it."""

    def __init__(self, icon_name, accent, size=26, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name or 'hash'
        self.accent = accent
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(icons.tint(self.accent, 0.16))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 6, 6)
        inset = self.width() * 0.26
        icons.draw(p, self.icon_name,
                   QRectF(inset, inset, self.width() - inset * 2, self.height() - inset * 2),
                   self.accent, 1.7)
        p.end()


class Elided(QLabel):
    """A label that shortens with an ellipsis instead of being cut off."""

    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        self._full = text
        super().setText(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.ElideRight, max(10, self.width())))

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(10)
        return hint


class PaletteItem(QWidget):
    """One palette row. Drag to place, double-click to auto-place."""

    activated = Signal(str, str)       # kind, name
    forget = Signal(str)               # preset name

    def __init__(self, kind, name, title, blurb, accent, icon_name,
                 size_text='', removable=False, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.name = name
        self.title = title
        self.accent = accent
        self.icon_name = icon_name
        self._press = None
        self._dragged = False

        self.setObjectName('PaletteItem')
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(blurb or title)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 8, 5)
        row.setSpacing(8)
        row.addWidget(Swatch(icon_name, accent))

        text = QVBoxLayout()
        text.setSpacing(0)
        text.setContentsMargins(0, 0, 0, 0)
        lbl = Elided(title)
        lbl.setObjectName('PalName')
        sub = Elided(blurb or '')
        sub.setObjectName('PalBlurb')
        sub.setWordWrap(False)
        text.addWidget(lbl)
        text.addWidget(sub)
        row.addLayout(text, 1)

        if size_text:
            sz = QLabel(size_text)
            sz.setObjectName('PalSize')
            sz.setMinimumWidth(30)
            sz.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(sz, 0, Qt.AlignVCenter)

        if removable:
            drop = QLabel('×')
            drop.setObjectName('PalSize')
            drop.setCursor(Qt.PointingHandCursor)
            drop.setToolTip('Forget this preset')
            drop.mousePressEvent = self._forget
            row.addWidget(drop, 0, Qt.AlignVCenter)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumHeight(42)

    def _forget(self, event):
        event.accept()
        self.forget.emit(self.name)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._press is None or not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self._press).manhattanLength() < 6:
            return
        self._press = None
        self._dragged = True
        drag = make_drag(self, self.kind, self.name, self.title,
                         self.accent, self.icon_name)
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event):
        pressed = self._press is not None
        self._press = None
        if pressed and not self._dragged and event.button() == Qt.LeftButton:
            # Pressed and released without dragging: place it in the first
            # free spot, the way a click did in the web builder.
            self.activated.emit(self.kind, self.name)
        self._dragged = False

    def mouseDoubleClickEvent(self, event):
        # The first click of a double-click already placed one. Swallow this so
        # an impatient double-click does not silently add two cards.
        event.accept()


class PaletteRail(QWidget):
    """Search box plus the list of card types and presets."""

    place = Signal(str, str)     # kind, name - drop in the first free spot
    forgetPreset = Signal(str)
    clearCanvas = Signal()
    importBoard = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('PaletteRail')
        self.mods = {}
        self.presets = []
        self.theme = 'dark'
        self.query = ''

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QLabel('Cards')
        head.setObjectName('RailHead')
        outer.addWidget(head)

        hint = QLabel('drag onto the canvas, or click to place')
        hint.setObjectName('RailHint')
        hint.setContentsMargins(12, 0, 12, 6)
        outer.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search cards')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(10, 0, 10, 8)
        wl.addWidget(self.search)
        outer.addWidget(wrap)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.list = QVBoxLayout(self.body)
        self.list.setContentsMargins(4, 0, 4, 8)
        self.list.setSpacing(1)
        self.list.addStretch(1)
        self.area.setWidget(self.body)
        outer.addWidget(self.area, 1)

        # The web build kept these two at the foot of this rail. They are in
        # the menus as well, but a board-level action you use every session
        # should not be two clicks deep.
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(10, 6, 10, 10)
        fl.setSpacing(5)
        clear = QPushButton('Clear canvas')
        clear.setProperty('flavour', 'ghost')
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clearCanvas.emit)
        imp = QPushButton('Import board JSON')
        imp.setProperty('flavour', 'ghost')
        imp.setCursor(Qt.PointingHandCursor)
        imp.clicked.connect(self.importBoard.emit)
        fl.addWidget(clear)
        fl.addWidget(imp)
        outer.addWidget(foot)

        self.setMinimumWidth(232)
        self.setMaximumWidth(340)

    def _on_search(self, text):
        self.query = text.strip().lower()
        self.rebuild()

    def set_modules(self, mods):
        self.mods = mods
        self.rebuild()

    def set_presets(self, presets):
        self.presets = presets or []
        self.rebuild()

    def set_theme(self, name):
        self.theme = name
        self.rebuild()

    def _clear(self):
        while self.list.count():
            item = self.list.takeAt(0)
            w = item.widget()
            if w:
                # Reparent before deleting. deleteLater is queued, and a widget
                # that is merely removed from the layout keeps painting at its
                # old geometry until the event loop gets round to it - which is
                # how two rebuilds in one turn drew every row twice.
                w.setParent(None)
                w.deleteLater()

    def rebuild(self):
        self._clear()
        t = tokens(self.theme)
        q = self.query

        ids = sorted(self.mods, key=lambda i: self.mods[i]['name'].lower())
        if q:
            ids = [i for i in ids
                   if q in ('%s %s %s' % (self.mods[i]['name'],
                                          self.mods[i].get('blurb', ''), i)).lower()]
        if not ids and not self.presets:
            none = QLabel('Nothing matches "%s"' % self.query if q else 'No card types found')
            none.setObjectName('PalNone')
            none.setWordWrap(True)
            self.list.addWidget(none)

        for mid in ids:
            m = self.mods[mid]
            item = PaletteItem('module', mid, m['name'], m.get('blurb', ''),
                               m.get('accent') or t['signal'], m.get('icon'),
                               '%d×%d' % (m['size'][0], m['size'][1]))
            item.activated.connect(self.place.emit)
            self.list.addWidget(item)

        shown = [p for p in self.presets
                 if not q or q in ('%s %s' % (p.get('name', ''), p.get('moduleId', ''))).lower()]
        if shown:
            sep = QLabel('Presets')
            sep.setObjectName('PalSep')
            self.list.addWidget(sep)
            for p in shown:
                m = self.mods.get(p.get('moduleId'))
                accent = (m.get('accent') if m else None) or t['dim']
                item = PaletteItem('preset', p['name'], p['name'], p.get('moduleId', ''),
                                   accent, m.get('icon') if m else 'hash',
                                   '%d×%d' % (p['w'], p['h']), removable=True)
                item.activated.connect(self.place.emit)
                item.forget.connect(self.forgetPreset.emit)
                self.list.addWidget(item)

        self.list.addStretch(1)
