"""The encoded-query condition builder.

Two modes, and which one you get is not a preference:

  rows  the query parses and rebuilds byte for byte, so it is safe to show as
        editable conditions.
  raw   it does not, so it stays a plain text box with a note saying nothing
        was changed.

The widget keeps its own list of rows while you edit. It cannot re-derive them
from the query string on every keystroke, because `build_query` drops rows that
are not filled in yet - re-deriving would delete the blank row the moment you
added it.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ..query import COND_OPS, DATE_HINTS, DATE_OPS, NO_VALUE, Row, build_query, cond_safe


def _ghost(text, tip=''):
    b = QPushButton(text)
    b.setProperty('flavour', 'ghost')
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    return b


class CondRow(QWidget):
    """One condition: [and/or] field  operator  value  ×"""

    changed = Signal()
    removed = Signal(object)

    def __init__(self, row, first, parent=None):
        super().__init__(parent)
        self.setObjectName('CondRow')
        self.row = row
        self.first = first

        outer = QVBoxLayout(self)
        outer.setContentsMargins(7, 5, 7, 6)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        if not first:
            tag = QLabel('or' if row.join == 'OR' else 'and')
            tag.setObjectName('JoinTagOr' if row.join == 'OR' else 'JoinTag')
            tag.setFixedWidth(22)
            top.addWidget(tag)
        self.field = QLineEdit(row.field)
        self.field.setPlaceholderText('field name')
        self.field.setProperty('mono', '1')
        self.field.textChanged.connect(self._commit)
        top.addWidget(self.field, 1)
        x = QPushButton('×')
        x.setProperty('flavour', 'ghost')
        x.setFixedWidth(24)
        x.setToolTip('Remove this condition')
        x.clicked.connect(lambda: self.removed.emit(self))
        top.addWidget(x)
        outer.addLayout(top)

        bot = QHBoxLayout()
        bot.setSpacing(6)
        self.op = QComboBox()
        for code, label in COND_OPS:
            self.op.addItem(label, code)
        idx = self.op.findData(row.op)
        self.op.setCurrentIndex(idx if idx >= 0 else 0)
        self.op.currentIndexChanged.connect(self._op_changed)
        bot.addWidget(self.op)
        self.value = QLineEdit(row.value)
        self.value.setPlaceholderText('value')
        self.value.setProperty('mono', '1')
        self.value.textChanged.connect(self._commit)
        bot.addWidget(self.value, 1)
        outer.addLayout(bot)

        self._sync_value_box()

    def _sync_value_box(self):
        code = self.op.currentData()
        self.value.setVisible(code not in NO_VALUE)
        if code in DATE_OPS:
            comp = QCompleter(DATE_HINTS, self.value)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            comp.setFilterMode(Qt.MatchContains)
            self.value.setCompleter(comp)
        else:
            self.value.setCompleter(None)

    def _op_changed(self):
        self._sync_value_box()
        self._commit()

    def _commit(self):
        self.row.field = self.field.text().strip()
        self.row.op = self.op.currentData()
        self.row.value = '' if self.row.op in NO_VALUE else self.value.text()
        self.changed.emit()

    def focus_field(self):
        self.field.setFocus()


class ConditionEditor(QWidget):
    """Rows or raw text, with the round-trip guard deciding which."""

    changed = Signal(str)
    aboutToRemoveRow = Signal()

    # Above this many conditions the row editor stops being an editor and
    # starts being a stall - 5000 rows took fourteen seconds to build. A filter
    # that long is machine-generated and is better handled as text anyway.
    MAX_ROWS = 40

    def __init__(self, value='', parent=None):
        super().__init__(parent)
        self.value = value or ''
        self.rows = []
        self.mode = 'rows'
        self._building = False

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(5)
        self.rebuild()

    # -- construction ------------------------------------------------------

    def _clear(self):
        while self.outer.count():
            item = self.outer.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def _drop_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def rebuild(self, force_mode=None):
        self._building = True
        self._clear()
        parsed = cond_safe(self.value)
        self.too_long = parsed is not None and len(parsed) > self.MAX_ROWS
        if self.too_long:
            parsed = None
        mode = force_mode or ('raw' if parsed is None else 'rows')
        self.mode = mode

        if mode == 'raw':
            self._build_raw(parsed is not None)
        else:
            self.rows = parsed if parsed is not None else []
            self._build_rows()
        self._building = False

    def _build_raw(self, convertible):
        box = QLineEdit(self.value)
        box.setProperty('mono', '1')
        box.setPlaceholderText('encoded query, e.g. active=true^priority=1')
        box.textChanged.connect(self._raw_changed)
        self.outer.addWidget(box)
        self._raw_box = box

        if self.too_long:
            warn = QLabel('This filter has more than %d conditions, so it is shown as text. '
                          'Nothing has been changed.' % self.MAX_ROWS)
            warn.setObjectName('CondWarn')
            warn.setWordWrap(True)
            self.outer.addWidget(warn)
        elif self.value and not convertible:
            warn = QLabel('This filter uses syntax the visual editor would not rebuild '
                          'exactly, so it is left as text. Nothing has been changed.')
            warn.setObjectName('CondWarn')
            warn.setWordWrap(True)
            self.outer.addWidget(warn)

        acts = QHBoxLayout()
        acts.setSpacing(6)
        back = _ghost('Back to conditions')
        back.setEnabled(convertible and not self.too_long)
        if self.too_long:
            back.setToolTip('Too many conditions to edit one by one.')
        elif not convertible:
            back.setToolTip('This filter cannot be shown as conditions without changing it.')
        back.clicked.connect(self._to_rows)
        acts.addWidget(back)
        acts.addStretch(1)
        self.outer.addLayout(acts)

    def _build_rows(self):
        for i, r in enumerate(self.rows):
            w = CondRow(r, i == 0)
            w.changed.connect(self._rows_changed)
            w.removed.connect(self._remove_row)
            self.outer.addWidget(w)

        acts = QHBoxLayout()
        acts.setSpacing(6)
        add_and = _ghost('+ and', 'Add a condition that must also match')
        add_and.clicked.connect(lambda: self._add_row('AND'))
        add_or = _ghost('+ or', 'Add an alternative condition')
        add_or.clicked.connect(lambda: self._add_row('OR'))
        raw = _ghost('Edit as text', 'Type the encoded query directly')
        raw.clicked.connect(self._to_raw)
        acts.addWidget(add_and)
        acts.addWidget(add_or)
        acts.addWidget(raw)
        acts.addStretch(1)
        self.outer.addLayout(acts)

        self.out = QLabel()
        self.out.setWordWrap(True)
        self.out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.outer.addWidget(self.out)
        self._paint_out()

    def _paint_out(self):
        q = build_query(self.rows)
        self.out.setText(q or 'no filter — matches every record')
        self.out.setObjectName('CondOut' if q else 'CondOutEmpty')
        self.out.style().unpolish(self.out)
        self.out.style().polish(self.out)

    # -- edits -------------------------------------------------------------

    def _emit(self, q):
        self.value = q
        self.changed.emit(q)

    def _raw_changed(self, text):
        if self._building:
            return
        self._emit(text)

    def _rows_changed(self):
        if self._building:
            return
        self._paint_out()
        self._emit(build_query(self.rows))

    def _add_row(self, join):
        self.rows.append(Row(join, '', '=', ''))
        self._building = True
        self._clear()
        self._build_rows()
        self._building = False
        # focus the row just added
        widgets = [self.outer.itemAt(i).widget() for i in range(self.outer.count())]
        rows = [w for w in widgets if isinstance(w, CondRow)]
        if rows:
            rows[-1].focus_field()
        self._emit(build_query(self.rows))

    def _remove_row(self, widget):
        try:
            self.rows.remove(widget.row)
        except ValueError:
            return
        self.aboutToRemoveRow.emit()
        self._building = True
        self._clear()
        self._build_rows()
        self._building = False
        self._emit(build_query(self.rows))

    def _to_raw(self):
        self.rebuild(force_mode='raw')

    def _to_rows(self):
        rows = cond_safe(self.value)
        if rows is None or len(rows) > self.MAX_ROWS:
            return
        self.rebuild(force_mode='rows')

    # -- external ----------------------------------------------------------

    def set_value(self, value):
        """Replace the query, e.g. when a different card is selected."""
        if value == self.value:
            return
        self.value = value or ''
        self.rebuild()
