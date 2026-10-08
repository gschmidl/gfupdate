"""Extract GFUpdate.exe's images as base64 PNG for gfupdate.py.

    py extract_images.py UNPACKED_GFUPDATE_EXE [--into ../gfupdate.py]

Without --into the block is printed.

Needs pefile (pip). The exe must be UPX-unpacked (upx -d). Writes the
IMAGES dictionary that gfupdate.py embeds:

  icon            Image1.Picture (TIcon 64x64, 8 bpp, AND mask -> alpha)
  close, close_d  CloseBtn.Glyph (2 glyphs: normal, disabled)
  retry, retry_d  VCL's BBRETRY bitmap (TBitBtn Kind = bkRetry)
  ok, ok_d        VCL's BBOK bitmap (Kind = bkOK)

A TBitBtn glyph is transparent where it has the colour of its bottom-left
pixel.
"""
import base64
import struct
import sys
import zlib

import pefile


def png(width, height, rows):
    """rows: list of bytes, RGBA, top to bottom."""
    raw = b''.join(b'\0' + r for r in rows)

    def chunk(kind, data):
        c = struct.pack('>I', len(data)) + kind + data
        return c + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6,
                                         0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def dib(data):
    """A BITMAPINFOHEADER DIB -> (width, height, bpp, palette, pixel offset)."""
    hsize, w, h, _, bpp, comp = struct.unpack_from('<IiiHHI', data, 0)
    assert hsize == 40 and comp == 0 and h > 0, (hsize, comp, h)
    nclr = struct.unpack_from('<I', data, 32)[0] or (1 << bpp if bpp <= 8 else 0)
    pal = [tuple(data[40 + 4 * i:43 + 4 * i][::-1]) for i in range(nclr)]
    return w, h, bpp, pal, 40 + 4 * nclr


def decode_pixels(data, off, w, h, bpp, pal):
    stride = ((w * bpp + 31) // 32) * 4
    rows = []
    for y in range(h):
        line = data[off + y * stride:off + (y + 1) * stride]
        px = []
        for x in range(w):
            if bpp == 4:
                b = line[x // 2]
                i = (b >> 4) if x % 2 == 0 else (b & 15)
                px.append(pal[i])
            elif bpp == 8:
                px.append(pal[line[x]])
            elif bpp == 24:
                px.append(tuple(line[3 * x:3 * x + 3][::-1]))
            else:
                raise ValueError(bpp)
        rows.append(px)
    rows.reverse()       # bottom-up DIB
    return rows, off + h * stride


def glyphs(data, n):
    """A TBitBtn glyph strip -> n PNGs (transparent = bottom-left colour)."""
    w, h, bpp, pal, off = dib(data)
    rows, _ = decode_pixels(data, off, w, h, bpp, pal)
    key = rows[-1][0]
    gw = w // n
    out = []
    for k in range(n):
        img = []
        for r in rows:
            img.append(b''.join(bytes(p) + (b'\0' if p == key else b'\xff')
                                for p in r[k * gw:(k + 1) * gw]))
        out.append(png(gw, h, img))
    return out


def icon(data):
    """.ico (one image, BITMAPINFOHEADER + XOR + AND) -> PNG."""
    count = struct.unpack_from('<H', data, 4)[0]
    assert count == 1
    w, h, _, _, _, _, size, offset = struct.unpack_from('<BBBBHHII', data, 6)
    d = data[offset:offset + size]
    _, bw, bh, _, bpp, _ = struct.unpack_from('<IiiHHI', d, 0)
    nclr = struct.unpack_from('<I', d, 32)[0] or (1 << bpp)
    pal = [tuple(d[40 + 4 * i:43 + 4 * i][::-1]) for i in range(nclr)]
    rows, off = decode_pixels(d, 40 + 4 * nclr, bw, bh // 2, bpp, pal)
    stride = ((bw + 31) // 32) * 4
    mask = []
    for y in range(bh // 2):
        line = d[off + y * stride:off + (y + 1) * stride]
        mask.append([(line[x // 8] >> (7 - x % 8)) & 1 for x in range(bw)])
    mask.reverse()
    img = [b''.join(bytes(p) + (b'\0' if m else b'\xff')
                    for p, m in zip(r, mr)) for r, mr in zip(rows, mask)]
    return png(bw, bh // 2, img)


def rcdata(pe, rtype, name):
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id != rtype:
            continue
        for n in t.directory.entries:
            if str(n.name) == name:
                e = n.directory.entries[0].data.struct
                return pe.get_data(e.OffsetToData, e.Size)
    raise KeyError(name)


def dfm_binary(dfm, prop):
    """The bytes of a binary property (vaBinary) named prop in a DFM."""
    key = bytes([len(prop)]) + prop.encode()
    i = dfm.index(key) + len(key)
    assert dfm[i] == 10
    n = struct.unpack_from('<I', dfm, i + 1)[0]
    return dfm[i + 5:i + 5 + n]


BEGIN = '# BEGIN IMAGES'
END = '# END IMAGES'


def main():
    pe = pefile.PE(sys.argv[1])
    dfm = rcdata(pe, 10, 'TMAINFORM')
    pic = dfm_binary(dfm, 'Picture.Data')
    assert pic[:6] == b'\x05TIcon', pic[:8]
    images = {'icon': icon(pic[6:])}
    gl = dfm_binary(dfm, 'Glyph.Data')
    n = struct.unpack_from('<I', gl, 0)[0]
    assert gl[4:6] == b'BM'
    images['close'], images['close_d'] = glyphs(gl[4 + 14:4 + n], 2)
    images['retry'], images['retry_d'] = glyphs(rcdata(pe, 2, 'BBRETRY'), 2)
    images['ok'], images['ok_d'] = glyphs(rcdata(pe, 2, 'BBOK'), 2)
    lines = ['IMAGES = {']
    for k, v in images.items():
        b = base64.b64encode(v).decode()
        lines.append("    '%s': (" % k)
        for i in range(0, len(b), 72):
            lines.append("        '%s'" % b[i:i + 72])
        lines.append('    ),')
    lines.append('}')
    if len(sys.argv) > 3 and sys.argv[2] == '--into':
        # replace the block between the markers in the given source file
        with open(sys.argv[3], encoding='utf-8', newline='') as f:
            src = f.read()
        nl = '\r\n' if '\r\n' in src else '\n'
        a = src.index(BEGIN)
        a = src.index(nl, a) + len(nl)
        b = src.index(END, a)
        src = src[:a] + nl.join(lines) + nl + src[b:]
        with open(sys.argv[3], 'w', encoding='utf-8', newline='') as f:
            f.write(src)
    else:
        print('\n'.join(lines))


if __name__ == '__main__':
    main()
