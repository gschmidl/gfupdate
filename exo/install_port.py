#!/usr/bin/env python3
"""The portable GFUpdate (gfupdate.py) for eXoDOS's Girlfriend Terri and Tracy.

Both games' launchers (eXoDOS\\!dos\\gfterri\\exception.bat and
eXoDOS\\!dos\\gftracy\\exception.bat) then run gfupdate.py, the Python port of
GFUpdate.exe, for "Modify the Games User Information", with Python ("py")
when there is one; GFUpdate.exe otherwise, as before.

- util\\gfupdate: gfupdate.py, README.md, NOTES.md, LICENSE.
- exception.bat: the GFUpdate line runs gfupdate.py first; exception.bat.orig
  keeps the launcher as it was.

usage: python install_port.py [--check | --revert] EXO_FOLDER

EXO_FOLDER is eXoDOS's "eXo" folder, the one with eXoDOS, emulators and util
in it. --check shows what would change, --revert undoes it. The port lives in
util\\gfupdate, so reinstalling a game does not remove it.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ('gfupdate.py', 'README.md', 'NOTES.md', 'LICENSE')
DEST = Path('util') / 'gfupdate'
SCRIPT = '.\\util\\gfupdate\\gfupdate.py'
# game folder in !dos -> (the launcher's GFUpdate line, the game's folder);
# the launcher runs it from the eXo folder
GAMES = {
    'gfterri': ('.\\eXoDOS\\gfterri\\gf_terri\\GFUpdate',
                '.\\eXoDOS\\gfterri\\gf_terri'),
    'gftracy': ('.\\eXoDOS\\gftracy\\gf\\gfupdate',
                '.\\eXoDOS\\gftracy\\GF'),
}


def ours(folder):
    return 'py %s -C %s' % (SCRIPT, folder)


def block(folder):
    return ['where py >nul 2>nul',
            'if errorlevel 1 goto gfupdate_exe',
            'if not exist %s goto gfupdate_exe' % SCRIPT,
            ours(folder),
            'goto menu',
            ':gfupdate_exe']


def convert(text, exe_line, folder):
    """the launcher with the port before its GFUpdate line; None if none"""
    nl = '\r\n' if '\r\n' in text else '\n'
    out, found = [], False
    for line in text.split(nl):
        if line.strip().lower() in (exe_line.lower(),
                                    exe_line.lower() + '.exe') and not found:
            found = True
            out += block(folder)
        out.append(line)
    return nl.join(out) if found else None


def source(name):
    """NAME from the release zip (beside this script) or the project (one up)"""
    for p in (HERE / name, HERE.parent / name):
        if p.is_file():
            return p
    sys.exit(f'{name} is missing (it belongs beside install_port.py)')


class Patcher:
    def __init__(self, exo, check):
        self.exo, self.check = exo, check

    def say(self, text):
        print(('would ' if self.check else '') + text)

    def apply(self):
        for name in FILES:
            data = source(name).read_bytes()
            dest = self.exo / DEST / name
            if dest.is_file() and dest.read_bytes() == data:
                continue
            self.say(f'write {DEST / name}')
            if not self.check:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        for game, (exe_line, folder) in GAMES.items():
            launcher = Path('eXoDOS') / '!dos' / game / 'exception.bat'
            bat = self.exo / launcher
            orig = bat.with_name('exception.bat.orig')
            if not bat.is_file():
                print(f'{launcher} is missing: launcher not changed')
                continue
            text = bat.read_bytes().decode('latin-1')
            if ours(folder) in text:
                continue
            new = convert(text, exe_line, folder)
            if new is None:
                print(f'{launcher} has no GFUpdate line: launcher not changed')
                continue
            self.say(f'switch {launcher} to gfupdate.py (old one kept as '
                     f'{orig.name})')
            if not self.check:
                orig.write_bytes(text.encode('latin-1'))
                bat.write_bytes(new.encode('latin-1'))

    def revert(self):
        for game, (_, folder) in GAMES.items():
            launcher = Path('eXoDOS') / '!dos' / game / 'exception.bat'
            bat = self.exo / launcher
            orig = bat.with_name('exception.bat.orig')
            if bat.is_file() and ours(folder) in bat.read_bytes().decode(
                    'latin-1'):
                if orig.is_file():
                    self.say(f'restore {launcher}')
                    if not self.check:
                        bat.write_bytes(orig.read_bytes())
                        orig.unlink()
                else:
                    print(f'warning: {launcher} has no {orig.name}; left as '
                          f'it is')
        folder = self.exo / DEST
        for name in FILES:
            if (folder / name).is_file():
                self.say(f'delete {DEST / name}')
                if not self.check:
                    (folder / name).unlink()
        if folder.is_dir() and not self.check and not any(folder.iterdir()):
            folder.rmdir()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true',
                       help='only show what would change')
    group.add_argument('--revert', action='store_true', help='undo the patch')
    ap.add_argument('exo', metavar='EXO_FOLDER')
    args = ap.parse_args()
    exo = Path(args.exo)
    if not (exo / 'eXoDOS').is_dir():
        sys.exit(f'{exo} is not eXoDOS\'s "eXo" folder (no eXoDOS in it)')
    p = Patcher(exo, args.check)
    p.revert() if args.revert else p.apply()
    return 0


if __name__ == '__main__':
    sys.exit(main())
