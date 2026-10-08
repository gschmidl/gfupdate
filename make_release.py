#!/usr/bin/env python3
"""Builds the two eXo patches in release/, each one folder with its patch
script:

- gfupdate-windows-fix-<version>.zip: fix_windows.py and the fixed
  GFUpdate.exe (exo/build_fix.py makes it), with its source fixes.asm;
- gfupdate-port-<version>.zip: install_port.py and the port.
"""
import pathlib
import re
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
PATCHES = {
    'gfupdate-windows-fix': ['exo/fix_windows.py', 'exo/GFUpdate.exe',
                             'exo/fixes.asm', 'README.md', 'LICENSE'],
    'gfupdate-port': ['exo/install_port.py', 'gfupdate.py', 'README.md',
                      'NOTES.md', 'LICENSE'],
}


def main():
    version = re.search(r"^VERSION = '([^']+)'",
                        (HERE / 'gfupdate.py').read_text(encoding='utf-8'),
                        re.M).group(1)
    (HERE / 'release').mkdir(exist_ok=True)
    for name, files in PATCHES.items():
        top = f'{name}-{version}'
        out = HERE / 'release' / f'{top}.zip'
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(HERE / f, f'{top}/{pathlib.Path(f).name}')
        print(f'{out}: {out.stat().st_size} bytes, {len(files)} files')


if __name__ == '__main__':
    main()
