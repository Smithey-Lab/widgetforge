"""Colour tokens and the application stylesheet.

The token names and values come straight from builder.css, so the desktop app
looks like the tool it replaces rather than a different product. Every widget
reads through a token; nothing hard-codes a colour, which is what makes the
light/dark switch a single call.
"""

DARK = {
    'ink': '#0e1218',
    'panel': '#161c25',
    'rail': '#1b222c',
    'sunk': '#10151c',
    'line': '#29323f',
    'line2': '#38434f',
    'text': '#dde5ef',
    'dim': '#7d8b9e',
    'signal': '#3fb9b0',
    'sand': '#d9b26a',
    'bad': '#e2757b',
    'onSignal': '#0b1013',
    'gridline': '#1d2430',
    'gridline2': '#242d3a',
    'nodeFill': '#1e2733',
    'nodeLine': '#33404f',
    'scrim': 'rgba(0, 0, 0, 0.55)',
}

LIGHT = {
    'ink': '#eef1f6',
    'panel': '#ffffff',
    'rail': '#f7f9fc',
    'sunk': '#f1f4f9',
    'line': '#dde3ec',
    'line2': '#bcc7d6',
    'text': '#1b2530',
    'dim': '#5d6b7c',
    'signal': '#0f8f88',
    'sand': '#9a6f18',
    'bad': '#c0444b',
    'onSignal': '#ffffff',
    'gridline': '#e3e8f0',
    'gridline2': '#d5dce7',
    'nodeFill': '#ffffff',
    'nodeLine': '#c9d3e0',
    'scrim': 'rgba(27, 37, 48, 0.35)',
}

MONO = '"Cascadia Mono", "JetBrains Mono", Consolas, "DejaVu Sans Mono", monospace'


def tokens(name):
    return dict(LIGHT if name == 'light' else DARK)


def adjust_font(base, delta_pt=0.0, bold=None):
    """A copy of `base` resized by delta_pt, whichever unit it is defined in.

    QFont.pointSizeF() returns -1 when the font was set in pixels, which Qt
    does on some platforms and which the style sheet above triggers by setting
    font-size in px. Adding to -1 and assigning it back raises a warning and
    leaves the font unchanged, so the size has to be adjusted in whichever
    unit is actually in use.
    """
    from PySide6.QtGui import QFont

    f = QFont(base)
    if bold is not None:
        f.setBold(bold)
    if not delta_pt:
        return f
    pt = base.pointSizeF()
    if pt > 0:
        f.setPointSizeF(max(5.0, pt + delta_pt))
    else:
        px = base.pixelSize()
        if px > 0:
            # ~1.333 px per pt at 96 dpi; close enough for a nudge.
            f.setPixelSize(max(7, int(round(px + delta_pt * 1.333))))
    return f


def stylesheet(name):
    t = tokens(name)
    t['mono'] = MONO
    return _QSS % t


# Qt style sheets are not CSS: no variables, no nesting, and a narrow property
# set. Everything below is written flat and substituted once, which keeps the
# palette in one place and avoids the "two rules quietly fighting" problem the
# web build had a test for.
_QSS = """
QWidget {
    background: %(ink)s;
    color: %(text)s;
    font-size: 13px;
}
QToolTip {
    background: %(panel)s;
    color: %(text)s;
    border: 1px solid %(line2)s;
    padding: 4px 6px;
}

/* ---- structural panels ---- */
#TopBar, #Drawer { background: %(panel)s; }
#TopBar { border-bottom: 1px solid %(line)s; }
#Drawer { border-top: 1px solid %(line)s; }
#PaletteRail, #InspectRail { background: %(rail)s; }
#PaletteRail { border-right: 1px solid %(line)s; }
#InspectRail { border-left: 1px solid %(line)s; }
#Stage { background: %(ink)s; }

QLabel#RailHead {
    color: %(dim)s;
    font-size: 11px;
    font-weight: 600;
    padding: 10px 12px 6px 12px;
    background: transparent;
}
QLabel#RailHint { color: %(dim)s; font-size: 10px; background: transparent; }
QLabel#Version { color: %(dim)s; font-size: 11px; background: transparent; }
QLabel#Hud { color: %(dim)s; font-size: 11px; background: transparent; }
QLabel#StatusOk { color: %(signal)s; font-size: 11px; background: transparent; }
QLabel#StatusBad { color: %(bad)s; font-size: 11px; background: transparent; }
QLabel#StatusPlain { color: %(dim)s; font-size: 11px; background: transparent; }
QLabel#FieldLabel { color: %(dim)s; font-size: 11px; background: transparent; }
QLabel#FieldHelp { color: %(dim)s; font-size: 10px; background: transparent; }
QLabel#Required { color: %(sand)s; background: transparent; }
QLabel#InspectNone { color: %(dim)s; padding: 14px 12px; background: transparent; }
QLabel#CondWarn {
    color: %(sand)s; font-size: 10px; background: transparent; padding: 2px 0;
}
QLabel#ModalNote { color: %(dim)s; font-size: 11px; background: transparent; }

/* ---- buttons ---- */
QPushButton {
    background: %(sunk)s;
    border: 1px solid %(line2)s;
    border-radius: 5px;
    padding: 5px 10px;
    color: %(text)s;
}
QPushButton:hover { border-color: %(signal)s; }
QPushButton:pressed { background: %(line)s; }
QPushButton:disabled { color: %(dim)s; border-color: %(line)s; }
QPushButton[flavour="ghost"] { background: transparent; border-color: %(line)s; }
QPushButton[flavour="ghost"]:hover { border-color: %(line2)s; }
QPushButton[flavour="go"] {
    background: %(signal)s; color: %(onSignal)s; border-color: %(signal)s; font-weight: 600;
}
QPushButton[flavour="go"]:hover { border-color: %(text)s; }
QPushButton[flavour="danger"] { color: %(bad)s; border-color: %(line)s; background: transparent; }
QPushButton[flavour="danger"]:hover { border-color: %(bad)s; }
QPushButton#Issue {
    background: transparent; border: 1px solid %(sand)s; color: %(sand)s;
    font-size: 10px; padding: 2px 7px; border-radius: 9px; text-align: left;
}
QPushButton#IssueBad { border-color: %(bad)s; color: %(bad)s; }

/* ---- inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background: %(sunk)s;
    border: 1px solid %(line2)s;
    border-radius: 5px;
    padding: 4px 7px;
    selection-background-color: %(signal)s;
    selection-color: %(onSignal)s;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus { border-color: %(signal)s; }
QLineEdit[mono="1"], QPlainTextEdit[mono="1"] { font-family: %(mono)s; font-size: 12px; }
QLineEdit#BoardTitle {
    background: transparent; border: none; border-bottom: 1px solid transparent;
    font-size: 15px; font-weight: 600; padding: 3px 0; border-radius: 0;
}
QLineEdit#BoardTitle:focus { border-bottom: 1px solid %(signal)s; }
QLineEdit#BoardSub {
    background: transparent; border: none; border-bottom: 1px solid transparent;
    color: %(dim)s; font-size: 12px; padding: 3px 0; border-radius: 0;
}
QLineEdit#BoardSub:focus { border-bottom: 1px solid %(line2)s; }
/* The drop-down sub-control is deliberately left unstyled. Giving it
   `border: none` stops Qt drawing its arrow, and the CSS border-triangle trick
   that would replace it renders as a solid block under Qt's box model - so a
   combo box ends up looking exactly like a text field. The native arrow is the
   right answer; only the frame around it is themed. */
QComboBox QAbstractItemView {
    background: %(panel)s; border: 1px solid %(line2)s;
    selection-background-color: %(signal)s; selection-color: %(onSignal)s;
    outline: none;
}
QCheckBox { spacing: 7px; background: transparent; }
QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid %(line2)s;
    border-radius: 3px; background: %(sunk)s;
}
QCheckBox::indicator:checked { background: %(signal)s; border-color: %(signal)s; }

/* ---- output drawer ---- */
QTabWidget::pane { border: none; background: %(panel)s; }
QTabBar::tab {
    background: transparent; color: %(dim)s;
    padding: 6px 12px; border: none; border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(signal)s; }
QTabBar::tab:hover { color: %(text)s; }
QPlainTextEdit#Pane {
    background: %(sunk)s; border: none; font-family: %(mono)s; font-size: 12px;
    color: %(text)s;
}
QPlainTextEdit#PaneBad { color: %(bad)s; }

/* ---- palette entries ---- */
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QWidget#PaletteItem { background: transparent; border-radius: 6px; }
QWidget#PaletteItem:hover { background: %(sunk)s; }
QLabel#PalName { background: transparent; font-size: 12px; }
QLabel#PalBlurb { background: transparent; color: %(dim)s; font-size: 10px; }
QLabel#PalSize { background: transparent; color: %(dim)s; font-size: 10px; font-family: %(mono)s; }
QLabel#PalNone { background: transparent; color: %(dim)s; padding: 12px; }
QLabel#PalSep {
    background: transparent; color: %(dim)s; font-size: 10px; font-weight: 600;
    padding: 12px 12px 4px 12px;
}

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical {
    background: %(line2)s; border-radius: 5px; min-height: 26px;
}
QScrollBar::handle:vertical:hover { background: %(dim)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: %(line2)s; border-radius: 5px; min-width: 26px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- dialogs ---- */
QDialog { background: %(panel)s; }
QDialog QLabel { background: transparent; }
QFrame#Divider { background: %(line)s; max-height: 1px; border: none; }
QWidget#CondRow { background: %(sunk)s; border: 1px solid %(line)s; border-radius: 6px; }
QWidget#CondRowOr { border-left: 2px solid %(sand)s; }
QLabel#CondOut {
    background: %(sunk)s; border: 1px solid %(line)s; border-radius: 5px;
    font-family: %(mono)s; font-size: 11px; color: %(signal)s; padding: 5px 7px;
}
QLabel#CondOutEmpty { color: %(dim)s; }
QLabel#JoinTag {
    background: transparent; color: %(dim)s; font-size: 10px; font-weight: 600;
}
QLabel#JoinTagOr { color: %(sand)s; }
QTableWidget {
    background: %(sunk)s; gridline-color: %(line)s; border: 1px solid %(line)s;
}
QHeaderView::section {
    background: %(rail)s; color: %(dim)s; border: none;
    border-bottom: 1px solid %(line)s; padding: 4px 6px;
}
"""
