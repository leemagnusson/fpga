#!/usr/bin/env python3
"""Read (and optionally enable) the SQI block of the LAN867x PHY behind the
smsc95xx USB adapter, through the MII ioctl. Needs CAP_NET_ADMIN: run with sudo.

Clause-45 registers are reached through the clause-22 indirect pair (reg 13/14),
so each access is four ioctls; the kernel driver uses the same pair, so a read
that lands between its own 13/14 writes can return garbage once in a while.

usage: sudo python3 -I tools/t1s0_phy_regs.py [-i t1s0] [--enable | --dcq] [--watch SECONDS]

Two SQI engines exist on the LAN867x Rev D0 (datasheet DS60001573K):
  legacy block (0x00A0..0x00AC, same as LAN8650): --enable sets TOID=0xFF and SQIEN;
    deprecated on Rev D0 but it did produce results here. Result in SQI_STS0.
  DCQ block (OPEN Alliance TC14, 0xCC02..0xCC04): --dcq clears SQIEN (the two cannot
    run together), writes DCQ_TOID=0xFF which starts a measurement; the watch loop
    polls DCQ_SQIP bit 15, prints the 5-bit SQI+ and 3-bit SQI, then reads DCQ_SQI,
    which clears its update bit and starts the next measurement. The OA spec requires
    an update after at most 16 kB and 32 frames. ethtool only reads DCQ_SQIP and never
    restarts the measurement, so its value is the one result taken after reset.

Register map (MMD 31):
  0x00A0 SQI_CTL   bit 15 SQIRST, bit 14 SQIEN; bits 12 and 10 reset to 1, undocumented
  0x00A1 SQI_STS0  bit 7 SQIERR, bit 6 SQIVLD (read-to-clear), 5:3 SQIVAL, 2:0 SQIERRC
  0x00AA SQI_CFG0  bits 11:4 TOID (0xFF = all nodes)
  0x00AC SQI_CFG2  bits 12:8 SQIINTTHR (0x1F = interrupt off)
  0xCC00 ADFCAP    bit 0 SQI, 4:1 SQI+ bits, 10:8 HDD class
  0xCC02 DCQ_TOID  bits 7:0 TOID, a write starts a measurement
  0xCC03 DCQ_SQI   bit 15 SQI_UPD (read-to-clear, restarts), bits 2:0 SQI
  0xCC04 DCQ_SQIP  bit 15 SQIP_UPD (read-to-clear), bits 7:3 SQI+, bits 2:0 read 1
"""
import argparse
import fcntl
import socket
import struct
import time

SIOCGMIIPHY, SIOCGMIIREG, SIOCSMIIREG = 0x8947, 0x8948, 0x8949
MMD = 31
REGS = [(0x00A0, 'SQI_CTL'), (0x00A1, 'SQI_STS0'), (0x00AA, 'SQI_CFG0'), (0x00AC, 'SQI_CFG2'),
        (0xCC00, 'ADFCAP'), (0xCC02, 'DCQ_TOID'), (0xCC04, 'DCQ_SQIP')]   # DCQ_SQI not dumped: reading it restarts the DCQ measurement


class Mii:
    def __init__(self, ifname):
        self.ifname = ifname.encode()
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.phy = self._ioctl(SIOCGMIIPHY, 0, 0, 0)[1]

    def _ioctl(self, req, phy, reg, val):
        r = fcntl.ioctl(self.s, req, struct.pack('16sHHHH', self.ifname, phy, reg, val, 0))
        return struct.unpack('16sHHHH', r)

    def read(self, reg):
        return self._ioctl(SIOCGMIIREG, self.phy, reg, 0)[4]

    def write(self, reg, val):
        self._ioctl(SIOCSMIIREG, self.phy, reg, val)

    def read_mmd(self, addr):
        self.write(13, MMD)
        self.write(14, addr)
        self.write(13, 0x4000 | MMD)
        return self.read(14)

    def write_mmd(self, addr, val):
        self.write(13, MMD)
        self.write(14, addr)
        self.write(13, 0x4000 | MMD)
        self.write(14, val)


def decode_sts0(v):
    return (f'SQIERR={v >> 7 & 1} SQIVLD={v >> 6 & 1} SQIVAL={v >> 3 & 7} SQIERRC={v & 7}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', default='t1s0')
    ap.add_argument('--enable', action='store_true', help='legacy block: set SQI_CFG0 TOID=0xFF and SQI_CTL SQIEN, as the motor firmware does')
    ap.add_argument('--dcq', action='store_true', help='DCQ block: clear SQIEN, write DCQ_TOID=0xFF to start, and watch DCQ_SQIP/DCQ_SQI')
    ap.add_argument('--watch', type=float, default=0, help='poll the status registers every second for this long')
    a = ap.parse_args()
    m = Mii(a.i)
    rx_path = f'/sys/class/net/{a.i}/statistics/rx_packets'
    def rx(): return int(open(rx_path).read())
    print(f'{a.i}: PHY address {m.phy}, ID {m.read(2):04x}{m.read(3):04x}')
    for addr, name in REGS:
        v = m.read_mmd(addr)
        extra = '  ' + decode_sts0(v) if name == 'SQI_STS0' else ''
        print(f'  MMD31 0x{addr:04X} {name:12s} = 0x{v:04X}{extra}')
    if a.enable:
        cfg0 = m.read_mmd(0x00AA)
        m.write_mmd(0x00AA, cfg0 | 0xFF0)
        ctl = m.read_mmd(0x00A0)
        m.write_mmd(0x00A0, ctl | 1 << 14)
        print(f'enabled: SQI_CFG0 0x{cfg0:04X} -> 0x{m.read_mmd(0x00AA):04X}, SQI_CTL 0x{ctl:04X} -> 0x{m.read_mmd(0x00A0):04X}')
    if a.dcq:
        ctl = m.read_mmd(0x00A0)
        if ctl & 1 << 14:
            m.write_mmd(0x00A0, ctl & ~(1 << 14))
        m.write_mmd(0xCC02, 0xFF)                   # starts a DCQ measurement over all nodes
        print(f'dcq: SQI_CTL 0x{ctl:04X} -> 0x{m.read_mmd(0x00A0):04X}, DCQ_TOID -> 0x{m.read_mmd(0xCC02):04X}, '
              f'measurement started at rx_packets {rx()}')
    t0 = time.time()
    last_rx = rx()
    while time.time() - t0 < a.watch:
        now = time.strftime('%H:%M:%S')
        if a.dcq:
            plus = m.read_mmd(0xCC04)
            if plus & 1 << 15:
                sqi = m.read_mmd(0xCC03)            # clears SQI_UPD and starts the next measurement
                r = rx()
                print(f'{now} rx={r} (+{r - last_rx}) DCQ_SQIP 0x{plus:04X} SQI+={plus >> 3 & 0x1F}/31 '
                      f'DCQ_SQI 0x{sqi:04X} SQI={sqi & 7}/7', flush=True)
                last_rx = r
            else:
                print(f'{now} rx={rx()} DCQ_SQIP 0x{plus:04X} (no update)', flush=True)
        else:
            sts, plus = m.read_mmd(0x00A1), m.read_mmd(0xCC04)
            print(f'{now} rx={rx()} SQI_STS0 0x{sts:04X} {decode_sts0(sts)}  DCQ_SQIP 0x{plus:04X}', flush=True)
        time.sleep(1)


if __name__ == '__main__':
    main()
