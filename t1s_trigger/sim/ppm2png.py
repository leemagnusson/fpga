#!/usr/bin/env python3
"""Convert the P3 PPM frame dumped by tb_oled into a PNG, scaled up. No PIL needed.
usage: ppm2png.py in.ppm out.png [scale]"""
import struct, sys, zlib

src, dst = sys.argv[1], sys.argv[2]
scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
tok = open(src).read().split()
assert tok[0] == 'P3'
w, h, _ = int(tok[1]), int(tok[2]), int(tok[3])
vals = list(map(int, tok[4:4 + 3 * w * h]))
rows = []
for y in range(h):
    line = bytearray()
    for x in range(w):
        line += bytes(vals[3 * (y * w + x):3 * (y * w + x) + 3]) * scale
    rows += [bytes([0]) + bytes(line)] * scale
def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w * scale, h * scale, 8, 2, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))
open(dst, 'wb').write(png)
print('wrote', dst, w * scale, 'x', h * scale)
