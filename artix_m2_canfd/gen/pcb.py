"""PCB emitter: writes the .kicad_pcb with the M.2 2280 outline, a 6-layer
0.8 mm stackup, net list, and every footprint placed (unrouted). Footprints
are embedded by reading the generated .kicad_mod files."""
import os, re, math
from sexp import W, q, num, uid
from footprints import (M2_TONGUE_HALF, M2_TONGUE_H, M2_TONGUE_R, M2_KEY_W, M2_KEY_D, M2_KEY_C, M2_MOUNT_R)

PCB_VERSION = "20241229"
BOARD_W = 22.0
BOARD_L = 80.0

LAYERS = [
    (0, "F.Cu", "signal"), (4, "In1.Cu", "power"), (8, "In2.Cu", "power"), (12, "In3.Cu", "power"),
    (16, "In4.Cu", "power"), (2, "B.Cu", "signal"),
    (9, "F.Adhes", "user", "F.Adhesive"), (11, "B.Adhes", "user", "B.Adhesive"),
    (13, "F.Paste", "user"), (15, "B.Paste", "user"), (5, "F.SilkS", "user", "F.Silkscreen"), (7, "B.SilkS", "user", "B.Silkscreen"),
    (1, "F.Mask", "user"), (3, "B.Mask", "user"), (17, "Dwgs.User", "user", "User.Drawings"), (19, "Cmts.User", "user", "User.Comments"),
    (21, "Eco1.User", "user", "User.Eco1"), (23, "Eco2.User", "user", "User.Eco2"), (25, "Edge.Cuts", "user"), (27, "Margin", "user"),
    (31, "F.CrtYd", "user", "F.Courtyard"), (29, "B.CrtYd", "user", "B.Courtyard"), (35, "F.Fab", "user"), (33, "B.Fab", "user"),
]

def _layers(w):
    w.open("layers")
    for item in LAYERS:
        if len(item) == 4:
            w.line(f"({item[0]} {q(item[1])} {item[2]} {q(item[3])})")
        else:
            w.line(f"({item[0]} {q(item[1])} {item[2]})")
    w.close()

def _setup(w):
    w.open("setup")
    w.open("stackup")
    def layer(name, typ, thick, extra=""):
        w.line(f"(layer {q(name)} (type {q(typ)}) (thickness {num(thick)}){extra})")
    layer("F.SilkS", "Top Silk Screen", 0.01) if False else w.line("(layer \"F.SilkS\" (type \"Top Silk Screen\"))")
    w.line("(layer \"F.Paste\" (type \"Top Solder Paste\"))")
    w.line("(layer \"F.Mask\" (type \"Top Solder Mask\") (thickness 0.01))")
    layer("F.Cu", "copper", 0.035)
    layer("dielectric 1", "prepreg", 0.1, " (material \"FR4\") (epsilon_r 4.5) (loss_tangent 0.02)")
    layer("In1.Cu", "copper", 0.0175)
    layer("dielectric 2", "core", 0.2, " (material \"FR4\") (epsilon_r 4.5) (loss_tangent 0.02)")
    layer("In2.Cu", "copper", 0.0175)
    layer("dielectric 3", "prepreg", 0.1, " (material \"FR4\") (epsilon_r 4.5) (loss_tangent 0.02)")
    layer("In3.Cu", "copper", 0.0175)
    layer("dielectric 4", "core", 0.2, " (material \"FR4\") (epsilon_r 4.5) (loss_tangent 0.02)")
    layer("In4.Cu", "copper", 0.0175)
    layer("dielectric 5", "prepreg", 0.1, " (material \"FR4\") (epsilon_r 4.5) (loss_tangent 0.02)")
    layer("B.Cu", "copper", 0.035)
    w.line("(layer \"B.Mask\" (type \"Bottom Solder Mask\") (thickness 0.01))")
    w.line("(layer \"B.Paste\" (type \"Bottom Solder Paste\"))")
    w.line("(layer \"B.SilkS\" (type \"Bottom Silk Screen\"))")
    w.line("(copper_finish \"ENIG\")")
    w.line("(dielectric_constraints no)")
    w.close()
    w.line("(pad_to_mask_clearance 0)")
    w.line("(allow_soldermask_bridges_in_footprints no)")
    w.open("pcbplotparams")
    w.line("(layerselection 0x00000000_00000000_55555555_5755f5ff)")
    w.line("(plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)")
    w.line("(disableapertmacros no)")
    w.line("(usegerberextensions no)")
    w.line("(usegerberattributes yes)")
    w.line("(usegerberadvancedattributes yes)")
    w.line("(creategerberjobfile yes)")
    w.line("(dashed_line_dash_ratio 12.000000)")
    w.line("(dashed_line_gap_ratio 3.000000)")
    w.line("(svgprecision 4)")
    w.line("(plotframeref no)")
    w.line("(mode 1)")
    w.line("(useauxorigin no)")
    w.line("(hpglpennumber 1)")
    w.line("(hpglpenspeed 20)")
    w.line("(hpglpendiameter 15.000000)")
    w.line("(pdf_front_fp_property_popups yes)")
    w.line("(pdf_back_fp_property_popups yes)")
    w.line("(pdf_metadata yes)")
    w.line("(pdf_single_document no)")
    w.line("(dxfpolygonmode yes)")
    w.line("(dxfimperialunits yes)")
    w.line("(dxfusepcbnewfont yes)")
    w.line("(psnegative no)")
    w.line("(psa4output no)")
    w.line("(plot_black_and_white yes)")
    w.line("(sketchpadsonfab no)")
    w.line("(plotpadnumbers no)")
    w.line("(hidednponfab no)")
    w.line("(sketchdnponfab yes)")
    w.line("(crossoutdnponfab yes)")
    w.line("(subtractmaskfromsilk no)")
    w.line("(outputformat 1)")
    w.line("(mirror no)")
    w.line("(drillshape 1)")
    w.line("(scaleselection 1)")
    w.line("(outputdirectory \"\")")
    w.close()
    w.close()

def _outline(w):
    """M.2 2280: 22 x 80, connector edge at y = 0 (board extends to y = -80 in
    KiCad's y-down coordinates we flip: board occupies y in [0, 80] with the
    connector at y = 80? No: we keep the design's convention (y away from the
    connector) and map to KiCad y = -y_design + 80, so the connector edge is
    at the bottom (y_k = 80) and the semicircular mount notch at the top."""
    L = BOARD_L; W_ = BOARD_W
    def seg(x0, y0, x1, y1):
        w.open("gr_line")
        w.line(f"(start {num(x0)} {num(y0)}) (end {num(x1)} {num(y1)})")
        w.line("(stroke (width 0.05) (type default))")
        w.line("(layer \"Edge.Cuts\")")
        w.line(f"(uuid {q(uid('edge', x0, y0, x1, y1))})")
        w.close()
    def arc(sx, sy, mx, my, ex, ey):
        w.open("gr_arc")
        w.line(f"(start {num(sx)} {num(sy)}) (mid {num(mx)} {num(my)}) (end {num(ex)} {num(ey)})")
        w.line("(stroke (width 0.05) (type default))")
        w.line("(layer \"Edge.Cuts\")")
        w.line(f"(uuid {q(uid('arc', sx, sy, ex, ey))})")
        w.close()
    xl, xr = -W_/2, W_/2
    yt, yb = 0.0, L            # yt: far end (mount notch), yb: connector edge
    # Connector end (see footprints.M2_*): the 19.85 mm tongue carries the
    # fingers and is 4.0 mm tall; 1.075 mm shoulders either side with R0.5
    # inside fillets; round-ended key-M slot 1.2 wide and 3.5 deep next to pin 75.
    key_c, kw, kd = M2_KEY_C, M2_KEY_W, M2_KEY_D
    th, tt, tr = M2_TONGUE_HALF, M2_TONGUE_H, M2_TONGUE_R
    ys = yb - tt                      # shoulder line
    s45 = tr * (1 - math.sqrt(0.5))   # fillet mid-point offset from the corner lines
    # far edge with the mount notch: R1.75 semicircle centred on the edge
    r = M2_MOUNT_R
    seg(xl, yt, -r, yt)
    arc(-r, yt, 0.0, yt + r, r, yt)
    seg(r, yt, xr, yt)
    # sides down to the shoulders
    seg(xr, yt, xr, ys)
    seg(xl, ys, xl, yt)
    # shoulders, inside fillets, tongue walls
    seg(xl, ys, -th - tr, ys)
    arc(-th - tr, ys, -th - s45, ys + s45, -th, ys + tr)
    seg(-th, ys + tr, -th, yb)
    seg(xr, ys, th + tr, ys)
    arc(th + tr, ys, th + s45, ys + s45, th, ys + tr)
    seg(th, ys + tr, th, yb)
    # connector edge with the key slot (the slot goes up into the board by kd)
    seg(-th, yb, key_c - kw/2, yb)
    seg(key_c - kw/2, yb, key_c - kw/2, yb - kd + kw/2)
    arc(key_c - kw/2, yb - kd + kw/2, key_c, yb - kd, key_c + kw/2, yb - kd + kw/2)
    seg(key_c + kw/2, yb - kd + kw/2, key_c + kw/2, yb)
    seg(key_c + kw/2, yb, th, yb)

def _load_footprint(libdir, name):
    path = os.path.join(libdir, name + ".kicad_mod")
    return open(path).read()

def _embed_footprint(w, fp_text, libname, part, nets, x, y, rot, side):
    """Rewrite a library footprint as a board instance: add position, reference,
    nets on pads, and flip to the back if needed."""
    lines = fp_text.strip().split("\n")
    # header line: (footprint "NAME"
    name = lines[0].split('"')[1]
    body = "\n".join(lines[1:-1])  # drop first and last line
    body = body.replace('(layer "F.Cu")', f'(layer "{"B" if side == "B" else "F"}.Cu")', 1)
    body = re.sub(r'\(property "Reference" "REF\*\*"', f'(property "Reference" {q(part.ref)}', body)
    body = re.sub(r'\(property "Value" "[^"]*"', f'(property "Value" {q(part.value)}', body)
    # part data as footprint fields, so BOM tools and the fab uploaders can read them off the board
    body = re.sub(r'\(property "MPN" ""', f'(property "MPN" {q(part.mpn)}', body)
    body = re.sub(r'\(property "Description" ""', f'(property "Description" {q(part.description)}', body)
    if side == "B":
        for a, b in (("F.Cu", "B.Cu"), ("F.Paste", "B.Paste"), ("F.Mask", "B.Mask"), ("F.SilkS", "B.SilkS"),
                     ("F.Fab", "B.Fab"), ("F.CrtYd", "B.CrtYd")):
            body = body.replace(f'"{a}"', f'"__{b}__"')
        body = body.replace("__", "")
        # KiCad's flip (top/bottom) negates local Y and mirrors text
        def negy(m):
            return f"{m.group(1)}{m.group(2)} {num(-float(m.group(3)))}"
        body = re.sub(r'(\((?:at|start|end|center) )(-?[0-9.]+) (-?[0-9.]+)', negy, body)
        body = body.replace("(effects (font (size 1 1) (thickness 0.15)))", "(effects (font (size 1 1) (thickness 0.15)) (justify mirror))")
    # pads: attach nets
    def padnet(m):
        number = m.group(1)
        net = part.net_of(number) if _has_pin(part, number) else None
        if net is None:
            return m.group(0)
        return m.group(0) + f"\n\t\t(net {nets[net]} {q(net)})"
    body = re.sub(r'\(pad "([^"]*)" [a-z_]+ [a-z_]+\n\t+\(at -?[0-9.]+ -?[0-9.]+\)', padnet, body)
    # uuids must be unique per instance
    body = re.sub(r'\(uuid "([0-9a-f-]+)"\)', lambda m: f'(uuid {q(uid(part.ref, m.group(1)))})', body)
    w.open(f"footprint {q(libname + ':' + name)}")
    for line in body.split("\n"):
        w.lines.append("\t" * w.depth + line.strip("\t"))
    w.line(f"(at {num(x)} {num(y)} {num(rot)})")
    w.line(f"(uuid {q(uid('fp', part.ref))})")
    w.open("property \"Footprint\" " + q(part.footprint))
    w.line(f"(at 0 0 0) (layer \"F.Fab\") (hide yes) (uuid {q(uid('fpprop', part.ref))}) (effects (font (size 1 1) (thickness 0.15)))")
    w.close()
    w.open(f"property \"Datasheet\" \"\"")
    w.line(f"(at 0 0 0) (layer \"F.Fab\") (hide yes) (uuid {q(uid('dsprop', part.ref))}) (effects (font (size 1 1) (thickness 0.15)))")
    w.close()
    w.open(f"property \"Description\" {q(part.description)}")
    w.line(f"(at 0 0 0) (layer \"F.Fab\") (hide yes) (uuid {q(uid('descprop', part.ref))}) (effects (font (size 1 1) (thickness 0.15)))")
    w.close()
    w.line(f"(path {q('/' + uid('sheetpath', part.sheet) + '/' + uid('sym', part.ref, 1))})")
    w.line("(sheetname \"\")")
    w.line(f"(sheetfile {q(part.sheet + '.kicad_sch')})")
    w.line(f"(attr smd{' dnp' if part.dnp else ''})")
    w.close()

def _has_pin(part, number):
    return any(p.number == number for p in part.pins)

ZONES = {
    # name: (x0, x1, y0, y1, side)   design coordinates, y from the connector edge.
    # Zones stop 3 mm short of the long edges so each side keeps a routing
    # corridor on both layers for the signals that run the length of the card.
    "pcie":       (-8.0, -4.8, 4.6, 9.8, "F"),       # left of the fixed AC-coupling capacitors
    "fpga_io":    (-8.0, 8.0, 32.6, 42.2, "F"),        # J2 (fixed) sits at y 42.5-46.1
    "power":      (-8.0, 8.0, 46.4, 62.5, "F"),
    "can":        (-8.0, 8.0, 62.5, 75.3, "F"),
    # decoupling on the back, just beyond the BGA (the BGA shadow is full of
    # fan-out vias), one zone per rail so every capacitor sits over its own
    # plane: 1.0 V on the centre strip, 1.8 V and 3.3 V either side, the two
    # transceiver rails below the GTP corner on their island extensions.
    "decap_3v3":  (-8.0, -2.9, 31.9, 44.0, "B"),
    "decap_1v0":  (-2.3, 2.3, 31.9, 44.0, "B"),   # inside the 1.0 V strip with room for the vias
    "decap_1v8":  (3.4, 8.0, 31.9, 44.0, "B"),      # clear of the 1.0 V strip edge so the vias land on 1.8 V copper
    # transceiver-rail decoupling: AVCC on the back west of the PCIe capacitors, AVTT on the top
    # in the east corridor just below the GTP corner; both over their In2 plane blocks (PLANES).
    # The back between x -5 and 8.6 at y 8-16 stays free for REFCLK and the transmit pairs' B.Cu runs.
    "decap_avcc": (-8.0, -5.1, 6.6, 16.0, "B"),   # west of REFCLK's B.Cu run and capacitor vias (x > -4.9)
    "decap_avtt": (7.7, 10.6, 7.6, 15.9, "F"),
    # back-side zones for parts that are not placed relative to an IC
    "power_b":    (-8.0, 8.0, 56.0, 62.5, "B"),
    "can_b":      (-8.0, 8.0, 62.5, 76.5, "B"),      # the headers above it are top-side only
}
GAP = 0.3
GAP_BACK = 0.5   # room for a fan-out via between neighbouring parts on the back

def courtyard(fp_text):
    m = re.search(r'\(fp_rect\n\s*\(start (-?[0-9.]+) (-?[0-9.]+)\)\n\s*\(end (-?[0-9.]+) (-?[0-9.]+)\)\n\s*\(stroke[^\n]*\n\s*\(fill no\)\n\s*\(layer "F.CrtYd"\)', fp_text)
    if not m:
        return (2.0, 2.0)
    x0, y0, x1, y1 = map(float, m.groups())
    return (abs(x1 - x0), abs(y1 - y0))

def _rot(x, y, deg):
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c - y * s_, x * s_ + y * c

def _extent(w, h, rot):
    return (h, w) if rot % 180 == 90 else (w, h)

def _block(parts, fp_texts, max_w, gap, owner):
    """Lay out one owner's parts as a block. Parts with a relative placement (Part.rel,
    the reference layout) sit at their offset from the owner; the other ICs go side by
    side on the first row and the other passives flow below, never wider than max_w.
    Returns ([(part, dx, dy, rot, side)], bw, bh); dx, dy are courtyard centres, y down."""
    size = lambda p: courtyard(fp_texts[p.footprint.split(':')[1]])
    head = next((p for p in parts if p.ref == owner), None)
    fixed = [p for p in parts if p.rel is not None and head is not None]
    heads = sorted([p for p in parts if p not in fixed and p is not head
                    and not p.footprint.split(':')[1].startswith(("C_", "R_", "L_", "FB_", "LED_"))],
                   key=lambda p: (-size(p)[1], -size(p)[0], p.ref))
    if head is not None:
        heads.insert(0, head)
    passives = sorted([p for p in parts if p not in heads and p not in fixed], key=lambda p: (-size(p)[1], -size(p)[0], p.ref))
    out = []
    x = 0.0; y = 0.0; head_h = 0.0
    for p in heads:                      # ICs side by side, wrapping if the block would get too wide
        w, h = size(p)
        if x > 0 and x + w > max_w + 1e-6:
            x = 0.0; y += head_h + gap; head_h = 0.0
        out.append((p, x + w / 2, y + h / 2, 0.0, p.place[3])); x += w + gap; head_h = max(head_h, h)
    head_h += y
    if fixed:                            # reference layout around the owner (design y up -> block y down)
        hx, hy = out[0][1], out[0][2]
        for p in fixed:
            dx, dy, rot, side = p.rel
            out.append((p, hx + dx, hy - dy, rot, side))
        minx = min(cx - _extent(*size(p), rot)[0] / 2 for p, cx, cy, rot, side in out)
        miny = min(cy - _extent(*size(p), rot)[1] / 2 for p, cx, cy, rot, side in out)
        out = [(p, cx - minx, cy - miny, rot, side) for p, cx, cy, rot, side in out]
        x = max(cx + _extent(*size(p), rot)[0] / 2 for p, cx, cy, rot, side in out)
        head_h = max(cy + _extent(*size(p), rot)[1] / 2 for p, cx, cy, rot, side in out)
    px0 = x if heads and not fixed else 0.0      # passives start beside the ICs ...
    px, py, row_h = px0, (head_h + gap if fixed else 0.0), 0.0   # ... or below a reference layout
    for p in passives:
        w, h = size(p)
        if px + w > max_w + 1e-6:
            py += row_h + gap; row_h = 0.0
            px = px0 if py < head_h + gap - 1e-6 else 0.0      # ... and below them once clear of their courtyards
        out.append((p, px + w / 2, py + h / 2, 0.0, p.place[3]))
        px += w + gap; row_h = max(row_h, h)
    bw = max([cx + _extent(*size(p), rot)[0] / 2 for p, cx, cy, rot, side in out], default=0.0)
    bh = max([cy + _extent(*size(p), rot)[1] / 2 for p, cx, cy, rot, side in out], default=0.0)
    return out, bw, bh

def pack(design, fp_texts):
    """Place every non-fixed part in its zone, block by block: each IC together with the
    passives it owns (Part.owner), blocks shelf-packed down the zone. Sets part.place."""
    groups = {}
    byref = {p.ref: p for p in design.parts}
    for part in design.parts:
        zone = part.zone
        if part.rel is not None and part.owner in byref:
            zone = byref[part.owner].zone                     # a reference layout stays with its IC
        if zone == "fixed":
            continue
        groups.setdefault(zone, {}).setdefault(part.owner, []).append(part)
    overflow = []
    for zone, owners in groups.items():
        if zone not in ZONES:
            raise KeyError(f"no zone rectangle for {zone}")
        x0, x1, y0, y1, side = ZONES[zone]
        gap = GAP_BACK if side == "B" else GAP
        x = x0; y = y0; row_h = 0
        for owner, parts in owners.items():
            max_w = (x1 - x0) / 2 - gap / 2 if x1 - x0 >= 12 else x1 - x0       # two blocks per row in the wide zones
            items, bw, bh = _block(parts, fp_texts, max_w, gap, owner)
            if x + bw > x1 + 1e-6:
                x = x0; y += row_h + gap; row_h = 0
            for p, dx, dy, rot, pside in items:
                w, h = _extent(*courtyard(fp_texts[p.footprint.split(':')[1]]), rot)
                if y + dy + h / 2 > y1 + 1e-6:
                    overflow.append((zone, p.ref))
                p.place = (x + dx, y + dy, rot, pside if p.rel is not None else side)
            x += bw + gap
            row_h = max(row_h, bh)
    # parts placed relative to a fixed owner (headers, connector)
    byref = {p.ref: p for p in design.parts}
    for p in design.parts:
        if p.rel is not None and p.owner in byref and byref[p.owner].zone == "fixed":
            o = byref[p.owner]
            dx, dy = _rot(p.rel[0], p.rel[1], o.place[2])
            p.place = (o.place[0] + dx, o.place[1] + dy, (p.rel[2] + o.place[2]) % 360, p.rel[3])
    return overflow

def _groups(w, design):
    """KiCad groups: every owner with more than one part, named after the owner."""
    members = {}
    for p in design.parts:
        members.setdefault(p.owner, []).append(p)
    for owner, parts in members.items():
        if len(parts) < 2:
            continue
        head = next((p for p in parts if p.ref == owner), None)
        name = f"{owner} {head.value}" if head else owner
        w.open(f"group {q(name)}")
        w.line(f"(uuid {q(uid('group', owner))})")
        w.open("members")
        for p in parts:
            w.line(q(uid('fp', p.ref)))
        w.close(); w.close()

# (net, layer, priority, x0, x1, y0, y1) in design coordinates
PLANES = [
    ("GND",       "In1.Cu", 0, -11, 11,  0, 80),
    ("GND",       "In4.Cu", 0, -11, 11,  0, 80),
    ("VCC3V3",    "In2.Cu", 0, -11, 11, 16.3, 80),       # VCCO balls are all around the package; the transceiver rails have In2 below it
    ("VCC1V8",    "In3.Cu", 0, -11, 11, 10, 62.3),
    ("VCC1V0",    "In3.Cu", 1, -2.6, 2.6, 20.6, 46.5),   # VCCINT/VCCBRAM core balls, strip up to the buck ...
    ("VCC1V0",    "In3.Cu", 2, -3.2, 0.2, 46.0, 51.5),   # ... ending under its output capacitors, so the 1.8 V plane
                                                         #     is whole under the LDOs, switch and boost further up
    ("VIN_3V3",   "In3.Cu", 1, -11, 11,  0, 9.5),        # under the connector fingers
    ("VIN_3V3",   "In3.Cu", 2,  7.6, 11,  9.0, 62),      # ... and a strip up to the regulators (overlaps the above so they join;
                                                         #     different priority so DRC does not flag the overlap)
    ("VIN_3V3",   "In3.Cu", 4, -11, -9.4,  9.0, 62.3),   # ... a strip up the west edge too: it feeds the two islands below
                                                         #     (the 1.0 V buck and the load switch) in copper, not through tracks
    ("VIN_3V3",   "In3.Cu", 3, -11, -3.0, 46.4, 50.2),   # 3.3 V input under the 1.0 V buck and its input capacitor
    ("VIN_3V3",   "In3.Cu", 3,  3.0, 11,  46.4, 50.5),   # ... under the 1.8 V buck's input
    ("VIN_3V3",   "In3.Cu", 3,  4.5, 11,  56.0, 62.3),   # ... under the boost's input capacitor and inductor
    ("VIN_3V3",   "In3.Cu", 3, -11, -2.5, 57.0, 62.3),   # ... under the load switch input
    ("VCC5V_CAN", "In3.Cu", 1, -11, 11, 62.3, 80),
    ("VCC5V_CAN", "In3.Cu", 3,  0.5, 4.0, 56.0, 62.5),   # down to the boost output and its capacitor
    # Transceiver rails on In2 (the 3.3 V plane keeps everything inside x +/-8.6): a strip
    # along each long edge from the LDO (y ~55) down to a block below the package that
    # carries the decoupling, plus the corner island under the GTP balls (FPGA rotated 180).
    # The escape via row at y 16.4 separates block and island; LINKS below joins them.
    ("MGTAVCC",   "In2.Cu", 4, -11.0, -8.6,  8.0, 56.5),   # west strip (same-net rectangles overlap: distinct priorities keep DRC quiet)
    ("MGTAVCC",   "In2.Cu", 5, -11.0,  4.0,  2.5, 16.1),   # block below the package (AVCC decoupling on the back)
    ("MGTAVCC",   "In2.Cu", 6,   2.8,  5.0, 17.2, 21.8),   # GTP corner island
    ("MGTAVTT",   "In2.Cu", 7,   8.6, 11.0,  8.0, 56.5),   # east strip
    ("MGTAVTT",   "In2.Cu", 8,   4.2, 11.0,  2.5, 16.1),   # block below the package (AVTT decoupling beside the east edge)
    ("MGTAVTT",   "In2.Cu", 9,   4.8,  7.4, 16.6, 22.6),   # GTP corner island
    ("MGTAVTT",   "In2.Cu", 10,  7.3,  9.4, 16.0, 17.5),   # neck round the east end of the escape via row: joins island and block
]

# Fixed links (design coordinates) that the fan-out adds and locks: the two
# transceiver-rail island extensions below the package cannot be joined to the
# corner islands on In3 (the BGA escape via row at y 16.4 is solid from x 1.2
# to 6.8), so a short 0.1 mm B.Cu track threads between those vias instead;
# placed right after the escapes so the plane fan-out keeps their cells free.
# (net, [("via", x, y) | ("track", "B"|"F", width, [(x, y), ...])])
LINKS = []      # none now: gen/router.py joins each corner island to the rest of its rail (ISLANDS)

# Corner islands of the transceiver rails (design coordinates x0, x1, y0, y1): copper under
# the GTP balls that the escape via row cuts off from the rest of the rail's plane. The
# router treats everything on an island as one group and links it to the main part.
ISLANDS = {"MGTAVCC": (2.8, 5.0, 17.2, 21.8), "MGTAVTT": (4.8, 7.4, 16.6, 22.6)}

def _zones(w, nets):
    for net, layer, prio, x0, x1, y0, y1 in PLANES:
        if net not in nets:
            continue
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        w.open(f"zone (net {nets[net]}) (net_name {q(net)}) (layer {q(layer)})")
        w.line(f"(uuid {q(uid('zone', net, layer, x0, y0))})")
        w.line("(hatch edge 0.5)")
        w.line(f"(priority {prio})")
        # 0.1 mm clearance and width: with 0.4 mm vias on the 0.8 mm BGA cell grid
        # anything larger leaves no copper between neighbouring vias and the
        # small islands under the package fall apart into disconnected slivers.
        w.line("(connect_pads (clearance 0.1))")
        w.line("(min_thickness 0.1)")
        w.line("(filled_areas_thickness no)")
        w.line("(fill yes (thermal_gap 0.25) (thermal_bridge_width 0.3))")
        w.open("polygon")
        w.open("pts")
        for x, y in pts:
            w.line(f"(xy {num(x + 31.0)} {num(BOARD_L - y + 20.0)})")
        w.close(); w.close()
        w.close()

def _edge_keepout(w, width=0.3):
    """Rule areas hugging the outline: no tracks or vias within `width` of the
    edge (pads and copper pours are still allowed). Freerouting honours these."""
    key_c, th = M2_KEY_C, M2_TONGUE_HALF
    strips = [(-11, 11, 0, width), (-11, 11, 80 - width, 80), (-11, -11 + width, 0, 80), (11 - width, 11, 0, 80),
              (key_c - M2_KEY_W/2 - width, key_c + M2_KEY_W/2 + width, 0, M2_KEY_D + width),   # key-M slot
              (-11, -th + width, 0, M2_TONGUE_H + width), (th - width, 11, 0, M2_TONGUE_H + width)]  # shoulders
    polys = [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)] for x0, x1, y0, y1 in strips]
    r = M2_MOUNT_R + width
    polys.append([(r * math.cos(a), 80.0 + r * math.sin(a)) for a in [i * math.pi / 16 for i in range(33)]])  # mount notch
    for k, pts in enumerate(polys):
        w.open("zone (net 0) (net_name \"\") (layers \"F&B.Cu\")")
        w.line(f"(uuid {q(uid('keepout', k))})")
        w.line("(hatch edge 0.5)")
        w.line("(keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed))")
        w.line("(connect_pads (clearance 0))")
        w.line("(min_thickness 0.25)")
        w.line("(filled_areas_thickness no)")
        w.line("(fill (thermal_gap 0.5) (thermal_bridge_width 0.5))")
        w.open("polygon"); w.open("pts")
        for x, y in pts:
            w.line(f"(xy {num(x + 31.0)} {num(BOARD_L - y + 20.0)})")
        w.close(); w.close(); w.close()

def write_pcb(path, design, libdir, libname):
    fp_texts = {}
    for part in design.parts:
        fpname = part.footprint.split(":")[1]
        if fpname not in fp_texts:
            fp_texts[fpname] = _load_footprint(libdir, fpname)
    overflow = pack(design, fp_texts)
    if overflow:
        raise SystemExit(f"parts overflow their zone (they would land on other parts): {overflow}")
    nets = {}
    for i, n in enumerate(design.nets(), start=1):
        nets[n] = i
    w = W()
    w.open("kicad_pcb")
    w.line(f"(version {PCB_VERSION})")
    w.line("(generator \"artix_m2_canfd\")")
    w.line("(generator_version \"9.0\")")
    w.open("general")
    w.line("(thickness 0.8)")
    w.line("(legacy_teardrops no)")
    w.close()
    w.line("(paper \"A4\")")
    _layers(w)
    _setup(w)
    w.line("(net 0 \"\")")
    for n, i in sorted(nets.items(), key=lambda kv: kv[1]):
        w.line(f"(net {i} {q(n)})")
    cache = fp_texts
    for part in design.parts:
        fpname = part.footprint.split(":")[1]
        x, y, rot, side = part.place
        # design coords: origin at connector edge centre, y away from the connector.
        # KiCad: y down; put the connector edge at y = 80 so the board sits in [0, 80].
        kx = x + 11.0 + 20.0          # board left edge at x = 20 mm on the sheet
        ky = BOARD_L - y + 20.0       # far end at y = 20 mm
        _embed_footprint(w, cache[fpname], libname, part, nets, kx, ky, rot, side)
    # power and ground planes (design coords, converted like the parts)
    _zones(w, nets)
    _groups(w, design)
    _edge_keepout(w)
    # outline, translated by the same offsets
    w2 = W(); w2.depth = w.depth
    _outline(w2)
    for line in w2.lines:
        line2 = re.sub(r'\((start|end|mid) (-?[0-9.]+) (-?[0-9.]+)\)',
                       lambda m: f"({m.group(1)} {num(float(m.group(2)) + 31.0)} {num(float(m.group(3)) + 20.0)})", line)
        w.lines.append(line2)
    w.close()
    with open(path, "w") as f:
        f.write(w.text())
    return nets
