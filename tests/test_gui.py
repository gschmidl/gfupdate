"""Drive gfupdate.py's Tk window through its widgets (needs a display).

    py test_gui.py GAME_FOLDER

GAME_FOLDER holds PURSEU.DAT and TERRI.GF/PURSEA.DAT (Girlfriend Terri); it is
copied to a scratch folder first. On Windows the window is made on a private
desktop, so nothing shows on the screen. Message boxes and file dialogs are
intercepted.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

if os.name == 'nt':
    import orig_driver
    orig_driver.join_private_desktop()

import tkinter  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

import gfupdate  # noqa: E402
from compare_original import make_fixture  # noqa: E402

shown = []
answers = []
messagebox.showerror = lambda title, msg, **kw: shown.append((title, msg))
filedialog.askopenfilename = lambda **kw: answers.pop(0)

fails = 0


def check(what, got, want):
    global fails
    if got != want:
        fails += 1
        print('FAIL %s: %r, want %r' % (what, got, want))
    else:
        print('ok   %s' % what)


def view_for(folder, fixes=gfupdate.FIXES):
    ansi = gfupdate.Ansi('cp1252')
    m = gfupdate.GFUpdate(folder, fixes, ansi=ansi)
    v = gfupdate.TkView(m, ansi, tkinter)
    v.root.update()
    return m, v


def main():
    src = sys.argv[1]
    base = tempfile.mkdtemp(prefix='gfupdate-gui-')
    try:
        run(src, base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print('%d failure(s)' % fails)
    return 1 if fails else 0


def run(src, base):
    d = os.path.join(base, 'a')
    make_fixture(src, d)
    m, v = view_for(d)
    w = v.w
    check('name shown', v.vars['Name3Edit'].get(), 'Nikel')
    check('dir shown', v.vars['GFDirNmEdit'].get(), 'TERRI.GF')
    check('OK disabled', str(w['PUOKBtn'].cget('state')), 'disabled')
    check('Open hidden', w['OpenPUBtn'].winfo_ismapped(), 0)
    check('focus on name', v.root.focus_get() is w['Name3Edit'], True)
    # typing is limited to 15 characters, like MaxLength
    e = w['Name3Edit']
    e.delete(0, 'end')
    e.insert(0, 'Abcdefghijklmnopqrst')
    v.root.update()
    check('MaxLength 15', v.vars['Name3Edit'].get(), 'Abcdefghijklmno')
    e.insert(3, 'xyz')
    v.root.update()
    check('full edit takes nothing', v.vars['Name3Edit'].get(),
          'Abcdefghijklmno')
    e.delete(0, 'end')
    e.insert(0, 'Jos\xe9')
    v.vars['MyBDEdit'].set('7/4/1990')
    w['TestPUBtn'].invoke()
    v.root.update()
    check('age label', v.dyn['MyBDLb'].cget('text'),
          m.c['MyBDLb'].text)
    check('age label purple', v.dyn['MyBDLb'].cget('fg'), '#800080')
    check('OK enabled', str(w['PUOKBtn'].cget('state')), 'normal')
    # Return with the focus in an edit presses the default (OK) button
    e.focus_set()
    v.root.update()
    e.event_generate('<Return>')
    v.root.update()
    check('saved by Return', v.dyn['SaveLb'].cget('text'),
          'Old data saved as PURSEU.BAK\nNew written as PURSEU.DAT')
    with open(os.path.join(d, 'PURSEU.DAT'), 'rb') as f:
        data = f.read()
    check('name in file (cp1252)', data[:5], b'Jos\xe9 ')
    check('key in file', data[578:583], bytes((ord('J') + 1, ord('o') + 2,
                                               ord('s') + 3, 0xE9 + 4,
                                               ord(' ') + 5)))
    # an error message box
    v.vars['MyBDEdit'].set('257/1/2000')
    w['TestPUBtn'].invoke()
    check('exception box', shown[-1:],
          [('Gfupdate', "'257/1/2000' is not a valid date.")])
    # the checkbox
    w['SaveBakCheck'].invoke()
    check('bak unchecked', m.checked, False)
    # the girlfriend's side, Alt+T goes to the first enabled Test button
    v.vars['GFBDEdit'].set('3/6/1990')
    w['TestPUBtn'].configure(state='disabled')
    m.c['TestPUBtn'].enabled = False
    v._accel('t')
    check('Alt+T -> TestPABtn', v.dyn['GFBDLb'].cget('text').split('\n')[0],
          'I am %d years old' % int(abs(m.date - gfupdate.encode_date(
              1990, 3, 6)) / 365.25))
    v.root.destroy()

    # PURSEU.DAT missing: Open button, file dialog
    d = os.path.join(base, 'b')
    make_fixture(src, d)
    os.makedirs(os.path.join(d, 'sub'))
    os.rename(os.path.join(d, 'PURSEU.DAT'),
              os.path.join(d, 'sub', 'PURSEU.DAT'))
    m, v = view_for(d)
    w = v.w
    check('not found', v.dyn['SaveLb'].cget('text'),
          'File PURSEU.DAT not found')
    check('Open shown', w['OpenPUBtn'].winfo_ismapped(), 1)
    check('Open caption', v.dyn['OpenPULb'].cget('text'),
          'Find&open PURSEU.DAT')
    check('name disabled', str(w['Name3Edit'].cget('state')), 'disabled')
    answers.append('')
    w['OpenPUBtn'].invoke()
    check('cancel keeps it', w['OpenPUBtn'].winfo_ismapped(), 1)
    answers.append(os.path.join(d, 'sub', 'PURSEU.DAT').replace('\\', '/'))
    w['OpenPUBtn'].invoke()
    v.root.update()
    check('opened', v.vars['Name3Edit'].get(), 'Nikel')
    check('Open hidden again', w['OpenPUBtn'].winfo_ismapped(), 0)
    check('path', m.pupath, os.path.join(d, 'sub', 'PURSEU.DAT'))
    w['CloseBtn'].invoke()
    check('closed', m.closed, True)


if __name__ == '__main__':
    sys.exit(main())
