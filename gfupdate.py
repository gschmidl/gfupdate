#!/usr/bin/env python3
"""gfupdate.py - platform-independent port of GFUpdate.exe ("GirlFriend Change")

GFUpdate.exe (2017, Delphi 7) edits the player data of the DOS games
"Girlfriend Terri" and "Girlfriend Tracy": the player's name and birthday in
PURSEU.DAT and the girlfriend's birthday in <name>.GF/PURSEA.DAT. eXoDOS runs
it from the games' "Modify the Games User Information" menu entry.

This port does the same with Python 3.8+ and only the standard library: a Tk
window laid out like the original form, or a console version (--console, or
automatically when Tk or a display is missing).

    gfupdate.py [-C DIR] [--console] [--no-fixes] [--codepage CP]

DIR is the folder the original exe sits in (with PURSEU.DAT and the *.GF
folder); the default is the folder of this script. --no-fixes behaves exactly
like the original, bugs included (see README.md, "Differences").
"""
import argparse
import datetime
import errno
import fnmatch
import os
import sys
import time

VERSION = '1.0'
TITLE = 'GirlFriend Change'
APP_TITLE = 'Gfupdate'          # Application.Title: the exe name, CharLower'd

# --- the records (offsets found in GFUpdate.exe, see NOTES.md) -------------
PU_SIZE = 768                   # PURSEU.DAT: user data
PU_NAME = ((0, 30), (30, 20), (50, 15))     # three name fields
PU_DATE = 65                    # month, 0, day, 0, year (word)
PU_TEXT = 71                    # birthday as text, 10 chars
PU_KEY = 578                    # name[i] + i for i = 1..5
PA_SIZE = 512                   # PURSEA.DAT: girlfriend data
PA_DATE = 36
PA_TEXT = 42
TEXT_LEN = 10

# --- Delphi colours (TColor, $00BBGGRR) ------------------------------------
CL_BLACK = 0x000000
CL_MAROON = 0x000080
CL_RED = 0x0000FF
CL_NAVY = 0x800000
CL_PURPLE = 0x800080
CL_TEAL_DARK = 0x02504000       # the form's own dark teal (38813696)
CL_FORM = 0x02D8D0B0            # MainForm.Color
CL_TITLE = 0x02E8E0C0           # PgmLabel/Label10.Color

# TestBD: per kind (1 = player, 2 = girlfriend) the prefix and age range
PREFIX = {1: 'You are ', 2: 'I am '}
AGE_MAX = {1: 200, 2: 60}
AGE_MIN = {1: 14, 2: 10}

# fixes of the original's bugs; --no-fixes turns all off (see README.md)
FIXES = ('names', 'birthday', 'mtime', 'opengf')

DELPHI_EPOCH = datetime.date(1899, 12, 30).toordinal()
TWO_DIGIT_YEAR_WINDOW = 50      # SysUtils.TwoDigitYearCenturyWindow


class DelphiError(Exception):
    """An exception the original shows in a message box (and survives)."""

    def dialog(self):
        # TApplication.ShowException: a '.' is added unless the message ends
        # in a character <= '.'
        msg = str(self)
        if msg and msg[-1] > '.':
            msg += '.'
        return {'title': APP_TITLE, 'text': [msg]}


class ConvertError(DelphiError):
    pass


IO_MESSAGES = {2: 'File not found', 3: 'Invalid filename',
               4: 'Too many open files', 5: 'File access denied',
               100: 'Read beyond end of file', 101: 'Disk full',
               106: 'Invalid numeric input'}

ERRNO_TO_WIN = {errno.ENOENT: 2, errno.ENOTDIR: 3, errno.ENAMETOOLONG: 3,
                errno.EMFILE: 4, errno.ENFILE: 4, errno.EACCES: 5,
                errno.EPERM: 5, errno.EISDIR: 5, errno.EROFS: 19,
                errno.ENOSPC: 112}


def in_out_error(code):
    """SysUtils.CreateInOutError."""
    return DelphiError(IO_MESSAGES.get(code, 'I/O error %d' % code))


def os_error_code(e):
    """The Win32 error code GetLastError would give for an OSError."""
    code = getattr(e, 'winerror', None)
    if code:
        return code
    return ERRNO_TO_WIN.get(e.errno, e.errno or 0)


def access_violation(addr, kind=None, target=None):
    # The original's message also names the address it read; when that
    # depends on its heap layout it is left out here.
    msg = "Access violation at address %08X in module 'GFUpdate.exe'." % addr
    if kind:
        msg = msg[:-1] + '. %s of address %08X' % (kind, target & 0xFFFFFFFF)
    return DelphiError(msg)


# --- Delphi 7 RTL, as compiled into GFUpdate.exe ---------------------------
def val_long(s):
    """System._ValLong -> (value, error position or 0)."""
    if not s:
        return 0, 1
    s += '\0'
    i = 0
    while s[i] == ' ':
        i += 1
    c = s[i]
    i += 1
    neg = False
    if c == '-':
        neg = True
        c = s[i]
        i += 1
    elif c == '+':
        c = s[i]
        i += 1
    hexa = False
    if c in '$xX':
        hexa = True
    elif c == '0':
        c = s[i]
        i += 1
        if c in 'xX':
            hexa = True
        elif c == '\0':
            return 0, 0
    elif c == '\0':
        return 0, i
    v = 0
    if hexa:
        c = s[i]
        i += 1
        if c == '\0':
            return 0, i + 1
        while True:
            b = ord(c)
            if b >= 0x61:
                b = (b - 0x20) & 0xFF
            b = (b - 0x30) & 0xFF
            if b > 9:
                b = (b - 0x11) & 0xFF
                if b > 5:
                    return 0, i
                b += 10
            if v > 0x0FFFFFFF:
                return 0, i
            v = (v << 4) + b
            c = s[i]
            i += 1
            if c == '\0':
                break
        if neg:
            v = -v
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v & 0x80000000 else v, 0
    while True:
        b = (ord(c) - 0x30) & 0xFF
        if b > 9 or v > 0x0CCCCCCC:
            return 0, i
        v = v * 10 + b
        c = s[i]
        i += 1
        if c == '\0':
            break
    if neg:
        v = -v
        if v < -0x80000000:     # neg overflowed into a positive number
            return 0, i
        return v, 0
    if v > 0x7FFFFFFF:
        return 0, i
    return v, 0


def str_to_int(s):
    v, code = val_long(s)
    if code:
        raise ConvertError("'%s' is not a valid integer value" % s)
    return v


def is_leap_year(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    return (31, 29 if is_leap_year(y) else 28, 31, 30, 31, 30, 31, 31, 30,
            31, 30, 31)[m - 1]


def is_valid_date(y, m, d):
    """DateUtils.IsValidDate (Word arguments)."""
    return 1 <= y <= 9999 and 1 <= m <= 12 and 1 <= d <= days_in_month(y, m)


def encode_date(y, m, d):
    return datetime.date(y, m, d).toordinal() - DELPHI_EPOCH


def try_str_to_date(s, current_year):
    """SysUtils.TryStrToDate with ShortDateFormat 'mm/dd/yyyy' and
    DateSeparator '/' (set by FormCreate); None if not a date."""
    pos = [0]

    def blanks():
        while pos[0] < len(s) and s[pos[0]] == ' ':
            pos[0] += 1

    def number():
        blanks()
        i = pos[0]
        n = 0
        while i < len(s) and '0' <= s[i] <= '9' and n < 1000:
            n = n * 10 + ord(s[i]) - 48
            i += 1
        if i > pos[0]:
            count = (i - pos[0]) & 0xFF
            pos[0] = i
            return n, count
        return None

    def char(ch):
        blanks()
        if pos[0] < len(s) and s[pos[0]] == ch:
            pos[0] += 1
            return True
        return False

    n1 = number()
    if n1 is None or not char('/'):
        return None
    n2 = number()
    if n2 is None:
        return None
    if char('/'):
        n3 = number()
        if n3 is None:
            return None
        y, ylen = n3
        m, d = n1[0], n2[0]
        if ylen <= 2:
            base = current_year - TWO_DIGIT_YEAR_WINDOW
            y = (y + base // 100 * 100) & 0xFFFF
            if TWO_DIGIT_YEAR_WINDOW > 0 and base > y:
                y = (y + 100) & 0xFFFF
    else:
        y, m, d = current_year, n1[0], n2[0]
    char('/')
    blanks()
    if not is_valid_date(y, m, d) or pos[0] < len(s):
        return None
    return encode_date(y, m, d)


def str_to_date(s, current_year):
    v = try_str_to_date(s, current_year)
    if v is None:
        raise ConvertError("'%s' is not a valid date" % s)
    return v


def trim_spaces(s, mode):
    """GFUpdate's own trim (unit at 458F34): spaces only; mode 1 = left,
    2 = right, 3 = both; a lone remaining space becomes ''."""
    n = len(s) & 0xFF
    if n == 0:
        return ''
    i = 1
    if mode & 1:
        while n > i and s[i - 1] == ' ':
            i += 1
    if mode in (2, 3):
        while n > i and s[n - 1] == ' ':
            n -= 1
    r = s[i - 1:n]
    return '' if r == ' ' else r


def extract_word(s, delim, n):
    """GFUpdate's word splitter (458E40): the n-th delim-separated part."""
    count = 1
    out = []
    for ch in s:
        if ch == delim:
            count += 1
        elif count == n:
            out.append(ch)
        if count > n:
            break
    return ''.join(out)


def change_file_ext(path, ext):
    i = max(path.rfind('.'), path.rfind(os.sep), path.rfind('/'))
    if i < 0 or path[i] != '.':
        return path + ext
    return path[:i] + ext


# --- files -----------------------------------------------------------------
def resolve(path):
    """The existing entry for path, matched without regard to case where the
    file system cares (Windows, and Wine running the original, do not)."""
    if os.path.lexists(path) or os.name == 'nt':
        return path
    head, tail = os.path.split(path)
    if not tail:
        return path
    head = resolve(head) if head else head
    try:
        names = os.listdir(head or '.')
    except OSError:
        return os.path.join(head, tail)
    if tail in names:
        return os.path.join(head, tail)
    low = tail.lower()
    for n in names:
        if n.lower() == low:
            return os.path.join(head, n)
    return os.path.join(head, tail)


class Ctl:
    """The state of one control of the form."""

    def __init__(self, text='', enabled=True, visible=True, color=None):
        self.text = text
        self.enabled = enabled
        self.visible = visible
        self.color = color


LABELS = ('NameLb', 'MyBDLb', 'DirLabel', 'DirLb', 'GFBDLb', 'OpenPULb',
          'SaveLb', 'OpenPALb')
EDITS = ('Name3Edit', 'MyBDEdit', 'GFDirNmEdit', 'GFBDEdit')
BUTTONS = ('TestPUBtn', 'OpenPUBtn', 'PUOKBtn', 'TestPABtn', 'PAOKBtn',
           'OpenPABtn', 'SaveBakCheck', 'CloseBtn')
MAXLEN = {'Name3Edit': 15, 'GFDirNmEdit': 30}


class GFUpdate:
    """TMainForm without the pixels: GFUpdate.exe's logic and control state.

    Strings are byte strings shown as str (one character per byte, latin-1),
    exactly what the original keeps in its ANSI strings and records. Event
    methods mirror the original's handlers; a DelphiError ends a handler and
    becomes a message box (self.dialogs), as Application.HandleException
    does.
    """

    def __init__(self, folder, fixes=FIXES, today=None, ansi=None):
        self.fixes = set(fixes)
        self._today = today
        self.ansi = ansi or Ansi('cp1252')  # for file names shown
        self.dialogs = []
        self.closed = False
        self._leaked = []           # files the original leaves open
        self._opened_pa = None      # PURSEA.DAT chosen with Open
        c = self.c = {}
        for k in ('NameLb', 'MyBDLb', 'DirLb', 'GFBDLb', 'SaveLb'):
            c[k] = Ctl('', color=CL_NAVY)
        c['DirLabel'] = Ctl('Directory', color=CL_BLACK)
        c['OpenPULb'] = Ctl('Find&&open PURSEU.DAT', color=CL_TEAL_DARK)
        c['OpenPALb'] = Ctl('Find&&open PURSEA.DAT', color=CL_TEAL_DARK)
        for k in EDITS:
            c[k] = Ctl('?')
        for k in BUTTONS:
            c[k] = Ctl(enabled=k in ('SaveBakCheck', 'CloseBtn'))
        self.checked = True
        self.pu_rec = bytearray(PU_SIZE)
        self.pa_rec = bytearray(PA_SIZE)
        self.exedir = os.path.join(os.path.abspath(folder), '')
        self.pupath = ''
        self.papath = ''
        self._call(self._form_create)

    # --- plumbing ---
    def today(self):
        return self._today or datetime.date.today()

    def _call(self, fn, *args):
        try:
            fn(*args)
        except DelphiError as e:
            self.dialogs.append(e.dialog())

    def set_text(self, name, text):
        """The user edits a TEdit (text as bytes-in-str)."""
        self.c[name].text = text

    def click(self, name, *args):
        """The user clicks a button (only enabled, visible ones)."""
        ctl = self.c[name]
        if not (ctl.enabled and ctl.visible):
            raise RuntimeError('%s is disabled or hidden' % name)
        if name == 'SaveBakCheck':
            self.checked = not self.checked
            return
        handler = {'TestPUBtn': self._test_pu, 'TestPABtn': self._test_pa,
                   'PUOKBtn': self._pu_ok, 'PAOKBtn': self._pa_ok,
                   'OpenPUBtn': self._open_pu, 'OpenPABtn': self._open_pa,
                   'CloseBtn': self._close}[name]
        self._call(handler, *args)

    def state(self):
        st = {'alive': not self.closed}
        for k in LABELS:
            c = self.c[k]
            st[k] = {'text': c.text, 'color': c.color, 'visible': c.visible}
        for k in EDITS + BUTTONS:
            c = self.c[k]
            st[k] = {'enabled': c.enabled, 'visible': c.visible}
            if k in EDITS:
                st[k]['text'] = c.text.split('\0', 1)[0]
        st['checked'] = self.checked
        st['exedir'] = self.exedir
        st['pupath'] = self.pupath
        st['papath'] = self.papath
        st['pu_rec'] = self.pu_rec.hex()
        st['pa_rec'] = self.pa_rec.hex()
        st['dialogs'] = list(self.dialogs)
        return st

    # --- SysUtils on files ---
    def file_exists(self, path):
        """SysUtils.FileExists = FileAge(path) <> -1: an existing file (not a
        directory) whose local time fits a DOS date (1980..2107)."""
        path = resolve(path)
        try:
            st = os.stat(path)
        except (OSError, ValueError):
            return False
        if os.path.isdir(path):
            return False
        if 'mtime' not in self.fixes:
            try:
                year = time.localtime(st.st_mtime).tm_year
            except (OverflowError, OSError, ValueError):
                return False
            if not 1980 <= year <= 2107:
                return False
        return True

    def find_first(self, folder, pattern):
        """SysUtils.FindFirst(folder + pattern, faAnyFile): the first name."""
        try:
            names = os.listdir(folder)
        except OSError:
            return None
        if os.name != 'nt':
            names.sort(key=str.upper)
        pat = pattern.upper()
        for n in names:
            if fnmatch.fnmatchcase(n.upper(), pat):
                return n
        return None

    def read_record(self, path, rec):
        """AssignFile; Reset(F, size); Read(F, rec); Close(F) with {$I+}."""
        path = resolve(path)
        try:
            f = open(path, 'r+b')       # FileMode 2: read/write
        except OSError as e:
            raise in_out_error(os_error_code(e)) from None
        try:
            data = f.read(len(rec))
        except OSError as e:
            self._leaked.append(f)      # the original never closes it
            raise in_out_error(os_error_code(e)) from None
        rec[:len(data)] = data
        if len(data) != len(rec):
            self._leaked.append(f)
            raise in_out_error(100)
        f.close()

    def write_record(self, path, rec):
        """AssignFile; Rewrite(F, size); Write(F, rec); Close(F)."""
        path = resolve(path)
        try:
            f = open(path, 'w+b')
        except OSError as e:
            raise in_out_error(os_error_code(e)) from None
        try:
            f.write(rec)
            f.flush()
        except OSError as e:
            self._leaked.append(f)
            raise in_out_error(os_error_code(e)) from None
        f.close()

    # --- TMainForm ---
    def _form_create(self):
        # NameLb, MyBDLb, GFBDLb, DirLb, SaveLb.ParentColor := True (view)
        self.date = encode_date(*self.today().timetuple()[:3])
        self.pupath = self.exedir + 'PURSEU.DAT'
        self._reset_pu()
        self.papath = self.exedir + 'PURSEA.DAT'
        self._reset_pa()

    def _comment(self, label, text, color):
        lb = self.c[label]
        lb.color = color
        lb.text = text if lb.text == '' else lb.text + '\r' + text

    def _clean_labels(self, which):
        if which == 1:
            self.c['NameLb'].text = self.c['MyBDLb'].text = ''
        elif which == 2:
            self.c['GFBDLb'].text = self.c['DirLb'].text = ''
        self.c['SaveLb'].text = ''

    def _reset_pu(self):
        c = self.c
        if self.file_exists(self.pupath):
            self.pupath = resolve(self.pupath)
            c['OpenPUBtn'].visible = False
            c['OpenPULb'].visible = False
            c['TestPUBtn'].enabled = True
            c['Name3Edit'].enabled = True
            c['MyBDEdit'].enabled = True
            self.read_record(self.pupath, self.pu_rec)
            name = self.pu_rec[50:65].decode('latin-1')
            c['Name3Edit'].text = trim_spaces(name, 3).split('\0', 1)[0]
            text = self.pu_rec[PU_TEXT:PU_TEXT + TEXT_LEN].decode('latin-1')
            c['MyBDEdit'].text = trim_spaces(text, 3).split('\0', 1)[0]
        else:
            c['Name3Edit'].enabled = False
            c['MyBDEdit'].enabled = False
            self._comment('SaveLb', 'File PURSEU.DAT not found', CL_RED)
            c['OpenPUBtn'].enabled = True
            c['OpenPULb'].visible = True

    def _reset_pa(self):
        c = self.c
        gf = self.find_first(self.exedir, '*.GF')
        if gf is not None:
            c['DirLabel'].visible = True
            c['GFDirNmEdit'].visible = True
            c['GFDirNmEdit'].text = self.ansi.to_bytes(gf)
            if self._opened_pa is None or 'opengf' not in self.fixes:
                self.papath = self.exedir + gf + os.sep + 'PURSEA.DAT'
        else:
            c['DirLabel'].visible = False
            c['GFDirNmEdit'].visible = False
        if self.file_exists(self.papath):
            self.papath = resolve(self.papath)
            c['OpenPABtn'].visible = False
            c['OpenPALb'].visible = False
            c['TestPABtn'].enabled = True
            c['GFDirNmEdit'].enabled = True
            c['GFBDEdit'].enabled = True
            self.read_record(self.papath, self.pa_rec)
            text = self.pa_rec[PA_TEXT:PA_TEXT + TEXT_LEN].decode('latin-1')
            c['GFBDEdit'].text = trim_spaces(text, 3).split('\0', 1)[0]
        else:
            c['GFBDEdit'].enabled = False
            self._comment('SaveLb', 'File PURSEA.DAT not found', CL_RED)
            c['OpenPABtn'].enabled = True
            c['OpenPALb'].visible = True

    def _open_pu(self, path):
        """OpenPUBtnClick; path is the dialog's file name, None = Cancel."""
        if path:
            self.pupath = path
            self._clean_labels(1)
            self._reset_pu()

    def _open_pa(self, path):
        if path:
            self.papath = path
            self._opened_pa = path
            self._clean_labels(2)
            self._reset_pa()

    def _close(self):
        self.closed = True

    def _to_int(self, s, label):
        try:
            return str_to_int(s)
        except ConvertError:
            self.c[label].text = ("'" + s + "' is not integer value!"
                                  ).split('\0', 1)[0]
            return 0

    def _test_bd(self, edit, label, rec, text_off, date_off, which):
        """TMainForm.TestBD: check a birthday, store it in rec; returns the
        number of errors."""
        err = 0
        s = self.c[edit].text
        n = len(s)
        if 'birthday' in self.fixes:
            n = min(n, TEXT_LEN)
        for i in range(n):
            if text_off + i < len(rec):     # the original writes on
                rec[text_off + i] = ord(s[i])
        for i in range(n, TEXT_LEN):
            rec[text_off + i] = 0x20
        s10 = s[:255][:TEXT_LEN]
        m = self._to_int(extract_word(s, '/', 1), label)
        d = self._to_int(extract_word(s, '/', 2), label) & 0xFF
        y = self._to_int(extract_word(s, '/', 3), label)
        age = 0
        if is_valid_date(y & 0xFFFF, m & 0xFF, d):
            if y & 0xFFFF < 1000:
                self._comment(label, 'The year must contain 4 digits!',
                              CL_RED)
                err += 1
            else:
                bd = str_to_date(s10, self.today().year)
                age = int(abs(self.date - bd) / 365.25)
                if self.date < bd:
                    age = -age
                self._comment(label, PREFIX[which] + str(age) + ' years old',
                              CL_PURPLE)
                self._age_comment(label, age, which)
            if age > AGE_MAX[which] or age < AGE_MIN[which]:
                err += 1
        else:
            self._comment(label, 'Invalid date!', CL_RED)
            err += 1
        rec[date_off:date_off + 6] = bytes((m & 0xFF, 0, d, 0, y & 0xFF,
                                            (y >> 8) & 0xFF))
        return err

    def _age_comment(self, label, age, which):
        if which == 1:
            if age > 200:
                self._comment(label, 'Invalid date?', CL_RED)
            elif age > 110:
                self._comment(label, 'Oh, you are from the list of the '
                              'oldest living people!', CL_MAROON)
            elif age < 0:
                self._comment(label, 'Are you a guest from the future?!',
                              CL_RED)
            elif age < 8:
                self._comment(label, "Oh, you're a very cool kid!", CL_RED)
            elif age < 18:
                self._comment(label, 'Do your parents let you play this '
                              'game?', CL_MAROON)
        elif which == 2:
            if age > 100:
                self._comment(label, 'Invalid date?', CL_RED)
            elif age > 40:
                self._comment(label, "Do you really think that I'm so old?!",
                              CL_MAROON)
            elif age < 0:
                self._comment(label, "Oh, it's a time machine ?!", CL_RED)
            elif age < 16:
                self._comment(label, "I'm not a little baby, but if you...",
                              CL_MAROON)
            elif age < 25:
                self._comment(label, 'Do I look so young? Thank you!!!',
                              CL_MAROON)

    def _test_pu(self):
        self._clean_labels(1)
        self.c['PUOKBtn'].enabled = False
        err = 0
        if ' ' in self.c['Name3Edit'].text:
            self._comment('NameLb', 'Name must not contain a space!',
                          CL_MAROON)
            err += 1
        err += self._test_bd('MyBDEdit', 'MyBDLb', self.pu_rec, PU_TEXT,
                             PU_DATE, 1)
        if err:
            return
        if 'names' in self.fixes:
            self._store_name()
        else:
            self._store_name_original()
        self.c['PUOKBtn'].enabled = True

    def _store_name(self):
        name = self.c['Name3Edit'].text
        name = name[:len(trim_spaces(name, 3))]
        for off, size in PU_NAME:
            field = name[:size].ljust(size)
            self.pu_rec[off:off + size] = field.encode('latin-1')
        key = name[:5].ljust(5)
        self.pu_rec[PU_KEY:PU_KEY + 5] = bytes(
            (ord(ch) + i + 1) & 0xFF for i, ch in enumerate(key))

    def _store_name_original(self):
        """TestPUBtnClick's name part as compiled: the five-character buffer
        for the key overflows into the stack frame for longer names. Bytes
        6-9 overwrite the length, so the space padding is skipped (the old
        name's tail stays in the record), byte 13 the error flag, bytes 14-15
        the form pointer (access violation)."""
        rec = self.pu_rec
        name = self.c['Name3Edit'].text
        n = len(trim_spaces(name, 3))
        # frame from ebp-11h: key chars c[1..5], n (dword), 3 bytes, the
        # error flag, Self (dword)
        frame = bytearray(17)
        frame[5:9] = (n & 0xFFFFFFFF).to_bytes(4, 'little')
        self_ok = lambda: frame[13:17] == bytes(4)      # noqa: E731
        for i in range(1, n + 1):
            if not self_ok():
                raise access_violation(0x00438F2D)
            ch = ord(name[i - 1])
            if i - 1 < len(frame):
                frame[i - 1] = ch
            for off, _ in PU_NAME:
                rec[off + i - 1] = ch
        n = int.from_bytes(frame[5:9], 'little', signed=True)
        for (off, size), code in zip(PU_NAME, (0x45A75A, 0x45A773,
                                                0x45A78C)):
            for j in range(n + 1, size + 1):
                if not 0 <= off + j - 1 < PU_SIZE:
                    raise access_violation(code, 'Write',
                                           0x45DBEC + off + j - 1)
                rec[off + j - 1] = 0x20
        for j in range(n + 1, 6):
            frame[j - 1] = 0x20
        rec[PU_KEY:PU_KEY + 5] = bytes((frame[i] + i + 1) & 0xFF
                                       for i in range(5))
        if not self_ok():
            raise access_violation(0x0045A7E7)

    def _test_pa(self):
        self._clean_labels(2)
        self.c['PAOKBtn'].enabled = False
        err = self._test_bd('GFBDEdit', 'GFBDLb', self.pa_rec, PA_TEXT,
                            PA_DATE, 2)
        if err == 0:
            self.c['PAOKBtn'].enabled = True

    def _save(self, path, rec, name, button):
        """PUOKBtnClick / PAOKBtnClick."""
        self.c['SaveLb'].text = ''
        if self.checked:
            bak = change_file_ext(path, '.BAK')
            if self.file_exists(bak):
                self._delete_file(bak)
                self._comment('SaveLb', self.ansi.to_bytes(
                    os.path.basename(bak)) + ' deleted', CL_MAROON)
            if self._move_file(path, bak):
                self._comment('SaveLb', 'Old data saved as '
                              + self.ansi.to_bytes(os.path.basename(bak)),
                              CL_PURPLE)
        self.write_record(path, rec)
        self._comment('SaveLb', 'New written as ' + name, CL_PURPLE)
        self.c[button].enabled = False

    @staticmethod
    def _delete_file(path):
        """Windows DeleteFile, result ignored: it refuses read-only files
        (so does Wine), which POSIX would delete."""
        path = resolve(path)
        if os.name != 'nt' and not os.access(path, os.W_OK):
            return
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _move_file(old, new):
        """Windows MoveFile: fails if the target exists."""
        old = resolve(old)
        if os.path.lexists(resolve(new)):
            return False
        try:
            os.rename(old, new)
        except OSError:
            return False
        return True

    def _pu_ok(self):
        self._save(self.pupath, self.pu_rec, 'PURSEU.DAT', 'PUOKBtn')

    def _pa_ok(self):
        self._save(self.papath, self.pa_rec, 'PURSEA.DAT', 'PAOKBtn')


# --- text conversion between the user's characters and ANSI bytes ----------
def ansi_codepage():
    if os.name == 'nt':
        try:
            import ctypes
            return 'cp%d' % ctypes.windll.kernel32.GetACP()
        except (AttributeError, OSError):
            pass
    return 'cp1252'


class Ansi:
    def __init__(self, codepage):
        self.cp = codepage

    def to_bytes(self, text):
        return text.encode(self.cp, 'replace').decode('latin-1')

    def to_text(self, s):
        return s.encode('latin-1').decode(self.cp, 'replace')


def caption(s):
    """A Delphi caption with '&' accelerators -> (text, underline index)."""
    out = []
    underline = -1
    i = 0
    while i < len(s):
        if s[i] == '&' and i + 1 < len(s):
            i += 1
            if s[i] != '&' and underline < 0:
                underline = len(out)
        out.append(s[i])
        i += 1
    return ''.join(out), underline


# BEGIN IMAGES (generated by tools/extract_images.py from GFUpdate.exe)
IMAGES = {
    'icon': (
        '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'
        'gg=='
    ),
    'close': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAbUlEQVR42u2TSwrAMAgFPfo7'
        'mjezkdRgrW0+tNBFDYMLw/AQJIAoo5RkXP6/FcW3LHoi0SxJEsgIQ6KyDsHe665qtT4qgpOp'
        '6CCZEX0/Uaw/0cuJlkReojBzX5Tfkl06GlF0ohohPTSVJfPdZhsKLzDKEf7e1wAAAABJRU5E'
        'rkJggg=='
    ),
    'close_d': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAYklEQVR42u2UQQoAMQgD83Sf'
        '5s+2lMVDs8FNe66Qi8g0BiwiAK14uKrHs7OHDqR0AHoHVJkg7eQrA7Tm8Z9V6ygzm1xMUL1a'
        'sGPQdXQdtYcqQfu3pX4EG8Su+O7Aa/iuVugA//C3Z82ctt0AAAAASUVORK5CYII='
    ),
    'retry': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAhElEQVR42q2TUQ6AMAhDOXpv'
        'PvVjyrAFZsxCsgT3TNmbAWZ/lG4Mvtqg+whEBeDcvyFolv+hYWjI1YyloBJ0NugcFHCCOpA0'
        '/gJyEbYgMVrbFza7L6DUIyVfJiAHiWtNZxVmKkHtm6tAKhYTt4xGF7hzK6h6CtDiPiBPr94V'
        'kXZbPPX9AY7FqcPwk35bAAAAAElFTkSuQmCC'
    ),
    'retry_d': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAjUlEQVR42q2TUQ7AIAhDOTo3'
        'dx9kQaEUSVxColMrhaeoirwIsqgLx7WQHai+LGjjJOIH8M1R8B8nEW4NCdpeiSnGzLgt3w+y'
        'UWqtFdqjFqrWNmvZxgyLMXgVFg18uoZkK+wQq1W8jDDEn0/sMhRyZm46R4ROMYaGz8OPs8CY'
        'bpxZevF9jTC0JSsMB9TND4EYd9maxeFEAAAAAElFTkSuQmCC'
    ),
    'ok': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAb0lEQVR42rXUwRKAIAgEUD6d'
        'PzcrR8EwF6gDB531XZaRmIm+mNzjQiUNnQjxPWFIIvUmBikkCq0QF/SGwNAOUZCs0ot0qIcn'
        'DEUGJMMN8yADqqEZU2cUMjEH8mjNxADErF9hILLcowtzIOlv5BfoAEyUc7DuuiMpAAAAAElF'
        'TkSuQmCC'
    ),
    'ok_d': (
        'iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAAaElEQVR42q3UUQoAIQgEUI8+'
        'N59lP5ZqUWvSQOinRzmSAWYdVQTABgh814cVkbEvIteQj4hPixEBypEfBN4iE7RGqSIONN/s'
        'HAmg6NARlPVojzipedgeCeIHVSSZI1BB0oFUkIb/aNQDku3JAeALg1kAAAAASUVORK5CYII='
    ),
}
# END IMAGES


def tk_color(c):
    c &= 0xFFFFFF
    return '#%02x%02x%02x' % (c & 0xFF, (c >> 8) & 0xFF, c >> 16)


# The form, from GFUpdate.exe's DFM: (left, top, width, height) in the
# client area (668 x 592); nested panels already added up.
PANELS = [  # (x, y, w, h, framed): framed = lowered + raised bevel, border 2
    (0, 0, 668, 80, True), (0, 80, 668, 435, True), (4, 84, 330, 427, False),
    (334, 84, 330, 427, False), (5, 420, 328, 90, False),
    (335, 420, 328, 90, False), (0, 515, 668, 77, True)]
TIMES, TAHOMA = 'times', 'tahoma'
# static labels: x, y, w, h, caption, font, size(px), colour, centred,
# autosize/wordwrap, background
STATIC = [
    (365, 15, 170, 30, 'GIRLFRIEND', TIMES, 24, CL_NAVY, True, False,
     CL_TITLE),
    (365, 45, 170, 21, 'UPDATE', TIMES, 19, CL_NAVY, True, False, CL_TITLE),
    (34, 114, 270, 27, 'PURSEU.DAT: user data', TIMES, 21, CL_TEAL_DARK,
     True, False, None),
    (34, 184, 43, 21, 'Name', TIMES, 19, CL_BLACK, False, True, None),
    (34, 289, 63, 21, 'Birthday', TIMES, 19, CL_BLACK, False, True, None),
    (194, 289, 98, 19, 'MM/DD/YYYY', TAHOMA, 16, CL_TEAL_DARK, False, True,
     None),
    (34, 149, 270, 21, 'Input your name and birthday:', TIMES, 19, CL_NAVY,
     True, False, None),
    (215, 470, 96, 38, 'Overwrite PURSEU.DAT', TAHOMA, 16, CL_TEAL_DARK,
     True, True, None),
    (364, 114, 270, 27, 'PURSEA.DAT: girlfriend data', TIMES, 21,
     CL_TEAL_DARK, True, False, None),
    (364, 289, 63, 21, 'Birthday', TIMES, 19, CL_BLACK, False, True, None),
    (524, 289, 98, 19, 'MM/DD/YYYY', TAHOMA, 16, CL_TEAL_DARK, False, True,
     None),
    (364, 149, 270, 21, "Change girlfriend's date of birth:", TIMES, 19,
     CL_NAVY, True, False, None),
    (545, 470, 96, 38, 'Overwrite PURSEA.DAT', TAHOMA, 16, CL_TEAL_DARK,
     True, True, None),
    (580, 545, 35, 19, '(Esc)', TAHOMA, 16, CL_TEAL_DARK, False, True, None),
]
# state labels: name -> x, y, w, h, font, size, centred, autosize
DYNAMIC = {
    'NameLb': (34, 249, 270, 29, TIMES, 19, False, False),
    'MyBDLb': (24, 354, 300, 60, TAHOMA, 16, False, False),
    'DirLabel': (364, 184, 70, 21, TIMES, 19, False, True),
    'DirLb': (364, 249, 270, 29, TIMES, 19, False, False),
    'GFBDLb': (354, 354, 300, 60, TAHOMA, 16, False, False),
    'OpenPULb': (25, 470, 96, 38, TAHOMA, 16, True, True),
    'OpenPALb': (355, 470, 96, 38, TAHOMA, 16, True, True),
    'SaveLb': (215, 525, 230, 60, TAHOMA, 16, False, False),
}
EDIT_POS = {'Name3Edit': (34, 209, 270, 29), 'MyBDEdit': (34, 314, 180, 29),
            'GFDirNmEdit': (364, 209, 270, 29),
            'GFBDEdit': (364, 314, 180, 29)}
# buttons: x, y, w, h, caption, glyph, font colour (None = form's)
BUTTON_POS = {
    'TestPUBtn': (130, 440, 80, 32, '&Test', 'retry', None),
    'OpenPUBtn': (35, 440, 80, 32, '&Open', 'retry', CL_PURPLE),
    'PUOKBtn': (225, 440, 80, 32, 'OK', 'ok', None),
    'TestPABtn': (460, 440, 80, 32, '&Test', 'retry', None),
    'PAOKBtn': (555, 440, 80, 32, 'OK', 'ok', None),
    'OpenPABtn': (365, 440, 80, 32, '&Open', 'retry', CL_PURPLE),
    'CloseBtn': (460, 540, 100, 36, '&Close', 'close', None),
}
# tab order of the original
TAB_ORDER = ('Name3Edit', 'MyBDEdit', 'TestPUBtn', 'OpenPUBtn', 'PUOKBtn',
             'GFDirNmEdit', 'GFBDEdit', 'TestPABtn', 'PAOKBtn', 'OpenPABtn',
             'CloseBtn', 'SaveBakCheck')
# the order in which the original offers keys to its buttons
BROADCAST = ('TestPUBtn', 'OpenPUBtn', 'PUOKBtn', 'TestPABtn', 'PAOKBtn',
             'OpenPABtn', 'CloseBtn')


class TkView:
    """The original form in Tk, driving a GFUpdate model."""

    def __init__(self, model, ansi, tk):
        import tkinter.font as tkfont
        self.m = model
        self.ansi = ansi
        self.tk = tk
        root = self.root = tk.Tk()
        self.s = s = max(1.0, root.winfo_fpixels('1i') / 96.0)
        families = {f.lower(): f for f in tkfont.families(root)}
        self.family = {
            TIMES: families.get('times new roman', 'Times'),
            TAHOMA: families.get('tahoma', families.get('dejavu sans',
                                                        'Helvetica'))}
        root.title(TITLE)
        root.resizable(False, False)
        root.geometry('%dx%d+%d+%d' % (668 * s, 592 * s, 624, 147))
        bg = tk_color(CL_FORM)
        root.configure(bg=bg)
        self.images = {}
        for k, v in IMAGES.items():
            try:
                self.images[k] = tk.PhotoImage(master=root, data=''.join(v))
            except tk.TclError:     # Tk 8.5 has no PNG
                pass
        if 'icon' in self.images:
            root.iconphoto(True, self.images['icon'])
        cv = tk.Canvas(root, bg=bg, highlightthickness=0, bd=0)
        cv.place(x=0, y=0, relwidth=1, relheight=1)
        for x, y, w, h, framed in PANELS:
            self._bevel(cv, x, y, w, h, framed)
        for (x, y, w, h, text, fam, size, color, centred, auto,
             back) in STATIC:
            self._label(text, x, y, w, h, fam, size, color, centred, auto,
                        tk_color(back) if back is not None else bg)
        if 'icon' in self.images:
            tk.Label(root, image=self.images['icon'], bd=0, bg=bg).place(
                x=565 * s, y=8 * s, width=64 * s, height=64 * s)
        self.w = {}
        self.vars = {}
        self.dyn = {}
        for k, (x, y, w, h, fam, size, centred, auto) in DYNAMIC.items():
            self.dyn[k] = self._label('', x, y, w, h, fam, size, CL_NAVY,
                                      centred, auto, bg)
        self.pos = {}
        for k in TAB_ORDER:
            if k in EDIT_POS:
                self._edit(k)
            elif k == 'SaveBakCheck':
                self._check()
            else:
                self._button(k)
        root.bind('<Return>', self._on_return)
        root.bind('<KP_Enter>', self._on_return)
        root.bind('<Escape>', lambda e: self._click('CloseBtn'))
        root.bind_all('<Alt-KeyPress>', self._on_alt)
        root.bind('<KeyPress>', self._on_key, add='+')
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.push()
        self._show_dialogs()
        first = [k for k in TAB_ORDER if self._can_focus(k)]
        if first:
            self.w[first[0]].focus_set()

    # --- building ---
    def _font(self, family, size):
        return (self.family[family], -int(round(size * self.s)))

    def _place(self, widget, x, y, w=None, h=None):
        s = self.s
        kw = {'x': x * s, 'y': y * s}
        if w is not None:
            kw.update(width=w * s, height=h * s)
        widget.place(**kw)
        return kw

    def _bevel(self, cv, x, y, w, h, framed):
        s = self.s
        light, dark = '#ffffff', '#a0a0a0'

        def box(x0, y0, x1, y1, tl, br):
            cv.create_line(x0 * s, y1 * s, x0 * s, y0 * s, x1 * s, y0 * s,
                           fill=tl)
            cv.create_line(x1 * s, y0 * s, x1 * s, y1 * s, x0 * s, y1 * s,
                           fill=br)
        if framed:          # BevelOuter = bvLowered, BevelInner = bvRaised
            box(x, y, x + w - 1, y + h - 1, dark, light)
            box(x + 3, y + 3, x + w - 4, y + h - 4, light, dark)
        else:               # BevelOuter = bvRaised
            box(x, y, x + w - 1, y + h - 1, light, dark)

    def _label(self, text, x, y, w, h, fam, size, color, centred, auto, bg):
        text, ul = caption(text)
        lb = self.tk.Label(self.root, text=text, underline=ul, bd=0, padx=0,
                           pady=0, bg=bg, fg=tk_color(color),
                           font=self._font(fam, size),
                           anchor='n' if centred else 'nw',
                           justify='center' if centred else 'left',
                           wraplength=w * self.s)
        if auto and not centred:
            self._place(lb, x, y)
        else:
            self._place(lb, x, y, w, h if not auto else h + 4)
        lb._pos = (x, y, w, h, auto, centred)
        return lb

    def _edit(self, k):
        tk = self.tk
        var = self.vars[k] = tk.StringVar(self.root)
        limit = MAXLEN.get(k)
        vcmd = None
        if limit:
            vcmd = (self.root.register(
                lambda new, act, at, ins, n=limit, k=k:
                self._limit(k, n, new, act, at, ins)), '%P', '%d', '%i', '%S')
        e = tk.Entry(self.root, textvariable=var, font=self._font(TIMES, 19),
                     relief='sunken', bd=2, bg='#ffffff',
                     disabledbackground='#f0f0f0', disabledforeground='#6d6d6d',
                     validate='key' if vcmd else 'none',
                     validatecommand=vcmd)
        self.w[k] = e
        self.pos[k] = EDIT_POS[k]

    def _limit(self, k, n, new, action, at, inserted):
        """MaxLength: like a Windows edit, keep what fits of a paste."""
        if len(self.ansi.to_bytes(new)) <= n:
            return True
        if action == '1':
            old = self.vars[k].get()
            room = n - len(self.ansi.to_bytes(old))
            part = ''
            for ch in inserted:
                if len(self.ansi.to_bytes(part + ch)) > room:
                    break
                part += ch
            if part:
                e = self.w[k]
                i = int(at)
                self.root.after_idle(lambda: (e.insert(i, part),
                                              e.icursor(i + len(part))))
        return False

    def _check(self):
        tk = self.tk
        bg = tk_color(CL_FORM)
        var = self.vars['SaveBakCheck'] = tk.IntVar(self.root, value=1)
        cb = tk.Checkbutton(self.root, text='Save previous states as *.bak '
                            'files', variable=var, onvalue=1, offvalue=0,
                            font=self._font(TIMES, 19), fg=tk_color(CL_NAVY),
                            bg=bg, activebackground=bg, anchor='w',
                            justify='left', wraplength=155 * self.s,
                            highlightthickness=1, highlightbackground=bg,
                            command=lambda: self._click('SaveBakCheck'))
        self.w['SaveBakCheck'] = cb
        self.pos['SaveBakCheck'] = (30, 535, 180, 40)

    def _button(self, k):
        x, y, w, h, text, glyph, color = BUTTON_POS[k]
        text, ul = caption(text)
        b = self.tk.Button(self.root, text=' ' + text if glyph else text,
                           underline=ul + 1 if ul >= 0 else -1,
                           compound='left', font=self._font(TIMES, 19),
                           fg=tk_color(color) if color else '#000000',
                           command=lambda: self._click(k), padx=2, pady=0)
        b.bind('<Button-1>', lambda e: e.widget.focus_set(), add='+')
        b._glyph = glyph
        self.w[k] = b
        self.pos[k] = (x, y, w, h)

    # --- model <-> widgets ---
    def pull(self):
        for k in EDITS:
            self.m.set_text(k, self.ansi.to_bytes(self.vars[k].get()))

    def push(self):
        m = self.m
        for k, lb in self.dyn.items():
            c = m.c[k]
            text, ul = caption(self.ansi.to_text(c.text.replace('\r', '\n')))
            lb.configure(text=text, underline=ul, fg=tk_color(c.color))
            self._show(lb, c.visible, lb._pos)
        for k in EDITS:
            c = m.c[k]
            text = self.ansi.to_text(c.text.split('\0', 1)[0])
            if self.vars[k].get() != text:
                self.vars[k].set(text)
            self.w[k].configure(state='normal' if c.enabled else 'disabled')
            self._show(self.w[k], c.visible, self.pos[k])
        for k in BUTTON_POS:
            c = m.c[k]
            b = self.w[k]
            img = self.images.get(b._glyph + ('' if c.enabled else '_d'))
            b.configure(state='normal' if c.enabled else 'disabled',
                        image=img or '')
            self._show(b, c.visible, self.pos[k])
        cb = self.w['SaveBakCheck']
        self.vars['SaveBakCheck'].set(1 if m.checked else 0)
        self._show(cb, m.c['SaveBakCheck'].visible, self.pos['SaveBakCheck'])

    def _show(self, widget, visible, pos):
        if not visible:
            widget.place_forget()
            return
        if len(pos) == 6:       # a label
            x, y, w, h, auto, centred = pos
            if auto and not centred:
                self._place(widget, x, y)
            else:
                self._place(widget, x, y, w, h if not auto else h + 4)
        else:
            self._place(widget, *pos)

    def _show_dialogs(self):
        from tkinter import messagebox
        while self.m.dialogs:
            d = self.m.dialogs.pop(0)
            messagebox.showerror(d['title'],
                                 self.ansi.to_text('\n'.join(d['text'])),
                                 parent=self.root)

    # --- events ---
    def _can_focus(self, k):
        c = self.m.c[k]
        return c.enabled and c.visible

    def _click(self, k):
        if not self._can_focus(k):
            return
        if k == 'SaveBakCheck':
            # the Checkbutton already toggled its variable
            self.m.click(k)
            self.vars[k].set(1 if self.m.checked else 0)
            return
        self.pull()
        arg = ()
        if k in ('OpenPUBtn', 'OpenPABtn'):
            arg = (self._ask_file('PURSEU.DAT' if k == 'OpenPUBtn'
                                  else 'PURSEA.DAT'),)
        self.m.click(k, *arg)
        self.push()
        self._show_dialogs()
        if self.m.closed:
            self.root.destroy()

    def _ask_file(self, name):
        from tkinter import filedialog
        pats = (name,) if os.name == 'nt' else (name, name.lower())
        path = filedialog.askopenfilename(parent=self.root,
                                          filetypes=[(name, pats)],
                                          initialdir=os.getcwd())
        return os.path.normpath(path) if path else None

    def _on_return(self, event):
        w = self.root.focus_get()
        for k in BROADCAST:
            if self.w[k] is w:
                self._click(k)
                return 'break'
        for k in ('PUOKBtn', 'PAOKBtn'):    # both are Default buttons
            if self._can_focus(k):
                self._click(k)
                return 'break'
        return None

    def _accel(self, ch):
        for k in BROADCAST:
            text, ul = caption(BUTTON_POS[k][4])
            if ul >= 0 and text[ul].lower() == ch and self._can_focus(k):
                self.w[k].focus_set()
                self._click(k)
                return True
        return False

    @staticmethod
    def _key_char(event):
        ch = event.char or event.keysym
        return ch.lower() if len(ch) == 1 else ''

    def _on_alt(self, event):
        ch = self._key_char(event)
        if ch and self._accel(ch):
            return 'break'
        return None

    def _on_key(self, event):
        # letters work without Alt unless an edit has the focus
        w = self.root.focus_get()
        ch = self._key_char(event)
        if isinstance(w, self.tk.Entry) or not ch or event.state & 0x0004:
            return None
        if self._accel(ch):
            return 'break'
        return None

    def _on_close(self):
        self.m.closed = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()


class ConsoleView:
    """The same form as a text menu, for systems without Tk."""

    def __init__(self, model, ansi, inp=input, out=None):
        self.m = model
        self.ansi = ansi
        self.inp = inp
        self.out = out or sys.stdout

    def say(self, text=''):
        self.out.write(text + '\n')
        self.out.flush()

    def _lbl(self, k):
        c = self.m.c[k]
        if not c.visible or not c.text:
            return []
        text = caption(self.ansi.to_text(c.text))[0]
        return ['    ' + line for line in text.split('\r')]

    def show(self):
        m = self.m
        c = m.c
        t = self.ansi.to_text
        on = self._can

        def line(key, text):
            self.say(('  %s) ' % key if key else '     ') + text)
        self.say()
        self.say('GIRLFRIEND UPDATE - ' + TITLE)
        self.say()
        self.say('PURSEU.DAT: user data - input your name and birthday:')
        line('1' if on('Name3Edit') else '', 'Name:      ' + t(c['Name3Edit'].text))
        for s in self._lbl('NameLb'):
            self.say(s)
        line('2' if on('MyBDEdit') else '',
             'Birthday:  ' + t(c['MyBDEdit'].text) + '   (MM/DD/YYYY)')
        for s in self._lbl('MyBDLb'):
            self.say(s)
        if on('OpenPUBtn'):
            line('O', 'Find & open PURSEU.DAT')
        if on('TestPUBtn'):
            line('T', 'Test')
        if on('PUOKBtn'):
            line('W', 'Overwrite PURSEU.DAT')
        self.say()
        self.say("PURSEA.DAT: girlfriend data - change girlfriend's date of "
                 "birth:")
        if c['GFDirNmEdit'].visible:
            line('', 'Directory: ' + t(c['GFDirNmEdit'].text))
        line('3' if on('GFBDEdit') else '',
             'Birthday:  ' + t(c['GFBDEdit'].text) + '   (MM/DD/YYYY)')
        for s in self._lbl('GFBDLb'):
            self.say(s)
        if on('OpenPABtn'):
            line('P', 'Find & open PURSEA.DAT')
        if on('TestPABtn'):
            line('U', 'Test')
        if on('PAOKBtn'):
            line('V', 'Overwrite PURSEA.DAT')
        self.say()
        line('B', '[%s] Save previous states as *.bak files'
             % ('x' if m.checked else ' '))
        line('C', 'Close (or Esc / empty line)')
        for s in self._lbl('SaveLb'):
            self.say(s)

    def _can(self, k):
        c = self.m.c[k]
        return c.enabled and c.visible

    def _edit(self, k, prompt):
        try:
            text = self.inp(prompt)
        except EOFError:
            return
        data = self.ansi.to_bytes(text)
        if k in MAXLEN:
            data = data[:MAXLEN[k]]
        self.m.set_text(k, data)

    def _dialogs(self):
        while self.m.dialogs:
            d = self.m.dialogs.pop(0)
            self.say()
            self.say('*** %s: %s' % (d['title'],
                                     self.ansi.to_text(' '.join(d['text']))))

    def run(self):
        self._dialogs()
        keys = {'T': 'TestPUBtn', 'W': 'PUOKBtn', 'U': 'TestPABtn',
                'V': 'PAOKBtn', 'B': 'SaveBakCheck', 'C': 'CloseBtn',
                'O': 'OpenPUBtn', 'P': 'OpenPABtn'}
        while not self.m.closed:
            self.show()
            try:
                choice = self.inp('Please choose: ').strip().upper()
            except EOFError:
                break
            if choice in ('', '\x1b', 'ESC', 'Q'):
                choice = 'C'
            if choice == '1' and self._can('Name3Edit'):
                self._edit('Name3Edit', 'Name (max. 15 characters): ')
            elif choice == '2' and self._can('MyBDEdit'):
                self._edit('MyBDEdit', 'Your birthday (MM/DD/YYYY): ')
            elif choice == '3' and self._can('GFBDEdit'):
                self._edit('GFBDEdit', "Girlfriend's birthday (MM/DD/YYYY): ")
            elif choice in keys and self._can(keys[choice]):
                k = keys[choice]
                if k in ('OpenPUBtn', 'OpenPABtn'):
                    name = 'PURSEU.DAT' if k == 'OpenPUBtn' else 'PURSEA.DAT'
                    try:
                        path = self.inp('Path of %s (empty = cancel): '
                                        % name).strip()
                    except EOFError:
                        path = ''
                    self.m.click(k, os.path.abspath(path) if path else None)
                else:
                    self.m.click(k)
                self._dialogs()
            else:
                self.say('?')


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        prog='gfupdate.py',
        description='Change the player name and the birthdays of Girlfriend '
                    'Terri / Tracy (port of GFUpdate.exe).')
    ap.add_argument('-C', '--directory', metavar='DIR', default=here,
                    help="the game folder with PURSEU.DAT and the *.GF folder "
                         "(default: this script's folder)")
    ap.add_argument('--console', action='store_true',
                    help='text menu instead of the window')
    ap.add_argument('--no-fixes', action='store_true',
                    help="behave exactly like the original, bugs included")
    ap.add_argument('--codepage', default=None,
                    help='code page of the names in the files (default: the '
                         'Windows ANSI code page, else cp1252)')
    ap.add_argument('--version', action='version',
                    version='%(prog)s ' + VERSION)
    args = ap.parse_args(argv)
    if not os.path.isdir(args.directory):
        ap.error('no such folder: %s' % args.directory)
    ansi = Ansi(args.codepage or ansi_codepage())
    try:
        ''.encode(ansi.cp)
    except LookupError:
        ap.error('unknown code page: %s' % ansi.cp)
    fixes = () if args.no_fixes else FIXES
    model = GFUpdate(args.directory, fixes, ansi=ansi)
    if not args.console:
        try:
            import tkinter
        except ImportError as e:
            tkinter = None
            why = e
        if tkinter is not None:
            try:
                view = TkView(model, ansi, tkinter)
            except tkinter.TclError as e:   # no display
                why = e
            else:
                view.run()
                return 0
        sys.stderr.write('gfupdate: no window (%s), using the console\n'
                         % why)
    ConsoleView(model, ansi).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
