"""Generate the whole KiCad project: python3 gen/build.py"""
import os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design, footprints, symbols, schematic, pcb
from sexp import uid

PROJECT = "artix_m2_canfd"
ROOT = os.path.dirname(HERE)
LIBDIR = os.path.join(ROOT, "lib")

def main():
    d = design.build(os.path.join(HERE, "data", "xc7a50tcsg325pkg.txt"))
    missing = d.check()
    if missing:
        print("WARNING single-pin nets:", missing)
    balls = [p.number for p in d.parts[0].pins] if d.parts[0].ref == "U1" else []
    fps = footprints.write_all(LIBDIR, balls)
    # symbol specs from parts
    specs = {}
    for p in d.parts:
        if p.symbol in specs:
            continue
        kind = p.symbol if p.symbol in symbols.TWO_PIN else "box"
        pbu = {}
        for pin in p.pins:
            pbu.setdefault(pin.unit, []).append(pin)
        specs[p.symbol] = {"kind": kind, "pins_by_unit": pbu, "ref": p.ref.rstrip("0123456789"), "description": p.description}
    libpath = os.path.join(LIBDIR, f"{symbols.LIB}.kicad_sym")
    geos = symbols.write_library(libpath, specs)
    lib_text = open(libpath).read()
    root_uuid = uid("root")
    sheets = []
    for i, name in enumerate(d.sheets, start=2):
        suuid = uid("sheetpath", name)
        parts = [p for p in d.parts if any(p.sheet_of(u) == name for u in p.units())]
        fname = f"{name}.kicad_sch"
        schematic.write_sheet(os.path.join(ROOT, fname), PROJECT, root_uuid, suuid,
                              d.sheet_titles.get(name, name), i, parts, geos, lib_text, name)
        sheets.append((name, d.sheet_titles.get(name, name), fname, suuid, i))
    schematic.write_root(os.path.join(ROOT, f"{PROJECT}.kicad_sch"), PROJECT, root_uuid, sheets)
    schematic.write_project(ROOT, PROJECT)
    nets = pcb.write_pcb(os.path.join(ROOT, f"{PROJECT}.kicad_pcb"), d, os.path.join(LIBDIR, symbols.LIB + ".pretty"), symbols.LIB)
    # BOM
    with open(os.path.join(ROOT, "bom.csv"), "w") as f:
        f.write("Reference,Value,MPN,Footprint,Description,DNP\n")
        for p in sorted(d.parts, key=lambda p: (p.ref.rstrip("0123456789"), int(p.ref.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") or 0))):
            f.write(f'{p.ref},"{p.value}","{p.mpn}","{p.footprint}","{p.description}",{"yes" if p.dnp else ""}\n')
    print(f"{len(d.parts)} parts, {len(nets)} nets, {len(fps)} footprints, {len(sheets)} sheets written to {ROOT}")

if __name__ == "__main__":
    main()
