#!/usr/bin/env python3
"""Firmware update over PCIe for the artix_m2_canfd card.

The card's configuration flash holds two bitstreams (go.tcl builds both):

    0x000000  golden.bin   bootloader: sends the FPGA on to the application and is
                           what the FPGA falls back to if the application is
                           missing or damaged. Written once (JTAG); leave it alone.
    0x400000  top.bin      application: the image that normally runs. This tool
                           replaces it.

Both contain the same design, including the flash access this tool uses, so a
card that fell back to the bootloader can still be updated.

    sw/flash.py info                 which image runs, what is in the flash
    sw/flash.py update top.bin       write the application, reboot the FPGA, check it runs
    sw/flash.py write top.bin        write and verify only
    sw/flash.py verify top.bin
    sw/flash.py reboot               reconfigure the FPGA from flash (as at power-up)
    sw/flash.py erase                erase the application (the bootloader then runs)
    sw/flash.py read out.bin --len 0x180000 [--slot golden]

Needs read/write access to the card's BAR0 (/sys/bus/pci/devices/<card>/resource0):
run as root, or install the udev rule once with sw/host-setup.sh.

Registers (BAR0, rtl/misc_regs.vhd): 0x4060 signature, 0x4064 control, 0x4068 TX,
0x406C RX, 0x4070 image ID, 0x4074 reboot.
"""
import argparse
import ctypes
import glob
import mmap
import os
import sys
import time

FL_ID, FL_CTL, FL_TX, FL_RX, IMAGE_ID, REBOOT = 0x4060, 0x4064, 0x4068, 0x406C, 0x4070, 0x4074
SIGNATURE = 0x464C5348          # "FLSH"
GOLD = 0x474F4C44               # "GOLD": USR_ACCESS of the bootloader image
CS, GO, AUTO_RX, AUTO_TX = 0x01, 0x10, 0x20, 0x40
REBOOT_KEY = 0xB7000000

SLOTS = {"golden": (0x000000, 0x400000), "app": (0x400000, 0x400000)}   # name: (address, size)
BLOCK, PAGE = 0x10000, 256
IDCODES = {0x0362C093: "XC7A50T", 0x0362D093: "XC7A35T"}                # FPGAs this card can carry


def die(msg):
    sys.exit(f"flash.py: {msg}")


def find_card(dev, ids):
    if dev:
        path = f"/sys/bus/pci/devices/{dev if dev.count(':') == 2 else '0000:' + dev}"
        if not os.path.isdir(path):
            die(f"no PCI device {dev}")
        return path
    vendor, device = (int(x, 16) for x in ids.split(":"))
    found = [os.path.dirname(v) for v in glob.glob("/sys/bus/pci/devices/*/vendor")
             if int(open(v).read(), 16) == vendor
             and int(open(os.path.join(os.path.dirname(v), "device")).read(), 16) == device]
    if not found:
        die(f"no card with PCI ID {ids} found (lspci -d {ids}); if the FPGA was just reconfigured, "
            "replug it or rescan the bus")
    if len(found) > 1:
        die("several cards found, pick one with --dev: " + " ".join(os.path.basename(f) for f in found))
    return found[0]


class Card:
    """BAR0 of the card and the SPI flash behind it."""

    def __init__(self, path):
        self.path = path
        res = os.path.join(path, "resource0")
        try:
            fd = os.open(res, os.O_RDWR)
        except PermissionError:
            die(f"no access to {res}: run as root, or install the udev rule (sudo sw/host-setup.sh)")
        self.mm = mmap.mmap(fd, os.fstat(fd).st_size)
        os.close(fd)
        # ctypes reads and writes a c_uint32 as exactly one 32-bit bus access, which matters here
        # (a read of FLASH_RX can start a transfer); slicing the mmap may access it twice.
        self.reg = {off: ctypes.c_uint32.from_buffer(self.mm, off)
                    for off in (0, FL_ID, FL_CTL, FL_TX, FL_RX, IMAGE_ID, REBOOT)}
        if self.rd(0) == 0xFFFFFFFF:
            die("the card answers all ones: its memory space is not enabled (is the driver bound? "
                f"as root: echo 1 > {path}/enable)")
        if self.rd(FL_ID) != SIGNATURE:
            die(f"this bitstream has no flash access (signature {self.rd(FL_ID):#010x} at BAR0+0x4060): "
                "load one built from this revision over JTAG first (see README)")
        self.go = self.rd(FL_CTL) & GO
        self._ctl(0)
        self._go(1, cs=0)           # STARTUPE2 swallows the first three clocks after configuration

    def close(self):
        self.reg = None
        try:
            self.mm.close()
        except BufferError:
            pass

    def rd(self, off):
        return self.reg[off].value

    def wr(self, off, val):
        self.reg[off].value = val

    # --- SPI transfers -----------------------------------------------------------------------
    def _ctl(self, bits):
        """Write FLASH_CTRL without starting a transfer, and wait until the card has it. The
        read-back matters: AXI does not keep reads behind earlier writes, and bus accesses wait
        while a transfer runs, so once this returns everything sent so far is done."""
        want = bits | self.go
        self.wr(FL_CTL, want)
        for _ in range(1000):
            if self.rd(FL_CTL) == want:
                return
        die(f"FLASH_CTRL stuck at {self.rd(FL_CTL):#x}, wanted {want:#x}")

    def _go(self, nbytes, cs=CS):
        self.go ^= GO
        self._ctl(cs | (nbytes - 1) << 1)

    def _send(self, data):
        words, rest = divmod(len(data), 4)
        if words:
            self._ctl(CS | 3 << 1 | AUTO_TX)
            tx = self.reg[FL_TX]
            for i in range(0, 4 * words, 4):
                tx.value = int.from_bytes(data[i:i + 4], "big")
        if rest:
            self._ctl(CS | 3 << 1)
            self.wr(FL_TX, int.from_bytes(data[4 * words:], "big") << 8 * (4 - rest))
            self._go(rest)

    def _recv(self, n):
        out = bytearray()
        words, rest = divmod(n, 4)
        self._ctl(CS | 3 << 1)                         # AUTO_TX off before touching FLASH_TX
        self.wr(FL_TX, 0)
        if words:
            # With AUTO_RX each read returns the previous transfer and starts the next one.
            self._ctl(CS | 3 << 1 | AUTO_RX)
            rx = self.reg[FL_RX]
            rx.value                                   # starts transfer 1
            for _ in range(words - 1):
                out += rx.value.to_bytes(4, "big")
            self._ctl(CS | 3 << 1)                     # AUTO off, last transfer finished
            out += self.rd(FL_RX).to_bytes(4, "big")
        if rest:
            self._go(rest)
            out += (self.rd(FL_RX) & (1 << 8 * rest) - 1).to_bytes(rest, "big")
        return bytes(out)

    def spi(self, tx, nrx=0):
        """One chip-select cycle: send tx, then read nrx bytes."""
        self._ctl(CS)
        self._send(tx)
        data = self._recv(nrx) if nrx else b""
        self._ctl(0)
        return data

    # --- flash commands (W25Q128JV and other 3-byte-address SPI NOR) ---------------------------
    def jedec(self):
        return self.spi(b"\x9f", 3)

    def status(self):
        return self.spi(b"\x05", 1)[0]

    def wait_ready(self, timeout, what):
        end = time.monotonic() + timeout
        while self.status() & 1:
            if time.monotonic() > end:
                die(f"flash still busy {timeout} s after {what}")

    def write_enable(self):
        self.spi(b"\x06")
        if not self.status() & 2:
            die("the flash did not accept write enable")

    def read(self, addr, n):
        return self.spi(b"\x03" + addr.to_bytes(3, "big"), n)

    def erase_block(self, addr):
        self.write_enable()
        self.spi(b"\xd8" + addr.to_bytes(3, "big"))
        self.wait_ready(5, f"erasing block {addr:#x}")

    def program_page(self, addr, data):
        self.write_enable()
        self.spi(b"\x02" + addr.to_bytes(3, "big") + data)
        self.wait_ready(1, f"programming page {addr:#x}")


# --- bitstream files ----------------------------------------------------------------------------
def load_image(path):
    """Raw configuration data from a .bin or .bit file."""
    data = open(path, "rb").read()
    if data[:2] == b"\x00\x09":                        # .bit: tagged header, then 'e' + length + data
        i = data.find(b"\xff\xff\xff\xff\xff\xff\xff\xff")
        j = data.rfind(b"e", 0, i)
        if i < 0 or j < 0 or int.from_bytes(data[j + 1:j + 5], "big") != len(data) - j - 5:
            die(f"{path}: cannot parse this .bit file, pass the .bin instead")
        data = data[j + 5:]
    return data


def describe(header):
    """What the first bytes of a bitstream say: None if there is none, else a dict with the
    target FPGA's IDCODE, the MultiBoot jump address (bootloader images only), the watchdog
    value and the USR_ACCESS word."""
    i = header.find(b"\xaa\x99\x55\x66")
    if i < 0:
        return None
    w = [int.from_bytes(header[k:k + 4], "big") for k in range(i + 4, len(header) - 3, 4)]
    info = {"idcode": None, "jump": None, "timer": None, "usr_access": None}
    k = 0
    while k < len(w) - 1 and w[k] >> 13 != 0x30004000 >> 13:   # up to the first configuration data
        if w[k] == 0x30020001:                         # WBSTAR, then CMD: IPROG if this image jumps
            if k + 3 < len(w) and w[k + 2] == 0x30008001 and w[k + 3] == 0x0000000F:
                info["jump"] = w[k + 1] & 0x1FFFFFFF
        elif w[k] == 0x30022001:
            info["timer"] = w[k + 1]
        elif w[k] == 0x30018001:
            info["idcode"] = w[k + 1]
        elif w[k] == 0x3001A001:
            info["usr_access"] = w[k + 1]
        if w[k] >> 29 == 1 and (w[k] >> 27) & 3 == 2:  # type 1 write: skip its payload
            k += w[k] & 0x7FF
        k += 1
    return info


def image_name(usr_access):
    if usr_access == GOLD:
        return "bootloader"
    d, mo, y = usr_access >> 27, usr_access >> 23 & 15, 2000 + (usr_access >> 17 & 63)
    h, mi, s = usr_access >> 12 & 31, usr_access >> 6 & 63, usr_access & 63
    if 1 <= d <= 31 and 1 <= mo <= 12 and h < 24 and mi < 60 and s < 60:
        return f"application built {y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
    return f"image {usr_access:#010x}"


def check_image(path, data, slot):
    base, size = SLOTS[slot]
    if len(data) > size:
        die(f"{path} is {len(data)} bytes, the {slot} slot holds {size}")
    info = describe(data[:4096])
    if info is None or info["idcode"] is None:
        die(f"{path} does not look like a 7-series bitstream")
    if info["idcode"] & 0x0FFFFFFF not in IDCODES:
        die(f"{path} is for an FPGA with IDCODE {info['idcode']:#010x}, not this card's")
    if slot == "app" and info["jump"] is not None:
        die(f"{path} is a bootloader image (it jumps to {info['jump']:#x}); the application slot wants top.bin")
    if slot == "golden" and info["jump"] != SLOTS["app"][0]:
        die(f"{path} is not a bootloader image for this layout (no jump to {SLOTS['app'][0]:#x}); the golden slot wants golden.bin")
    if info["timer"] is None:
        print(f"warning: {path} has no configuration watchdog (TIMER_CFG): a damaged copy may hang instead of falling back")
    return info


# --- operations -----------------------------------------------------------------------------------
def progress(what, done, total, t0):
    sys.stdout.write(f"\r{what}: {100 * done // total:3d} %  {time.monotonic() - t0:5.1f} s")
    if done >= total:
        sys.stdout.write("\n")
    sys.stdout.flush()


def write_image(card, data, base):
    data += b"\xff" * (-len(data) % PAGE)
    t0 = time.monotonic()
    blocks = range(base, base + len(data), BLOCK)
    for n, addr in enumerate(blocks):                  # the first erase removes the old image's sync word
        card.erase_block(addr)
        progress("erase", n + 1, len(blocks), t0)
    t0 = time.monotonic()
    pages = list(range(PAGE, len(data), PAGE)) + [0]   # the page with the sync word goes in last:
    for n, off in enumerate(pages):                    # an interrupted write leaves no half-valid image
        page = data[off:off + PAGE]
        if page.count(0xFF) != PAGE:
            card.program_page(base + off, page)
        if n % 64 == 63 or n == len(pages) - 1:
            progress("program", n + 1, len(pages), t0)


def verify_image(card, data, base):
    t0 = time.monotonic()
    for off in range(0, len(data), BLOCK):
        want = data[off:off + BLOCK]
        got = card.read(base + off, len(want) + (-len(want) % 4))[:len(want)]
        if got != want:
            bad = next(i for i in range(len(want)) if got[i] != want[i])
            print()
            die(f"verify failed at flash address {base + off + bad:#x}: read {got[bad]:#04x}, expected {want[bad]:#04x}")
        progress("verify", min(off + BLOCK, len(data)), len(data), t0)


def cmd_info(card, args):
    print(f"card         {os.path.basename(card.path)}, {card.rd(0) & 15} CAN cores")
    running = card.rd(IMAGE_ID)
    print(f"running      {image_name(running)}" + ("  (the application is missing or failed to load)" if running == GOLD else ""))
    j = card.jedec()
    print(f"flash        JEDEC {j.hex()}, {(1 << j[2]) // (1 << 20) if 16 < j[2] < 32 else '?'} MB, status {card.status():#04x}")
    for slot, (base, size) in SLOTS.items():
        info = describe(card.read(base, 512))
        if info is None:
            what = "empty"
        else:
            what = image_name(info["usr_access"]) if info["usr_access"] is not None else "bitstream"
            what += f" for {IDCODES.get((info['idcode'] or 0) & 0x0FFFFFFF, 'another FPGA')}"
            if info["jump"] is not None:
                what += f", jumps to {info['jump']:#x}"
        print(f"{slot:6s} {base:#08x}  {what}")


def cmd_write(card, args):
    data = load_image(args.file)
    check_image(args.file, data, args.slot)
    base = SLOTS[args.slot][0]
    if args.slot == "golden" and not args.yes:
        print("This replaces the bootloader. If it is interrupted or the image is bad, the card will not\n"
              "configure and has to be reprogrammed over JTAG.")
        if input("Type 'golden' to go on: ") != "golden":
            die("not writing")
    print(f"{args.file}: {len(data)} bytes to the {args.slot} slot at {base:#x}")
    write_image(card, data, base)
    verify_image(card, data, base)


def cmd_verify(card, args):
    data = load_image(args.file)
    verify_image(card, data, SLOTS[args.slot][0])


def cmd_read(card, args):
    base = SLOTS[args.slot][0] if args.addr is None else args.addr
    n = args.len + (-args.len % 4)
    t0 = time.monotonic()
    with open(args.file, "wb") as f:
        for off in range(0, n, BLOCK):
            f.write(card.read(base + off, min(BLOCK, n - off)))
            progress("read", min(off + BLOCK, n), n, t0)
        f.truncate(args.len)


def cmd_erase(card, args):
    if args.slot == "golden":
        die("not erasing the bootloader")
    base = SLOTS[args.slot][0]
    info = describe(card.read(base, 512))
    card.erase_block(base)                             # enough: without its first block the image is not found
    print(f"erased the first block of the {args.slot} slot" + ("" if info else " (it was empty already)"))


def cmd_reboot(card, args):
    path, before = card.path, card.rd(IMAGE_ID)
    card.wr(REBOOT, REBOOT_KEY | args.addr)
    card.close()
    print("FPGA is reconfiguring", end="", flush=True)
    time.sleep(0.2)
    end = time.monotonic() + args.timeout
    card = None
    while time.monotonic() < end and card is None:
        time.sleep(0.5)
        print(".", end="", flush=True)
        res = os.path.join(path, "resource0")
        try:                                           # back when the device exists again, its driver has
            if os.path.exists(os.path.join(path, "driver")) and os.access(res, os.R_OK | os.W_OK):   # enabled it
                card = Card(path)
        except SystemExit:
            card = None
    print()
    if card is None:
        die(f"the card did not come back within {args.timeout} s. If the FPGA configured (LEDs), the PCIe "
            "link was not set up again. In a Thunderbolt enclosure that takes the ctucanfd-relink helper "
            "(sudo sw/host-setup.sh, then check /etc/default/ctucanfd-relink) or replugging the enclosure; "
            "otherwise try a rescan as root (echo 1 > /sys/bus/pci/rescan)")
    running = card.rd(IMAGE_ID)
    print(f"running      {image_name(running)}" + ("" if running != before else "  (same image as before)"))
    return card


def cmd_update(card, args):
    args.slot, args.yes, args.addr = "app", False, 0
    cmd_write(card, args)
    card = cmd_reboot(card, args)
    want = describe(load_image(args.file)[:4096])["usr_access"]
    if card.rd(IMAGE_ID) != want:
        die("the new application is not what is running: the FPGA fell back to the bootloader. "
            "Check the image and write it again")
    print("update done")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="See the top of this file and the README for the flash layout.")
    ap.add_argument("--dev", help="PCI address of the card, e.g. b7:00.0 (default: the only one found)")
    ap.add_argument("--id", default="1760:ff00", help="PCI vendor:device to look for (default %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="show the running image and the flash contents").set_defaults(fn=cmd_info)
    p = sub.add_parser("update", help="write the application image, reboot the FPGA and check it runs")
    p.add_argument("file")
    p.add_argument("--timeout", type=float, default=30)
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("write", help="erase, program and verify an image")
    p.add_argument("file")
    p.add_argument("--slot", choices=SLOTS, default="app")
    p.add_argument("--yes", action="store_true", help="do not ask before replacing the bootloader")
    p.set_defaults(fn=cmd_write)
    p = sub.add_parser("verify", help="compare the flash with an image file")
    p.add_argument("file")
    p.add_argument("--slot", choices=SLOTS, default="app")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("read", help="dump flash contents to a file")
    p.add_argument("file")
    p.add_argument("--slot", choices=SLOTS, default="app")
    p.add_argument("--addr", type=lambda s: int(s, 0), help="flash address (default: start of the slot)")
    p.add_argument("--len", type=lambda s: int(s, 0), required=True)
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("erase", help="remove the application image, so that the bootloader runs")
    p.add_argument("--slot", choices=SLOTS, default="app")
    p.set_defaults(fn=cmd_erase)
    p = sub.add_parser("reboot", help="reconfigure the FPGA from flash")
    p.add_argument("--addr", type=lambda s: int(s, 0), default=0,
                   help="flash address to boot from (default 0: bootloader, then application, as at power-up)")
    p.add_argument("--timeout", type=float, default=30)
    p.set_defaults(fn=cmd_reboot)
    args = ap.parse_args()
    card = Card(find_card(args.dev, args.id))
    args.fn(card, args)


if __name__ == "__main__":
    main()
