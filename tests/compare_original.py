"""A/B test: the original GFUpdate.exe against gfupdate.py --no-fixes.

    py compare_original.py --exe GFUpdate.exe --terri DIR --tracy DIR
                           [--keep] [--only NAME...] [--list]

Windows only (the original runs on a private desktop, see orig_driver.py).
DIR is a game folder with PURSEU.DAT and the *.GF folder (eXo's
gfterri\\gf_terri and gftracy\\GF, or the same files unpacked from the game
zips); only PURSEU.DAT and *.GF\\PURSEA.DAT are copied. Every scenario runs
in two fresh scratch folders, one per program, under the system temp folder.
After every step the whole form state (labels with colour, edits, buttons,
records in memory, file paths, message boxes) must be equal, and at the end
the files in both folders.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gfupdate  # noqa: E402

TODAY = datetime.date.today()


def ago(years, days=0):
    """A MM/DD/YYYY birthday `years` years (365.25 days) and `days` ago."""
    d = TODAY - datetime.timedelta(days=int(years * 365.25) + days)
    return '%02d/%02d/%04d' % (d.month, d.day, d.year)


def name_steps(*names):
    out = []
    for n in names:
        out += [('text', 'Name3Edit', n), ('click', 'TestPUBtn')]
    return out


def bd_steps(edit, button, *values):
    out = []
    for v in values:
        out += [('text', edit, v), ('click', button)]
    return out


BD_EDGE = ['', 'abc', '1/2/3', '12/08/1972', '2/30/2000', '02/29/2000',
           '02/29/1900', '13/1/2000', '0/1/2000', '257/1/2000', '1/2/999',
           '1/2/0999', '1/2/65536', '1/2/66536', '1/2/ 2000', ' 1/2/2000',
           '1/2/2000 ', '$C/2/2000', 'December 8, 1972', '12/08/19721',
           '01/02/02000', '01/02/  2000', '1/2/2000/', '1/2/2000/5',
           '+1/2/2000', '-1/2/2000', '1/-2/2000', '1/2/-2000', '1/2/x7D0',
           '0x1/2/2000', '1/2/2147483648', '1/2/0x', '1//2000', '/', '1/2',
           '  ', '1 /2/2000', '01/02/1990x', '1/2/1990 x', '1/2/90',
           '1/02/0090', 'x10/2/1990', '1/31/1990&a', '&&/1/1990']
PU_AGES = [ago(5), ago(8), ago(10), ago(13), ago(14), ago(14, -1),
           ago(14, 1), ago(15), ago(17), ago(18), ago(30), ago(110),
           ago(111), ago(115), ago(200), ago(201), ago(250), ago(0),
           ago(0, -1), ago(-3), ago(0, 1)]
PA_AGES = [ago(5), ago(9), ago(10), ago(12), ago(15), ago(16), ago(20),
           ago(24), ago(25), ago(30), ago(40), ago(41), ago(50), ago(60),
           ago(61), ago(70), ago(100), ago(101), ago(150), ago(-1)]


def setup_old_mtime(d):
    t = time.mktime((1975, 6, 1, 12, 0, 0, 0, 0, -1))
    os.utime(os.path.join(d, 'PURSEU.DAT'), (t, t))


def setup_readonly(name):
    def f(d):
        p = os.path.join(d, name)
        os.chmod(p, stat.S_IREAD)
    return f


def setup_short(name, size):
    def f(d):
        p = os.path.join(d, name)
        with open(p, 'r+b') as fh:
            fh.truncate(size)
    return f


def setup_move(src, dst):
    def f(d):
        os.makedirs(os.path.dirname(os.path.join(d, dst)) or d, exist_ok=True)
        os.rename(os.path.join(d, src), os.path.join(d, dst))
    return f


def setup_mkdir(name):
    def f(d):
        os.makedirs(os.path.join(d, name), exist_ok=True)
    return f


def setup_file(name, data=b'x'):
    def f(d):
        with open(os.path.join(d, name), 'wb') as fh:
            fh.write(data)
    return f


def setup_copy(src, dst):
    def f(d):
        shutil.copyfile(os.path.join(d, src), os.path.join(d, dst))
    return f


SAVE_PU = [('click', 'TestPUBtn'), ('click', 'PUOKBtn')]
SAVE_PA = [('click', 'TestPABtn'), ('click', 'PAOKBtn')]

SCENARIOS = {
    'start': ('terri', [], []),
    'start_tracy': ('tracy', [], []),
    'save_pu': ('terri', [], SAVE_PU),
    'save_pu_twice': ('terri', [], SAVE_PU + SAVE_PU),
    'save_pu_nobak': ('terri', [], [('click', 'SaveBakCheck')] + SAVE_PU),
    'save_pa': ('terri', [], SAVE_PA + SAVE_PA),
    'save_both_tracy': ('tracy', [], SAVE_PU + SAVE_PA),
    'test_twice_save': ('terri', [], [('click', 'TestPUBtn'),
                                      ('text', 'Name3Edit', 'Zed'),
                                      ('click', 'PUOKBtn')]),
    'names': ('terri', [], name_steps(
        '', 'A', 'Al', 'Abcde', 'Abcdef', 'Alexander', 'Nicolas', 'Bo',
        'Abcdefghijklm', 'Ni kel', ' ', 'X', 'Tab\there', 'Abcdefghijklmn',
        'Bob') + [('click', 'PUOKBtn')]),
    'name15': ('terri', [], name_steps('Abcdefghijklmno', 'Abcdefgh')
               + [('click', 'PUOKBtn')]),
    'name_6_ctrl': ('terri', [], name_steps('Abcde\x01', 'Abcdefgh\xe9')),
    'name_highbyte': ('terri', [], name_steps('\xc4\xe9\xf6\xfc\xdf') +
                      [('click', 'PUOKBtn')]),
    'name_space_bd_bad': ('terri', [], [('text', 'Name3Edit', 'A B'),
                                        ('text', 'MyBDEdit', 'x'),
                                        ('click', 'TestPUBtn')]),
    'pu_birthdays': ('terri', [], bd_steps('MyBDEdit', 'TestPUBtn',
                                           *BD_EDGE)),
    'pu_ages': ('terri', [], bd_steps('MyBDEdit', 'TestPUBtn', *PU_AGES)),
    'pa_birthdays': ('terri', [], bd_steps('GFBDEdit', 'TestPABtn',
                                           *BD_EDGE)),
    'pa_ages': ('terri', [], bd_steps('GFBDEdit', 'TestPABtn', *PA_AGES)),
    'bd_overflow_saved': ('terri', [], bd_steps(
        'MyBDEdit', 'TestPUBtn', 'December 8, 1972', '12/08/1972')
        + [('click', 'PUOKBtn')] + bd_steps(
        'GFBDEdit', 'TestPABtn', 'March the 6th, 1966', '3/6/1966')
        + [('click', 'PAOKBtn')]),
    'bd_long': ('terri', [], bd_steps('MyBDEdit', 'TestPUBtn', '1' * 300,
                                      '12/08/1972' + ' ' * 50)),
    'no_pu': ('terri', [setup_move('PURSEU.DAT', 'sub/PURSEU.DAT')],
              [('open', 'OpenPUBtn', None),
               ('open', 'OpenPUBtn', 'sub/nothere.dat'),
               ('open', 'OpenPUBtn', 'sub/PURSEU.DAT')] + SAVE_PU),
    'no_pa': ('terri', [setup_move('TERRI.GF/PURSEA.DAT', 'sub/PURSEA.DAT')],
              [('open', 'OpenPABtn', 'sub/PURSEA.DAT')]),
    'no_gf_dir': ('terri', [setup_move('TERRI.GF/PURSEA.DAT', 'PURSEA.DAT'),
                            lambda d: os.rmdir(os.path.join(d, 'TERRI.GF'))],
                  SAVE_PA),
    'no_gf_dir_no_pa': ('terri', [setup_move('TERRI.GF/PURSEA.DAT',
                                             'sub/PURSEA.DAT'),
                                  lambda d: os.rmdir(os.path.join(d,
                                                                  'TERRI.GF'))],
                        [('open', 'OpenPABtn', 'sub/PURSEA.DAT')] + SAVE_PA),
    'nothing': ('terri', [setup_move('TERRI.GF/PURSEA.DAT', 'sub/PURSEA.DAT'),
                          setup_move('PURSEU.DAT', 'sub/PURSEU.DAT')],
                [('text', 'GFDirNmEdit', 'whatever')]),
    'two_gf_dirs': ('terri', [setup_mkdir('ALPHA.GF'), setup_mkdir('zeta.gf')],
                    []),
    'gf_file_first': ('terri', [setup_file('A.GF')], []),
    'gf_lower': ('terri', [setup_move('TERRI.GF', 'terri.gf')], SAVE_PA),
    'short_pu': ('terri', [setup_short('PURSEU.DAT', 100)], []),
    'short_pa': ('terri', [setup_short('TERRI.GF/PURSEA.DAT', 10)], []),
    'readonly_pu': ('terri', [setup_readonly('PURSEU.DAT')], []),
    'readonly_bak': ('terri', [setup_copy('PURSEU.DAT', 'PURSEU.BAK'),
                               setup_readonly('PURSEU.BAK')], SAVE_PU),
    'old_mtime': ('terri', [setup_old_mtime], []),
    'pu_is_dir': ('terri', [setup_move('PURSEU.DAT', 'x.dat'),
                            setup_mkdir('PURSEU.DAT')], []),
    'bak_dir': ('terri', [setup_mkdir('PURSEU.BAK')], SAVE_PU),
    'open_cancel_pa': ('terri', [setup_move('TERRI.GF/PURSEA.DAT', 'x/PURSEA.DAT')],
                       [('open', 'OpenPABtn', None),
                        ('open', 'OpenPABtn', 'x/PURSEA.DAT')]),
}

AV_READ = re.compile(r"(Access violation at address [0-9A-F]{8} in module "
                     r"'GFUpdate.exe')\. Read of address [0-9A-F]{8}\.")


def normalise(st, root):
    st = json.loads(json.dumps(st))
    for k in ('exedir', 'pupath', 'papath'):
        if k in st:
            p = st[k].replace('/', '\\')
            r = root.replace('/', '\\')
            if p.lower().startswith(r.lower()):
                p = '<root>' + p[len(r):]
            st[k] = p.lower()
    for d in st.get('dialogs', []):
        d['text'] = [AV_READ.sub(r'\1.', t) for t in d['text']]
    return st


def tree(root):
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for f in files:
            if f.lower() == 'gfupdate.exe':
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root).replace('\\', '/').lower()
            with open(p, 'rb') as fh:
                out[rel] = hashlib.md5(fh.read()).hexdigest()
        for d in dirs:
            rel = os.path.relpath(os.path.join(dirpath, d), root)
            out[rel.replace('\\', '/').lower() + '/'] = 'dir'
    return out


def make_fixture(src, dst, exe=None):
    os.makedirs(dst)
    shutil.copy2(os.path.join(src, 'PURSEU.DAT'), dst)
    for n in os.listdir(src):
        if n.upper().endswith('.GF') and os.path.isdir(os.path.join(src, n)):
            os.makedirs(os.path.join(dst, n))
            shutil.copy2(os.path.join(src, n, 'PURSEA.DAT'),
                         os.path.join(dst, n))
    if exe:
        shutil.copy2(exe, dst)


def unlock(root):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            os.chmod(os.path.join(dirpath, f), stat.S_IWRITE | stat.S_IREAD)


def run_original(exe_dir, steps):
    import orig_driver as d
    o = d.Original(os.path.join(exe_dir, 'GFUpdate.exe'), exe_dir)
    states = [o.state()]
    try:
        for step in steps:
            if step[0] == 'text':
                o.set_text(step[1], step[2])
            elif step[0] == 'click':
                if not o.can_click(step[1]):
                    states.append({'skipped': step[1]})
                    continue
                o.click(step[1])
            elif step[0] == 'open':
                path = step[2] and os.path.normpath(os.path.join(exe_dir,
                                                                 step[2]))
                o.click(step[1], dialog_hook=lambda oo, p=path:
                        d_open_dialog(oo, p))
            states.append(o.state())
    finally:
        o.close()
    return states


def d_open_dialog(o, path, timeout=15.0):
    """Answer the original's TOpenDialog: type path and OK, or Cancel."""
    import ctypes

    import orig_driver as d

    def find():
        for h in d.top_windows(o.pid):
            if d.class_name(h) == '#32770' and d.user32.IsWindowVisible(h):
                kids = d.child_windows(h)
                edits = [c for c in kids if d.class_name(c) == 'Edit']
                if edits:
                    return h, edits[0], kids
        return None

    t0 = time.time()
    while time.time() - t0 < timeout:
        found = find()
        if not found:
            time.sleep(0.1)
            continue
        time.sleep(0.5)                 # let the dialog finish setting up
        h, edit, kids = found
        want = 1 if path else 2         # Open / Cancel
        if path:
            buf = ctypes.create_string_buffer(path.encode('mbcs'))
            res = ctypes.c_size_t()
            d.user32.SendMessageTimeoutA(
                edit, d.WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value,
                0, 3000, ctypes.byref(res))
            assert d.get_text(edit) == path, d.get_text(edit)
        for b in kids:
            if (d.class_name(b) == 'Button'
                    and d.user32.GetDlgCtrlID(b) == want):
                wparam = (d.BN_CLICKED << 16) | want
                d.user32.PostMessageW(h, d.WM_COMMAND, wparam, b)
        t1 = time.time()
        while time.time() - t1 < 5:
            if find() is None:
                return
            time.sleep(0.1)
        raise TimeoutError('open dialog did not close')
    raise TimeoutError('no open dialog')


def run_port(exe_dir, steps, today=TODAY, fixes=()):
    m = gfupdate.GFUpdate(exe_dir, fixes=fixes, today=today)
    states = [m.state()]
    for step in steps:
        if step[0] == 'text':
            m.set_text(step[1], step[2])
        elif step[0] == 'click':
            c = m.c[step[1]]
            if not (c.enabled and c.visible):
                states.append({'skipped': step[1]})
                continue
            m.click(step[1])
        elif step[0] == 'open':
            m.click(step[1], step[2] and os.path.normpath(
                os.path.join(exe_dir, step[2])))
        states.append(m.state())
    return states


def diff(a, b, path=''):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += diff(a.get(k), b.get(k), path + '.' + str(k))
    elif a != b:
        if isinstance(a, str) and isinstance(b, str) and len(a) > 64:
            i = next(i for i in range(min(len(a), len(b)) + 1)
                     if i >= len(a) or i >= len(b) or a[i] != b[i])
            out.append('%s: differ at %d: %r / %r' % (path, i, a[i:i + 24],
                                                      b[i:i + 24]))
        else:
            out.append('%s: %r / %r' % (path, a, b))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', help='the original (not needed with --replay)')
    ap.add_argument('--terri', required=True)
    ap.add_argument('--tracy', required=True)
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--save', metavar='JSON',
                    help="record the original's results (for --replay)")
    ap.add_argument('--replay', metavar='JSON',
                    help='compare the port with recorded results instead of '
                         'running the original (any OS)')
    ap.add_argument('--fixes', action='store_true',
                    help="the port with its fixes (for exo/GFUpdate.exe, the "
                         "fixed original)")
    ap.add_argument('--no-invoker', action='store_true',
                    help='start the exe without __COMPAT_LAYER=RunAsInvoker '
                         '(fails with error 740 without a manifest)')
    args = ap.parse_args()
    if args.no_invoker:
        import orig_driver
        orig_driver.Original.as_invoker = False
    if args.list:
        print('\n'.join(SCENARIOS))
        return 0
    if not args.replay and not args.exe:
        ap.error('--exe or --replay is needed')
    record = {}
    if args.replay:
        with open(args.replay, encoding='utf-8') as f:
            record = json.load(f)
    base = tempfile.mkdtemp(prefix='gfupdate-ab-')
    fails = 0
    names = args.only or (list(record) if args.replay else list(SCENARIOS))
    for name in names:
        fixture, setups, steps = SCENARIOS[name]
        today = TODAY
        if args.replay:
            rec = record[name]
            steps = [tuple(s) for s in rec['steps']]
            today = datetime.date.fromisoformat(rec['today'])
        src = args.terri if fixture == 'terri' else args.tracy
        oroot = os.path.join(base, name, 'orig')
        proot = os.path.join(base, name, 'port')
        make_fixture(src, proot)
        for s in setups:
            s(proot)
        if args.replay:
            so, to = rec['states'], rec['tree']
        else:
            make_fixture(src, oroot, args.exe)
            for s in setups:
                s(oroot)
            so = [normalise(st, oroot) for st in run_original(oroot, steps)]
            unlock(oroot)
            to = tree(oroot)
            record[name] = {'steps': steps, 'today': TODAY.isoformat(),
                            'states': so, 'tree': to}
        sp = [normalise(st, proot) for st in run_port(
            proot, steps, today, gfupdate.FIXES if args.fixes else ())]
        problems = []
        for i, (a, b) in enumerate(zip(so, sp)):
            for line in diff(a, b):
                problems.append('step %d %s %s' % (i, steps[i - 1] if i else
                                                   '(start)', line))
        if len(so) != len(sp):
            problems.append('state counts %d / %d' % (len(so), len(sp)))
        unlock(proot)
        tp = tree(proot)
        for line in diff(to, tp):
            problems.append('files ' + line)
        if problems:
            fails += 1
            print('FAIL %s' % name)
            for p in problems[:40]:
                print('   ' + p)
        else:
            print('ok   %s (%d steps)' % (name, len(steps)))
    if args.save:
        with open(args.save, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=0)
    if not args.keep:
        shutil.rmtree(base, ignore_errors=True)
    else:
        print('kept', base)
    print('%d/%d scenarios identical' % (len(names) - fails, len(names)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
