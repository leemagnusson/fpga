#!/usr/bin/env python3
"""Plot `sqi update count` against `received packet count` from a log of
repeated `motor_util ... phy_stats` output (blocks starting with
't1s nonzero stats:'). Top panel: update count as a step; bottom panel:
received packets between consecutive updates. SVG written by hand (no
plotting library on the bench).

usage: sqi_updates_plot.py [-i /tmp/sqi_stats.txt] [-o arb/sqi_updates_vs_rx.svg]
"""
import argparse
import re

INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
BLUE, ORANGE = '#2a78d6', '#eb6834'
FONT = 'font-family="system-ui,-apple-system,Segoe UI,sans-serif"'


def parse(path):
    """Yield (received, updates, worst) once per stats block."""
    rx = upd = worst = None
    name = ''
    with open(path, errors='replace') as f:
        for line in f:
            if line.startswith('t1s nonzero stats:'):
                if rx is not None:
                    yield rx, upd or 0, worst
                rx = upd = worst = None
            elif line.startswith('received packet count:'):
                rx = int(line.split()[-1])
            elif line.startswith('sqi update count:'):
                upd = int(line.split()[-1])
            elif line.startswith('worst sqi:'):
                worst = int(line.split()[-1])
            elif not name:
                m = re.match(r'(\S+:\S+)\s+(\S+)\s', line)
                if m and ':' in m.group(1) and m.group(1).count(':') == 5:
                    name = f'{m.group(2)} ({m.group(1)})'
    if rx is not None:
        yield rx, upd or 0, worst
    parse.name = name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', default='/tmp/sqi_stats.txt')
    ap.add_argument('-o', default='arb/sqi_updates_vs_rx.svg')
    a = ap.parse_args()

    first_rx = last_rx = None
    steps = []                       # (rx, new update count, worst) at each change
    prev = -1
    for rx, upd, worst in parse(a.i):
        if first_rx is None:
            first_rx = rx
        last_rx = rx
        if upd != prev:
            steps.append((rx, upd, worst))
            prev = upd
    name = parse.name
    gaps = [(steps[i][1], steps[i][0] - steps[i - 1][0]) for i in range(1, len(steps))]
    worst = {w for _, _, w in steps if w is not None}

    W, H = 760, 540
    L, R = 70, 30
    top = dict(y0=48, y1=300)
    bot = dict(y0=340, y1=480)
    xmin, xmax = 0, last_rx
    nmax = steps[-1][1]
    gmax = max(g for _, g in gaps) if gaps else 1
    def X(v): return L + (W - L - R) * (v - xmin) / (xmax - xmin)
    def Yt(n): return top['y1'] - (top['y1'] - top['y0']) * n / nmax
    def Yb(g): return bot['y1'] - (bot['y1'] - bot['y0']) * g / (gmax * 1.08)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" {FONT} font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
         f'<text x="{L}" y="22" font-size="15" font-weight="600" fill="{INK}">SQI update count against received packets</text>',
         f'<text x="{L}" y="38" fill="{INK2}" font-size="11">{name}, {a.i}; worst sqi reported: '
         f'{", ".join(str(w) for w in sorted(worst)) or "none"}</text>']
    # x ticks (shared)
    stepx = 10 ** max(0, len(str(int(xmax))) - 1) // 2 or 1
    v = 0
    while v <= xmax:
        x = X(v)
        for pan in (top, bot):
            o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pan["y0"]}" y2="{pan["y1"]}" stroke="{GRID}"/>')
        o.append(f'<text x="{x:.1f}" y="{bot["y1"] + 16}" text-anchor="middle" fill="{MUTED}">{v / 1000:g}k</text>')
        v += stepx
    # top panel y
    ty = max(1, nmax // 5)
    for n in range(0, nmax + 1, ty):
        y = Yt(n)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{n}</text>')
    # bottom panel y
    by = 10 ** (len(str(int(gmax))) - 1) // 2 or 1
    g = 0
    while g <= gmax:
        y = Yb(g)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{g / 1000:g}k</text>')
        g += by
    for pan in (top, bot):
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{pan["y1"]}" y2="{pan["y1"]}" stroke="{AXIS}"/>')
    o.append(f'<text x="{(L + W - R) / 2:.0f}" y="{bot["y1"] + 32}" text-anchor="middle" fill="{INK2}">received packet count</text>')
    o.append(f'<text transform="translate(16,{(top["y0"] + top["y1"]) / 2:.0f}) rotate(-90)" text-anchor="middle" fill="{INK2}">sqi update count</text>')
    o.append(f'<text transform="translate(16,{(bot["y0"] + bot["y1"]) / 2:.0f}) rotate(-90)" text-anchor="middle" fill="{INK2}">packets since previous update</text>')

    # step line
    d = f'M{X(first_rx):.1f},{Yt(steps[0][1]):.1f}'
    for i in range(1, len(steps)):
        d += f' H{X(steps[i][0]):.1f} V{Yt(steps[i][1]):.1f}'
    d += f' H{X(last_rx):.1f}'
    o.append(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linejoin="round"/>')
    for rx, n, _ in steps[1:]:
        o.append(f'<circle cx="{X(rx):.1f}" cy="{Yt(n):.1f}" r="3.5" fill="{BLUE}" stroke="{SURF}" stroke-width="1.5"/>')
    # gaps
    if gaps:
        med = sorted(g for _, g in gaps)[len(gaps) // 2]
        y = Yb(med)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{ORANGE}" stroke-dasharray="4 3"/>')
        o.append(f'<text x="{W - R}" y="{y - 5:.1f}" text-anchor="end" fill="{ORANGE}">median {med:,} packets</text>')
        for n, g in gaps:
            rx = next(r for r, m, _ in steps if m == n)
            o.append(f'<circle cx="{X(rx):.1f}" cy="{Yb(g):.1f}" r="4" fill="{BLUE}" stroke="{SURF}" stroke-width="2"/>')
    o.append('</svg>')
    open(a.o, 'w').write('\n'.join(o))
    print(f'{a.o}: {len(steps) - 1} updates over {last_rx - first_rx:,} received packets; '
          f'gaps {", ".join(f"{g:,}" for _, g in gaps)}')


if __name__ == '__main__':
    main()
