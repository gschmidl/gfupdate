"""Builds the fixed GFUpdate.exe: the original with its bugs fixed.

    py build_fix.py [--upx UPX] [-o OUT] ORIGINAL_GFUPDATE_EXE

ORIGINAL_GFUPDATE_EXE is the GFUpdate.exe eXoDOS ships with Girlfriend Terri
and Tracy (eXo's eXoDOS/gfterri/gf_terri/GFUpdate.exe). It is UPX-packed;
UPX (--upx, else $UPX_PATH, else upx on the PATH) unpacks it. Then:

- the machine code changes in PATCHES (assembled from fixes.asm by
  tools/assemble_fixes.py) fix the four bugs of README.md;
- a manifest that asks for no administrator rights (asInvoker) is added, so
  Windows' installer detection ("Update" in the name) stops asking for them.

Everything else stays. OUT defaults to GFUpdate.exe in this folder; it is
not UPX-packed again. Windows only (the manifest is added with
UpdateResource).
"""
import argparse
import ctypes
import ctypes.wintypes as W
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_SHA1 = '610d1b026779892e55c9e53cb9289285c6d7a786'   # as shipped
UNPACKED_SHA1 = 'cb6f04a47583c3f6bafe20aa005436f304d0ca3b'   # upx -d of it
RT_MANIFEST = 24
MANIFEST = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
'''.replace(b'\n', b'\r\n')

# BEGIN PATCHES
PATCHES = [  # (address, new bytes): exo/fixes.asm, assembled
    (0x459963, bytes.fromhex(  # 5 bytes: call FILE_EXISTS                ; ResetP
        'e80a0e0000'
    )),
    (0x459B78, bytes.fromhex(  # 6 bytes: jmp PA_PATH
        'e93b0c000090'
    )),
    (0x459BBE, bytes.fromhex(  # 5 bytes: call FILE_EXISTS                ; ResetP
        'e8af0b0000'
    )),
    (0x459E02, bytes.fromhex(  # 5 bytes: call PA_OPENED
        'e8c9090000'
    )),
    (0x459FE4, bytes.fromhex(  # 5 bytes: call LEN_MAX10
        'e8bf070000'
    )),
    (0x45A6F9, bytes.fromhex(  # 121 bytes: TestPUBtnClick, the name part (bug 1). W
        '8b45dce82fa0faff83f80f7e05b80f0000008945f4bfecdb4500b941000000b0'
        '20f3aac745ef20202020c645f3208b4df48b75d831db85c97e238a041e8883ec'
        'db450088830adc450088831edc450083fb05730488441def4339cb7cdd31db8a'
        '441def8d530100d088832ede45004383fb057cebe96a000000'
    )),
    (0x45A772, bytes.fromhex(  # 54 bytes: FileExists without FileAge's DOS date (b
        '5381c4c0feffff89c35489d8e8ada1faff50e807bdfaff83f8ff741050e8f4bc'
        'fafff60424107504b001eb0231c081c4400100005bc3'
    )),
    (0x45A7A8, bytes.fromhex(  # 16 bytes: TestBD: the length of the birthday text,
        'e8839ffaff83f80a7e05b80a000000c3'
    )),
    (0x45A7B8, bytes.fromhex(  # 24 bytes: ResetPA: keep a PURSEA.DAT chosen with O
        '803de3db4500000f85f4f3ffffff35dcdb4500e9aef3ffff'
    )),
    (0x45A7D0, bytes.fromhex(  # 12 bytes: OpenPABtnClick: PApath := the dialog's f
        'c605e3db450001e9e89cfaff'
    )),
    (0x45A908, bytes.fromhex(  # 5 bytes: call FILE_EXISTS                ; PUOKBt
        'e865feffff'
    )),
    (0x45AAFC, bytes.fromhex(  # 5 bytes: call FILE_EXISTS                ; PAOKBt
        'e871fcffff'
    )),
]
# END PATCHES


def sections(data):
    """(virtual address, virtual size, raw offset, raw size) per section."""
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    assert data[pe:pe + 4] == b'PE\0\0'
    count = struct.unpack_from('<H', data, pe + 6)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    out = []
    for i in range(count):
        s = pe + 24 + opt + 40 * i
        vsize, va, rsize, raw = struct.unpack_from('<IIII', data, s + 8)
        out.append((base + va, vsize, raw, rsize))
    return out


def file_offset(data, address):
    for va, vsize, raw, rsize in sections(data):
        if va <= address < va + min(vsize, rsize):
            return raw + address - va
    raise ValueError('%X is not in the file' % address)


def patch(data):
    data = bytearray(data)
    for address, code in PATCHES:
        off = file_offset(data, address)
        data[off:off + len(code)] = code
    return bytes(data)


def add_manifest(path):
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.BeginUpdateResourceW.restype = W.HANDLE
    k32.BeginUpdateResourceW.argtypes = [W.LPCWSTR, W.BOOL]
    k32.UpdateResourceW.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    W.WORD, ctypes.c_void_p, W.DWORD]
    k32.EndUpdateResourceW.argtypes = [W.HANDLE, W.BOOL]
    h = k32.BeginUpdateResourceW(path, False)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    buf = ctypes.create_string_buffer(MANIFEST, len(MANIFEST))
    if not k32.UpdateResourceW(h, RT_MANIFEST, 1, 0, buf, len(MANIFEST)):
        err = ctypes.get_last_error()
        k32.EndUpdateResourceW(h, True)
        raise ctypes.WinError(err)
    if not k32.EndUpdateResourceW(h, False):
        raise ctypes.WinError(ctypes.get_last_error())


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('original')
    ap.add_argument('--upx', default=os.environ.get('UPX_PATH')
                    or shutil.which('upx'))
    ap.add_argument('-o', '--output', default=os.path.join(HERE,
                                                           'GFUpdate.exe'))
    args = ap.parse_args()
    if os.name != 'nt':
        sys.exit('build_fix.py: Windows only (UpdateResource)')
    if not args.upx:
        sys.exit('build_fix.py: UPX is needed to unpack GFUpdate.exe '
                 '(--upx, $UPX_PATH or upx on the PATH)')
    with open(args.original, 'rb') as f:
        orig = f.read()
    if sha1(orig) != ORIGINAL_SHA1:
        sys.exit('%s is not the GFUpdate.exe this fix is for (sha1 %s)'
                 % (args.original, sha1(orig)))
    tmp = tempfile.mkdtemp(prefix='gfufix-')
    try:
        work = os.path.join(tmp, 'GFUpdate.exe')
        r = subprocess.run([args.upx, '-d', '-q', '-o', work, args.original],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit('UPX failed:\n' + r.stdout + r.stderr)
        with open(work, 'rb') as f:
            data = f.read()
        if sha1(data) != UNPACKED_SHA1:
            sys.exit('the unpacked GFUpdate.exe is not the expected one '
                     '(sha1 %s)' % sha1(data))
        with open(work, 'wb') as f:
            f.write(patch(data))
        add_manifest(work)
        shutil.copyfile(work, args.output)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(args.output, 'rb') as f:
        data = f.read()
    print('%s: %d bytes, sha1 %s' % (args.output, len(data), sha1(data)))


if __name__ == '__main__':
    main()
