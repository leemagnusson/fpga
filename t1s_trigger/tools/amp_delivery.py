#!/usr/bin/env python3
"""Delivery-only amplitude run: for each generator level, build a clean 120-byte
frame at that amplitude, load it, fire N shots, and count how many frames the
motor's MAC (STATS7_FRX via phy_stats) and the host interface (rx_packets)
received. The generator is never running while phy_stats is read.

usage: amp_delivery.py --dst 02:00:00:00:00:01 [-n 500] [--host t1s0] -o out.csv 0.5 0.4 0.3 ...
"""
import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sqi_sweep import FRAME, log, motor, mxo, payload, sh, stats  # noqa: E402


def host_rx(ifname):
    try:
        return int(open(f'/sys/class/net/{ifname}/statistics/rx_packets').read())
    except OSError:
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('-n', '--shots', type=int, default=500)
    ap.add_argument('--dst', default='02:00:00:00:00:03')
    ap.add_argument('--host', default='t1s0')
    ap.add_argument('--workdir', default=os.path.join(os.environ.get('TMPDIR', '/tmp'), 'amp_delivery'))
    ap.add_argument('levels', nargs='+', type=float, help='generator levels (t1s_arb -a), e.g. 0.5 = 1 Vpp nominal')
    a = ap.parse_args()
    FRAME[3] = a.dst
    os.makedirs(a.workdir, exist_ok=True)
    pay = payload()
    rows = []
    for lvl in a.levels:
        path = os.path.join(a.workdir, f'amp{lvl:g}.csv')
        out = sh(['python3', '-I', os.path.join(HERE, 't1s_arb.py'), '-o', path, '-F', 'rs', '-a', str(lvl),
                  *FRAME, '--payload', pay])
        if 'samples' not in out:
            log(f'{lvl:g}: waveform generation failed'); continue
        out = mxo('load', path)
        if 'loaded' not in out:
            mxo('clear'); mxo('reopen'); out = mxo('load', path)
            if 'loaded' not in out:
                log(f'{lvl:g}: load failed: {out[-120:]}'); continue
        s0, h0 = stats(), host_rx(a.host)
        t0 = time.time()
        fired = mxo('fire', '-n', str(a.shots), '--gap', '0.005', timeout=120)
        time.sleep(0.5)
        s1, h1 = stats(), host_rx(a.host)
        row = {'level': lvl, 'vpp_nominal': 2 * lvl, 'shots': a.shots, 'motor_frames': s1['frx'] - s0['frx'],
               'motor_symbol_errors': s1['rxse'] - s0['rxse'], 'host_frames': h1 - h0,
               'seconds': round(time.time() - t0, 1), 'fired': 'fired' in fired}
        rows.append(row)
        log(f'{lvl:g} ({2 * lvl:g} Vpp nominal): motor {row["motor_frames"]}/{a.shots} frames, '
            f'{row["motor_symbol_errors"]} symbol errors; host {row["host_frames"]}/{a.shots}')
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['level'])
        w.writeheader(); w.writerows(rows)
    log('done')


if __name__ == '__main__':
    main()
