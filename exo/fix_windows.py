#!/usr/bin/env python3
"""The fixed GFUpdate.exe for eXoDOS's Girlfriend Terri (1994) and Tracy (1995).

GFUpdate.exe ("Modify the Games User Information") with its bugs fixed (see
README.md): long names keep no letters of the old name and no longer crash,
a long birthday text no longer spills into the game's data, files dated
before 1980 are found, a PURSEA.DAT chosen with Open is used, and Windows no
longer asks for administrator rights when it starts. Everything else is the
original program; it still needs Windows (or Wine).

- eXoDOS\\gfterri\\gf_terri\\GFUpdate.exe and eXoDOS\\gftracy\\GF\\GFUpdate.exe
  are replaced with the GFUpdate.exe next to this script; GFUpdate.exe.orig
  keeps the original.

usage: python fix_windows.py [--check | --revert] [--force] EXO_FOLDER

EXO_FOLDER is eXoDOS's "eXo" folder, the one with eXoDOS, emulators and util
in it. --check shows what would change, --revert undoes it. Only the installed
games are patched: their zips are left alone, so after a reinstall run this
again.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL_SHA1 = '610d1b026779892e55c9e53cb9289285c6d7a786'   # eXoDOS's copies
TARGETS = (Path('eXoDOS') / 'gfterri' / 'gf_terri' / 'GFUpdate.exe',
           Path('eXoDOS') / 'gftracy' / 'GF' / 'GFUpdate.exe')


def sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def one(exo, rel, fixed_sha1, args):
    target = exo / rel
    orig = target.with_name('GFUpdate.exe.orig')
    would = 'would ' if args.check else ''
    if not target.is_file():
        print(f'{rel} is missing (game not installed): nothing to do')
        return 0
    now = sha1(target)
    is_fixed = now == fixed_sha1
    if args.revert:
        if not orig.is_file():
            print(f'{rel} has no {orig.name}: nothing to undo')
            return 0
        if not is_fixed and not args.force:
            print(f'{rel} is not the fixed GFUpdate.exe any more; left alone '
                  f'(--force restores {orig.name} anyway)')
            return 1
        print(f'{would}restore {rel} from {orig.name}')
        if not args.check:
            shutil.copy2(orig, target)
            orig.unlink()
        return 0
    if is_fixed:
        print(f'{rel} is already the fixed one')
        return 0
    if now != ORIGINAL_SHA1 and not args.force:
        print(f'{rel} is not the GFUpdate.exe this patch was made for (sha1 '
              f'{now}); left alone (--force replaces it anyway)')
        return 1
    print(f'{would}replace {rel} with the fixed one (the original kept as '
          f'{orig.name})')
    if not args.check:
        if not orig.is_file():
            shutil.copy2(target, orig)
        shutil.copyfile(HERE / 'GFUpdate.exe', target)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true',
                       help='only show what would change')
    group.add_argument('--revert', action='store_true',
                       help='put the original GFUpdate.exe back')
    ap.add_argument('--force', action='store_true',
                    help='replace (or restore) a GFUpdate.exe that is neither '
                         'the original nor the fixed one')
    ap.add_argument('exo', metavar='EXO_FOLDER')
    args = ap.parse_args()
    exo = Path(args.exo)
    if not (exo / 'eXoDOS').is_dir():
        sys.exit(f'{exo} is not eXoDOS\'s "eXo" folder (no eXoDOS in it)')
    fixed = HERE / 'GFUpdate.exe'
    if not fixed.is_file():
        sys.exit('GFUpdate.exe is missing (it belongs beside fix_windows.py)')
    fixed_sha1 = sha1(fixed)
    return max(one(exo, rel, fixed_sha1, args) for rel in TARGETS)


if __name__ == '__main__':
    sys.exit(main())
