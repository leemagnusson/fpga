"""Cross-check: every footprint pad net on the board == schematic netlist (kicad-cli sch export netlist --format kicadxml)."""
import sys, os, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
from netlist import PARTS
xml = ET.parse(sys.argv[1]); board = pcbnew.LoadBoard(sys.argv[2])
sch = {}
for net in xml.getroot().iter('net'):
    for node in net.findall('node'):
        sch[(node.get('ref'), node.get('pin'))] = net.get('name')
pcb = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        pcb[(fp.GetReference(), pad.GetNumber())] = pad.GetNetname()
src = {(r, p): (n if n in ('+3V3', 'GND') else '/' + n) for r, (_, _, _, pins, _) in PARTS.items() for p, n in pins.items()}
bad = 0
for key in sorted(set(sch) | set(pcb) | set(src)):
    a, b, c = sch.get(key), pcb.get(key), src.get(key)
    if not (a == b == c):
        bad += 1; print('MISMATCH', key, 'sch', a, 'pcb', b, 'netlist.py', c)
print(f'{len(src)} pins checked, {bad} mismatches; nets in schematic: {len(set(sch.values()))}, on board: {len(set(pcb.values()))}')
sys.exit(1 if bad else 0)
