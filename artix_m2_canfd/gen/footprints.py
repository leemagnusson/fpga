"""Footprint generator: writes lib/artix_m2_canfd.pretty/*.kicad_mod.

Every footprint the board uses is generated here so the project does not
depend on the KiCad library version. Dimensions follow the vendor
recommended land patterns (see comments). Units: mm."""
import os
from sexp import W, q, num, uid

LIB = "artix_m2_canfd"

def _hdr(w, name, desc, attr="smd"):
    w.open(f"footprint {q(name)}")
    w.line("(version 20241229)")
    w.line("(generator \"artix_m2_canfd\")")
    w.line("(generator_version \"9.0\")")
    w.line("(layer \"F.Cu\")")
    w.line(f"(descr {q(desc)})")
    w.line(f"(attr {attr})")
    for prop, val, y in (("Reference", "REF**", -3), ("Value", name, 3)):
        w.open(f"property {q(prop)} {q(val)}")
        w.line(f"(at 0 {num(y)} 0)")
        w.line("(layer \"F.Fab\")")
        w.line(f"(uuid {q(uid(name, prop))})")
        w.line("(effects (font (size 1 1) (thickness 0.15)))")
        w.close()
    for prop in ("Datasheet", "Description"):
        w.open(f"property {q(prop)} \"\"")
        w.line("(at 0 0 0)")
        w.line("(layer \"F.Fab\")")
        w.line("(hide yes)")
        w.line(f"(uuid {q(uid(name, prop))})")
        w.line("(effects (font (size 1 1) (thickness 0.15)))")
        w.close()

def _rect(w, layer, x0, y0, x1, y1, width=0.1, tag=""):
    w.open("fp_rect")
    w.line(f"(start {num(x0)} {num(y0)})")
    w.line(f"(end {num(x1)} {num(y1)})")
    w.line(f"(stroke (width {num(width)}) (type default))")
    w.line("(fill no)")
    w.line(f"(layer {q(layer)})")
    w.line(f"(uuid {q(uid('rect', layer, x0, y0, x1, y1, tag))})")
    w.close()

def _line(w, layer, x0, y0, x1, y1, width=0.1):
    w.open("fp_line")
    w.line(f"(start {num(x0)} {num(y0)})")
    w.line(f"(end {num(x1)} {num(y1)})")
    w.line(f"(stroke (width {num(width)}) (type default))")
    w.line(f"(layer {q(layer)})")
    w.line(f"(uuid {q(uid('line', layer, x0, y0, x1, y1))})")
    w.close()

def _circle(w, layer, cx, cy, r, width=0.1):
    w.open("fp_circle")
    w.line(f"(center {num(cx)} {num(cy)})")
    w.line(f"(end {num(cx + r)} {num(cy)})")
    w.line(f"(stroke (width {num(width)}) (type default))")
    w.line("(fill no)")
    w.line(f"(layer {q(layer)})")
    w.line(f"(uuid {q(uid('circle', layer, cx, cy, r))})")
    w.close()

def _pad(w, number, x, y, sx, sy, shape="roundrect", layers=("F.Cu", "F.Paste", "F.Mask"),
         kind="smd", drill=None, rratio=0.25, name=""):
    w.open(f"pad {q(number)} {kind} {shape}")
    w.line(f"(at {num(x)} {num(y)})")
    w.line(f"(size {num(sx)} {num(sy)})")
    if drill:
        w.line(f"(drill {num(drill)})")
    w.line("(layers " + " ".join(q(l) for l in layers) + ")")
    if shape == "roundrect":
        w.line(f"(roundrect_rratio {num(rratio)})")
    w.line(f"(uuid {q(uid('pad', name, number, x, y))})")
    w.close()

# ---------------------------------------------------------------------------
def chip(name, body_l, body_w, pad_l, pad_w, pad_gap, desc):
    w = W(); _hdr(w, name, desc)
    cx = pad_gap / 2 + pad_l / 2
    _pad(w, "1", -cx, 0, pad_l, pad_w, name=name)
    _pad(w, "2", cx, 0, pad_l, pad_w, name=name)
    _rect(w, "F.Fab", -body_l/2, -body_w/2, body_l/2, body_w/2)
    cy = max(body_w/2, pad_w/2) + 0.25
    _line(w, "F.SilkS", -cx - pad_l/2 - 0.1, -cy, cx + pad_l/2 + 0.1, -cy, 0.12)
    _line(w, "F.SilkS", -cx - pad_l/2 - 0.1, cy, cx + pad_l/2 + 0.1, cy, 0.12)
    c = cx + pad_l/2 + 0.3
    _rect(w, "F.CrtYd", -c, -cy - 0.05, c, cy + 0.05, 0.05)
    w.close(); return name, w.text()

def polarized_chip(name, body_l, body_w, pad_l, pad_w, pad_gap, desc):
    name, txt = chip(name, body_l, body_w, pad_l, pad_w, pad_gap, desc)
    # add a cathode mark on pin 1 side
    w = W(); _hdr(w, name, desc)
    cx = pad_gap / 2 + pad_l / 2
    _pad(w, "1", -cx, 0, pad_l, pad_w, name=name)
    _pad(w, "2", cx, 0, pad_l, pad_w, name=name)
    _rect(w, "F.Fab", -body_l/2, -body_w/2, body_l/2, body_w/2)
    cy = max(body_w/2, pad_w/2) + 0.25
    x0 = -cx - pad_l/2 - 0.35
    _line(w, "F.SilkS", x0, -cy, cx + pad_l/2 + 0.1, -cy, 0.12)
    _line(w, "F.SilkS", x0, cy, cx + pad_l/2 + 0.1, cy, 0.12)
    _line(w, "F.SilkS", x0, -cy, x0, cy, 0.12)
    c = cx + pad_l/2 + 0.3
    _rect(w, "F.CrtYd", -c - 0.2, -cy - 0.05, c, cy + 0.05, 0.05)
    w.close(); return name, w.text()

def sot(name, npins_per_side_left, right_pins, pitch, pad_l, pad_w, row_dist, body_l, body_w, desc):
    """Generic SOT: left pins 1..n (top to bottom), right pins listed (bottom to top)."""
    w = W(); _hdr(w, name, desc)
    nL = npins_per_side_left
    y0 = -(nL - 1) * pitch / 2
    for i in range(nL):
        _pad(w, str(i + 1), -row_dist/2, y0 + i * pitch, pad_l, pad_w, name=name)
    nR = len(right_pins)
    y0 = (nR - 1) * pitch / 2
    for i, p in enumerate(right_pins):
        _pad(w, str(p), row_dist/2, y0 - i * pitch, pad_l, pad_w, name=name)
    _rect(w, "F.Fab", -body_w/2, -body_l/2, body_w/2, body_l/2)
    _circle(w, "F.Fab", -body_w/2 + 0.4, -body_l/2 + 0.4, 0.2)
    c = row_dist/2 + pad_l/2 + 0.25
    _rect(w, "F.CrtYd", -c, -body_l/2 - 0.25, c, body_l/2 + 0.25, 0.05)
    _line(w, "F.SilkS", -body_w/2, -body_l/2 - 0.15, body_w/2, -body_l/2 - 0.15, 0.12)
    _line(w, "F.SilkS", -body_w/2, body_l/2 + 0.15, body_w/2, body_l/2 + 0.15, 0.12)
    _line(w, "F.SilkS", -row_dist/2 - pad_l/2 - 0.3, -body_l/2 - 0.15, -row_dist/2 - pad_l/2 - 0.3, y0 - (nL-1)*pitch + 0.2 if False else -body_l/2 + 0.6, 0.12)
    w.close(); return name, w.text()

def dfn(name, n, pitch, pad_l, pad_w, row_dist, body, ep, desc, ep_num=None):
    """Dual flat no-lead: n pins total, n/2 per side, pin 1 top-left, counter-clockwise."""
    w = W(); _hdr(w, name, desc)
    h = n // 2
    y0 = -(h - 1) * pitch / 2
    for i in range(h):
        _pad(w, str(i + 1), -row_dist/2, y0 + i * pitch, pad_l, pad_w, name=name)
    for i in range(h):
        _pad(w, str(h + 1 + i), row_dist/2, y0 + (h - 1 - i) * pitch, pad_l, pad_w, name=name)
    if ep:
        ex, ey = ep
        _pad(w, str(ep_num or n + 1), 0, 0, ex, ey, shape="rect", name=name)
    bw, bl = body
    _rect(w, "F.Fab", -bw/2, -bl/2, bw/2, bl/2)
    _circle(w, "F.Fab", -bw/2 + 0.35, -bl/2 + 0.35, 0.15)
    _circle(w, "F.SilkS", -row_dist/2 - pad_l/2 - 0.3, y0, 0.12, 0.12)
    c = max(row_dist/2 + pad_l/2, bw/2) + 0.25
    _rect(w, "F.CrtYd", -c, -bl/2 - 0.25, c, bl/2 + 0.25, 0.05)
    w.close(); return name, w.text()

def osc_2520(name="Oscillator_2520_4pin", desc="2.5x2.0 mm 4-pad oscillator, pin1 = EN/NC, 2 GND, 3 OUT, 4 VDD"):
    w = W(); _hdr(w, name, desc)
    # ECS-2520MV suggested land: pads 0.9 x 0.8, gaps 0.95 (x) and 0.65 (y);
    # pin 1 bottom-left (chamfered corner), numbering counter-clockwise (top view)
    for n, (x, y) in enumerate([(-0.925, 0.725), (0.925, 0.725), (0.925, -0.725), (-0.925, -0.725)], start=1):
        _pad(w, str(n), x, y, 0.9, 0.8, name=name)
    _rect(w, "F.Fab", -1.25, -1.0, 1.25, 1.0)
    _circle(w, "F.SilkS", -1.7, 1.2, 0.12, 0.12)
    _rect(w, "F.CrtYd", -1.75, -1.5, 1.75, 1.5, 0.05)
    w.close(); return name, w.text()

def tag_connect_tc2050(name="TagConnect_TC2050-NL", desc="Tag-Connect TC2050-IDC-NL 2x5 pogo pad footprint, no legs"):
    w = W(); _hdr(w, name, desc, attr="smd exclude_from_pos_files")
    # pads 0.787 mm (31 mil) round-ish, pitch 1.27, two rows 1.27 apart; pin 1 top-left, numbering per row
    for i in range(5):
        x = -2.54 + i * 1.27
        _pad(w, str(i * 2 + 1), x, -0.635, 0.787, 0.787, shape="circle", layers=("F.Cu", "F.Mask"), name=name)
        _pad(w, str(i * 2 + 2), x, 0.635, 0.787, 0.787, shape="circle", layers=("F.Cu", "F.Mask"), name=name)
    # alignment holes: 0.991 mm (39 mil) at 3 positions
    for n, (x, y) in enumerate([(-3.81, 0.0), (3.81, -1.016), (3.81, 1.016)], start=1):
        w.open(f"pad \"\" np_thru_hole circle")
        w.line(f"(at {num(x)} {num(y)})")
        w.line("(size 0.991 0.991)")
        w.line("(drill 0.991)")
        w.line("(layers \"*.Cu\" \"*.Mask\")")
        w.line(f"(uuid {q(uid('tcpad', name, n))})")
        w.close()
    _rect(w, "F.CrtYd", -4.6, -1.8, 4.6, 1.8, 0.05)
    _circle(w, "F.SilkS", -2.54, -1.6, 0.15, 0.15)
    w.close(); return name, w.text()

def hirose_df52(n=20, name=None, desc=None):
    """Hirose DF52-nS-0.8H(21) right-angle SMT header, 0.8 mm pitch, 1.5 mm high.
    From the Hirose DF52 catalog table: contact span B = (n-1)*0.8, mechanical
    pad centres C = B + 2.4, overall A = B + 3.0 (20S: 15.2 / 17.6 / 18.2).
    Contact pad width 0.5; pad length and the row offset of the mechanical
    pads are not in the table and should be checked against the drawing."""
    name = name or f"Hirose_DF52-{n}S-0.8H"
    desc = desc or f"Hirose DF52-{n}S-0.8H(21) wire-to-board header, 0.8 mm pitch, 1.5 mm height"
    w = W(); _hdr(w, name, desc)
    B = (n - 1) * 0.8
    C = B + 2.4
    A = B + 3.0
    x0 = -B / 2
    for i in range(n):
        _pad(w, str(i + 1), x0 + i * 0.8, -2.0, 0.5, 1.0, name=name)
    for k, x in enumerate((-C / 2, C / 2), start=1):
        _pad(w, "MP", x, 0.0, 0.6, 0.9, shape="rect", name=f"{name}_mp{k}")
    _rect(w, "F.Fab", -A / 2, -1.6, A / 2, 1.4)
    _rect(w, "F.CrtYd", -A / 2 - 0.3, -2.8, A / 2 + 0.3, 1.7, 0.05)
    _circle(w, "F.SilkS", x0 - 0.6, -2.9, 0.12, 0.12)
    w.close(); return name, w.text()

def bga_csg325(balls, name="Xilinx_CSG325", desc="Xilinx CSG325: 18x18 0.8 mm pitch BGA, 0.4 mm balls, NSMD 0.35 mm pads"):
    """balls: list of ball names like 'A1' present on the device."""
    w = W(); _hdr(w, name, desc)
    rows = "ABCDEFGHJKLMNPRTUV"
    pitch = 0.8
    for b in balls:
        r = b[0]; c = int(b[1:])
        ri = rows.index(r)
        x = (c - 1 - 8.5) * pitch
        y = (ri - 8.5) * pitch
        _pad(w, b, x, y, 0.35, 0.35, shape="circle", name=name)
    half = 15.0 / 2
    _rect(w, "F.Fab", -half, -half, half, half)
    _line(w, "F.Fab", -half, -half + 1.0, -half + 1.0, -half)   # pin A1 chamfer
    _rect(w, "F.SilkS", -half - 0.1, -half - 0.1, half + 0.1, half + 0.1, 0.12)
    _circle(w, "F.SilkS", -half - 0.6, -half - 0.6, 0.2, 0.15)
    _rect(w, "F.CrtYd", -half - 0.25, -half - 0.25, half + 0.25, half + 0.25, 0.05)
    w.close(); return name, w.text()

def m2_edge(name="M2_Edge_2280_KeyM", desc="M.2 card-edge gold fingers, 75 positions, key M (pins 59-66 removed). Pads on both sides; card outline drawn separately."):
    """Geometry from the PCIe M.2 spec rev 1.0 figures 16/17 and table 48:
    0.5 mm pitch, odd pins on top (38 x 2.0 mm long), even pins on bottom
    (37 x 2.5 mm long) staggered 0.25 mm; pin 1 nearest the right edge
    (top view); finger span 19.85 from the right (datum E) edge.
    Origin: card centreline, at the connector edge (y = 0, card extends to -y)."""
    w = W(); _hdr(w, name, desc, attr="smd exclude_from_pos_files allow_soldermask_bridges")
    pad_w = 0.35
    # pin 1 pad right edge is 22 - 19.85 - (card left margin). Fingers span 19.85 mm measured
    # from the right card edge to the far (left) edge of pin 75. Right margin = 22 - 19.85 - span? Spec:
    # the 19.85 dimension runs from the left edge of pin 75's pad to datum E (right card edge).
    right_edge = 11.0                      # card is 22 wide, centred
    x_pin75_left = right_edge - 19.85      # = -8.85
    x_pin1_center = x_pin75_left + pad_w/2 + 37 * 0.5   # 18.5 mm between pin 75 and pin 1 centres
    keyed = set(range(59, 67))
    for n in range(1, 76):
        if n in keyed:
            continue
        if n % 2 == 1:
            i = (n - 1) // 2
            x = x_pin1_center - i * 0.5
            # pads stop 0.3 mm short of the edge (the 20 degree bevel removes that strip anyway)
            _pad(w, str(n), x, -1.15, pad_w, 1.7, shape="rect", layers=("F.Cu", "F.Mask"), name=name)
        else:
            i = (n - 2) // 2
            x = x_pin1_center - 0.25 - i * 0.5
            _pad(w, str(n), x, -1.4, pad_w, 2.2, shape="rect", layers=("B.Cu", "B.Mask"), name=name)
    # component keep-out marks
    _line(w, "F.Fab", -11, -4.0, 11, -4.0)
    _line(w, "B.Fab", -11, -5.2, 11, -5.2)
    w.close(); return name, w.text()

def all_footprints(fpga_balls):
    fps = [
        chip("C_0402", 1.0, 0.5, 0.6, 0.6, 0.5, "Capacitor 0402 (1005 metric)"),
        chip("R_0402", 1.0, 0.5, 0.6, 0.6, 0.5, "Resistor 0402 (1005 metric)"),
        chip("C_0603", 1.6, 0.8, 0.9, 0.95, 0.8, "Capacitor 0603 (1608 metric)"),
        chip("C_0805", 2.0, 1.25, 1.0, 1.4, 1.0, "Capacitor 0805 (2012 metric)"),
        chip("L_0806", 2.0, 1.6, 0.9, 1.7, 1.0, "Inductor 2016 (0806 inch), e.g. TDK TFM201610"),
        chip("FB_0402", 1.0, 0.5, 0.6, 0.6, 0.5, "Ferrite bead 0402"),
        polarized_chip("LED_0402", 1.0, 0.5, 0.6, 0.6, 0.5, "LED 0402, pin 1 = cathode"),
        sot("SOT-23-5", 3, [4, 5], 0.95, 1.0, 0.6, 2.6, 2.9, 1.6, "SOT-23-5 (TI DBV)"),
        sot("SOT-23-6", 3, [4, 5, 6], 0.95, 1.0, 0.6, 2.6, 2.9, 1.6, "SOT-23-6 (TI DBV)"),
        sot("SOT-23", 2, [3], 1.9, 1.0, 0.8, 2.4, 2.9, 1.3, "SOT-23 3-pin (pins 1,2 left; 3 right)"),
        sot("SOT-563", 3, [4, 5, 6], 0.5, 0.7, 0.3, 1.4, 1.6, 1.2, "SOT-563 (TI DRL), 6 pins, 0.5 mm pitch"),
        dfn("VSON-8_2x1.5mm_P0.5mm", 8, 0.5, 0.6, 0.25, 1.3, (1.5, 2.0), None, "VSON-HR 8 pin 2.0 x 1.5 mm, 0.5 mm pitch, no thermal pad (TI DLC)"),
        dfn("DFN-8_3x3mm_P0.65mm", 8, 0.65, 0.75, 0.35, 2.9, (3.0, 3.0), (1.7, 2.4), "DFN-8 3x3 mm 0.65 mm pitch with exposed pad (Microchip MF)", ep_num=9),
        dfn("WSON-8_6x5mm_P1.27mm", 8, 1.27, 0.9, 0.5, 5.6, (6.0, 5.0), (3.4, 4.0), "WSON-8 6x5 mm 1.27 mm pitch (Winbond PIQ)", ep_num=9),
        osc_2520(),
        tag_connect_tc2050(),
        hirose_df52(6),
        hirose_df52(20),
        bga_csg325(fpga_balls),
        m2_edge(),
    ]
    return fps

def write_all(libdir, fpga_balls):
    d = os.path.join(libdir, LIB + ".pretty")
    os.makedirs(d, exist_ok=True)
    names = []
    for name, txt in all_footprints(fpga_balls):
        with open(os.path.join(d, name + ".kicad_mod"), "w") as f:
            f.write(txt)
        names.append(name)
    return names
