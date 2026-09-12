"""WidgetForge installer.

    py install.py

Creates a virtual environment beside this file, installs PySide6 into it, runs
the test suite, and writes the launchers. Safe to run again - it reuses an
existing venv rather than rebuilding it.

PySide6 ships abi3 wheels built for cp310, which cover every Python from 3.10
up, so there is nothing to compile and nothing to wait for on a new Python.
"""

import os
import platform
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, 'venv')
WINDOWS = platform.system() == 'Windows'
BIN = os.path.join(VENV, 'Scripts' if WINDOWS else 'bin')
PY = os.path.join(BIN, 'python.exe' if WINDOWS else 'python')

REQUIREMENTS = os.path.join(HERE, 'requirements.txt')
STEPS = 5


def say(msg):
    print('  ' + msg)


def step(n, msg):
    print()
    print('  [%d/%d] %s' % (n, STEPS, msg))


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=HERE, **kw)


def main():
    print()
    print('  WidgetForge installer')
    print('  ' + '-' * 40)

    step(1, 'Checking Python')
    if sys.version_info < (3, 10):
        say('Python 3.10 or newer is required. This is %s.' % platform.python_version())
        say('Current PySide6 wheels are cp310-abi3; 3.9 will not find one.')
        return 1
    say('Python %s at %s' % (platform.python_version(), sys.executable))

    step(2, 'Creating the virtual environment')
    if os.path.isfile(PY):
        say('venv already exists, reusing it')
    else:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
        say('created venv/')

    step(3, 'Installing PySide6')
    # encoding is explicit: without it Python decodes pip's output with the
    # console code page, and one byte pip emits that cp1252 cannot represent
    # raises UnicodeDecodeError inside subprocess.run - before the error
    # handling below ever gets a chance to print something useful.
    result = run([PY, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                  '-r', REQUIREMENTS], capture_output=True, text=True,
                 encoding='utf-8', errors='replace')
    if result.returncode != 0:
        say('pip failed:')
        print(result.stdout)
        print(result.stderr)
        say('If you are behind a proxy, set HTTPS_PROXY and run this again.')
        say('If it reports an SSL or certificate error instead, the proxy is')
        say('inspecting TLS: point pip at your organisation\'s root certificate')
        say('with  set PIP_CERT=C:\\path\\to\\corp-root.pem  and try again.')
        say('If it reports no matching distribution, PySide6 has no wheel for')
        say('this Python yet - the wheels are cp310-abi3, so 3.10 and newer are')
        say('covered, but a brand new release can be ahead of them.')
        return 1
    check = run([PY, '-c', 'import PySide6; print(PySide6.__version__)'],
                capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check.returncode != 0:
        say('PySide6 installed but will not import:')
        print(check.stderr)
        return 1
    say('PySide6 %s installed' % check.stdout.strip())

    step(4, 'Running the test suite')
    env = dict(os.environ)
    # The interface checks build real widgets. Offscreen keeps them from
    # flashing windows on the desktop, and lets this run over a remote shell.
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    result = run([PY, 'tests.py'], capture_output=True, text=True, env=env,
                 encoding='utf-8', errors='replace')
    print(result.stdout.rstrip())
    if result.returncode != 0:
        print(result.stderr)
        say('Tests failed. Do not deploy anything from this install yet.')
        return 1

    step(5, 'Writing launchers')
    write_launchers()
    say('run.bat, run.sh, update.bat and update.sh written')

    print()
    print('  Done. Start it with:')
    print()
    print('      run.bat' if WINDOWS else '      ./run.sh')
    print()
    return 0


def write_launchers():
    with open(os.path.join(HERE, 'run.bat'), 'w', newline='\r\n') as f:
        # start "" /b detaches the GUI from the console window, and there is no
        # pause at the end - a desktop app that leaves a command prompt sitting
        # open behind it looks broken.
        f.write('@echo off\r\n'
                'cd /d "%~dp0"\r\n'
                'if not exist "venv\\Scripts\\pythonw.exe" (\r\n'
                '  echo.\r\n'
                '  echo   WidgetForge is not installed yet - venv\\ is missing.\r\n'
                '  echo   Run this first:   py install.py\r\n'
                '  echo.\r\n'
                '  pause\r\n'
                '  exit /b 1\r\n'
                ')\r\n'
                'start "WidgetForge" /b "venv\\Scripts\\pythonw.exe" main.py %*\r\n')
    with open(os.path.join(HERE, 'run.sh'), 'w', newline='\n') as f:
        f.write('#!/bin/sh\ncd "$(dirname "$0")"\nexec venv/bin/python main.py "$@"\n')
    # The updater runs the suite against the venv, where PySide6 lives.
    with open(os.path.join(HERE, 'update.bat'), 'w', newline='\r\n') as f:
        f.write('@echo off\r\ncd /d "%~dp0"\r\n'
                'venv\\Scripts\\python.exe update.py %*\r\npause\r\n')
    with open(os.path.join(HERE, 'update.sh'), 'w', newline='\n') as f:
        f.write('#!/bin/sh\ncd "$(dirname "$0")"\nvenv/bin/python update.py "$@"\n')
    for name in ('run.sh', 'update.sh'):
        try:
            # Executable launchers are intentionally readable/executable by users.
            os.chmod(os.path.join(HERE, name), 0o755)  # nosec B103
        except OSError:
            pass


if __name__ == '__main__':
    sys.exit(main())
