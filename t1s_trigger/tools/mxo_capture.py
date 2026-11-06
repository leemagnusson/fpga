#!/usr/bin/env python3
"""Fire the loaded arbitrary waveform once, capture one single-shot acquisition on a
scope channel and save it as raw float32 samples plus a small header, straight over
USBTMC (no VISA). Uses the scope's current timebase, sample rate and trigger setup.

usage: mxo_capture.py [-d /dev/usbtmc4] [-c 1] [--no-fire] out.f32
writes out.f32 (little-endian float32 volts) and out.f32.hdr (xstart xstop samples)
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mxo_arb import Usbtmc


def read_block(dev):
    """Read an IEEE 488.2 definite-length block fully (USBTMC returns it in pieces)."""
    buf = os.read(dev.fd, 1 << 20)
    assert buf[:1] == b'#', buf[:40]
    nd = int(buf[1:2])
    total = int(buf[2:2 + nd])
    start = 2 + nd
    need = start + total
    while len(buf) < need:
        chunk = os.read(dev.fd, min(1 << 22, need - len(buf) + 1))
        if not chunk:
            break
        buf += chunk
    return buf[start:start + total]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--dev', default='/dev/usbtmc4')
    ap.add_argument('-c', '--chan', type=int, default=1)
    ap.add_argument('--no-fire', action='store_true', help='do not run the generator, just wait for a trigger')
    ap.add_argument('out')
    a = ap.parse_args()
    dev = Usbtmc(a.dev, timeout_ms=120000)
    ch = f'CHAN{a.chan}'
    dev.write('*CLS')
    dev.write('FORM REAL,32')
    dev.write('FORM:BORD LSBF')
    dev.write('SING')
    time.sleep(0.5)
    if not a.no_fire:
        dev.write('WGEN1:ARBG:RUNS')
    dev.ask('*OPC?')
    head = dev.ask(f'{ch}:DATA:HEAD?')
    print('header:', head, '| error:', dev.err())
    dev.write(f'{ch}:DATA?')
    data = read_block(dev)
    open(a.out, 'wb').write(data)
    open(a.out + '.hdr', 'w').write(head.replace(',', ' ') + '\n')
    print(f'{a.out}: {len(data) // 4} samples, error: {dev.err()}')


if __name__ == '__main__':
    main()
