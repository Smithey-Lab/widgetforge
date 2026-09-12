# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a standalone WidgetForge.exe.

    venv\\Scripts\\python.exe -m pip install pyinstaller
    venv\\Scripts\\pyinstaller.exe widgetforge.spec

The result is dist/WidgetForge/WidgetForge.exe plus its folder. A one-file
build is deliberately NOT used: it unpacks to a temp directory on every launch,
which is slow, and it puts modules/ somewhere that changes each run - which
would break the whole point of being able to drop a new card type into
modules/ and see it in the palette.

WHAT SHIPS INSIDE, AND WHAT DOES NOT
------------------------------------
modules/, shell/ and VERSION are bundled, because the compiler cannot run
without them. They are ALSO the files a card-type author edits. In a bundled
build the copies next to the exe are what the app reads, so editing them there
works exactly as it does from source - see wf/compiler.py's HERE.

boards/ is not bundled. Boards are the user's work and belong beside the exe,
not inside it.

UNTESTED. This spec has never been built or run. It is written from the
documented behaviour of PyInstaller and PySide6 and is the starting point for
a build on the Windows machine, not a finished artefact. Expect to adjust
`excludes` after the first run: PySide6 pulls in a lot of Qt that a widget
builder never touches, and trimming it is what takes the folder from roughly
200 MB down to something reasonable.
"""

import os
import sys

block_cipher = None

# SPECPATH is injected by PyInstaller and is the folder holding this file.
# os.getcwd() would be wherever pyinstaller happened to be invoked from, and
# every relative data path below would then miss.
HERE = os.path.abspath(globals().get('SPECPATH') or os.getcwd())

# Data that must sit beside the executable. Each entry is (source, destination
# folder relative to the app root).
datas = [
    (os.path.join(HERE, 'VERSION'), '.'),
    (os.path.join(HERE, 'modules'), 'modules'),
    (os.path.join(HERE, 'shell'), 'shell'),
    (os.path.join(HERE, 'examples'), 'examples'),
    (os.path.join(HERE, 'tools', 'query-corpus.json'), 'tools'),
]

# Qt modules WidgetForge never loads. Excluding them is the difference between
# a ~200 MB folder and a ~90 MB one. Trim further only after a build still runs.
excludes = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtCharts',
    'PySide6.QtDataVisualization', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
    'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSerialPort',
    'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtHelp',
    'PySide6.QtNetwork', 'PySide6.QtWebSockets', 'PySide6.QtWebChannel',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtSpatialAudio',
    'PySide6.QtTextToSpeech', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml',
    'PySide6.QtSensors', 'PySide6.QtStateMachine',
    # Nothing here is a web app or a science project.
    'tkinter', 'unittest', 'pydoc', 'doctest', 'numpy', 'matplotlib', 'PIL',
    'flask', 'werkzeug', 'jinja2',
]

a = Analysis(
    [os.path.join(HERE, 'main.py')],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WidgetForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX and Qt DLLs are a known source of odd crashes.
    console=False,      # A GUI app. No console window behind the window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Point at a .ico here once there is one.
    # PyInstaller 6 hides everything under _internal/ by default, which would
    # bury modules/ where a card-type author would never find it. Flat layout
    # keeps modules/, shell/ and boards/ beside the exe. wf/compiler.py's
    # _find_root copes with either, so this is preference, not a dependency.
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WidgetForge',
)
