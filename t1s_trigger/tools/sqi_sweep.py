#!/usr/bin/env python3
"""Unattended SQI sweep: for each rms edge-jitter value, build a 120-byte
frame waveform with that jitter, reset the motor, fire frames from the MXO
until the firmware reports an SQI update (or a frame limit), and append the
result to a CSV. Everything that can fail (USB, motor API) is retried and a
failed level is logged and skipped.

usage: sqi_sweep.py -o results.csv [--max-frames 36000] 2.0 3.0 "dcd4=--dcd 4e-9" "pj=--pj 100e3 5e-9" ...
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
FRAME = ['--src', '9c:95:6e:b5:60:e5', '--dst', '02:00:04:00:00:03', '--type', '88b6']   # dst replaced by --dst
PAYLOAD_SEED, PAYLOAD_LEN = 8, 106        # 120-byte frame, same payload as the earlier runs


def log(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def sh(args, timeout=60):
    """Run a command, return stdout (stderr merged); '' on failure or timeout."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return ''


def motor(*api, tries=4):
    for _ in range(tries):
        out = sh(['motor_util', '-e', '--set-api', *api], timeout=25)
        if re.search(r'^[1-9][0-9]* connected motor', out, re.M):   # any motor answered
            return out
        time.sleep(1)
    return ''


def stats():
    """FRX, RXSE, update count, worst sqi (None if absent) from phy_stats."""
    out = motor('phy_stats')
    def num(pat):
        m = re.search(pat, out)
        return int(m.group(1)) if m else None
    return {'frx': num(r'STATS7_FRX: (\d+)') or 0, 'rxse': num(r'STATS0_RXSE: (\d+)') or 0,
            'updates': num(r'sqi update count: (\d+)') or 0, 'worst': num(r'worst sqi: (\d+)'),
            'sts0': num(r'last sqi sts0: (\d+)')}


def mxo(*args, timeout=180):
    return sh(['python3', '-I', os.path.join(HERE, 'mxo_arb.py'), *args], timeout=timeout)


def payload():
    import random
    rng = random.Random(PAYLOAD_SEED)
    return ''.join('%02x' % rng.randrange(256) for _ in range(PAYLOAD_LEN))


def one_level(label, extra, max_frames, workdir):
    """label: name for the CSV; extra: list of t1s_arb.py arguments describing the impairment."""
    path = os.path.join(workdir, f'sweep_{label}.csv')
    out = sh(['python3', '-I', os.path.join(HERE, 't1s_arb.py'), '-o', path, '-F', 'rs',
              *extra, *FRAME, '--payload', payload()])
    if 'samples' not in out:
        raise RuntimeError('waveform generation failed: ' + out[-200:])
    log(f'{label} ({" ".join(extra)}): {out.strip().splitlines()[0][-90:]}')
    log(f'{label}: resetting motor')
    sh(['motor_util', '-e', 'set', '--mode', 'reset'], timeout=30)
    time.sleep(6)
    for _ in range(5):
        out = motor('send_interval_ms=0')
        if 'set' in out or 'error' in out:      # 'error' = firmware without that variable; the motor is back
            if 'error' in out:
                log(f'{label}: send_interval_ms not supported by this firmware, continuing')
            break
        time.sleep(2)
    else:
        raise RuntimeError('motor did not come back after reset')

    mxo('scpi', '*CLS')
    out = mxo('load', path)
    if 'loaded' not in out:
        mxo('clear')
        out = mxo('load', path)
        if 'loaded' not in out:
            raise RuntimeError('scope load failed: ' + out[-200:])

    s0 = stats()
    prev = s0['frx']
    t0 = time.time()
    shots = 0
    while shots < max_frames:
        out = mxo('fire', '-n', '500', '--gap', '0.005', timeout=300)
        shots += 500
        if 'USB keeps' in out:
            mxo('clear'); mxo('reopen')
        s = stats()
        got = (s['frx'] + s['rxse']) - prev          # errored frames still prove the generator is running
        if got < 400:
            log(f'  only {got} frames delivered in the last batch: reopen')
            mxo('reopen')
        prev = s['frx'] + s['rxse']
        if s['updates'] >= 1:
            frames = s['frx'] - s0['frx']
            errs = s['rxse'] - s0['rxse']
            sqi = 0 if s['worst'] == 8 else s['worst']
            log(f'  SQI {sqi} after {frames} frames, {errs} symbol errors, {time.time() - t0:.0f} s, sts0 {s["sts0"]:#06x}' if s['sts0'] is not None else f'  SQI {sqi} after {frames} frames, {errs} symbol errors, {time.time() - t0:.0f} s')
            return {'spec': label, 'args': ' '.join(extra), 'sqi': sqi, 'frames': frames,
                    'symbol_errors': errs, 'seconds': round(time.time() - t0), 'raw_worst': s['worst']}
        if shots % 5000 == 0:
            log(f'  {shots} shots, {s["frx"] - s0["frx"]} frames, {s["rxse"] - s0["rxse"]} symbol errors')
    s = stats()
    log(f'  no update after {s["frx"] - s0["frx"]} frames' + (f', sts0 {s["sts0"]:#06x}' if s['sts0'] is not None else ''))
    return {'spec': label, 'args': ' '.join(extra), 'sqi': '', 'frames': s['frx'] - s0['frx'],
            'symbol_errors': s['rxse'] - s0['rxse'], 'seconds': round(time.time() - t0), 'raw_worst': ''}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-o', '--out', required=True, help='CSV to append results to')
    ap.add_argument('-a', '--amplitude', type=float, default=0.5)
    ap.add_argument('--max-frames', type=int, default=36000)
    ap.add_argument('--dst', default='02:00:04:00:00:03', help='MAC of the motor under test')
    ap.add_argument('--workdir', default='/tmp/claude-1000/-home-lee-magnusson-fpga/'
                    'e3028211-f981-40d0-8269-1114f45329bf/scratchpad/arb')
    ap.add_argument('specs', nargs='+',
                    help='either a jitter in ns, or label=<t1s_arb options>, e.g. "dcd4=--dcd 4e-9"')
    a = ap.parse_args()
    FRAME[3] = a.dst
    os.makedirs(a.workdir, exist_ok=True)
    fields = ['when', 'spec', 'args', 'sqi', 'frames', 'symbol_errors', 'seconds', 'raw_worst']
    new = not os.path.exists(a.out)
    for spec in a.specs:
        if '=' in spec:
            label, extra = spec.split('=', 1)
            extra = extra.split()
        else:
            label, extra = f'j{float(spec):g}', ['--jitter', f'{float(spec)}e-9']
        if '-a' not in extra:
            extra = ['-a', str(a.amplitude)] + extra
        try:
            row = one_level(label, extra, a.max_frames, a.workdir)
        except Exception as e:                       # keep going with the next level
            log(f'{label} FAILED: {e}')
            mxo('clear')
            row = {'spec': label, 'args': ' '.join(extra), 'sqi': 'fail', 'frames': '',
                   'symbol_errors': '', 'seconds': '', 'raw_worst': ''}
        row['when'] = time.strftime('%Y-%m-%d %H:%M')
        with open(a.out, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if new:
                w.writeheader(); new = False
            w.writerow(row)
    log('sweep done')
    mxo('scpi', 'WGEN1:ARBG:RUNM SING')


if __name__ == '__main__':
    main()
