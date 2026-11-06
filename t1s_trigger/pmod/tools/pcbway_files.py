#!/usr/bin/env python3
"""Write the BOM and placement files PCBWay's assembly quote reads, in the same
layout as PCBWay's official KiCad plugin, and bundle them with the gerbers.

usage: pcbway_files.py out/positions.csv t1s_tap.kicad_pcb out/
Reads out/positions.csv (kicad-cli pcb export pos --format csv --units mm) and the
board (for the SMD/THT attribute), writes out/PCBWay_bom.csv, out/PCBWay_positions.csv
and out/t1s_tap_assembly.zip (gerbers + both CSVs)."""
import csv, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(__file__))
from netlist import PARTS, MPN

pos_csv, pcb, out = sys.argv[1:4]

# mount type from the board's footprint attributes
mount = {}
for blk in open(pcb).read().split('\n\t(footprint ')[1:]:
    ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
    mount[ref] = 'smt' if re.search(r'\(attr [^)]*smd', blk) else 'tht'

# placement file: pos_x,pos_y,rotation,side,designator,mpn,pack,footprint,value,mount_type
rows = []
with open(pos_csv, newline='') as f:
    for r in csv.DictReader(f):
        ref = r['Ref']
        if ref not in MPN:
            continue
        rows.append({'pos_x': r['PosX'], 'pos_y': r['PosY'], 'rotation': r['Rot'],
                     'side': r['Side'], 'designator': ref, 'mpn': MPN[ref][1], 'pack': '',
                     'footprint': r['Package'], 'value': r['Val'], 'mount_type': mount[ref]})
assert {r['designator'] for r in rows} == set(MPN), 'placement file and MPN table disagree'
with open(os.path.join(out, 'PCBWay_positions.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

# BOM grouped by value + footprint + MPN
groups = {}
for ref, (_, value, fpid, _, desc) in PARTS.items():
    if ref not in MPN:
        continue
    key = (value, fpid.split(':')[1], MPN[ref])
    groups.setdefault(key, []).append(ref)
with open(os.path.join(out, 'PCBWay_bom.csv'), 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['Designator', 'Quantity', 'Value', 'Footprint', 'Package', 'MPN', 'Manufacturer', 'Mount_Type', 'Description'])
    for (value, fpname, (mfr, mpn)), refs in groups.items():
        w.writerow([', '.join(refs), len(refs), value, fpname, '', mpn, mfr, mount[refs[0]], PARTS[refs[0]][4]])

zpath = os.path.join(out, 't1s_tap_assembly.zip')
with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in sorted(os.listdir(os.path.join(out, 'gerbers'))):
        z.write(os.path.join(out, 'gerbers', name), name)
    for name in ('PCBWay_bom.csv', 'PCBWay_positions.csv'):
        z.write(os.path.join(out, name), name)
print('wrote', zpath, 'with', len(rows), 'placements,', len(groups), 'BOM lines')
