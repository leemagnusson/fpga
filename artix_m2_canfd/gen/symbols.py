"""Generates lib/artix_m2_canfd.kicad_sym: one box symbol per part type,
pins on the left/right as declared in the design. Multi-unit parts (the FPGA)
get one unit per bank."""
from sexp import W, q, num, uid

GRID = 2.54
PIN_LEN = 2.54
LIB = "artix_m2_canfd"

def _font(size=1.27):
    return f"(effects (font (size {num(size)} {num(size)})))"

def symbol_geometry(pins_by_unit):
    """Returns {unit: (width, height, {pin_number: (x, y, angle)})} in mm,
    symbol coordinates (y up), origin at box centre."""
    geo = {}
    for unit, pins in pins_by_unit.items():
        left = [p for p in pins if p.side == "L"]
        right = [p for p in pins if p.side == "R"]
        rows = max(len(left), len(right), 1)
        longest = max([len(p.name) for p in pins] + [4])
        width = max(4 * GRID, (longest * 1.1 + 3) * 2 if left and right else (longest * 1.1 + 3))
        width = round(width / GRID) * GRID
        height = (rows + 1) * GRID
        pos = {}
        top = height / 2 - GRID
        for i, p in enumerate(left):
            pos[p.number] = (-width / 2 - PIN_LEN, top - i * GRID, 0)
        for i, p in enumerate(right):
            pos[p.number] = (width / 2 + PIN_LEN, top - i * GRID, 180)
        geo[unit] = (width, height, pos)
    return geo

def _two_pin_glyph(w, kind, name):
    """Vertical two-terminal symbols: pin 1 at the top (y=+2.54), pin 2 at the bottom."""
    w.open(f"symbol {q(name + '_0_1')}")
    if kind == "R":
        w.line("(rectangle (start -1.016 2.54) (end 1.016 -2.54) (stroke (width 0.254) (type default)) (fill (type none)))")
    elif kind == "C":
        w.line("(polyline (pts (xy -2.032 0.508) (xy 2.032 0.508)) (stroke (width 0.508) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy -2.032 -0.508) (xy 2.032 -0.508)) (stroke (width 0.508) (type default)) (fill (type none)))")
    elif kind == "L":
        for i in range(4):
            y = 1.905 - i * 1.27
            w.line(f"(arc (start 0 {num(y + 0.635)}) (mid 0.635 {num(y)}) (end 0 {num(y - 0.635)}) (stroke (width 0.254) (type default)) (fill (type none)))")
    elif kind == "FB":
        w.line("(rectangle (start -1.016 2.54) (end 1.016 -2.54) (stroke (width 0.254) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy -1.016 2.54) (xy 1.016 -2.54)) (stroke (width 0.254) (type default)) (fill (type none)))")
    elif kind == "LED":
        w.line("(polyline (pts (xy -1.27 1.27) (xy 1.27 1.27) (xy 0 -1.27) (xy -1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy -1.27 -1.27) (xy 1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy 1.524 0.508) (xy 2.54 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy 2.286 1.27) (xy 3.302 0.254)) (stroke (width 0.254) (type default)) (fill (type none)))")
    elif kind == "TVS":
        w.line("(polyline (pts (xy -1.27 1.27) (xy 1.27 1.27) (xy 0 -1.27) (xy -1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))")
        w.line("(polyline (pts (xy -1.27 -1.27) (xy 1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))")
    w.close()

TWO_PIN = {"R", "C", "L", "FB", "LED"}

def write_library(path, symbol_specs):
    """symbol_specs: {name: {'kind': 'R'|'C'|...|'box', 'pins_by_unit': {unit: [Pin...]}, 'ref': 'R'}}
    Returns {name: geometry} for the schematic placer."""
    w = W()
    w.open("kicad_symbol_lib")
    w.line("(version 20241209)")
    w.line("(generator \"artix_m2_canfd\")")
    w.line("(generator_version \"9.0\")")
    geos = {}
    for name, spec in sorted(symbol_specs.items()):
        kind = spec["kind"]
        pbu = spec["pins_by_unit"]
        w.open(f"symbol {q(name)}")
        w.line("(pin_names (offset 1.016))")
        w.line("(exclude_from_sim no)")
        w.line("(in_bom yes)")
        w.line("(on_board yes)")
        if kind in TWO_PIN:
            geo = {1: (2.0, 5.08, {"1": (0, 2.54 + PIN_LEN, 270), "2": (0, -2.54 - PIN_LEN, 90)})}
            props = [("Reference", spec["ref"], 1.27, 1.27), ("Value", name, 1.27, -1.27)]
        else:
            geo = symbol_geometry(pbu)
            width, height, _ = geo[1]
            props = [("Reference", spec["ref"], -width/2, height/2 + 1.27), ("Value", name, -width/2, -height/2 - 1.27)]
        geos[name] = geo
        for prop, val, x, y in props:
            w.line(f"(property {q(prop)} {q(val)} (at {num(x)} {num(y)} 0) {_font()})")
        w.line(f"(property \"Footprint\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))")
        w.line(f"(property \"Datasheet\" \"\" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))")
        w.line(f"(property \"Description\" {q(spec.get('description', ''))} (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))")
        if kind in TWO_PIN:
            _two_pin_glyph(w, kind, name)
            w.open(f"symbol {q(name + '_1_1')}")
            for p in pbu[1]:
                x, y, ang = geo[1][2][p.number]
                w.line(f"(pin {p.etype} line (at {num(x)} {num(y)} {ang}) (length {num(PIN_LEN)}) (name {q(p.name)} {_font()}) (number {q(p.number)} {_font()}))")
            w.close()
        else:
            for unit, pins in sorted(pbu.items()):
                width, height, pos = geo[unit]
                w.open(f"symbol {q(f'{name}_{unit}_1')}")
                w.line(f"(rectangle (start {num(-width/2)} {num(height/2)}) (end {num(width/2)} {num(-height/2)}) (stroke (width 0.254) (type default)) (fill (type background)))")
                for p in pins:
                    x, y, ang = pos[p.number]
                    w.line(f"(pin {p.etype} line (at {num(x)} {num(y)} {ang}) (length {num(PIN_LEN)}) (name {q(p.name)} {_font()}) (number {q(p.number)} {_font()}))")
                w.close()
        w.close()
    w.close()
    with open(path, "w") as f:
        f.write(w.text())
    return geos
