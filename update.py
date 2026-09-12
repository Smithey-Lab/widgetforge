"""WidgetForge updater.

Two ways to use it:

    py update.py                      apply anything in updates/ that is newer
                                      than VERSION
    py update.py wf-update-3.1.0.zip  unpack an update pack, then apply it
    py update.py --check              say what would happen, change nothing
    py update.py --rollback           restore the last backup

An update is a file in updates/ named NNN_short_name.py containing:

    VERSION = '3.1.0'
    SUMMARY = 'One line about what this does.'

    def apply(ctx):
        ctx.edit('wf/compiler.py', 'old exact text', 'new text')
        ctx.write('modules/heatmap/module.json', '{...}')
        ctx.note('Added the heatmap card.')

ctx.edit asserts its anchor appears exactly once and raises if it does not.
An update that quietly does nothing is worse than one that fails, because
you go on believing it worked.

The whole tree is backed up before anything is touched, the test suite runs
afterwards, and a failure at any point restores the backup.
"""

import importlib.util
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATES = os.path.join(HERE, 'updates')
BACKUP = os.path.join(HERE, '.backup')
SKIP = {'.backup', 'venv', '.venv', '__pycache__', 'boards', '.git'}


class UpdateError(Exception):
    pass


def version_tuple(text):
    return tuple(int(p) for p in re.findall(r'\d+', str(text))[:3] or [0])


def read_version():
    with open(os.path.join(HERE, 'VERSION'), encoding='utf-8') as f:
        return f.read().strip()


def write_version(v):
    with open(os.path.join(HERE, 'VERSION'), 'w', encoding='utf-8') as f:
        f.write(v + '\n')


class Ctx(object):
    """What an update script is allowed to do. Every operation is loud."""

    def __init__(self, dry):
        self.dry = dry
        self.notes = []
        self.touched = []

    def _path(self, rel):
        full = os.path.normpath(os.path.join(HERE, rel))
        if not full.startswith(HERE + os.sep):
            raise UpdateError('update tried to write outside the install: %s' % rel)
        return full

    def edit(self, rel, old, new, count=1):
        full = self._path(rel)
        if not os.path.isfile(full):
            raise UpdateError('%s does not exist, so it cannot be edited' % rel)
        with open(full, encoding='utf-8') as f:
            text = f.read()
        found = text.count(old)
        if found != count:
            raise UpdateError('%s: expected %d match for the anchor, found %d.\n'
                              '  anchor: %r' % (rel, count, found, old[:120]))
        if not self.dry:
            with open(full, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text.replace(old, new))
        self.touched.append(rel)
        return True

    def write(self, rel, text):
        full = self._path(rel)
        if not self.dry:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
        self.touched.append(rel)

    def delete(self, rel):
        full = self._path(rel)
        if os.path.isdir(full):
            if not self.dry:
                shutil.rmtree(full)
        elif os.path.isfile(full):
            if not self.dry:
                os.remove(full)
        else:
            raise UpdateError('%s does not exist, so it cannot be deleted' % rel)
        self.touched.append(rel)

    def add_module(self, mid, files):
        """files: dict of filename -> text, e.g. {'module.json': '...'}"""
        if 'module.json' not in files:
            raise UpdateError('module %s needs a module.json' % mid)
        for name, text in files.items():
            self.write(os.path.join('modules', mid, name), text)

    def note(self, msg):
        self.notes.append(msg)


def discover():
    if not os.path.isdir(UPDATES):
        return []
    out = []
    for fn in sorted(os.listdir(UPDATES)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        path = os.path.join(UPDATES, fn)
        spec = importlib.util.spec_from_file_location('wfupd_' + fn[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, 'VERSION') or not hasattr(mod, 'apply'):
            raise UpdateError('%s needs both VERSION and apply(ctx)' % fn)
        out.append((version_tuple(mod.VERSION), fn, mod))
    out.sort(key=lambda r: (r[0], r[1]))
    return out


def make_backup():
    if os.path.isdir(BACKUP):
        shutil.rmtree(BACKUP)
    os.makedirs(BACKUP)
    for name in os.listdir(HERE):
        if name in SKIP:
            continue
        src = os.path.join(HERE, name)
        dst = os.path.join(BACKUP, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def restore():
    if not os.path.isdir(BACKUP):
        raise UpdateError('there is no backup to restore')
    for name in os.listdir(BACKUP):
        src = os.path.join(BACKUP, name)
        dst = os.path.join(HERE, name)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.isfile(dst):
            os.remove(dst)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def unpack(zip_path):
    if not os.path.isfile(zip_path):
        raise UpdateError('no such file: %s' % zip_path)
    os.makedirs(UPDATES, exist_ok=True)
    added = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            name = os.path.basename(member)
            if not name.endswith('.py') or name.startswith('_'):
                continue
            if '/updates/' not in member.replace('\\', '/') and not member.startswith('updates'):
                continue
            with zf.open(member) as src, open(os.path.join(UPDATES, name), 'wb') as dst:
                shutil.copyfileobj(src, dst)
            added.append(name)
    if not added:
        raise UpdateError('%s has no updates/ scripts in it' % os.path.basename(zip_path))
    print('  unpacked %d update script(s): %s' % (len(added), ', '.join(added)))


def interpreter():
    """The venv Python, not whichever one launched this.

    PySide6 is installed into venv/ by install.py. Running the suite with the
    launching interpreter meant `py update.py` tested against system Python,
    failed on a missing dependency, and rolled back a good update.
    """
    for rel in (os.path.join('venv', 'Scripts', 'python.exe'),
                os.path.join('venv', 'bin', 'python')):
        candidate = os.path.join(HERE, rel)
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def run_tests():
    import subprocess
    exe = interpreter()
    env = dict(os.environ)
    # The suite builds real widgets. Offscreen keeps the updater from flashing
    # a window onto the desktop half way through a rollback decision.
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    result = subprocess.run([exe, os.path.join(HERE, 'tests.py')],
                            capture_output=True, text=True, cwd=HERE, env=env,
                            encoding='utf-8', errors='replace')
    if result.returncode != 0 and 'No module named' in result.stderr:
        return False, (result.stderr.strip() +
                       '\n\n  Ran with: ' + exe +
                       '\n  If that is not the venv, run install.py again.')
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main(argv):
    dry = '--check' in argv
    if '--rollback' in argv:
        restore()
        print('  Restored the backup. Now at %s.' % read_version())
        return 0

    packs = [a for a in argv if a.lower().endswith('.zip')]
    for pack in packs:
        unpack(pack)

    current = read_version()
    cur = version_tuple(current)
    all_updates = discover()
    todo = [u for u in all_updates if u[0] > cur]

    print()
    print('  WidgetForge %s' % current)
    if not todo:
        print('  Nothing to apply. %d update script(s) already at or below this version.'
              % len(all_updates))
        print()
        return 0

    print('  %d update(s) to apply:' % len(todo))
    for ver, fn, mod in todo:
        print('    %-28s %-8s %s' % (fn, '.'.join(str(p) for p in ver),
                                     getattr(mod, 'SUMMARY', '')))
    print()

    if dry:
        ctx = Ctx(dry=True)
        try:
            for _, fn, mod in todo:
                mod.apply(ctx)
            print('  Dry run clean. %d file(s) would change: %s'
                  % (len(set(ctx.touched)), ', '.join(sorted(set(ctx.touched)))))
        except Exception as exc:
            print('  Dry run FAILED on %s: %s' % (fn, exc))
            return 1
        print()
        return 0

    print('  Backing up to .backup/ ...')
    make_backup()

    ctx = Ctx(dry=False)
    target = current
    try:
        for ver, fn, mod in todo:
            print('  Applying %s ...' % fn)
            mod.apply(ctx)
            target = '.'.join(str(p) for p in ver)
        write_version(target)
    except Exception as exc:
        print()
        print('  FAILED: %s' % exc)
        print('  Restoring the backup, nothing has changed.')
        restore()
        return 1

    print('  Running the test suite ...')
    passed, output = run_tests()
    if not passed:
        print()
        print(output)
        print()
        print('  Tests failed after the update. Restoring the backup.')
        restore()
        return 1

    print()
    for note in ctx.notes:
        print('  - %s' % note)
    print('  Updated to %s. %s' % (target, output.strip().splitlines()[-1] if output else ''))
    print('  The previous version is in .backup/ if you need it.')
    print()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except UpdateError as exc:
        print('  %s' % exc)
        sys.exit(1)
