#!/usr/bin/env python3
"""candump with nanosecond hardware timestamps.

candump -H truncates to microseconds; this prints the raw hardware clock in
ns (seconds.nanoseconds) plus the delta to the previous frame. Note that in
'loopback on' mode each frame you send shows up twice: the kernel echo of the
sent frame (carrying the TX stamp) and the frame received back from the bus.

Usage: candump-ns.py [ifname]
"""
import socket, struct, sys

SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6
SO_TIMESTAMPING = 37
CAN_RAW_FD_FRAMES = 5
CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000

def main():
    ifname = sys.argv[1] if len(sys.argv) > 1 else "can0"
    s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    s.setsockopt(socket.SOL_CAN_RAW, CAN_RAW_FD_FRAMES, 1)
    s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING,
                 SOF_TIMESTAMPING_RX_HARDWARE | SOF_TIMESTAMPING_RAW_HARDWARE)
    s.bind((ifname,))
    last = None
    while True:
        data, anc, _, _ = s.recvmsg(72, 1024)
        ns = None
        for level, typ, cdata in anc:
            if level == socket.SOL_SOCKET and typ == SO_TIMESTAMPING:
                sec, nsec = struct.unpack_from("qq", cdata, 32)   # [2] = raw hardware
                ns = sec * 10**9 + nsec
        can_id, length, flags = struct.unpack_from("=IBB", data)
        ident = f"{can_id & 0x1fffffff:08X}" if can_id & CAN_EFF_FLAG else f"{can_id & 0x7ff:03X}"
        if can_id & CAN_ERR_FLAG:
            ident = "ERR " + ident
        fd = "FD" if len(data) == 72 else "  "
        payload = " ".join(f"{b:02X}" for b in data[8:8 + length])
        if ns is None:
            stamp, delta = "no hw stamp".rjust(20), ""
        else:
            stamp = f"{ns // 10**9:10d}.{ns % 10**9:09d}"
            delta = f"+{(ns - last) / 1e3:12.3f} us" if last is not None else ""
            last = ns
        print(f"{stamp} {delta:>18}  {ifname}  {ident:>8} {fd} [{length:2d}]  {payload}", flush=True)

if __name__ == "__main__":
    main()
