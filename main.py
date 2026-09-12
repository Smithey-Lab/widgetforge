"""WidgetForge - desktop entry point.

    run.bat            Windows
    ./run.sh           anything else
    python main.py     directly, from the venv

Everything is local. There is no server, no port and no connection of any kind
to a ServiceNow instance.
"""

import os
import sys


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)

    # Import errors here are the single most likely thing to greet a fresh
    # install, so say what to do rather than showing a traceback.
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write(
            'WidgetForge needs PySide6, and it is not installed in this interpreter.\n\n'
            '  %s -m pip install PySide6\n\n'
            'On Windows, run install.py or update.bat rather than a bare "py" - the\n'
            'system interpreter is not the one with the dependencies.\n' % sys.executable)
        return 2

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from wf import boards as boardstore
    from wf import compiler
    from wf.ui.main_window import MainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(argv)
    app.setApplicationName('WidgetForge')
    app.setApplicationVersion(compiler.VERSION)
    app.setOrganizationName('WidgetForge')

    state = boardstore.State()
    window = MainWindow(state)

    if state.readonly:
        window.set_status('Settings could not be saved - presets and theme will not '
                          'persist between runs.', 'bad')

    # A board file named on the command line opens instead of the draft.
    extra = [a for a in argv[1:] if not a.startswith('-')]
    if extra and os.path.isfile(extra[0]):
        try:
            board = boardstore.load_board_file(extra[0])
        except (OSError, ValueError) as exc:
            window.set_status('Could not open %s: %s' % (extra[0], exc), 'bad')
        else:
            repairs = window.model.replace(board, keep_history=False)
            window._sync_title_fields()
            window.inspector.rebuild()
            window.refresh(structural=True)
            if repairs:
                window._report_repairs(repairs, os.path.basename(extra[0]))

    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
