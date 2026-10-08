"""Test the two eXo patches on scratch copies (EXO_FOLDER is only read).

    py test_patches.py EXO_FOLDER

fix_windows.py: both GFUpdate.exe of EXO_FOLDER (their GFUpdate.exe.orig if
it is patched) are copied; then --check, the fix, a second run, --revert, a
changed exe that is refused, --force.

install_port.py: EXO_FOLDER's eXoDOS\\!dos\\gfterri and gftracy
exception.bat (their exception.bat.orig if it is patched) are copied; then
--check, the patch, a second patch (no change), and --revert (byte-identical
launchers again). On Windows the inserted lines are also run with cmd: with
py, with a stub gfupdate.py that records its arguments; without py (PATH
without it) and without gfupdate.py, the old GFUpdate line, a stub
GFUpdate.bat.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'exo'))
import install_port  # noqa: E402

fails = 0


def check(what, got, want):
    global fails
    if got != want:
        fails += 1
        print('FAIL %s:\n     got  %r\n     want %r' % (what, got, want))
    else:
        print('ok   %s' % what)


def run(cmd):
    r = subprocess.run([sys.executable, install_port.__file__] + cmd,
                       capture_output=True, text=True)
    return r.stdout


def run_block(exo, game, with_py, with_script):
    """Run the patched launcher's :modify part with cmd; what ran?"""
    bat = os.path.join(exo, 'eXoDOS', '!dos', game, 'exception.bat')
    with open(bat, encoding='latin-1', newline='') as f:
        text = f.read()
    part = text[text.index(':modify'):]
    part = part.replace('goto menu', 'goto end_of_test')
    test = os.path.join(exo, 'modify_test.bat')
    with open(test, 'w', encoding='latin-1', newline='') as f:
        f.write('@echo off\r\ncd /d "%s"\r\n' % os.path.join(
            exo, 'eXoDOS', '!dos', game))
        f.write(part + '\r\n:end_of_test\r\n')
    script = os.path.join(exo, 'util', 'gfupdate', 'gfupdate.py')
    out = os.path.join(exo, 'ran.txt')
    if os.path.exists(out):
        os.remove(out)
    if with_script:
        with open(script, 'w') as f:
            f.write('import os, sys\nopen(%r, "w").write("port " + '
                    '" ".join(sys.argv[1:]) + " in " + os.getcwd())\n' % out)
    elif os.path.exists(script):
        os.remove(script)
    env = dict(os.environ)
    env.pop('NoDefaultCurrentDirectoryInExePath', None)
    if not with_py:
        env['PATH'] = os.path.join(os.environ['SystemRoot'], 'System32')
    subprocess.run(['cmd', '/c', test], env=env, capture_output=True)
    if not os.path.exists(out):
        return None
    with open(out) as f:
        return f.read().replace(exo, '<exo>').strip()


def run_fix(cmd):
    r = subprocess.run([sys.executable, os.path.join(
        os.path.dirname(HERE), 'exo', 'fix_windows.py')] + cmd,
        capture_output=True, text=True)
    return r.returncode, r.stdout


def test_fix_windows(src):
    import fix_windows
    exo = tempfile.mkdtemp(prefix='gfupdate-exo-')
    try:
        exes = []
        for rel in fix_windows.TARGETS:
            orig = os.path.join(src, rel)
            if os.path.exists(orig + '.orig'):      # already fixed there
                orig += '.orig'
            dest = os.path.join(exo, rel)
            os.makedirs(os.path.dirname(dest))
            shutil.copyfile(orig, dest)
            exes.append(dest)
        with open(exes[0], 'rb') as f:
            original = f.read()
        with open(os.path.join(os.path.dirname(HERE), 'exo', 'GFUpdate.exe'),
                  'rb') as f:
            fixed = f.read()
        code, out = run_fix(['--check', exo])
        check('fix --check: 2 lines', (code, len(out.splitlines())), (0, 2))
        check('fix --check changes nothing', open(exes[0], 'rb').read(),
              original)
        code, out = run_fix([exo])
        for e in exes:
            check('fixed ' + e[len(exo):], open(e, 'rb').read(), fixed)
            check('.orig ' + e[len(exo):], open(e + '.orig', 'rb').read(),
                  original)
        check('fix again: nothing', run_fix([exo])[1].count('already'), 2)
        code, out = run_fix(['--revert', exo])
        for e in exes:
            check('reverted ' + e[len(exo):], open(e, 'rb').read(), original)
            check('.orig gone ' + e[len(exo):], os.path.exists(e + '.orig'),
                  False)
        with open(exes[1], 'ab') as f:
            f.write(b'x')
        code, out = run_fix([exo])
        check('other exe refused', (code, open(exes[1], 'rb').read()[-1:]),
              (1, b'x'))
        check('the known one fixed anyway', open(exes[0], 'rb').read(), fixed)
        code, out = run_fix(['--force', exo])
        check('--force replaces it', open(exes[1], 'rb').read(), fixed)
        run_fix(['--revert', exo])
        check('--force revert gives the changed one back',
              open(exes[1], 'rb').read()[-1:], b'x')
    finally:
        shutil.rmtree(exo, ignore_errors=True)


def main():
    src = sys.argv[1]
    test_fix_windows(src)
    exo = tempfile.mkdtemp(prefix='gfupdate-exo-')
    try:
        bats = {}
        for game in install_port.GAMES:
            d = os.path.join(exo, 'eXoDOS', '!dos', game)
            os.makedirs(d)
            orig = os.path.join(src, 'eXoDOS', '!dos', game, 'exception.bat')
            if os.path.exists(orig + '.orig'):      # already patched there
                orig += '.orig'
            shutil.copyfile(orig, os.path.join(d, 'exception.bat'))
            with open(os.path.join(d, 'exception.bat'), 'rb') as f:
                bats[game] = f.read()
        out = run(['--check', exo])
        check('--check lists 6 changes', len(out.splitlines()), 6)
        check('--check changes nothing', os.path.exists(
            os.path.join(exo, 'util')), False)
        run([exo])
        for game in install_port.GAMES:
            p = os.path.join(exo, 'eXoDOS', '!dos', game, 'exception.bat')
            with open(p, 'rb') as f:
                new = f.read()
            check('%s patched' % game, install_port.ours(
                install_port.GAMES[game][1]).encode() in new, True)
            check('%s CRLF kept' % game, new.count(b'\n'), new.count(b'\r\n'))
            check('%s .orig' % game, open(p + '.orig', 'rb').read(),
                  bats[game])
        check('port installed', sorted(os.listdir(os.path.join(
            exo, 'util', 'gfupdate'))), sorted(install_port.FILES))
        check('second run: nothing to do', run([exo]), '')
        if os.name == 'nt':
            for game, (exe, folder) in install_port.GAMES.items():
                gd = os.path.join(exo, *exe.split('\\')[1:-1])
                os.makedirs(gd, exist_ok=True)
                stub = os.path.join(gd, exe.split('\\')[-1] + '.bat')
                with open(stub, 'w') as f:
                    f.write('@echo exe %s> "%s"\n' % (game, os.path.join(
                        exo, 'ran.txt')))
                check('%s runs the port' % game,
                      run_block(exo, game, True, True),
                      'port -C %s in <exo>' % folder)
                check('%s without py: the exe' % game,
                      run_block(exo, game, False, True), 'exe %s' % game)
                check('%s without gfupdate.py: the exe' % game,
                      run_block(exo, game, True, False), 'exe %s' % game)
                os.remove(stub)
            run([exo])          # put the real files back
        run(['--revert', exo])
        for game in install_port.GAMES:
            p = os.path.join(exo, 'eXoDOS', '!dos', game, 'exception.bat')
            check('%s reverted' % game, open(p, 'rb').read(), bats[game])
            check('%s .orig gone' % game, os.path.exists(p + '.orig'), False)
        check('util/gfupdate gone', os.path.exists(
            os.path.join(exo, 'util', 'gfupdate')), False)
    finally:
        shutil.rmtree(exo, ignore_errors=True)
    print('%d failure(s)' % fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
