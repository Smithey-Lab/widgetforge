"""The output drawer: the four compiled fields, in paste order.

Tab order is deliberate and matches the paste panel. CSS is first because it is
the field ServiceNow is most likely to reject and it fails fastest, so a bad
build is discovered before effort goes into the other three.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)


# (build key, tab label, file extension)
PASTE_ORDER = [
    ('css', 'CSS', 'css'),
    ('template', 'HTML template', 'html'),
    ('client', 'Client controller', 'js'),
    ('server', 'Server script', 'js'),
]


class OutputDrawer(QWidget):
    """Four read-only panes plus copy and hide."""

    copyRequested = Signal(str)     # build key
    toggled = Signal(bool)          # True when hidden

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Drawer')
        self.build = None
        self.hidden_state = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 0)
        row.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.panes = {}
        mono = QFont()
        mono.setFamilies(['Cascadia Mono', 'JetBrains Mono', 'Consolas',
                          'DejaVu Sans Mono', 'monospace'])
        mono.setStyleHint(QFont.Monospace)
        for key, label, _ext in PASTE_ORDER:
            pane = QPlainTextEdit()
            pane.setObjectName('Pane')
            pane.setReadOnly(True)
            pane.setFont(mono)
            pane.setLineWrapMode(QPlainTextEdit.NoWrap)
            pane.setPlaceholderText('Add a card and this fills in.')
            self.panes[key] = pane
            self.tabs.addTab(pane, label)

        self.meta = QLabel('')
        self.meta.setObjectName('Hud')
        self.copy = QPushButton('Copy pane')
        self.copy.setProperty('flavour', 'ghost')
        self.copy.clicked.connect(self._copy)
        self.hide_btn = QPushButton('Hide')
        self.hide_btn.setProperty('flavour', 'ghost')
        self.hide_btn.clicked.connect(self.toggle)

        row.addWidget(self.meta, 1)
        row.addWidget(self.copy)
        row.addWidget(self.hide_btn)

        self.tabs.setCornerWidget(bar, Qt.TopRightCorner)
        outer.addWidget(self.tabs, 1)

        self.tabs.currentChanged.connect(self._sync_meta)
        self.setMinimumHeight(46)

    def current_key(self):
        idx = self.tabs.currentIndex()
        return PASTE_ORDER[idx][0] if 0 <= idx < len(PASTE_ORDER) else 'css'

    def _copy(self):
        self.copyRequested.emit(self.current_key())

    def set_build(self, build, error=''):
        self.build = build
        for key, _label, _ext in PASTE_ORDER:
            pane = self.panes[key]
            if error:
                pane.setPlainText(error)
                pane.setObjectName('PaneBad')
            else:
                pane.setPlainText((build or {}).get(key, '') if build else '')
                pane.setObjectName('Pane')
            pane.style().unpolish(pane)
            pane.style().polish(pane)
        self._sync_meta()

    def _sync_meta(self):
        if not self.build:
            self.meta.setText('')
            return
        text = self.build.get(self.current_key(), '') or ''
        lines = text.count('\n') + 1 if text else 0
        self.meta.setText('%s lines · %.1f KB' % (lines, len(text.encode('utf-8')) / 1024.0))

    def toggle(self):
        self.hidden_state = not self.hidden_state
        # Nothing is hidden here. The window collapses the splitter to the
        # height of the tab row, which leaves the tabs and this button reachable
        # - hiding the tab widget would hide the way back.
        self.hide_btn.setText('Show' if self.hidden_state else 'Hide')
        self.toggled.emit(self.hidden_state)

    def set_hidden(self, hidden):
        if hidden != self.hidden_state:
            self.toggle()
