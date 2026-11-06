#!/usr/bin/env python3
"""Pull Ethernet frames out of a usbmon capture of a smsc95xx adapter: bulk-IN completions
from the given device, each holding [4-byte LE RX status][frame][pad to 4]. Prints errored
frames (which the driver drops before tcpdump can see them) and compares them with a reference.

usage: sudo modprobe usbmon; sudo chmod a+r /dev/usbmonN   (N = USB bus of the adapter)
       tcpdump -i usbmonN -s 0 -w cap.pcap
       usb_frames.py cap.pcap <devnum> [reference frame hex incl. FCS]
"""
import struct, sys, binascii
pcap, devnum = sys.argv[1], int(sys.argv[2])
ref = bytes.fromhex(sys.argv[3]) if len(sys.argv) > 3 else None
f = open(pcap, 'rb').read()
magic = f[:4]
assert magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4'), 'pcap only'
endian = '<' if magic == b'\xd4\xc3\xb2\xa1' else '>'
linktype = struct.unpack(endian + 'I', f[20:24])[0]
off = 24
urbs = []
while off + 16 <= len(f):
    ts, tu, incl, orig = struct.unpack(endian + 'IIII', f[off:off + 16]); off += 16
    d = f[off:off + incl]; off += incl
    if len(d) < 48: continue
    typ, xfer, ep, dev = d[8], d[9], d[10], d[11]
    if typ == 0x43 and xfer == 3 and ep == 0x81 and dev == devnum:
        hdr = 64 if linktype == 220 else 48
        urbs.append(d[hdr:])
BITS = {0x8000: 'ES', 0x1000: 'LE', 0x800: 'RF', 0x80: 'TL', 0x40: 'CS', 0x20: 'FT', 0x10: 'RW', 0x8: 'ME', 0x4: 'DB', 0x2: 'CRC', 0x40000000: 'FF', 0x2000: 'BF', 0x400: 'MF'}
good = bad = 0
lens = {}
for u in urbs:
    p = 0
    while p + 4 <= len(u):
        st = struct.unpack('<I', u[p:p + 4])[0]; p += 4
        fl = (st >> 16) & 0x3FFF
        frame = u[p:p + fl]
        p += fl + (4 - ((fl + 2) % 4)) % 4
        if fl == 0: break
        flags = [n for b, n in BITS.items() if st & b]
        if st & 0x8000:
            bad += 1
            lens[fl] = lens.get(fl, 0) + 1
            if bad <= 12:
                print(f'ERR status 0x{st:08x} len {fl} {" ".join(flags)}')
                if ref:
                    n = min(len(frame), len(ref))
                    diff = [i for i in range(n) if frame[i] != ref[i]]
                    print(f'   first difference at byte {diff[0] if diff else "none"} of {n} compared; '
                          f'{len(diff)} bytes differ; ref len {len(ref)}')
                    if diff:
                        i = max(0, diff[0] - 4)
                        print('   got ', frame[i:i + 24].hex(' '))
                        print('   ref ', ref[i:i + 24].hex(' '))
                    print('   tail', frame[-16:].hex(' '))
        else:
            good += 1
print(f'{good} good frames, {bad} errored; errored lengths: {dict(sorted(lens.items()))}')
