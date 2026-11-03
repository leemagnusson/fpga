"""Schematic emitter: a root sheet with one hierarchical sheet per design
sheet. Parts are placed on a grid; every connected pin gets a global label
with the net name, so the drawing is a labelled netlist rather than a
hand-routed schematic (all sheets share one global namespace)."""
import os
from sexp import W, q, num, uid
from symbols import LIB, GRID, PIN_LEN, TWO_PIN

SCH_VERSION = "20250114"
PAPER = "A3"           # 420 x 297 mm
MARGIN = 15.0
ROW_GAP = 6.0 * 2.54
COL_GAP = 40.0

def _snap(v):
    return round(v / 1.27) * 1.27

def _font(size=1.27, extra=""):
    return f"(effects (font (size {num(size)} {num(size)})) {extra})".replace(" )", ")")

def _prop(w, name, value, x, y, hide=False, justify="left"):
    w.open(f"property {q(name)} {q(value)}")
    w.line(f"(at {num(x)} {num(y)} 0)")
    h = " (hide yes)" if hide else ""
    w.line(f"(effects (font (size 1.27 1.27)) (justify {justify}){h})")
    w.close()

def _lib_symbols_block(w, lib_text, used):
    """Copy the used symbols from the generated library text into lib_symbols,
    renaming "NAME" to "lib:NAME" as KiCad does."""
    # crude but adequate parser: split the library at top-level "(symbol "
    body = lib_text
    start = body.index("(symbol ")
    chunks = []
    depth = 0; cur = []; i = start
    while i < len(body):
        ch = body[i]
        if ch == "(":
            if depth == 0:
                cur = []
            depth += 1
        cur.append(ch)
        if ch == ")":
            depth -= 1
            if depth == 0:
                chunks.append("".join(cur)); cur = []
        i += 1
    w.open("lib_symbols")
    for c in chunks:
        if not c.startswith("(symbol "):
            continue
        name = c.split('"')[1]
        if name not in used:
            continue
        c2 = c.replace(f'(symbol "{name}"', f'(symbol "{LIB}:{name}"', 1)
        for line in c2.split("\n"):
            w.line(line.strip()) if False else w.lines.append("\t" * w.depth + line.rstrip())
    w.close()

def _place_symbol(w, project, root_uuid, sheet_uuid, part, unit, geo, x, y, footprint_hidden=True):
    """Emit one symbol instance; returns {pin_number: (lx, ly, angle)} label positions."""
    width, height, pos = geo[unit]
    sym_uuid = uid("sym", part.ref, unit)
    w.open(f"symbol (lib_id {q(f'{LIB}:{part.symbol}')}) (at {num(x)} {num(y)} 0) (unit {unit})")
    w.line("(exclude_from_sim no)")
    w.line("(in_bom yes)")
    w.line("(on_board yes)")
    w.line(f"(dnp {'yes' if part.dnp else 'no'})")
    w.line(f"(uuid {q(sym_uuid)})")
    if part.symbol in TWO_PIN:
        _prop(w, "Reference", part.ref, x + 1.27, y - 1.27)
        _prop(w, "Value", part.value, x + 1.27, y + 1.27)
    else:
        _prop(w, "Reference", part.ref + (chr(64 + unit) if len(geo) > 1 else ""), x - width/2, y - height/2 - 1.27)
        _prop(w, "Value", part.value, x - width/2, y + height/2 + 1.27)
    _prop(w, "Footprint", part.footprint, x, y, hide=True)
    _prop(w, "Datasheet", "", x, y, hide=True)
    _prop(w, "Description", part.description, x, y, hide=True)
    if part.mpn:
        _prop(w, "MPN", part.mpn, x, y, hide=True)
    for p in part.pins:
        if p.unit == unit:
            w.line(f"(pin {q(p.number)} (uuid {q(uid('pin', part.ref, p.number))}))")
    w.open("instances")
    w.open(f"project {q(project)}")
    w.line(f"(path {q('/' + root_uuid + '/' + sheet_uuid)} (reference {q(part.ref)}) (unit {unit}))")
    w.close(); w.close()
    w.close()
    labels = {}
    for p in part.pins:
        if p.unit != unit:
            continue
        px, py, ang = pos[p.number]
        labels[p.number] = (x + px, y - py, ang)
    return labels

def _global_label(w, net, x, y, angle):
    w.open(f"global_label {q(net)} (shape bidirectional) (at {num(x)} {num(y)} {angle}) (fields_autoplaced yes)")
    justify = "right" if angle == 180 else ("left" if angle == 0 else ("left" if angle == 90 else "right"))
    w.line(f"(effects (font (size 1.27 1.27)) (justify {justify}))")
    w.line(f"(uuid {q(uid('lbl', net, x, y))})")
    w.open(f"property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\"")
    w.line(f"(at {num(x)} {num(y)} 0)")
    w.line("(effects (font (size 1.27 1.27)) (hide yes))")
    w.close()
    w.close()

def _no_connect(w, x, y):
    w.line(f"(no_connect (at {num(x)} {num(y)}) (uuid {q(uid('nc', x, y))}))")

def _sheet_header(w, uuid):
    w.open("kicad_sch")
    w.line(f"(version {SCH_VERSION})")
    w.line("(generator \"artix_m2_canfd\")")
    w.line("(generator_version \"9.0\")")
    w.line(f"(uuid {q(uuid)})")
    w.line(f"(paper {q(PAPER)})")

def _title(w, title, page):
    w.open("title_block")
    w.line(f"(title {q(title)})")
    w.line("(rev \"A\")")
    w.line("(company \"artix_m2_canfd: M.2 2280 Artix-7 CAN FD card\")")
    w.close()

def layout_sheet(parts, geos):
    """Place units of parts column by column. Returns [(part, unit, x, y)]."""
    items = []
    for part in parts:
        for unit in part.units():
            items.append((part, unit))
    # sort: big symbols first, then by reference
    def size(item):
        p, u = item
        g = geos[p.symbol][u]
        return -(g[0] * g[1])
    items.sort(key=lambda it: (size(it), it[0].ref, it[1]))
    placed = []
    x = MARGIN + 25
    y = MARGIN + 10
    col_w = 0
    max_y = 297 - MARGIN
    for p, u in items:
        wdt, hgt, _ = geos[p.symbol][u]
        label_room = 22.0 if p.symbol not in TWO_PIN else 10.0
        need_h = hgt + ROW_GAP
        if y + hgt > max_y and placed:
            y = MARGIN + 10
            x += col_w + COL_GAP
            col_w = 0
        cx = _snap(x + wdt/2 + label_room/2)
        cy = _snap(y + hgt/2)
        placed.append((p, u, cx, cy))
        y += need_h
        col_w = max(col_w, wdt + label_room)
    return placed

def write_sheet(path, project, root_uuid, sheet_uuid, title, page, parts, geos, lib_text):
    w = W()
    _sheet_header(w, sheet_uuid)
    _title(w, title, page)
    _lib_symbols_block(w, lib_text, {p.symbol for p in parts})
    placed = layout_sheet(parts, geos)
    for part, unit, x, y in placed:
        labels = _place_symbol(w, project, root_uuid, sheet_uuid, part, unit, geos[part.symbol], x, y)
        for p in part.pins:
            if p.unit != unit:
                continue
            lx, ly, ang = labels[p.number]
            if p.net:
                # label text points away from the symbol
                lab_angle = {0: 180, 180: 0, 90: 90, 270: 270}[ang]
                _global_label(w, p.net, lx, ly, lab_angle)
            else:
                _no_connect(w, lx, ly)
    w.line("(sheet_instances (path \"/\" (page \"1\")))") if False else None
    w.close()
    with open(path, "w") as f:
        f.write(w.text())
    return placed

def write_root(path, project, root_uuid, sheets):
    """sheets: [(name, title, file, uuid, page)]"""
    w = W()
    _sheet_header(w, root_uuid)
    _title(w, "artix_m2_canfd: M.2 Artix-7 CAN FD card (root)", 1)
    w.line("(lib_symbols)")
    x0, y0 = 30.0, 30.0
    for i, (name, title, fname, suuid, page) in enumerate(sheets):
        x = x0 + (i % 3) * 60
        y = y0 + (i // 3) * 40
        w.open(f"sheet (at {num(x)} {num(y)}) (size 45 20) (fields_autoplaced yes)")
        w.line("(stroke (width 0.1524) (type solid))")
        w.line("(fill (color 0 0 0 0.0000))")
        w.line(f"(uuid {q(suuid)})")
        _prop(w, "Sheetname", name, x, y - 0.7)
        _prop(w, "Sheetfile", fname, x, y + 20.6)
        w.open("instances")
        w.open(f"project {q(project)}")
        w.line(f"(path {q('/' + root_uuid)} (page {q(str(page))}))")
        w.close(); w.close()
        w.close()
    w.open("sheet_instances")
    w.line("(path \"/\" (page \"1\"))")
    w.close()
    w.close()
    with open(path, "w") as f:
        f.write(w.text())

def write_project(dirname, project):
    """Minimal .kicad_pro so the project opens; KiCad fills in defaults."""
    pro = {
        "board": {"design_settings": {"defaults": {}, "rules": {
            # 0.2 mm copper-to-edge: the finger beside the key slot only has 0.225 mm by
            # the spec geometry; routed tracks/vias keep 0.3 mm via the edge keep-out ring
            "min_copper_edge_clearance": 0.2, "min_clearance": 0.1, "min_track_width": 0.1,
            "min_via_diameter": 0.4, "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.2,
            "min_hole_clearance": 0.2, "min_silk_clearance": 0.0, "solder_mask_clearance": 0.0,
            "solder_mask_min_width": 0.0, "min_hole_to_hole": 0.25}}, "layer_presets": [], "viewports": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{project}.kicad_pro", "version": 1},
        "net_settings": {"classes": [
            {"name": "Default", "clearance": 0.1, "track_width": 0.1, "via_diameter": 0.4, "via_drill": 0.2,
             "diff_pair_width": 0.1, "diff_pair_gap": 0.15, "microvia_diameter": 0.2, "microvia_drill": 0.1,
             "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6},
            {"name": "pcie", "clearance": 0.1, "track_width": 0.1, "via_diameter": 0.4, "via_drill": 0.2,
             "diff_pair_width": 0.1, "diff_pair_gap": 0.15, "microvia_diameter": 0.2, "microvia_drill": 0.1,
             "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6},
            {"name": "power", "clearance": 0.15, "track_width": 0.3, "via_diameter": 0.4, "via_drill": 0.2,
             "diff_pair_width": 0.3, "diff_pair_gap": 0.2, "microvia_diameter": 0.2, "microvia_drill": 0.1,
             "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6}],
                         "meta": {"version": 3},
                         "netclass_patterns": [{"netclass": "pcie", "pattern": "PCIE_*"},
                                               {"netclass": "power", "pattern": "VCC*"}, {"netclass": "power", "pattern": "VIN_3V3"},
                                               {"netclass": "power", "pattern": "MGTAV*"}, {"netclass": "power", "pattern": "SW_*"},
                                               {"netclass": "power", "pattern": "GND"}]},
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [],
        "text_variables": {},
    }
    import json
    with open(os.path.join(dirname, f"{project}.kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)
    # library tables pointing at the generated libraries
    with open(os.path.join(dirname, "sym-lib-table"), "w") as f:
        f.write(f'(sym_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{LIB}.kicad_sym")(options "")(descr "generated"))\n)\n')
    with open(os.path.join(dirname, "fp-lib-table"), "w") as f:
        f.write(f'(fp_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{LIB}.pretty")(options "")(descr "generated"))\n)\n')
