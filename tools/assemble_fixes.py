"""Assemble exo/fixes.asm into the patch table of exo/build_fix.py.

    py assemble_fixes.py [--into ../exo/build_fix.py]

Each ";; at ADDRESS" block of fixes.asm is assembled on its own with NASM at
that address (the lines before the first block are put in front of every
block). NASM comes from $NASM (a command line, e.g. "wsl -d Debian -- nasm")
or the PATH. Prints the PATCHES table, or with --into replaces the one
between the "# BEGIN PATCHES" and "# END PATCHES" lines of build_fix.py.
"""
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ASM = os.path.join(HERE, '..', 'exo', 'fixes.asm')
ROOM = (0x45A6F9, 0x45A7DC)     # the old name routine's bytes, free now


def nasm():
    env = os.environ.get('NASM')
    if env:
        return shlex.split(env, posix=os.name != 'nt')
    exe = shutil.which('nasm')
    if exe:
        return [exe]
    sys.exit('nasm not found: put it on the PATH or set NASM')


def blocks(text):
    parts = re.split(r'^;; at ([0-9A-Fa-f]+)\s*$', text, flags=re.M)
    prelude = parts[0]
    for i in range(1, len(parts), 2):
        yield int(parts[i], 16), prelude, parts[i + 1]


def main():
    with open(ASM, encoding='utf-8') as f:
        text = f.read()
    cmd = nasm()
    out = []
    tmp = tempfile.mkdtemp(prefix='gfufix-', dir=HERE)
    try:
        for addr, prelude, body in blocks(text):
            src = os.path.join(tmp, 'p.asm')
            with open(src, 'w', newline='\n') as f:
                f.write('bits 32\norg 0x%X\n%s\nblock:\n%s' % (addr, prelude,
                                                              body))
            r = subprocess.run(cmd + ['-f', 'bin', '-o', 'p.bin', 'p.asm'],
                               cwd=tmp, capture_output=True, text=True)
            if r.returncode:
                sys.exit('nasm failed for the block at %X:\n%s'
                         % (addr, r.stderr))
            with open(os.path.join(tmp, 'p.bin'), 'rb') as f:
                code = f.read()
            first = body.strip().splitlines()[0].strip().lstrip('; ')
            out.append((addr, code, first))
    finally:
        # WSL may hold on to the folder (its working directory) a moment
        for _ in range(50):
            shutil.rmtree(tmp, ignore_errors=True)
            if not os.path.exists(tmp):
                break
            time.sleep(0.1)
    out.sort()
    for a, c, _ in out:
        sys.stderr.write('%X-%X %d bytes\n' % (a, a + len(c) - 1, len(c)))
    for (a, c, _), (b, _, _) in zip(out, out[1:]):
        if a + len(c) > b:
            sys.exit('blocks at %X and %X overlap' % (a, b))
    for a, c, _ in out:
        if ROOM[0] <= a < ROOM[1] and a + len(c) > ROOM[1]:
            sys.exit('block at %X runs out of the free room' % a)
    lines = ['PATCHES = [  # (address, new bytes): exo/fixes.asm, assembled']
    for a, c, first in out:
        lines.append('    (0x%X, bytes.fromhex(  # %d bytes: %s'
                     % (a, len(c), first[:40]))
        h = c.hex()
        for i in range(0, len(h), 64):
            lines.append("        '%s'" % h[i:i + 64])
        lines.append('    )),')
    lines.append(']')
    if len(sys.argv) > 2 and sys.argv[1] == '--into':
        with open(sys.argv[2], encoding='utf-8', newline='') as f:
            src = f.read()
        nl = '\r\n' if '\r\n' in src else '\n'
        a = src.index(nl, src.index('# BEGIN PATCHES')) + len(nl)
        b = src.index('# END PATCHES', a)
        src = src[:a] + nl.join(lines) + nl + src[b:]
        with open(sys.argv[2], 'w', encoding='utf-8', newline='') as f:
            f.write(src)
    else:
        print('\n'.join(lines))


if __name__ == '__main__':
    main()
