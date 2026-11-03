"""PCB emitter: writes the .kicad_pcb with the M.2 2280 outline, a 6-layer
0.8 mm stackup, net list, and every footprint placed (unrouted). Footprints
are embedded by reading the generated .kicad_mod files."""
import os, re
from sexp import W, q, num, uid

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
    # key-M notch at the connector edge: 1.2 wide, 4.0 deep, centred between pins 57 and 67.
    # Pin 1 centre = 11 - 19.85 + 0.175 + 18.5 (see footprints.m2_edge); pin n odd centre = pin1 - (n-1)/2*0.5
    pin1 = 11.0 - 19.85 + 0.175 + 18.5
    key_c = pin1 - 15.25            # midway between pin 57 (-14.0) and pin 67 (-16.5)
    kw, kd = 1.2, 4.0
    # mount notch: R3 semicircle, centre 1.0 mm inboard of the far edge
    r = 3.0; cy = yt + 1.0
    import math
    dx = math.sqrt(r*r - 1.0*1.0)     # half-width where the circle meets the edge
    # far edge with semicircle
    seg(xl, yt, -dx, yt)
    arc(-dx, yt, 0.0, cy + r, dx, yt)
    seg(dx, yt, xr, yt)
    # sides
    seg(xr, yt, xr, yb)
    seg(xl, yb, xl, yt)
    # connector edge with key notch (notch goes up into the board by kd)
    seg(xl, yb, key_c - kw/2, yb)
    seg(key_c - kw/2, yb, key_c - kw/2, yb - kd + kw/2)
    arc(key_c - kw/2, yb - kd + kw/2, key_c, yb - kd, key_c + kw/2, yb - kd + kw/2)
    seg(key_c + kw/2, yb - kd + kw/2, key_c + kw/2, yb)
    seg(key_c + kw/2, yb, xr, yb)

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
    # name: (x0, x1, y0, y1, side)   design coordinates, y from the connector edge
    "pcie":       (-10.5, 10.5, 4.6, 9.8, "F"),
    "fpga_io":    (-10.5, 10.5, 32.6, 42.2, "F"),      # J2 (fixed) sits at y 42.5-46.1
    "power":      (-10.5, 10.5, 46.4, 62.5, "F"),
    "can":        (-10.5, 10.5, 62.5, 75.3, "F"),
    # decoupling on the back, just beyond the BGA (the BGA shadow is full of fan-out vias)
    "fpga_decap": (-10.5, 10.5, 31.9, 38.0, "B"),
    "fpga_pwr":   (-10.5, 10.5, 31.9, 38.0, "B"),
    "m2":         (-10.5, 10.5, 4.6, 9.8, "F"),
    "misc":       (-10.5, 10.5, 46.4, 62.5, "F"),
}
GAP = 0.3

def courtyard(fp_text):
    m = re.search(r'\(fp_rect\n\s*\(start (-?[0-9.]+) (-?[0-9.]+)\)\n\s*\(end (-?[0-9.]+) (-?[0-9.]+)\)\n\s*\(stroke[^\n]*\n\s*\(fill no\)\n\s*\(layer "F.CrtYd"\)', fp_text)
    if not m:
        return (2.0, 2.0)
    x0, y0, x1, y1 = map(float, m.groups())
    return (abs(x1 - x0), abs(y1 - y0))

def pack(design, fp_texts):
    """Shelf-pack every non-fixed part into its zone. Sets part.place."""
    groups = {}
    for part in design.parts:
        if part.zone == "fixed":
            continue
        groups.setdefault(part.zone, []).append(part)
    overflow = []
    for zone, parts in groups.items():
        if zone not in ZONES:
            raise KeyError(f"no zone rectangle for {zone}")
        x0, x1, y0, y1, side = ZONES[zone]
        parts.sort(key=lambda p: (-courtyard(fp_texts[p.footprint.split(':')[1]])[1], -courtyard(fp_texts[p.footprint.split(':')[1]])[0], p.ref))
        x = x0; y = y0; row_h = 0
        for p in parts:
            w, h = courtyard(fp_texts[p.footprint.split(':')[1]])
            if x + w > x1 + 1e-6:
                x = x0; y += row_h + GAP; row_h = 0
            if y + h > y1 + 1e-6:
                overflow.append((zone, p.ref))
            p.place = (x + w / 2, y + h / 2, 0.0, side)
            x += w + GAP
            row_h = max(row_h, h)
    return overflow

# (net, layer, priority, x0, x1, y0, y1) in design coordinates
PLANES = [
    ("GND",       "In1.Cu", 0, -11, 11,  0, 80),
    ("GND",       "In4.Cu", 0, -11, 11,  0, 80),
    ("VCC3V3",    "In2.Cu", 0, -11, 11,  2.5, 80),       # VCCO balls are all around the package
    ("VCC1V8",    "In3.Cu", 0, -11, 11, 10, 62.3),
    ("VCC1V0",    "In3.Cu", 1, -2.6, 2.6, 20.6, 62),     # VCCINT/VCCBRAM core balls, strip up to the buck
    ("VIN_3V3",   "In3.Cu", 1, -11, 11,  0, 9.5),        # under the connector fingers
    ("VIN_3V3",   "In3.Cu", 1,  7.6, 11,  9.6, 62),      # ... and a strip up to the regulators
    ("VCC5V_CAN", "In3.Cu", 1, -11, 11, 62.3, 80),
    ("MGTAVCC",   "In3.Cu", 2,  2.8, 5.0, 17.2, 21.8),   # GTP corner, FPGA rotated 180
    ("MGTAVTT",   "In3.Cu", 3,  4.8, 7.4, 16.6, 22.6),
]

def _zones(w, nets):
    for net, layer, prio, x0, x1, y0, y1 in PLANES:
        if net not in nets:
            continue
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        w.open(f"zone (net {nets[net]}) (net_name {q(net)}) (layer {q(layer)})")
        w.line(f"(uuid {q(uid('zone', net, layer, x0, y0))})")
        w.line("(hatch edge 0.5)")
        w.line(f"(priority {prio})")
        w.line("(connect_pads (clearance 0.2))")
        w.line("(min_thickness 0.15)")
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
    import math
    pin1 = 11.0 - 19.85 + 0.175 + 18.5
    key_c = pin1 - 15.25
    strips = [(-11, 11, 0, width), (-11, 11, 80 - width, 80), (-11, -11 + width, 0, 80), (11 - width, 11, 0, 80),
              (key_c - 0.6 - width, key_c + 0.6 + width, 0, 4.0 + width)]          # key-M slot
    polys = [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)] for x0, x1, y0, y1 in strips]
    r = 3.0 + width
    polys.append([(r * math.cos(a), 79.0 + r * math.sin(a)) for a in [i * math.pi / 16 for i in range(33)]])  # mount notch
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
        print("WARNING parts overflow their zone:", overflow)
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
