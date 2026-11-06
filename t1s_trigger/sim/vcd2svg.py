#!/usr/bin/env python3
"""Draw a timing diagram (SVG) from a VCD file, for a look at a simulation
without a waveform viewer. Open the SVG in a browser or VS Code.

usage: vcd2svg.py in.vcd out.svg [-f FROM] [-t TO] SIGNAL...
       vcd2svg.py in.vcd -l

  SIGNAL  full hierarchical name (tb_top.line_p) or an unambiguous tail
          (line_p, u_dme.start). Order on the command line is top to bottom.
  -f/-t   time window, e.g. -f 10us -t 12us (default: whole simulation)
  -l      list every signal in the file and exit

Single bits are drawn as traces, vectors as buses labelled in hex; 'U', 'X',
'Z' and friends are hatched red. Std_logic bit values from GHDL are kept.
"""
import argparse
import re
import sys

UNITS = {'s': 1, 'ms': 1e-3, 'us': 1e-6, 'ns': 1e-9, 'ps': 1e-12, 'fs': 1e-15}


def parse_time(s):
    m = re.fullmatch(r'\s*([0-9.]+)\s*([a-z]+)\s*', s)
    if not m:
        sys.exit(f'bad time: {s!r}')
    return float(m.group(1)) * UNITS[m.group(2)]


def fmt_time(t):
    for u, k in (('s', 1), ('ms', 1e-3), ('us', 1e-6), ('ns', 1e-9), ('ps', 1e-12)):
        if t >= k or u == 'ps':
            v = t / k
            return (f'{v:.0f}' if abs(v - round(v)) < 1e-6 else f'{v:.3g}') + u


def read_vcd(path):
    """Returns (timescale seconds, {code: [(name, width)]}, [(time, code, value)])."""
    scope, names, codes = [], {}, {}
    scale = 1e-9
    changes = []
    with open(path) as f:
        tok = f.read().split()
    i, n = 0, len(tok)
    # header
    while i < n and tok[i] != '$enddefinitions':
        t = tok[i]
        if t == '$timescale':
            scale = parse_time(''.join(tok[i + 1:tok.index('$end', i)]))
        elif t == '$scope':
            scope.append(tok[i + 2])
        elif t == '$upscope':
            scope.pop()
        elif t == '$var':
            width, code, name = int(tok[i + 2]), tok[i + 3], tok[i + 4]
            j = i + 5
            while tok[j] != '$end':             # "[7:0]" may follow the name
                name += tok[j]
                j += 1
            full = '.'.join(scope + [name])
            names[full] = (code, width)
            codes.setdefault(code, []).append(full)
        if t in ('$timescale', '$var', '$comment', '$date', '$version'):
            i = tok.index('$end', i)
        i += 1
    # value changes: "#time", "1code" for bits, "b0101 code" for vectors
    now = 0
    j = i + 1
    while j < len(tok):
        t = tok[j]
        if t[0] == '#':
            now = int(t[1:])
        elif t[0] in 'bB':
            changes.append((now, tok[j + 1], t[1:]))
            j += 1
        elif t[0] in 'rR':
            changes.append((now, tok[j + 1], t[1:]))
            j += 1
        elif t[0] != '$':
            changes.append((now, t[1:], t[0]))
        elif t == '$comment':
            j = tok.index('$end', j)
        # other keywords ($dumpvars, $end) carry nothing
        j += 1
    return scale, names, changes


def resolve(names, want):
    if want in names:
        return want
    bare = lambda k: re.sub(r'\[[^\]]*\]$', '', k)      # drop a "[7:0]" suffix
    hits = [k for k in names if bare(k) == want or bare(k).endswith('.' + want)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        sys.exit(f'no signal matches {want!r} (use -l to list)')
    sys.exit(f'{want!r} is ambiguous: ' + ', '.join(hits))


def to_hex(v, width):
    if any(c not in '01' for c in v):
        return v if len(v) <= 4 else v[0] + '..'
    return f'{int(v, 2):0{(width + 3) // 4}X}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('vcd')
    ap.add_argument('svg', nargs='?')
    ap.add_argument('-f', '--from', dest='t0')
    ap.add_argument('-t', '--to', dest='t1')
    ap.add_argument('-l', '--list', action='store_true')
    ap.add_argument('-W', '--width', type=int, default=1600, help='pixels')
    ap.add_argument('signals', nargs='*')
    a = ap.parse_args()

    scale, names, changes = read_vcd(a.vcd)
    if a.list:
        for k in sorted(names):
            print(k, names[k][1])
        return
    if not a.signals or not a.svg:
        sys.exit('need an output file and at least one signal')
    sigs = [resolve(names, s) for s in a.signals]
    t_end = changes[-1][0] * scale if changes else 0
    t0 = parse_time(a.t0) if a.t0 else 0
    t1 = parse_time(a.t1) if a.t1 else t_end
    if t1 <= t0:
        sys.exit('empty window')

    # value history per signal: list of (time, value), clipped to the window
    hist = {s: [] for s in sigs}
    code_of = {names[s][0]: s for s in sigs}
    last = {s: 'U' * names[s][1] for s in sigs}
    for tm, code, v in changes:
        s = code_of.get(code)
        if s is None:
            continue
        ts = tm * scale
        if ts <= t0:
            last[s] = v
            hist[s] = [(t0, v)]
        elif ts < t1:
            if not hist[s]:
                hist[s] = [(t0, last[s])]
            hist[s].append((ts, v))
    for s in sigs:
        if not hist[s]:
            hist[s] = [(t0, last[s])]

    # geometry
    W, label_w, row_h, pad = a.width, 220, 34, 10
    plot_w = W - label_w - pad
    H = pad * 2 + 24 + row_h * len(sigs)
    px = lambda t: label_w + (t - t0) / (t1 - t0) * plot_w
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'font-family="monospace" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="#111"/>',
           '<defs><pattern id="hx" width="6" height="6" patternUnits="userSpaceOnUse">'
           '<path d="M0 6L6 0" stroke="#e55" stroke-width="1"/></pattern></defs>']
    # time axis
    ticks = 10
    for k in range(ticks + 1):
        t = t0 + (t1 - t0) * k / ticks
        x = px(t)
        out.append(f'<line x1="{x:.1f}" y1="{pad + 18}" x2="{x:.1f}" y2="{H - pad}" stroke="#333"/>')
        out.append(f'<text x="{x:.1f}" y="{pad + 12}" fill="#aaa" text-anchor="middle">{fmt_time(t)}</text>')
    y = pad + 24
    for s in sigs:
        width = names[s][1]
        hi, lo = y + 6, y + row_h - 8
        out.append(f'<text x="{label_w - 8}" y="{(hi + lo) / 2 + 4}" fill="#ddd" text-anchor="end">'
                   f'{s.split(".", 1)[-1]}</text>')
        h = hist[s] + [(t1, None)]
        for (ta, v), (tb, _) in zip(h, h[1:]):
            xa, xb = px(ta), px(tb)
            if width == 1:
                if v in '01':
                    yy = hi if v == '1' else lo
                    out.append(f'<line x1="{xa:.1f}" y1="{yy}" x2="{xb:.1f}" y2="{yy}" '
                               f'stroke="#4e4" stroke-width="1.5"/>')
                    if ta > t0:
                        out.append(f'<line x1="{xa:.1f}" y1="{hi}" x2="{xa:.1f}" y2="{lo}" '
                                   f'stroke="#4e4" stroke-width="1.5"/>')
                else:
                    out.append(f'<rect x="{xa:.1f}" y="{hi}" width="{max(xb - xa, 1):.1f}" '
                               f'height="{lo - hi}" fill="url(#hx)"/>')
            else:
                bad = any(c not in '01' for c in v)
                fill = 'url(#hx)' if bad else 'none'
                d = 3 if xb - xa > 6 else 0
                out.append(f'<path d="M{xa:.1f} {(hi + lo) / 2} L{xa + d:.1f} {hi} L{xb - d:.1f} {hi} '
                           f'L{xb:.1f} {(hi + lo) / 2} L{xb - d:.1f} {lo} L{xa + d:.1f} {lo} Z" '
                           f'fill="{fill}" stroke="#ec4" stroke-width="1.2"/>')
                txt = to_hex(v, width)
                if xb - xa > 7 * len(txt) + 6:
                    out.append(f'<text x="{(xa + xb) / 2:.1f}" y="{(hi + lo) / 2 + 4}" fill="#fff" '
                               f'text-anchor="middle">{txt}</text>')
        y += row_h
    out.append('</svg>')
    open(a.svg, 'w').write('\n'.join(out))
    print(f'wrote {a.svg}: {len(sigs)} signals, {fmt_time(t0)} to {fmt_time(t1)}')


if __name__ == '__main__':
    main()
