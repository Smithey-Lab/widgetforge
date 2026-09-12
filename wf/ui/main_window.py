"""The main window: assembles the rails, canvas and drawer, and owns the board.

Compilation happens in-process on a short debounce. There is no server, no
port and no HTTP; the same `compile_board` the test suite exercises is called
directly, and a BuildError becomes a message rather than a 400.
"""

import copy
import json
import os
import traceback

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QGuiApplication, QKeySequence, QPainter,
                           QPalette, QPixmap)
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from .. import boards as boardstore
from .. import compiler
from ..model import BoardModel
from . import icons
from .canvas import GridCanvas, Ruler
from .dialogs import BoardSettingsDialog, PasteDialog, ShortcutsDialog, UpdateSetDialog
from .inspector import InspectorRail
from .output import PASTE_ORDER, OutputDrawer
from .palette import PaletteRail
from .theme import stylesheet, tokens

COMPILE_DELAY_MS = 240
STATUS_CLEAR_MS = 6000


def _system_theme():
    """'dark' or 'light', following the desktop where it says.

    Qt 6.5 added a real colour-scheme hint; older builds and desktops that do
    not publish one fall back to reading the window-text-on-window contrast out
    of the palette, which is how everyone did this before the hint existed.
    """
    app = QGuiApplication.instance()
    if app is not None:
        hints = app.styleHints()
        scheme = getattr(hints, 'colorScheme', None)
        if scheme is not None:
            try:
                value = scheme()
                name = str(getattr(value, 'name', value)).lower()
                if 'dark' in name:
                    return 'dark'
                if 'light' in name:
                    return 'light'
            except (TypeError, RuntimeError):
                pass
        palette = app.palette()
        window = palette.color(QPalette.ColorRole.Window)
        if window.isValid():
            return 'dark' if window.lightness() < 128 else 'light'
    return 'dark'


def _button(text, flavour=None, tip=''):
    b = QPushButton(text)
    if flavour:
        b.setProperty('flavour', flavour)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class MainWindow(QMainWindow):

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.theme = state.get('theme') or _system_theme()
        self.mods = {}
        self.meta = {}
        self.last_build = None
        self.last_error = ''
        self.last_sys_id = state.get('lastSysId', '') or ''
        self.current_file = None
        # Which of the four fields have been copied or saved this session.
        # Closing the panel is not the same as starting the paste again.
        self.pasted = set()

        self.model = BoardModel(self._initial_board())

        self.setWindowTitle('WidgetForge')
        self.setMinimumSize(940, 600)
        self._size_to_screen()

        self._build_ui()
        self._build_menus()
        self._apply_theme(self.theme)
        self._load_modules(initial=True)
        self._restore_geometry()

        self.compile_timer = QTimer(self)
        self.compile_timer.setSingleShot(True)
        self.compile_timer.timeout.connect(self.compile_now)

        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(lambda: self.set_status('', ''))

        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.timeout.connect(self._save_draft)

        self.refresh(structural=True)
        self.refresh_board_list()

    # ------------------------------------------------------------------ ui

    def _initial_board(self):
        draft = self.state.get('draft')
        if isinstance(draft, dict):
            return draft
        return {'title': '', 'subtitle': '', 'cards': []}

    def _report_repairs(self, repairs, where):
        """Say what sanitise_board had to change, rather than changing it quietly."""
        if not repairs:
            return
        head = '%s needed %d repair%s to open.' % (where, len(repairs),
                                                   '' if len(repairs) == 1 else 's')
        QMessageBox.warning(self, 'Board repaired',
                            head + '\n\n- ' + '\n- '.join(repairs[:12])
                            + ('\n\n(and %d more)' % (len(repairs) - 12)
                               if len(repairs) > 12 else '')
                            + '\n\nNothing has been saved yet. Save the board to keep '
                              'the repaired version, or close it to keep the original.')
        self.set_status('%s opened with %d repair%s' % (where, len(repairs),
                                                        '' if len(repairs) == 1 else 's'),
                        'bad', sticky=True)

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._top_bar())

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(1)

        self.palette_rail = PaletteRail()
        self.palette_rail.place.connect(self._place_from_palette)
        self.palette_rail.forgetPreset.connect(self._forget_preset)
        self.palette_rail.clearCanvas.connect(self.clear_canvas)
        self.palette_rail.importBoard.connect(self.import_json)
        self.split.addWidget(self.palette_rail)

        self.split.addWidget(self._stage())

        self.inspector = InspectorRail(self.model)
        self.inspector.settingsChanged.connect(lambda: self.refresh(structural=False))
        self.inspector.structureChanged.connect(lambda: self.refresh(structural=True))
        self.inspector.action.connect(self._card_action)
        self.inspector.alignRequested.connect(self._align)
        self.split.addWidget(self.inspector)

        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setStretchFactor(2, 0)
        self.split.setSizes([250, 900, 300])

        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.setChildrenCollapsible(False)
        self.vsplit.setHandleWidth(1)
        self.vsplit.addWidget(self.split)

        self.drawer = OutputDrawer()
        self.drawer.copyRequested.connect(self._copy_pane)
        self.drawer.toggled.connect(self._drawer_toggled)
        self.vsplit.addWidget(self.drawer)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setStretchFactor(1, 0)
        self.vsplit.setSizes([640, 240])

        root.addWidget(self.vsplit, 1)
        self.setCentralWidget(central)

        if self.state.get('drawerHidden'):
            self.drawer.set_hidden(True)

    def _top_bar(self):
        bar = QWidget()
        bar.setObjectName('TopBar')
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(6)

        self._optional_buttons = []
        self.brand = QLabel()
        self.brand.setFixedSize(30, 30)
        row.addWidget(self.brand)

        self.title_edit = QLineEdit(self.model.board.get('title', ''))
        self.title_edit.setObjectName('BoardTitle')
        self.title_edit.setPlaceholderText('Untitled board')
        self.title_edit.setMinimumWidth(90)
        self.title_edit.setMaximumWidth(220)
        self.title_edit.textChanged.connect(self._title_changed)
        row.addWidget(self.title_edit)

        self.sub_edit = QLineEdit(self.model.board.get('subtitle', ''))
        self.sub_edit.setObjectName('BoardSub')
        self.sub_edit.setPlaceholderText('subtitle')
        self.sub_edit.setMinimumWidth(70)
        self.sub_edit.setMaximumWidth(170)
        self.sub_edit.textChanged.connect(self._sub_changed)
        row.addWidget(self.sub_edit)

        row.addStretch(1)

        self.status = QLabel('')
        self.status.setObjectName('StatusPlain')
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        row.addWidget(self.status)

        self.board_picker = QComboBox()
        self.board_picker.setToolTip('Open a saved board')
        self.board_picker.setMinimumWidth(120)
        self.board_picker.activated.connect(self._picked_board)
        row.addWidget(self.board_picker)

        self.btn_undo = _button('', 'ghost', 'Undo (Ctrl+Z)')
        self.btn_undo.setFixedSize(30, 28)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = _button('', 'ghost', 'Redo (Ctrl+Shift+Z)')
        self.btn_redo.setFixedSize(30, 28)
        self.btn_redo.clicked.connect(self.redo)
        row.addWidget(self.btn_undo)
        row.addWidget(self.btn_redo)

        for text, flavour, slot, tip in [
            ('Board', 'ghost', self.board_settings, 'Default table, base filter, board theme'),
            ('Save', None, self.save_board, 'Save this board (Ctrl+S)'),
            ('Save as', 'ghost', self.save_board_as, 'Save under a new name (Ctrl+Shift+S)'),
            ('JSON', 'ghost', self.export_json, 'Write the board JSON to a file'),
            ('Update Set', None, self.export_update_set, 'Export an update set XML'),
            ('Copy for ServiceNow', 'go', self.open_paste_panel,
             'The four fields, in paste order (Ctrl+E)'),
        ]:
            b = _button(text, flavour, tip)
            b.clicked.connect(slot)
            row.addWidget(b)
            if text in ('Save as', 'JSON'):
                self._optional_buttons.append(b)

        help_btn = _button('?', 'ghost', 'Shortcuts (F1)')
        help_btn.setFixedSize(26, 28)
        help_btn.clicked.connect(self.show_shortcuts)
        row.addWidget(help_btn)

        self.btn_theme = _button('', 'ghost', 'Switch theme')
        self.btn_theme.setFixedSize(30, 28)
        self.btn_theme.clicked.connect(self.toggle_theme)
        row.addWidget(self.btn_theme)

        self.version = QLabel('')
        self.version.setObjectName('Version')
        row.addWidget(self.version)
        return bar

    def resizeEvent(self, event):
        """Shed the least useful things in the top bar before it overflows.

        Qt will happily clip the last widget in a row rather than wrap it, and
        the last widget here is the one action you press most - so the bar
        drops the subtitle first, then the two buttons that also live in the
        File menu, exactly as the web build's media queries did.
        """
        super().resizeEvent(event)
        width = self.width()
        if hasattr(self, 'sub_edit'):
            self.sub_edit.setVisible(width >= 1240)
        for button in getattr(self, '_optional_buttons', ()):
            button.setVisible(width >= 1120)

    def _stage(self):
        stage = QWidget()
        stage.setObjectName('Stage')
        col = QVBoxLayout(stage)
        col.setContentsMargins(10, 8, 10, 6)
        col.setSpacing(4)

        self.ruler = Ruler(self.model.cols)
        col.addWidget(self.ruler)

        self.canvas = GridCanvas(self.model)
        self.canvas.ruler = self.ruler
        self.canvas.selectionChanged.connect(self._selection_changed)
        self.canvas.boardChanged.connect(lambda: self.refresh(structural=True))
        self.canvas.liveMoved.connect(self._live_moved)
        self.canvas.hudChanged.connect(self._hud)
        self.canvas.statusMessage.connect(self.set_status)
        self.canvas.placeModule.connect(self._drop_module)
        self.canvas.placePreset.connect(self._drop_preset)
        col.addWidget(self.canvas, 1)

        foot = QWidget()
        frow = QHBoxLayout(foot)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.setSpacing(6)
        self.hud = QLabel('')
        self.hud.setObjectName('Hud')
        frow.addWidget(self.hud)
        frow.addStretch(1)
        self.issues = QWidget()
        self.issues_row = QHBoxLayout(self.issues)
        self.issues_row.setContentsMargins(0, 0, 0, 0)
        self.issues_row.setSpacing(5)
        frow.addWidget(self.issues)
        col.addWidget(foot)
        self._hud('')
        return stage

    def _build_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu('&File')
        self._act(file_menu, 'New board', 'Ctrl+N', self.new_board)
        self._act(file_menu, 'Open board…', 'Ctrl+O', self.open_board_dialog)
        self._act(file_menu, 'Save board', 'Ctrl+S', self.save_board)
        self._act(file_menu, 'Save board as…', 'Ctrl+Shift+S', self.save_board_as)
        file_menu.addSeparator()
        self._act(file_menu, 'Import board JSON…', None, self.import_json)
        self._act(file_menu, 'Export board JSON…', None, self.export_json)
        file_menu.addSeparator()
        self._act(file_menu, 'Copy for ServiceNow…', 'Ctrl+E', self.open_paste_panel)
        self._act(file_menu, 'Export Update Set…', None, self.export_update_set)
        file_menu.addSeparator()
        self._act(file_menu, 'Quit', 'Ctrl+Q', self.close)

        edit_menu = menubar.addMenu('&Edit')
        self.act_undo = self._act(edit_menu, 'Undo', QKeySequence.Undo, self.undo)
        self.act_redo = self._act(edit_menu, 'Redo', QKeySequence.Redo, self.redo)
        # QKeySequence.Redo is Ctrl+Y on Windows. Ctrl+Shift+Z is what the web
        # build used and what most people reach for, so bind both rather than
        # documenting one and shipping the other.
        self.act_redo.setShortcuts([QKeySequence(QKeySequence.Redo),
                                    QKeySequence('Ctrl+Shift+Z')])
        edit_menu.addSeparator()
        self._act(edit_menu, 'Duplicate card', 'Ctrl+D', lambda: self._card_action('dup'))
        self._act(edit_menu, 'Delete selection', QKeySequence.Delete, self.delete_selection)
        self._act(edit_menu, 'Clear canvas', None, self.clear_canvas)
        edit_menu.addSeparator()
        self._act(edit_menu, 'Board settings…', None, self.board_settings)

        view_menu = menubar.addMenu('&View')
        self._act(view_menu, 'Toggle theme', 'Ctrl+T', self.toggle_theme)
        self._act(view_menu, 'Show / hide output', 'Ctrl+`', self.drawer_toggle)
        self._act(view_menu, 'Reload card types', 'Ctrl+R', self.reload_modules)

        help_menu = menubar.addMenu('&Help')
        self._act(help_menu, 'Shortcuts', 'F1', self.show_shortcuts)
        self._act(help_menu, 'About WidgetForge', None, self.show_about)

        # Escape clears the selection wherever focus happens to be.
        esc = QAction(self)
        esc.setShortcut(QKeySequence(Qt.Key_Escape))
        esc.setShortcutContext(Qt.WindowShortcut)
        esc.triggered.connect(self.canvas.clear_selection)
        self.addAction(esc)

    def _act(self, menu, text, shortcut, slot):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut) if isinstance(shortcut, str) else shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # --------------------------------------------------------------- theme

    def _apply_theme(self, name):
        self.theme = name
        app = QApplication.instance()
        app.setStyleSheet(stylesheet(name))
        t = tokens(name)
        self.canvas.set_theme(name)
        self.ruler.set_theme(name)
        self.palette_rail.set_theme(name)
        self.btn_theme.setIcon(icons.icon('sun' if name == 'dark' else 'moon', 15, t['text']))
        self.btn_theme.setIconSize(QSize(15, 15))
        self.btn_theme.setToolTip('Switch to %s mode' % ('light' if name == 'dark' else 'dark'))
        for button, glyph in ((self.btn_undo, 'undo'), (self.btn_redo, 'redo')):
            button.setIcon(icons.icon(glyph, 15, t['text']))
            button.setIconSize(QSize(15, 15))
        self._paint_brand(t)
        self._paint_issues(self.last_build.get('warnings') if self.last_build else [],
                           self.last_error)

    def _paint_brand(self, t):
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(30 * dpr), int(30 * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(icons.tint(t['signal'], 0.18))
        p.drawRoundedRect(QRectF(0, 0, 30, 30), 8, 8)
        icons.draw(p, 'columns', QRectF(7, 7, 16, 16), t['signal'], 1.8)
        p.end()
        self.brand.setPixmap(pm)

    def toggle_theme(self):
        self._apply_theme('light' if self.theme == 'dark' else 'dark')
        self.state.set('theme', self.theme)

    # ------------------------------------------------------------- modules

    def _load_modules(self, initial=False):
        try:
            mods, _shell = compiler.load_cached()
        except compiler.BuildError as exc:
            self.mods = {}
            self.canvas.set_modules({})
            self.palette_rail.set_modules({})
            self.inspector.set_modules({})
            self.set_status('Card types could not be loaded: %s' % exc, 'bad')
            if initial:
                QMessageBox.critical(
                    self, 'WidgetForge',
                    'The card types in modules/ could not be loaded, so nothing can be '
                    'built until this is fixed.\n\n%s' % exc)
            return False
        self.mods = {mid: mods[mid]['meta'] for mid in mods}
        self.canvas.set_modules(self.mods)
        self.palette_rail.set_modules(self.mods)
        self.inspector.set_modules(self.mods)
        self.palette_rail.set_presets(self.state.get('presets', []))
        self.canvas.presets = self.state.get('presets', [])
        self.version.setText('v%s' % compiler.VERSION)
        return True

    def reload_modules(self):
        compiler.invalidate_cache()
        if self._load_modules():
            self.set_status('Reloaded %d card types' % len(self.mods), 'ok')
            self.inspector.rebuild()
            self.refresh(structural=True)

    # -------------------------------------------------------------- status

    def set_status(self, text, kind='', sticky=False):
        """Show a message. Transient ones fade; the compile readout does not.

        The compile line ("Compiles - 11 cards - 9 types") is a state
        indicator, not an event, and a board that has not changed for a minute
        is still compiling fine. Fading it out would say nothing about the
        board and everything about the clock.
        """
        self.status.setText(text or '')
        self.status.setObjectName({'ok': 'StatusOk', 'bad': 'StatusBad'}.get(kind, 'StatusPlain'))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
            if text and not sticky:
                self.status_timer.start(STATUS_CLEAR_MS)

    def _hud(self, text):
        if text:
            self.hud.setText(text)
        else:
            self.hud.setText('%d × %d grid · fills the screen, no scroll'
                             % (self.model.cols, self.model.rows))

    # ------------------------------------------------------------ refresh

    def refresh(self, structural=True):
        if structural:
            self.canvas.prune_selection()
            self.canvas.update()
            self.inspector.show_card(self.canvas.selected, len(self.canvas.selection()))
        self._sync_undo_actions()
        self.compile_timer.start(COMPILE_DELAY_MS)
        self.draft_timer.start(700)

    def _live_moved(self):
        self.inspector.show_card(self.canvas.selected, len(self.canvas.selection()))

    def _selection_changed(self):
        self.inspector.show_card(self.canvas.selected, len(self.canvas.selection()))

    def _sync_undo_actions(self):
        self.btn_undo.setEnabled(self.model.can_undo())
        self.btn_redo.setEnabled(self.model.can_redo())
        if hasattr(self, 'act_undo'):
            self.act_undo.setEnabled(self.model.can_undo())
            self.act_redo.setEnabled(self.model.can_redo())

    # ------------------------------------------------------------ compile

    def compile_now(self):
        if not self.model.cards:
            self.last_build = None
            self.last_error = ''
            self.drawer.set_build(None)
            self._paint_issues([], '')
            self.set_status('', '')
            return
        try:
            build = compiler.compile_board(self.model.board)
        except compiler.BuildError as exc:
            self.last_build = None
            self.last_error = str(exc)
            self.drawer.set_build(None, str(exc))
            self._paint_issues([], str(exc))
            self.set_status(str(exc), 'bad', sticky=True)
            return
        except Exception as exc:  # pragma: no cover - defensive
            detail = traceback.format_exc(limit=4)
            self.last_build = None
            self.last_error = 'Unexpected compiler failure: %s' % exc
            self.drawer.set_build(None, self.last_error + '\n\n' + detail)
            self._paint_issues([], self.last_error)
            self.set_status(self.last_error, 'bad')
            return

        self.last_build = build
        self.last_error = ''
        self.drawer.set_build(build)
        self._paint_issues(build.get('warnings') or [], '')
        self.set_status('Compiles · %d cards · %d types'
                        % (build['cards'], len(build['modules'])), 'ok', sticky=True)

    def _paint_issues(self, warnings, error):
        while self.issues_row.count():
            item = self.issues_row.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        entries = [error] if error else list(warnings or [])
        for text in entries[:4]:
            cid = self._card_named_in(text)
            btn = QPushButton(text if len(text) < 90 else text[:87] + '…')
            btn.setObjectName('IssueBad' if error else 'Issue')
            btn.setToolTip(text)
            if cid:
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _=False, c=cid: self._jump_to(c))
            else:
                btn.setEnabled(False)
            self.issues_row.addWidget(btn)
        if len(entries) > 4:
            more = QLabel('+%d more' % (len(entries) - 4))
            more.setObjectName('Hud')
            self.issues_row.addWidget(more)

    def _card_named_in(self, text):
        import re
        for match in re.findall(r'"([a-z0-9_-]+)"', text or ''):
            if self.model.card(match):
                return match
        return None

    def _jump_to(self, cid):
        self.canvas.select(cid)
        self.canvas.flash(cid)
        self.canvas.setFocus()

    # -------------------------------------------------------------- cards

    def _place_from_palette(self, kind, name):
        if kind == 'module':
            self._drop_module(name, None, None)
        else:
            self._drop_preset(name, None, None)

    def _drop_module(self, module_id, x, y):
        meta = self.mods.get(module_id)
        if not meta:
            self.set_status('That card type is not installed.', 'bad')
            return
        base = ((self.model.board.get('defaults') or {}).get('table') or '').strip()
        at = None if x is None else (x, y)
        card = self.model.add_card(module_id, meta, at, base)
        if not card:
            self.set_status('No room left for a %d×%d card. Shrink or remove one first.'
                            % (meta['size'][0], meta['size'][1]), 'bad')
            return
        self.canvas.select(card['id'])
        self.refresh(structural=True)

    def _drop_preset(self, name, x, y):
        preset = next((p for p in self.state.get('presets', []) if p['name'] == name), None)
        if not preset or preset['moduleId'] not in self.mods:
            self.set_status('That preset uses a card type this install does not have.', 'bad')
            return
        if x is None:
            card = self.model.add_preset(preset)
        else:
            if not self.model.fits(x, y, int(preset['w']), int(preset['h'])):
                self.set_status('That spot is taken or off the grid.', 'bad')
                return
            self.model.begin()
            from ..model import next_id
            card = {'id': next_id(self.model.cards, preset['moduleId']),
                    'moduleId': preset['moduleId'], 'x': x, 'y': y,
                    'w': int(preset['w']), 'h': int(preset['h']),
                    'settings': copy.deepcopy(preset.get('settings') or {})}
            self.model.cards.append(card)
        if not card:
            self.set_status('No room for that preset.', 'bad')
            return
        self.canvas.select(card['id'])
        self.refresh(structural=True)

    def _card_action(self, what):
        cid = self.canvas.selected
        card = self.model.card(cid) if cid else None
        if not card:
            self.set_status('Select a card first.', 'bad')
            return
        if what == 'dup':
            copy_ = self.model.duplicate(cid)
            if not copy_:
                self.set_status('No room left to duplicate that card.', 'bad')
                return
            self.canvas.select(copy_['id'])
        elif what == 'lock':
            self.model.begin()
            card['locked'] = not card.get('locked')
        elif what == 'del':
            if card.get('locked'):
                self.set_status('That card is locked. Unlock it first.', 'bad')
                return
            self.model.remove([cid])
            self.canvas.clear_selection()
        elif what == 'preset':
            self._save_preset(card)
            return
        self.refresh(structural=True)

    def delete_selection(self):
        ids = self.canvas.selection()
        if not ids:
            return
        gone = self.model.remove(ids)
        if not gone:
            self.set_status('Locked cards were not removed.', 'bad')
            return
        self.canvas.clear_selection()
        self.refresh(structural=True)

    def clear_canvas(self):
        if not self.model.cards:
            return
        if QMessageBox.question(
                self, 'Clear canvas',
                'Remove all %d cards from this board?' % len(self.model.cards),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.clear()
        self.canvas.clear_selection()
        self.refresh(structural=True)

    def _align(self, how):
        if self.model.align(self.canvas.selection(), how):
            self.refresh(structural=True)
        else:
            self.set_status('Shift-click a second unlocked card first.', 'bad')

    # ------------------------------------------------------------ presets

    def _save_preset(self, card):
        meta = self.mods.get(card['moduleId'])
        if not meta:
            self.set_status('That card type is not installed, so it cannot be saved.', 'bad')
            return
        suggested = (card.get('settings') or {}).get('title') or meta['name']
        name, ok = QInputDialog.getText(self, 'Save as preset', 'Name this preset',
                                        QLineEdit.Normal, str(suggested))
        name = (name or '').strip()
        if not ok or not name:
            return
        presets = [p for p in self.state.get('presets', []) if p.get('name') != name]
        presets.append({'name': name, 'moduleId': card['moduleId'],
                        'w': card['w'], 'h': card['h'],
                        'settings': copy.deepcopy(card.get('settings') or {})})
        self.state.set('presets', presets)
        self.palette_rail.set_presets(presets)
        self.canvas.presets = presets
        self.set_status('Saved the preset "%s"' % name, 'ok')

    def _forget_preset(self, name):
        presets = [p for p in self.state.get('presets', []) if p.get('name') != name]
        self.state.set('presets', presets)
        self.palette_rail.set_presets(presets)
        self.canvas.presets = presets

    # --------------------------------------------------------------- board

    def _title_changed(self, text):
        self.model.board['title'] = text
        self.refresh(structural=False)

    def _sub_changed(self, text):
        self.model.board['subtitle'] = text
        self.refresh(structural=False)

    def _sync_title_fields(self):
        self.title_edit.blockSignals(True)
        self.sub_edit.blockSignals(True)
        self.title_edit.setText(self.model.board.get('title', '') or '')
        self.sub_edit.setText(self.model.board.get('subtitle', '') or '')
        self.title_edit.setCursorPosition(0)
        self.sub_edit.setCursorPosition(0)
        self.title_edit.blockSignals(False)
        self.sub_edit.blockSignals(False)

    def board_settings(self):
        dlg = BoardSettingsDialog(self.model.board, self)
        if dlg.exec() != dlg.Accepted:
            return
        vals = dlg.values()
        self.model.begin()
        self.model.board['defaults'] = {'table': vals['table'], 'filter': vals['filter']}
        self.model.board['theme'] = vals['theme']
        if vals['table'] and vals['clear_tables']:
            for c in self.model.cards:
                if c.get('settings'):
                    c['settings'].pop('table', None)
        self.inspector.rebuild()
        self.refresh(structural=True)
        self.set_status('Board settings applied', 'ok')

    def new_board(self):
        if self.model.cards and QMessageBox.question(
                self, 'New board', 'Start a new board? The current one will be cleared '
                                   'from the canvas.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.replace({'title': '', 'subtitle': '', 'cards': []})
        self.canvas.clear_selection()
        self._sync_title_fields()
        self.current_file = None
        self.refresh(structural=True)

    def refresh_board_list(self):
        self.board_picker.blockSignals(True)
        self.board_picker.clear()
        self.board_picker.addItem('Open…', '')
        for title, filename in boardstore.list_boards():
            self.board_picker.addItem(title, title)
        self.board_picker.setCurrentIndex(0)
        self.board_picker.blockSignals(False)

    def _picked_board(self, index):
        name = self.board_picker.itemData(index)
        self.board_picker.setCurrentIndex(0)
        if name:
            self.open_board(name)

    def open_board_dialog(self):
        entries = boardstore.list_boards()
        if not entries:
            self.set_status('No saved boards yet.', 'bad')
            return
        titles = [t for t, _f in entries]
        name, ok = QInputDialog.getItem(self, 'Open board', 'Saved boards', titles, 0, False)
        if ok and name:
            self.open_board(name)

    def open_board(self, name):
        try:
            board = boardstore.load_board(name)
        except (OSError, ValueError, FileNotFoundError) as exc:
            self.set_status(str(exc), 'bad')
            return
        repairs = self.model.replace(board)
        self.canvas.clear_selection()
        self._sync_title_fields()
        self.inspector.rebuild()
        self.refresh(structural=True)
        if repairs:
            self._report_repairs(repairs, name)
        else:
            self.set_status('Opened %s' % name, 'ok')

    def save_board(self):
        title = (self.model.board.get('title') or '').strip()
        if not title:
            self.set_status('Give the board a name first', 'bad')
            self.title_edit.setFocus()
            return
        # Two different titles can slug to one filename ("Q1 Report!" and
        # "Q1 Report?"), and the second used to overwrite the first without a
        # word. Only ask when the file on disk holds a genuinely different
        # board - re-saving your own board must stay a single keystroke.
        path = boardstore.board_path(title)
        if os.path.isfile(path):
            try:
                existing = boardstore.load_board_file(path).get('title')
            except (OSError, ValueError):
                existing = None
            if existing and existing != title:
                answer = QMessageBox.question(
                    self, 'Overwrite board',
                    'A different board, "%s", is already saved under the file name '
                    '%s.\n\nSaving "%s" will replace it. Continue?'
                    % (existing, os.path.basename(path), title),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    return
        try:
            boardstore.save_board(title, self.model.board)
        except OSError as exc:
            self.set_status('Could not save: %s' % exc, 'bad')
            return
        self.refresh_board_list()
        self.set_status('Saved as %s' % title, 'ok')

    def save_board_as(self):
        current = self.model.board.get('title') or 'Board'
        name, ok = QInputDialog.getText(self, 'Save board as', 'Save this board as',
                                        QLineEdit.Normal, '%s copy' % current)
        name = (name or '').strip()
        if not ok or not name:
            return
        self.model.board['title'] = name
        self._sync_title_fields()
        self.save_board()

    # ---------------------------------------------------------------- files

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import board JSON',
                                              boardstore.BOARDS_DIR, 'Board JSON (*.json)')
        if not path:
            return
        try:
            board = boardstore.load_board_file(path)
        except (OSError, ValueError) as exc:
            self.set_status('That file is not a board: %s' % exc, 'bad')
            return
        repairs = self.model.replace(board)
        self.canvas.clear_selection()
        self._sync_title_fields()
        self.inspector.rebuild()
        self.refresh(structural=True)
        if repairs:
            self._report_repairs(repairs, os.path.basename(path))
        else:
            self.set_status('Loaded %s' % os.path.basename(path), 'ok')

    def export_json(self):
        name = compiler.slug(self.model.board.get('title') or 'board') + '.json'
        path, _ = QFileDialog.getSaveFileName(self, 'Export board JSON',
                                              os.path.join(boardstore.BOARDS_DIR, name),
                                              'Board JSON (*.json)')
        if not path:
            return
        try:
            boardstore._atomic_write(path, json.dumps(self.model.board, indent=2))
        except OSError as exc:
            self.set_status('Could not write that file: %s' % exc, 'bad')
            return
        self.set_status('Wrote %s' % os.path.basename(path), 'ok')

    def export_update_set(self):
        if not self._require_build():
            return
        dlg = UpdateSetDialog(self.model.board.get('title') or 'WidgetForge Board',
                              self.last_sys_id, self)
        if dlg.exec() != dlg.Accepted:
            return
        name, sys_id = dlg.values()
        if not name:
            self.set_status('The widget needs a name.', 'bad')
            return
        self.last_sys_id = sys_id or self.last_sys_id
        self.state.set('lastSysId', self.last_sys_id)
        try:
            xml = compiler.build_update_set(self.model.board, self.last_build, sys_id, name)
        except compiler.BuildError as exc:
            self.set_status(str(exc), 'bad')
            return
        filename = compiler.slug(name) + '-update-set.xml'
        path, _ = QFileDialog.getSaveFileName(self, 'Save update set',
                                              os.path.join(boardstore.BOARDS_DIR, filename),
                                              'Update set XML (*.xml)')
        if not path:
            return
        try:
            boardstore._atomic_write(path, xml)
        except OSError as exc:
            self.set_status('Could not write that file: %s' % exc, 'bad')
            return
        self.set_status('Update set written. Import it under Retrieved Update Sets.', 'ok')

    def _require_build(self):
        if self.last_build:
            return True
        self.compile_timer.stop()
        self.compile_now()
        if self.last_build:
            return True
        self.set_status(self.last_error or 'Add a card first', 'bad')
        return False

    def _copy_pane(self, key):
        if not self.last_build:
            self.set_status('Nothing to copy yet', 'bad')
            return False
        QGuiApplication.clipboard().setText(self.last_build.get(key, '') or '')
        self.set_status('Copied the %s pane' % key, 'ok')
        return True

    def open_paste_panel(self):
        if not self._require_build():
            return
        dlg = PasteDialog(self.last_build, self._paste_copy, self._paste_save,
                          self._paste_save_all, self, done=self.pasted)
        dlg.exec()
        self.pasted = set(dlg.done_keys)

    def _paste_copy(self, key):
        QGuiApplication.clipboard().setText(self.last_build.get(key, '') or '')
        self.set_status('Copied %s' % key, 'ok')
        return True

    def _paste_save(self, key, parent):
        ext = next(e for k, _l, e in PASTE_ORDER if k == key)
        base = compiler.slug(self.model.board.get('title') or 'widget')
        suggested = os.path.join(boardstore.BOARDS_DIR, '%s.%s.%s' % (base, key, ext))
        path, _ = QFileDialog.getSaveFileName(parent, 'Save %s' % key, suggested,
                                              '%s (*.%s)' % (ext.upper(), ext))
        if not path:
            return False
        try:
            boardstore._atomic_write(path, self.last_build.get(key, '') or '')
        except OSError as exc:
            self.set_status('Could not write that file: %s' % exc, 'bad')
            return False
        return True

    def _paste_save_all(self, parent):
        folder = QFileDialog.getExistingDirectory(parent, 'Save all four fields into',
                                                  boardstore.BOARDS_DIR)
        if not folder:
            return
        base = compiler.slug(self.model.board.get('title') or 'widget')
        written = 0
        for key, _label, ext in PASTE_ORDER:
            try:
                boardstore._atomic_write(os.path.join(folder, '%s.%s.%s' % (base, key, ext)),
                                         self.last_build.get(key, '') or '')
                written += 1
            except OSError as exc:
                self.set_status('Could not write %s: %s' % (key, exc), 'bad')
                return
        parent.mark_all()
        self.set_status('Wrote %d files into %s' % (written, folder), 'ok')

    # ----------------------------------------------------------------- misc

    def drawer_toggle(self):
        self.drawer.toggle()

    def _drawer_toggled(self, hidden):
        self.state.set('drawerHidden', bool(hidden))
        if hidden:
            self.vsplit.setSizes([self.vsplit.height() - 46, 46])
        else:
            self.vsplit.setSizes([int(self.vsplit.height() * 0.7),
                                  int(self.vsplit.height() * 0.3)])

    def undo(self):
        if self.model.undo():
            self.canvas.prune_selection()
            self._sync_title_fields()
            self.inspector.rebuild()
            self.refresh(structural=True)

    def redo(self):
        if self.model.redo():
            self.canvas.prune_selection()
            self._sync_title_fields()
            self.inspector.rebuild()
            self.refresh(structural=True)

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    def show_about(self):
        QMessageBox.about(
            self, 'WidgetForge',
            '<b>WidgetForge %s</b><br><br>'
            'A desktop builder that compiles ServiceNow Service Portal widgets.<br>'
            'Arrange cards on a %d × %d grid; it emits the four fields of an '
            '<code>sp_widget</code> record.<br><br>'
            'It never contacts a ServiceNow instance.'
            % (compiler.VERSION, self.model.cols, self.model.rows))

    def _save_draft(self):
        self.state.set('draft', self.model.board)

    def _size_to_screen(self):
        """Open at a comfortable size, but never larger than the display.

        1500 x 940 is right on a desktop monitor and larger than the whole
        work area on a 1366 x 768 laptop at 150% scaling, which would put the
        bottom of the window - the output drawer - off the screen.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1500, 940)
            return
        area = screen.availableGeometry()
        self.resize(min(1500, max(940, area.width() - 80)),
                    min(940, max(600, area.height() - 80)))

    def _restore_geometry(self):
        geom = self.state.get('geometry')
        if not geom:
            return
        try:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(geom.encode('ascii')))
        except (ValueError, TypeError, AttributeError):
            return
        # A geometry saved on a monitor that is no longer attached leaves the
        # window somewhere unreachable. Qt does not check; this does.
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        if not area.intersects(self.frameGeometry()):
            self._size_to_screen()
            self.move(area.center() - self.rect().center())

    def closeEvent(self, event):
        try:
            self.state.data['geometry'] = bytes(self.saveGeometry().toBase64()).decode('ascii')
            self.state.data['draft'] = self.model.board
            self.state.data['lastSysId'] = self.last_sys_id
            self.state.save()
        except Exception:  # pragma: no cover - never block a close
            pass
        super().closeEvent(event)
