"""The settings rail: card actions, then one editor per module field.

The field list is built from `module.json`, so a new card type gets a working
inspector with no code here. Field types map as follows:

  text      QLineEdit
  number    QLineEdit with a numeric validator, deliberately not a spin box -
            the compiler's normalise() already falls back to the default for
            anything unparseable, and a spin box cannot express "left blank",
            which would change what gets written into saved boards.
  select    QComboBox
  toggle    QCheckBox
  textarea  QPlainTextEdit
  list      QPlainTextEdit, one entry per line
  pairs     QPlainTextEdit, "Label | value" per line
  query     ConditionEditor

`showIf` hides a field, and a hidden field is omitted from the compiled output
rather than carried through stale - that rule lives in the compiler; here it
only decides what is drawn.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .condition import ConditionEditor

ALIGNMENTS = [
    ('left', 'Align left'), ('right', 'Align right'),
    ('top', 'Align top'), ('bottom', 'Align bottom'),
    ('width', 'Same width'), ('height', 'Same height'),
    ('spread', 'Spread across'),
]


def _ghost(text, flavour='ghost'):
    b = QPushButton(text)
    b.setProperty('flavour', flavour)
    b.setCursor(Qt.PointingHandCursor)
    return b


def field_visible(field, settings):
    cond = field.get('showIf')
    if not cond:
        return True
    for key, allowed in cond.items():
        if str(settings.get(key, '')) not in [str(a) for a in allowed]:
            return False
    return True


def gating_keys(meta):
    """Field keys that other fields' visibility depends on."""
    keys = set()
    for f in meta.get('fields', []):
        for k in (f.get('showIf') or {}):
            keys.add(k)
    return keys


class InspectorRail(QWidget):
    """Everything about the current selection."""

    settingsChanged = Signal()          # recompile
    structureChanged = Signal()         # recompile and repaint the canvas
    action = Signal(str)                # 'dup' | 'lock' | 'del' | 'preset'
    alignRequested = Signal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setObjectName('InspectRail')
        self.model = model
        self.mods = {}
        self.card_id = None
        self.selection_count = 0
        self._editors = {}
        self._building = False
        self._pos_label = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.head = QLabel('Settings')
        self.head.setObjectName('RailHead')
        outer.addWidget(self.head)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.form = QVBoxLayout(self.body)
        self.form.setContentsMargins(10, 4, 10, 12)
        self.form.setSpacing(8)
        self.area.setWidget(self.body)
        outer.addWidget(self.area, 1)

        self.setMinimumWidth(268)
        self.setMaximumWidth(420)
        self.rebuild()

    def set_modules(self, mods):
        self.mods = mods

    def show_card(self, card_id, selection_count):
        """Point the rail at a card, rebuilding only if it actually changed.

        This is called after every board change, including every keystroke in a
        field that also affects the canvas. Rebuilding unconditionally
        destroyed and recreated the very widget being typed into, so the caret
        vanished after the first character. Same card, same selection size means
        the form on screen is already the right form - only the position line
        can have gone stale, and that is one label.
        """
        if card_id == self.card_id and selection_count == self.selection_count:
            self.sync_position()
            return
        self.card_id = card_id
        self.selection_count = selection_count
        self.rebuild()

    def sync_position(self):
        """Refresh the x/y/size readout without touching any editor."""
        card = self.model.card(self.card_id) if self.card_id else None
        if card and self._pos_label is not None:
            try:
                self._pos_label.setText(self._position_text(card))
            except RuntimeError:
                # The label was deleted by a rebuild racing this call.
                self._pos_label = None

    @staticmethod
    def _position_text(card):
        return ('x%d y%d \u00b7 %d\u00d7%d \u00b7 id %s'
                % (card['x'], card['y'], card['w'], card['h'], card['id']))

    # -- construction ------------------------------------------------------

    def _clear(self):
        self._editors = {}
        while self.form.count():
            item = self.form.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop(item.layout())

    def _drop(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop(item.layout())

    def rebuild(self):
        try:
            self._rebuild()
        finally:
            # _building gates every editor callback. If a rebuild raises with
            # it still set, the rail keeps drawing but silently swallows every
            # subsequent edit - a far worse failure than the original error.
            self._building = False

    def _rebuild(self):
        self._building = True
        self._pos_label = None
        self._clear()
        card = self.model.card(self.card_id) if self.card_id else None

        if not card:
            self.head.setText('Settings')
            none = QLabel('Select a card to edit it.')
            none.setObjectName('InspectNone')
            none.setWordWrap(True)
            self.form.addWidget(none)
            self.form.addStretch(1)
            return

        meta = self.mods.get(card['moduleId'])
        self.head.setText(meta['name'] if meta else card['moduleId'])

        if self.selection_count > 1:
            multi = QLabel('%d cards selected' % self.selection_count)
            multi.setObjectName('FieldLabel')
            self.form.addWidget(multi)
            grid = QGridLayout()
            grid.setSpacing(5)
            for i, (how, label) in enumerate(ALIGNMENTS):
                b = _ghost(label)
                b.clicked.connect(lambda _=False, h=how: self.alignRequested.emit(h))
                grid.addWidget(b, i // 2, i % 2)
            self.form.addLayout(grid)
            self.form.addWidget(self._divider())

        acts = QHBoxLayout()
        acts.setSpacing(5)
        dup = _ghost('Duplicate')
        dup.clicked.connect(lambda: self.action.emit('dup'))
        lock = _ghost('Unlock' if card.get('locked') else 'Lock')
        lock.clicked.connect(lambda: self.action.emit('lock'))
        dele = _ghost('Delete', 'danger')
        dele.clicked.connect(lambda: self.action.emit('del'))
        acts.addWidget(dup)
        acts.addWidget(lock)
        acts.addWidget(dele)
        self.form.addLayout(acts)

        preset = _ghost('Save as preset')
        preset.clicked.connect(lambda: self.action.emit('preset'))
        self.form.addWidget(preset)

        pos = QLabel(self._position_text(card))
        pos.setObjectName('FieldHelp')
        pos.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._pos_label = pos
        self.form.addWidget(pos)
        self.form.addWidget(self._divider())

        if not meta:
            warn = QLabel('This board uses a card type "%s" that is not installed, so its '
                          'settings cannot be edited here. The build will fail until the '
                          'module folder is restored or the card is deleted.'
                          % card['moduleId'])
            warn.setObjectName('CondWarn')
            warn.setWordWrap(True)
            self.form.addWidget(warn)
            self.form.addStretch(1)
            return

        settings = card.setdefault('settings', {})
        for f in meta.get('fields', []):
            if not field_visible(f, settings):
                continue
            self._add_field(f, settings)

        self.form.addStretch(1)

    def _divider(self):
        line = QFrame()
        line.setObjectName('Divider')
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        return line

    def _add_field(self, f, settings):
        key = f['key']
        ftype = f['type']
        value = settings.get(key, f.get('default'))

        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)

        if ftype == 'toggle':
            box = QCheckBox(f.get('label', key))
            box.setChecked(bool(value) and value not in ('false', 'False'))
            box.toggled.connect(lambda on, k=key: self._set(k, on))
            col.addWidget(box)
            editor = box
        else:
            label = QLabel(f.get('label', key) + (' *' if f.get('required') else ''))
            label.setObjectName('FieldLabel')
            col.addWidget(label)

            if ftype == 'select':
                editor = QComboBox()
                for opt in f.get('options', []):
                    editor.addItem(str(opt[1]), str(opt[0]))
                idx = editor.findData('' if value is None else str(value))
                editor.setCurrentIndex(idx if idx >= 0 else 0)
                editor.currentIndexChanged.connect(
                    lambda _i, k=key, e=editor: self._set(k, e.currentData()))
            elif ftype == 'query':
                editor = ConditionEditor('' if value is None else str(value))
                editor.changed.connect(lambda q, k=key: self._set(k, q))
                # Removing a condition is destructive in a way that typing is
                # not, so it gets its own undo step, as it did in the web build.
                editor.aboutToRemoveRow.connect(self.model.begin)
            elif ftype in ('textarea', 'pairs', 'list'):
                editor = QPlainTextEdit(_as_text(value))
                editor.setProperty('mono', '1' if ftype in ('pairs', 'list') else '0')
                editor.setFixedHeight(74)
                editor.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                editor.textChanged.connect(
                    lambda k=key, e=editor: self._set(k, e.toPlainText()))
            elif ftype == 'number':
                editor = QLineEdit('' if value is None else str(value))
                editor.setValidator(QDoubleValidator(editor))
                editor.textChanged.connect(lambda text, k=key: self._set(k, text))
            else:
                editor = QLineEdit('' if value is None else str(value))
                if key == 'table':
                    editor.setProperty('mono', '1')
                    base = ((self.model.board.get('defaults') or {}).get('table') or '').strip()
                    if base:
                        editor.setPlaceholderText('%s (from the board)' % base)
                editor.textChanged.connect(lambda text, k=key: self._set(k, text))

            col.addWidget(editor)

        if f.get('help'):
            help_ = QLabel(f['help'])
            help_.setObjectName('FieldHelp')
            help_.setWordWrap(True)
            col.addWidget(help_)

        self._editors[key] = editor
        self.form.addWidget(wrap)

    # -- edits -------------------------------------------------------------

    def _set(self, key, value):
        if self._building:
            return
        card = self.model.card(self.card_id)
        if not card:
            return
        card.setdefault('settings', {})[key] = value
        meta = self.mods.get(card['moduleId'])

        if meta and key in gating_keys(meta):
            # A field that gates others changed, so the visible set may differ.
            # Rebuild, then hand focus back to whatever was being edited.
            self.rebuild()
            editor = self._editors.get(key)
            if editor is not None:
                editor.setFocus()
            self.structureChanged.emit()
            return

        if key in ('title', 'table', 'groupBy', 'filter', 'dateField', 'days', 'text', 'body'):
            # These appear in the card's summary line on the canvas, so the
            # canvas has to repaint. It does not mean rebuilding this rail.
            self.structureChanged.emit()
        else:
            self.settingsChanged.emit()


def _as_text(value):
    if value is None:
        return ''
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                out.append('%s | %s' % (item.get('label', ''), item.get('value', '')))
            else:
                out.append(str(item))
        return '\n'.join(out)
    return str(value)
