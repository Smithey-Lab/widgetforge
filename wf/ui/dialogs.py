"""Modal dialogs: board settings, shortcuts, the paste panel, update set."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .output import PASTE_ORDER


def _note(text):
    lbl = QLabel(text)
    lbl.setObjectName('ModalNote')
    lbl.setWordWrap(True)
    return lbl


def _field_label(text):
    lbl = QLabel(text)
    lbl.setObjectName('FieldLabel')
    return lbl


class BoardSettingsDialog(QDialog):
    """Default table, base filter and the compiled board's own theme."""

    def __init__(self, board, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Board settings')
        self.setMinimumWidth(460)
        defaults = board.get('defaults') or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        layout.addWidget(_field_label('Default table'))
        self.table = QLineEdit(str(defaults.get('table') or ''))
        self.table.setPlaceholderText('sn_si_incident')
        self.table.setProperty('mono', '1')
        layout.addWidget(self.table)

        layout.addWidget(_field_label('Base filter'))
        self.filter = QLineEdit(str(defaults.get('filter') or ''))
        self.filter.setPlaceholderText('active=true')
        self.filter.setProperty('mono', '1')
        layout.addWidget(self.filter)

        layout.addWidget(_note(
            'Cards with no table of their own use the default. The base filter is ANDed in '
            'front of every card filter, so a card asking for priority=1 on a board based on '
            'active=true queries active=true^priority=1.'))

        self.clear = QCheckBox('Clear the table on existing cards so they inherit')
        layout.addWidget(self.clear)

        layout.addWidget(_field_label('Board appearance'))
        self.theme = QComboBox()
        self.theme.addItem('Dark', 'dark')
        self.theme.addItem('Light', 'light')
        self.theme.setCurrentIndex(1 if str(board.get('theme')) == 'light' else 0)
        layout.addWidget(self.theme)
        layout.addWidget(_note('How the compiled dashboard looks in the portal. '
                               'Separate from the builder theme.'))

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        apply_ = buttons.addButton('Apply', QDialogButtonBox.AcceptRole)
        apply_.setProperty('flavour', 'go')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            'table': self.table.text().strip(),
            'filter': self.filter.text().strip(),
            'theme': self.theme.currentData(),
            'clear_tables': self.clear.isChecked(),
        }


class ShortcutsDialog(QDialog):
    ROWS = [
        ('Drag from the palette', 'Place a card exactly where you want it'),
        ('Click a palette card', 'Drop it in the first free spot'),
        ('Shift-click', 'Add a card to the selection'),
        ('Drag a selection', 'Move every selected card together'),
        ('Drag the corner grip', 'Resize a card'),
        ('Arrow keys', 'Nudge the selection one grid cell'),
        ('Delete', 'Remove everything selected that is not locked'),
        ('Esc', 'Clear the selection'),
        ('Ctrl+Z', 'Undo'),
        ('Ctrl+Shift+Z or Ctrl+Y', 'Redo'),
        ('Ctrl+D', 'Duplicate the selected card'),
        ('Ctrl+N', 'New board'),
        ('Ctrl+O', 'Open a saved board'),
        ('Ctrl+S', 'Save the board'),
        ('Ctrl+Shift+S', 'Save the board under a new name'),
        ('Ctrl+E', 'Copy for ServiceNow'),
        ('Ctrl+R', 'Reload card types from disk'),
        ('Ctrl+T', 'Switch between the light and dark app theme'),
        ('Ctrl+`', 'Show or hide the output drawer'),
        ('F1', 'This list'),
        ('Ctrl+Q', 'Quit'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Shortcuts')
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        for i, (keys, what) in enumerate(self.ROWS):
            k = QLabel(keys)
            k.setStyleSheet('font-weight: 600;')
            grid.addWidget(k, i, 0, Qt.AlignLeft | Qt.AlignTop)
            v = QLabel(what)
            v.setObjectName('ModalNote')
            v.setWordWrap(True)
            grid.addWidget(v, i, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class UpdateSetDialog(QDialog):
    """Widget name and optional sys_id for the update-set export."""

    def __init__(self, default_name, last_sys_id='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export Update Set')
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        layout.addWidget(_field_label('Widget name in ServiceNow'))
        self.name = QLineEdit(default_name or 'WidgetForge Board')
        layout.addWidget(self.name)

        layout.addWidget(_field_label('Existing widget sys_id'))
        self.sys_id = QLineEdit(last_sys_id or '')
        self.sys_id.setPlaceholderText('leave blank to create a new widget')
        self.sys_id.setProperty('mono', '1')
        layout.addWidget(self.sys_id)

        layout.addWidget(_note(
            'Import the file under Retrieved Update Sets, preview it, then commit. '
            'Filling in the sys_id updates that exact widget; leaving it blank creates '
            'a new one.'))

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        go = buttons.addButton('Export', QDialogButtonBox.AcceptRole)
        go.setProperty('flavour', 'go')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return self.name.text().strip(), self.sys_id.text().strip()


class PasteDialog(QDialog):
    """The four fields with copy and save buttons, ticking off as you go."""

    def __init__(self, build, on_copy, on_save, on_save_all, parent=None, done=None):
        super().__init__(parent)
        self.setWindowTitle('Copy for ServiceNow')
        self.setMinimumWidth(560)
        self.build = build
        self.on_copy = on_copy
        self.on_save = on_save
        # Ticks carry over from the last time the panel was open. Closing it to
        # go and paste into ServiceNow is the normal way to use it, and losing
        # your place every time you come back defeats the point of ticks.
        self.done_keys = set(done or ())
        self._rows = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        layout.addWidget(_note(
            'Open the widget record in ServiceNow and paste these four fields in this '
            'order. CSS first: it is the field most likely to be rejected and it fails '
            'fastest.'))

        for i, (key, label, _ext) in enumerate(PASTE_ORDER):
            layout.addWidget(self._row(i, key, label))
        self._paint()

        layout.addWidget(_note(
            'Use a scratch widget the first time. Never paste over one you care about '
            'until you have seen this board render.'))

        line = QFrame()
        line.setObjectName('Divider')
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        foot = QHBoxLayout()
        reset = QPushButton('Reset ticks')
        reset.setProperty('flavour', 'ghost')
        reset.clicked.connect(self._reset)
        save_all = QPushButton('Save all four')
        save_all.setProperty('flavour', 'go')
        save_all.clicked.connect(lambda: on_save_all(self))
        close = QPushButton('Close')
        close.setProperty('flavour', 'ghost')
        close.clicked.connect(self.accept)
        foot.addWidget(reset)
        foot.addStretch(1)
        foot.addWidget(close)
        foot.addWidget(save_all)
        layout.addLayout(foot)

    def _row(self, index, key, label):
        text = (self.build or {}).get(key, '') or ''
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        tick = QLabel(str(index + 1))
        tick.setObjectName('FieldLabel')
        tick.setFixedWidth(16)
        tick.setAlignment(Qt.AlignCenter)

        name = QLabel(label)
        meta = QLabel('%d lines · %.1f KB'
                      % (text.count('\n') + 1 if text else 0,
                         len(text.encode('utf-8')) / 1024.0))
        meta.setObjectName('FieldHelp')

        stack = QVBoxLayout()
        stack.setSpacing(0)
        stack.addWidget(name)
        stack.addWidget(meta)

        save = QPushButton('Save')
        save.setProperty('flavour', 'ghost')
        save.clicked.connect(lambda _=False, k=key: self._did(k, self.on_save(k, self)))
        copy = QPushButton('Copy')
        copy.clicked.connect(lambda _=False, k=key: self._did(k, self.on_copy(k)))

        row.addWidget(tick)
        row.addLayout(stack, 1)
        row.addWidget(save)
        row.addWidget(copy)
        self._rows[key] = (tick, index)
        return wrap

    def _did(self, key, ok):
        if ok is False:
            return
        self.done_keys.add(key)
        self._paint()

    def mark_all(self):
        self.done_keys = set(k for k, _l, _e in PASTE_ORDER)
        self._paint()

    def _reset(self):
        self.done_keys = set()
        self._paint()

    def _paint(self):
        for key, (tick, index) in self._rows.items():
            done = key in self.done_keys
            tick.setText('✓' if done else str(index + 1))
            tick.setObjectName('StatusOk' if done else 'FieldLabel')
            tick.style().unpolish(tick)
            tick.style().polish(tick)
