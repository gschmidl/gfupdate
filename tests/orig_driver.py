"""Drive the original GFUpdate.exe (Windows only) for A/B tests.

The program runs on a private, invisible desktop, so its windows never show
on the user's screen and never take the keyboard focus. The driver thread
joins that desktop (SetThreadDesktop) to find and message the windows.

Controls are found through the Delphi objects: the form object comes from
the program's MainForm variable, each component from its published field
offset (see NOTES.md), each window handle from TWinControl.FHandle. Labels
have no window, so their caption, font colour and visibility are read from
the TLabel object. The PURSEU/PURSEA records and the file paths are read
from the program's globals.

Clicks are WM_COMMAND/BN_CLICKED sent to the button's parent, which is what
a real click produces; the driver refuses to click a disabled or hidden
button. Message boxes (Delphi's exception dialogs) are read and closed.
"""
import ctypes
import os
import time
from ctypes import wintypes as W

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# --- addresses in GFUpdate.exe (2017-09-13, UPX packed, MD5 538235e1...) ---
G_MAINFORM_REF = 0x45BF8C   # -> address of the MainForm variable
G_EXEDIR = 0x45DBDC         # AnsiString: ExtractFilePath(ExeName)
G_PUPATH = 0x45DBE4         # AnsiString: path of PURSEU.DAT
G_PAPATH = 0x45DBE8         # AnsiString: path of PURSEA.DAT
G_PU_REC = 0x45DBEC         # 768-byte PURSEU record
G_PA_REC = 0x45E038         # 512-byte PURSEA record

FIELDS = {
    'CloseBtn': 0x318, 'Name3Edit': 0x324, 'MyBDEdit': 0x32C,
    'NameLb': 0x334, 'MyBDLb': 0x338, 'DirLabel': 0x33C,
    'GFDirNmEdit': 0x340, 'DirLb': 0x344, 'GFBDEdit': 0x34C,
    'GFBDLb': 0x354, 'TestPUBtn': 0x370, 'OpenPUBtn': 0x374,
    'PUOKBtn': 0x37C, 'TestPABtn': 0x380, 'PAOKBtn': 0x388,
    'OpenPABtn': 0x38C, 'OpenPULb': 0x390, 'SaveBakCheck': 0x394,
    'SaveLb': 0x398, 'OpenPALb': 0x3A0, 'Label1': 0x310,
}
LABELS = ('NameLb', 'MyBDLb', 'DirLabel', 'DirLb', 'GFBDLb', 'OpenPULb',
          'SaveLb', 'OpenPALb')
WINCONTROLS = ('Name3Edit', 'MyBDEdit', 'GFDirNmEdit', 'GFBDEdit',
               'TestPUBtn', 'OpenPUBtn', 'PUOKBtn', 'TestPABtn', 'PAOKBtn',
               'OpenPABtn', 'SaveBakCheck', 'CloseBtn')
TCONTROL_VISIBLE = 0x57     # TControl.FVisible (SetVisible)
TCONTROL_ENABLED = 0x58     # TControl.FEnabled (SetEnabled, VMT +64h)
TCONTROL_FONT = 0x68        # TControl.FFont (TMainForm.Comment)
TFONT_COLOR = 0x18          # TFont.FColor (TFont.SetColor)
TCHECKBOX_STATE = None      # found by calibration

WM_NULL = 0x0000
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
BN_CLICKED = 0
SMTO_NORMAL = 0
IDOK = 1
ERROR_TIMEOUT = 1460

DESKTOP_ALL = 0x01FF
CREATE_NEW_CONSOLE = 0x10

WNDENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR),
                ('lpDesktop', W.LPWSTR), ('lpTitle', W.LPWSTR),
                ('dwX', W.DWORD), ('dwY', W.DWORD), ('dwXSize', W.DWORD),
                ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD),
                ('dwFlags', W.DWORD), ('wShowWindow', W.WORD),
                ('cbReserved2', W.WORD), ('lpReserved2', ctypes.c_void_p),
                ('hStdInput', W.HANDLE), ('hStdOutput', W.HANDLE),
                ('hStdError', W.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE),
                ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


user32.CreateDesktopW.restype = W.HANDLE
user32.CreateDesktopW.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p,
                                  W.DWORD, W.DWORD, ctypes.c_void_p]
user32.SetThreadDesktop.argtypes = [W.HANDLE]
user32.EnumWindows.argtypes = [WNDENUMPROC, W.LPARAM]
user32.EnumChildWindows.argtypes = [W.HWND, WNDENUMPROC, W.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
user32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
user32.SendMessageTimeoutA.restype = ctypes.c_size_t
user32.SendMessageTimeoutA.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM,
                                       W.UINT, W.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.GetParent.restype = W.HWND
user32.GetParent.argtypes = [W.HWND]
user32.GetDlgCtrlID.argtypes = [W.HWND]
user32.IsWindowEnabled.argtypes = [W.HWND]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
kernel32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
kernel32.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p,
                                    ctypes.c_void_p, W.BOOL, W.DWORD,
                                    ctypes.c_void_p, W.LPCWSTR,
                                    ctypes.POINTER(STARTUPINFOW),
                                    ctypes.POINTER(PROCESS_INFORMATION)]
kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
kernel32.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
kernel32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
kernel32.CloseHandle.argtypes = [W.HANDLE]

_desktop = None
DESKTOP_NAME = 'gfupdate-ab'


def join_private_desktop():
    """Create the invisible desktop and move this thread onto it."""
    global _desktop
    if _desktop is None:
        _desktop = user32.CreateDesktopW(DESKTOP_NAME, None, None, 0,
                                         DESKTOP_ALL, None)
        if not _desktop:
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.SetThreadDesktop(_desktop):
            raise ctypes.WinError(ctypes.get_last_error())
    return _desktop


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd):
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def top_windows(pid):
    found = []

    def cb(hwnd, _):
        if window_pid(hwnd) == pid:
            found.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def child_windows(hwnd):
    found = []

    def cb(h, _):
        found.append(h)
        return True
    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return found


def get_text(hwnd, timeout=2000):
    """WM_GETTEXT as ANSI bytes, decoded latin-1 (byte-transparent)."""
    res = ctypes.c_size_t()
    n = user32.SendMessageTimeoutA(hwnd, WM_GETTEXTLENGTH, 0, 0, SMTO_NORMAL,
                                   timeout, ctypes.byref(res))
    if not n:
        raise TimeoutError('WM_GETTEXTLENGTH')
    buf = ctypes.create_string_buffer(res.value + 2)
    n = user32.SendMessageTimeoutA(hwnd, WM_GETTEXT, res.value + 1,
                                   ctypes.cast(buf, ctypes.c_void_p).value,
                                   SMTO_NORMAL, timeout, ctypes.byref(res))
    if not n:
        raise TimeoutError('WM_GETTEXT')
    return buf.value.decode('latin-1')


class Original:
    """One running instance of the original program."""

    as_invoker = True       # False: start it as Windows would by itself

    def __init__(self, exe, cwd, args=None):
        join_private_desktop()
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = DESKTOP_NAME
        pi = PROCESS_INFORMATION()
        cmd = ctypes.create_unicode_buffer('"%s"%s' % (exe, args or ''))
        # "GFUpdate" has no manifest, so Windows' installer detection would
        # demand elevation (error 740); run it as the invoker instead
        if self.as_invoker:
            os.environ['__COMPAT_LAYER'] = 'RunAsInvoker'
        else:
            os.environ.pop('__COMPAT_LAYER', None)
        if not kernel32.CreateProcessW(exe, cmd, None, None, False, 0, None,
                                       cwd, ctypes.byref(si),
                                       ctypes.byref(pi)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hproc = pi.hProcess
        kernel32.CloseHandle(pi.hThread)
        self.pid = pi.dwProcessId
        self.dialogs = []          # texts of message boxes seen so far
        self._answered = set()
        self.form_hwnd = None
        self._wait_form()
        self._calibrate()

    # --- process memory ---
    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(self.hproc, addr, buf, n,
                                          ctypes.byref(got)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw[:got.value]

    def dword(self, addr):
        return int.from_bytes(self.read(addr, 4), 'little')

    def ansistring(self, ptr):
        if ptr == 0:
            return ''
        n = self.dword(ptr - 4)
        return self.read(ptr, n).decode('latin-1')

    def pchar(self, ptr, limit=65536):
        """A #0-terminated string, read page by page (the next page may not
        be mapped)."""
        if ptr == 0:
            return ''
        data = b''
        while len(data) < limit:
            n = 0x1000 - ((ptr + len(data)) & 0xFFF)
            chunk = self.read(ptr + len(data), n)
            if b'\0' in chunk:
                data += chunk.split(b'\0', 1)[0]
                break
            data += chunk
        return data.decode('latin-1')

    # --- startup ---
    def alive(self):
        code = W.DWORD()
        kernel32.GetExitCodeProcess(self.hproc, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE

    def _wait_form(self, timeout=15.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.collect_dialogs()
            for h in top_windows(self.pid):
                if class_name(h) == 'TMainForm' and user32.IsWindowVisible(h):
                    self.form_hwnd = h
                    # let FormCreate's dialogs (if any) settle
                    self.sync()
                    return
            if not self.alive():
                raise RuntimeError('original exited during start-up')
            time.sleep(0.05)
        raise TimeoutError('no TMainForm window')

    def _calibrate(self):
        self.form = self.dword(self.dword(G_MAINFORM_REF))
        self.obj = {k: self.dword(self.form + off) for k, off in FIELDS.items()}
        hwnds = set(child_windows(self.form_hwnd))
        # TWinControl.FHandle
        blob = self.read(self.obj['Name3Edit'], 0x300)
        self.off_handle = None
        for off in range(0x15C, 0x2FC, 4):
            if int.from_bytes(blob[off:off + 4], 'little') in hwnds:
                self.off_handle = off
                break
        assert self.off_handle is not None, 'FHandle not found'
        # TControl.FText (PChar)
        blob = self.read(self.obj['Label1'], 0x15C)
        self.off_text = None
        for off in range(0, 0x15C, 4):
            p = int.from_bytes(blob[off:off + 4], 'little')
            if 0x10000 < p < 0x7FFF0000:
                try:
                    if self.pchar(p, 64) == 'PURSEU.DAT: user data':
                        self.off_text = off
                        break
                except OSError:
                    pass
        assert self.off_text is not None, 'FText not found'

    @property
    def hwnd(self):
        """Window handles; 0 for a control whose window does not exist yet
        (the VCL makes it when the control is first shown)."""
        return {k: self.dword(self.obj[k] + self.off_handle)
                for k in WINCONTROLS}

    # --- message boxes ---
    def collect_dialogs(self):
        """Read and close every visible message box of the process."""
        seen = False
        for h in top_windows(self.pid):
            if class_name(h) != '#32770' or not user32.IsWindowVisible(h):
                continue
            if any(class_name(c) == 'Edit' for c in child_windows(h)):
                continue        # a file dialog, answered by the caller
            title = get_text(h)
            texts = [get_text(c) for c in child_windows(h)
                     if class_name(c) == 'Static']
            texts = [t for t in texts if t]
            buttons = [c for c in child_windows(h)
                       if class_name(c) == 'Button']
            key = (h, tuple(texts))
            if key not in self._answered:
                self._answered.add(key)
                self.dialogs.append({'title': title, 'text': texts})
            for b in buttons[:1]:   # the message box's only button, "OK"
                wparam = (BN_CLICKED << 16) | (user32.GetDlgCtrlID(b)
                                               & 0xFFFF)
                user32.PostMessageW(h, WM_COMMAND, wparam, b)
            seen = True
            time.sleep(0.1)
        return seen

    def sync(self, timeout=5.0):
        """Wait until the program is idle, closing message boxes on the way."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.collect_dialogs():
                continue
            res = ctypes.c_size_t()
            ok = user32.SendMessageTimeoutA(self.form_hwnd, WM_NULL, 0, 0,
                                            SMTO_NORMAL, 500,
                                            ctypes.byref(res))
            if ok:
                time.sleep(0.03)
                if not self.collect_dialogs():
                    return
            elif not self.alive():
                return
        raise TimeoutError('program did not become idle')

    # --- actions ---
    def set_text(self, name, text):
        h = self.hwnd[name]
        data = text.encode('latin-1')
        buf = ctypes.create_string_buffer(data)
        res = ctypes.c_size_t()
        ok = user32.SendMessageTimeoutA(h, WM_SETTEXT, 0,
                                        ctypes.cast(buf, ctypes.c_void_p).value,
                                        SMTO_NORMAL, 3000, ctypes.byref(res))
        if not ok:
            raise TimeoutError('WM_SETTEXT')
        self.sync()

    def flags(self, name):
        o = self.obj[name]
        b = self.read(o + TCONTROL_VISIBLE, 2)
        return bool(b[1]), bool(b[0])       # enabled, visible

    def can_click(self, name):
        h = self.hwnd[name]
        return bool(h and user32.IsWindowEnabled(h)
                    and user32.IsWindowVisible(h))

    def click(self, name, dialog_hook=None):
        h = self.hwnd[name]
        if not self.can_click(name):
            raise RuntimeError('%s is disabled or hidden' % name)
        parent = user32.GetParent(h)
        wparam = (BN_CLICKED << 16) | (user32.GetDlgCtrlID(h) & 0xFFFF)
        res = ctypes.c_size_t()
        ok = user32.SendMessageTimeoutA(parent, WM_COMMAND, wparam, h,
                                        SMTO_NORMAL, 1500, ctypes.byref(res))
        if not ok and dialog_hook is not None:
            dialog_hook(self)
        if self.alive():
            self.sync()

    def close(self):
        if self.alive():
            user32.PostMessageW(self.form_hwnd, WM_CLOSE, 0, 0)
            kernel32.WaitForSingleObject(self.hproc, 5000)
        if self.alive():
            kernel32.TerminateProcess(self.hproc, 1)
            kernel32.WaitForSingleObject(self.hproc, 5000)
        kernel32.CloseHandle(self.hproc)

    # --- observation ---
    def label(self, name):
        o = self.obj[name]
        font = self.dword(o + TCONTROL_FONT)
        return {'text': self.pchar(self.dword(o + self.off_text)),
                'color': self.dword(font + TFONT_COLOR),
                'visible': bool(self.read(o + TCONTROL_VISIBLE, 1)[0])}

    def control(self, name):
        h = self.hwnd[name]
        enabled, visible = self.flags(name)
        d = {'enabled': enabled, 'visible': visible}
        if name in ('Name3Edit', 'MyBDEdit', 'GFDirNmEdit', 'GFBDEdit'):
            if h:
                d['text'] = get_text(h)
            else:
                d['text'] = self.pchar(self.dword(self.obj[name]
                                                  + self.off_text))
        return d

    def state(self):
        if not self.alive():
            return {'alive': False, 'dialogs': self.dialogs}
        st = {'alive': True}
        for k in LABELS:
            st[k] = self.label(k)
        for k in WINCONTROLS:
            st[k] = self.control(k)
        st['checked'] = self.checked()
        st['exedir'] = self.ansistring(self.dword(G_EXEDIR))
        st['pupath'] = self.ansistring(self.dword(G_PUPATH))
        st['papath'] = self.ansistring(self.dword(G_PAPATH))
        st['pu_rec'] = self.read(G_PU_REC, 768).hex()
        st['pa_rec'] = self.read(G_PA_REC, 512).hex()
        st['dialogs'] = list(self.dialogs)
        return st

    def checked(self):
        # BM_GETCHECK reflects the window; Delphi keeps the state in sync
        BM_GETCHECK = 0x00F0
        res = ctypes.c_size_t()
        user32.SendMessageTimeoutA(self.hwnd['SaveBakCheck'], BM_GETCHECK, 0,
                                   0, SMTO_NORMAL, 2000, ctypes.byref(res))
        return res.value == 1


def main():
    import json
    import sys
    exe = os.path.abspath(sys.argv[1])
    o = Original(exe, os.path.dirname(exe))
    try:
        print(json.dumps(o.state(), indent=1))
    finally:
        o.close()


if __name__ == '__main__':
    main()
