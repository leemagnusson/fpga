#!/usr/bin/env python3
"""Load a WaveGen CSV into an R&S MXO oscilloscope's arbitrary generator over
USBTMC and fire it, no VISA needed (talks to /dev/usbtmcN directly).

usage:
  mxo_arb.py [-d /dev/usbtmc4] [-g 1] idn
  mxo_arb.py load arb/serial02_badcrc_rs.csv     copy the file to the scope, select and open it,
                                                 50 ohm load, single-shot mode, output on
  mxo_arb.py fire [-n 1] [--gap 0.2]             run the loaded waveform once (or n times)
  mxo_arb.py off                                  output off
  mxo_arb.py scpi 'WGEN1:ARBG:SRAT?' ...          raw commands (queries end in ?)

The device node must be readable and writable (sudo chmod a+rw /dev/usbtmcN
or a udev rule for 0aad:*). Commands: MXO 4 user manual 1335.5337.02,
"Waveform generator" remote commands; the MXO 3 uses the same set.
"""
import argparse
import fcntl
import os
import struct
import sys
import time


USBTMC_IOC_NR = 91                                   # linux/usb/tmc.h
USBTMC_IOCTL_CLEAR = (USBTMC_IOC_NR << 8) | 2
USBTMC_IOCTL_SET_TIMEOUT = (1 << 30) | (4 << 16) | (USBTMC_IOC_NR << 8) | 10


class Usbtmc:
    def __init__(self, path, timeout_ms=60000):
        self.fd = os.open(path, os.O_RDWR)
        fcntl.ioctl(self.fd, USBTMC_IOCTL_SET_TIMEOUT, struct.pack('I', timeout_ms))

    def clear(self):                    # USBTMC device clear: unsticks a device after a timeout
        fcntl.ioctl(self.fd, USBTMC_IOCTL_CLEAR)
        time.sleep(1)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        os.write(self.fd, data)

    def read(self, n=1 << 20):
        return os.read(self.fd, n).decode(errors='replace').strip()

    def ask(self, cmd):
        self.write(cmd)
        return self.read()

    def err(self):
        return self.ask('SYST:ERR?')

    def check(self, what):
        e = self.err()
        if not e.startswith('0,'):
            sys.exit(f'{what}: {e}')


def block(data):
    n = str(len(data)).encode()
    return b'#' + str(len(n)).encode() + n + data


def setup_gen(dev, wg, remote, want, rate):
    """Select and open the arbitrary file on the scope, single-shot, 50 ohm, output on."""
    dev.write(f'{wg}:ENAB OFF')
    dev.write(f'{wg}:FUNC ARB')
    dev.write(f'{wg}:ARBG:SOUR ARB')
    dev.write(f"{wg}:ARBG:NAME '{remote}'")
    dev.write(f'{wg}:ARBG:OPEN')
    for _ in range(120):                # the scope parses the CSV asynchronously
        time.sleep(0.5)
        if dev.ask(f'{wg}:ARBG:SAMP?').strip() == str(want):
            break
    else:
        sys.exit(f'OPEN did not finish: {dev.ask(f"{wg}:ARBG:SAMP?")} samples loaded, {want} in file; {dev.err()}')
    dev.check('ARBG:OPEN')
    if rate:                            # make sure the file's rate is applied
        dev.write(f'{wg}:ARBG:SRAT {rate}')
    dev.write(f'{wg}:ARBG:RUNM SING')
    dev.write(f'{wg}:OUTP:LOAD FIFT')
    dev.write(f'{wg}:ENAB ON')
    dev.ask('*OPC?')
    dev.check('generator setup')


def reopen(dev, wg):
    """Redo the setup with whatever file the generator has selected (after a USB clear the
    generator stays silent until this is done)."""
    remote = dev.ask(f'{wg}:ARBG:NAME?').strip().strip('"\'')
    want = int(dev.ask(f'{wg}:ARBG:SAMP?'))
    rate = dev.ask(f'{wg}:ARBG:SRAT?').strip()
    setup_gen(dev, wg, remote, want, rate)
    print(f'reopened {remote}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--dev', default='/dev/usbtmc4')
    ap.add_argument('-g', '--gen', type=int, default=1, help='generator 1 or 2')
    ap.add_argument('-n', type=int, default=1, help='fire: number of shots')
    ap.add_argument('--gap', type=float, default=0.2, help='fire: seconds between shots')
    ap.add_argument('--remote-dir', default=None, help='directory on the scope (default: MMEM:CDIR?)')
    ap.add_argument('cmd', choices=['idn', 'load', 'fire', 'off', 'scpi', 'clear', 'reopen'])
    ap.add_argument('args', nargs='*')
    a = ap.parse_args()

    dev = Usbtmc(a.dev)
    wg = f'WGEN{a.gen}'
    if a.cmd == 'clear':
        dev.clear()
        print(dev.ask('*IDN?'), '| last error:', dev.err())
        return
    if a.cmd == 'reopen':
        reopen(dev, wg)
        return
    if a.cmd == 'idn':
        print(dev.ask('*IDN?'))
        print('gen enabled:', dev.ask(f'{wg}:ENAB?'), ' function:', dev.ask(f'{wg}:FUNC?'),
              ' arb file:', dev.ask(f'{wg}:ARBG:NAME?'), ' srate:', dev.ask(f'{wg}:ARBG:SRAT?'),
              ' samples:', dev.ask(f'{wg}:ARBG:SAMP?'), ' Vpp:', dev.ask(f'{wg}:VOLT?'),
              ' load:', dev.ask(f'{wg}:OUTP:LOAD?'))
        print('last error:', dev.err())
    elif a.cmd == 'scpi':
        for c in a.args:
            if c.rstrip().endswith('?'):
                print(c, '->', dev.ask(c))
            else:
                dev.write(c)
                print(c, '->', dev.err())
    elif a.cmd == 'load':
        if len(a.args) != 1:
            sys.exit('load needs one file')
        src = a.args[0]
        data = open(src, 'rb').read()
        name = os.path.basename(src)
        rdir = a.remote_dir or dev.ask('MMEM:CDIR?').strip("'\"")
        remote = f'{rdir}/{name}' if rdir else name
        dev.write(b"MMEM:DATA '" + remote.encode() + b"'," + block(data))
        dev.check('MMEM:DATA')
        want = sum(1 for ln in data.decode(errors='replace').splitlines()
                   if ln.strip() and not ln.lstrip().startswith(('Rate', '//')))
        rate = None
        for ln in data.decode(errors='replace').splitlines():
            if ln.lstrip().startswith('Rate'):
                rate = ln.split('=')[1].split('/')[0].strip()
                break
        setup_gen(dev, wg, remote, want, rate)
        print(f'loaded {remote}: {len(data)} bytes; srate {dev.ask(f"{wg}:ARBG:SRAT?")} Sa/s, '
              f'{dev.ask(f"{wg}:ARBG:SAMP?")} samples, Vpp {dev.ask(f"{wg}:VOLT?")}, '
              f'load {dev.ask(f"{wg}:OUTP:LOAD?")}, output {dev.ask(f"{wg}:ENAB?")}')
    elif a.cmd == 'fire':
        stuck = 0
        for i in range(a.n):
            try:
                dev.write(f'{wg}:ARBG:RUNS')
                dev.ask('*OPC?')
            except TimeoutError:            # the USB link occasionally wedges: clear, reopen, carry on
                stuck += 1
                dev.clear()
                if stuck > 5:
                    sys.exit('USB keeps timing out')
                reopen(dev, wg)
            if i + 1 < a.n:
                time.sleep(a.gap)
        if stuck:
            print(f'{stuck} USB timeouts recovered')
        dev.check('RUNSingle')
        print(f'fired {a.n}x')
    elif a.cmd == 'off':
        dev.write(f'{wg}:ENAB OFF')
        dev.check('off')
        print('output off')


if __name__ == '__main__':
    main()
