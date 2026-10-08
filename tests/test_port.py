"""Tests of gfupdate.py that need no original: the fixes, the console.

    py test_port.py --terri DIR --tracy DIR

DIR as for compare_original.py; the files are copied to scratch folders.
"""
import argparse
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gfupdate  # noqa: E402
from compare_original import (SCENARIOS, TODAY, make_fixture,  # noqa: E402
                              normalise, run_port, setup_move,
                              setup_old_mtime)

fails = 0


def check(what, got, want):
    global fails
    if got != want:
        fails += 1
        print('FAIL %s:\n     got  %r\n     want %r' % (what, got, want))
    else:
        print('ok   %s' % what)


# the scenarios in which the fixes change something, and why
FIX_CHANGES = {
    'names': 'names',               # padding after names > 5, 14 chars
    'name15': 'names',
    'name_6_ctrl': 'names',
    'pu_birthdays': 'birthday',     # texts longer than 10
    'pa_birthdays': 'birthday',
    'bd_overflow_saved': 'birthday',
    'bd_long': 'birthday',
    'old_mtime': 'mtime',
    'no_pa': 'opengf',
    'open_cancel_pa': 'opengf',
}


def run_with(fixes, root, steps):
    m = gfupdate.GFUpdate(root, fixes=fixes, today=TODAY)
    states = [m.state()]
    for step in steps:
        if step[0] == 'text':
            m.set_text(step[1], step[2])
        elif step[0] == 'click':
            c = m.c[step[1]]
            if c.enabled and c.visible:
                m.click(step[1])
        elif step[0] == 'open':
            m.click(step[1], step[2] and os.path.normpath(
                os.path.join(root, step[2])))
        states.append(m.state())
    return m, states


def fixture(src, base, name, setups=()):
    d = os.path.join(base, name)
    make_fixture(src, d)
    for s in setups:
        s(d)
    return d


def read(path, a, b):
    with open(path, 'rb') as f:
        return f.read()[a:b]


def test_fixes(args, base):
    # every fix changes exactly the scenarios it should, and each one alone
    for name, (fx, setups, steps) in SCENARIOS.items():
        src = args.terri if fx == 'terri' else args.tracy
        off = [normalise(s, d) for d in [fixture(src, base, name + '-off',
                                                 setups)]
               for s in run_port(d, steps)]
        changed = []
        for fix in gfupdate.FIXES:
            d = fixture(src, base, '%s-%s' % (name, fix), setups)
            on = [normalise(s, d) for s in run_with((fix,), d, steps)[1]]
            if on != off:
                changed.append(fix)
        want = [FIX_CHANGES[name]] if name in FIX_CHANGES else []
        check('fixes changing %s' % name, changed, want)

    t = args.terri
    # names: no stale tail, no access violation, 15 characters saved
    d = fixture(t, base, 'names')
    m, _ = run_with(gfupdate.FIXES, d, [
        ('text', 'Name3Edit', 'Alexander'), ('click', 'TestPUBtn'),
        ('text', 'Name3Edit', 'Nicolas'), ('click', 'TestPUBtn')])
    check('Nicolas after Alexander', bytes(m.pu_rec[0:30]),
          b'Nicolas'.ljust(30))
    check('key of Nicolas', bytes(m.pu_rec[578:583]), b'Okfsq')
    m.set_text('Name3Edit', 'Abcdefghijklmno')
    m.click('TestPUBtn')
    check('15 chars: no box', m.dialogs, [])
    check('15 chars: OK', m.c['PUOKBtn'].enabled, True)
    m.click('PUOKBtn')
    p = os.path.join(d, 'PURSEU.DAT')
    check('15 chars saved, field 1', read(p, 0, 30),
          b'Abcdefghijklmno'.ljust(30))
    check('15 chars saved, field 2', read(p, 30, 50),
          b'Abcdefghijklmno'.ljust(20))
    check('15 chars saved, field 3', read(p, 50, 65), b'Abcdefghijklmno')
    m.set_text('Name3Edit', 'Al')
    m.click('TestPUBtn')
    check('short name pads the key with spaces', bytes(m.pu_rec[578:583]),
          b'Bn#$%')

    # birthday: a long text no longer spills into the next fields
    d = fixture(t, base, 'birthday')
    p = os.path.join(d, 'PURSEU.DAT')
    before = read(p, 0, 768)
    m, _ = run_with(gfupdate.FIXES, d, [
        ('text', 'MyBDEdit', 'December 8, 1972'), ('click', 'TestPUBtn'),
        ('text', 'MyBDEdit', '12/08/1972'), ('click', 'TestPUBtn'),
        ('click', 'PUOKBtn')])
    after = read(p, 0, 768)
    check('PURSEU unchanged after the text', after[81:], before[81:])
    check('PURSEU text', after[71:81], b'12/08/1972')
    pa = os.path.join(d, 'TERRI.GF', 'PURSEA.DAT')
    before = read(pa, 0, 512)
    run_with(gfupdate.FIXES, d, [
        ('text', 'GFBDEdit', 'March the 6th, 1966'), ('click', 'TestPABtn'),
        ('text', 'GFBDEdit', '3/6/1966'), ('click', 'TestPABtn'),
        ('click', 'PAOKBtn')])
    check('PURSEA unchanged after the text', read(pa, 52, 512), before[52:])

    # mtime: a file dated 1975 is found
    d = fixture(t, base, 'mtime', [setup_old_mtime])
    m, _ = run_with(gfupdate.FIXES, d, [])
    check('1975 file found', m.c['Name3Edit'].text, 'Nikel')

    # opengf: the chosen PURSEA.DAT is used although TERRI.GF exists
    d = fixture(t, base, 'opengf', [setup_move('TERRI.GF/PURSEA.DAT',
                                               'sub/PURSEA.DAT')])
    m, _ = run_with(gfupdate.FIXES, d, [
        ('open', 'OpenPABtn', 'sub/PURSEA.DAT'), ('click', 'TestPABtn'),
        ('click', 'PAOKBtn')])
    check('opened PURSEA used', m.papath, os.path.join(d, 'sub',
                                                       'PURSEA.DAT'))
    check('saved there', sorted(os.listdir(os.path.join(d, 'sub'))),
          ['PURSEA.BAK', 'PURSEA.DAT'])


def test_console(args, base):
    d = fixture(args.terri, base, 'console')
    lines = iter(['1', 'Bobby', '2', '1/2/1980', 't', 'w', '3', '2/3/1990',
                  'U', 'v', 'x', 'c'])
    out = io.StringIO()
    m = gfupdate.GFUpdate(d, today=TODAY)
    gfupdate.ConsoleView(m, gfupdate.Ansi('cp1252'),
                         inp=lambda prompt: next(lines), out=out).run()
    text = out.getvalue()
    check('console: closed', m.closed, True)
    check('console: name saved', read(os.path.join(d, 'PURSEU.DAT'), 0, 5),
          b'Bobby')
    check('console: PA saved', read(os.path.join(d, 'TERRI.GF',
                                                 'PURSEA.DAT'), 42, 52),
          b'2/3/1990  ')
    check('console: messages shown', 'New written as PURSEA.DAT' in text,
          True)
    check('console: unknown choice', '\n?\n' in text, True)
    # end of input closes it
    m = gfupdate.GFUpdate(d, today=TODAY)
    gfupdate.ConsoleView(m, gfupdate.Ansi('cp1252'),
                         inp=lambda p: (_ for _ in ()).throw(EOFError()),
                         out=io.StringIO()).run()
    check('console: EOF ends', True, True)
    # a missing PURSEU.DAT, opened by path; 16 characters are cut to 15
    d = fixture(args.terri, base, 'console2', [setup_move('PURSEU.DAT',
                                                          'sub/PURSEU.DAT')])
    lines = iter(['o', os.path.join(d, 'sub', 'PURSEU.DAT'), '1',
                  'Abcdefghijklmnop', 'c'])
    m = gfupdate.GFUpdate(d, today=TODAY)
    out = io.StringIO()
    gfupdate.ConsoleView(m, gfupdate.Ansi('cp1252'),
                         inp=lambda prompt: next(lines), out=out).run()
    check('console: opened', m.pupath, os.path.join(d, 'sub', 'PURSEU.DAT'))
    check('console: MaxLength', m.c['Name3Edit'].text, 'Abcdefghijklmno')
    check('console: not found shown', 'File PURSEU.DAT not found'
          in out.getvalue(), True)


def test_rtl():
    vl = gfupdate.val_long
    for s, want in [('12', (12, 0)), (' 12', (12, 0)), ('-0', (0, 0)),
                    ('$7D0', (2000, 0)), ('0x10', (16, 0)), ('x10', (16, 0)),
                    ('2147483647', (2147483647, 0)),
                    ('-2147483648', (-2147483648, 0)),
                    ('$FFFFFFFF', (-1, 0)), ('-$1', (-1, 0))]:
        check('ValLong %r' % s, vl(s), want)
    for s in ('', ' ', '-', '1 ', '2147483648', '-2147483649', '0x', '$',
              '1e3', '--1', '+-1', '$100000000'):
        check('ValLong %r fails' % s, vl(s)[1] != 0, True)
    sd = gfupdate.try_str_to_date
    check('date mm/dd/yyyy', sd('12/08/1972', 2026),
          gfupdate.encode_date(1972, 12, 8))
    check('date 2-digit year', sd('1/2/90', 2026),
          gfupdate.encode_date(1990, 1, 2))
    check('date 2-digit year 2020', sd('1/2/20', 2026),
          gfupdate.encode_date(2020, 1, 2))
    check('date no year', sd('1/2', 2026), gfupdate.encode_date(2026, 1, 2))
    check('date trailing /', sd('1/2/2000/', 2026),
          gfupdate.encode_date(2000, 1, 2))
    check('date junk', sd('1/2/2000x', 2026), None)
    check('trim', gfupdate.trim_spaces('  ab  ', 3), 'ab')
    check('trim single space', gfupdate.trim_spaces('   ', 3), '')
    check('word', gfupdate.extract_word('a/b/c/d', '/', 3), 'c')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--terri', required=True)
    ap.add_argument('--tracy', required=True)
    args = ap.parse_args()
    base = tempfile.mkdtemp(prefix='gfupdate-test-')
    try:
        test_rtl()
        test_fixes(args, base)
        test_console(args, base)
    finally:
        for dirpath, _dirs, files in os.walk(base):
            for f in files:
                os.chmod(os.path.join(dirpath, f), 0o600)
        shutil.rmtree(base, ignore_errors=True)
    print('%d failure(s)' % fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
