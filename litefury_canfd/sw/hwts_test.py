#!/usr/bin/env python3
"""Exercise hardware timestamps on a CAN interface.

Sends N frames and prints, for each, the hardware TX timestamp (from the
socket error queue, SOF_TIMESTAMPING_TX_HARDWARE) and the hardware RX
timestamp of the frame as it came back over the bus (needs the card's RX to
see its own TX, e.g. a TX-to-RX jumper with 'loopback on presume-ack on', or a
second node echoing). Raw hardware time is the card's free-running counter,
so only differences are meaningful.

Usage: hwts_test.py [ifname] [count]
"""
import select, socket, struct, sys, time

SOF_TIMESTAMPING_TX_HARDWARE = 1 << 0
SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6
SOF_TIMESTAMPING_OPT_ID = 1 << 7
SO_TIMESTAMPING = 37
SCM_TIMESTAMPING = SO_TIMESTAMPING
MSG_ERRQUEUE = 0x2000
CAN_RAW_RECV_OWN_MSGS = 4
CAN_RAW_FD_FRAMES = 5

def ts_of(ancdata):
    """Return (sw_ns, raw_hw_ns) from an SCM_TIMESTAMPING cmsg, or None."""
    for level, typ, data in ancdata:
        if level == socket.SOL_SOCKET and typ == SCM_TIMESTAMPING:
            s0, n0, s1, n1, s2, n2 = struct.unpack("qqqqqq", data[:48])
            return s0 * 10**9 + n0, s2 * 10**9 + n2
    return None

def main():
    ifname = sys.argv[1] if len(sys.argv) > 1 else "can0"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    # Own-message echo off: the frame seen on the normal queue is then the one
    # the hardware received back from the bus, and the TX timestamp arrives
    # on the error queue only.
    s.setsockopt(socket.SOL_CAN_RAW, CAN_RAW_RECV_OWN_MSGS, 0)
    s.setsockopt(socket.SOL_CAN_RAW, CAN_RAW_FD_FRAMES, 1)
    s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING,
                 SOF_TIMESTAMPING_TX_HARDWARE | SOF_TIMESTAMPING_RX_HARDWARE |
                 SOF_TIMESTAMPING_RAW_HARDWARE)
    s.bind((ifname,))
    s.setblocking(False)
    print(f"{'#':>3} {'tx_hw_ns':>16} {'rx_hw_ns':>16} {'rx-tx us':>9} {'d tx us':>10}")
    last_tx = None
    for i in range(count):
        payload = struct.pack("<Q", i)
        s.send(struct.pack("=IB3x8s", 0x123, 8, payload))
        tx_hw = rx_hw = None
        deadline = time.time() + 2.0
        while (tx_hw is None or rx_hw is None) and time.time() < deadline:
            try:
                # The error-queue entry carries a copy of the sent frame, so
                # it can be matched to this iteration's payload.
                data, anc, _, _ = s.recvmsg(72, 1024, MSG_ERRQUEUE)
                t = ts_of(anc)
                if t and t[1] and data[8:16] == payload:
                    tx_hw = t[1]
                continue
            except BlockingIOError:
                pass
            r, _, _ = select.select([s], [], [], 0.05)
            if not r:
                continue
            try:
                data, anc, _, _ = s.recvmsg(72, 1024)
            except BlockingIOError:
                continue
            can_id, length = struct.unpack_from("=IB", data)
            t = ts_of(anc)
            if can_id == 0x123 and t and t[1] and data[8:16] == payload:
                rx_hw = t[1]
        d = (rx_hw - tx_hw) / 1e3 if (tx_hw and rx_hw) else float("nan")
        dtx = (tx_hw - last_tx) / 1e3 if (tx_hw and last_tx) else float("nan")
        print(f"{i:>3} {tx_hw if tx_hw else 'none':>16} {rx_hw if rx_hw else 'none':>16} {d:>9.2f} {dtx:>10.2f}")
        last_tx = tx_hw
        time.sleep(0.01)

if __name__ == "__main__":
    main()
