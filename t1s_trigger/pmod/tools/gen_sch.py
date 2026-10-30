"""Generate t1s_tap.kicad_sch, t1s_tap.kicad_sym, sym-lib-table and t1s_tap.kicad_pro
from tools/netlist.py. Run inside the kicad/kicad:9.0 container (needs the symbol libs)."""
import sys, os, uuid, json, copy
sys.path.insert(0, os.path.dirname(__file__))
from sexp import parse, dumps, find, find1, load_symbol, Sym
from netlist import PARTS, MPN

LIB = '/usr/share/kicad/symbols/'
OUT = os.path.join(os.path.dirname(__file__), '..')
PROJECT = 't1s_tap'
NS = uuid.UUID('5f1c9a7e-3b2d-4c8e-9f10-2a6b7c8d9e01')
def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(str(p) for p in parts)))
ROOT = uid('root-sheet')

# ---------------------------------------------------------------- symbols
def flatten_u1():
    """SN65HVD78: same pinout/graphics as the library's LTC2850xS8 half-duplex symbol."""
    base, _ = load_symbol(LIB + 'Interface_UART.kicad_sym', 'LTC2850xS8')
    s = copy.deepcopy(base)
    s[1] = 'SN65HVD78'
    for u in find(s, 'symbol'):
        u[1] = u[1].replace('LTC2850xS8', 'SN65HVD78')
    vals = {'Value': 'SN65HVD78', 'Footprint': 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
            'Datasheet': 'https://www.ti.com/lit/ds/symlink/sn65hvd78.pdf',
            'Description': '3.3 V 50 Mbps half-duplex RS-485 transceiver, fail-safe receiver, SOIC-8 (pin compatible: ADM3065E)',
            'ki_keywords': 'RS-485 transceiver 3.3V 50Mbps', 'ki_fp_filters': 'SOIC*3.9x4.9mm*P1.27mm*'}
    for p in find(s, 'property'):
        if p[1] in vals: p[2] = vals[p[1]]
    return s

libsyms = {}
def get_lib_symbol(lib_id):
    if lib_id in libsyms: return libsyms[lib_id]
    lib, name = lib_id.split(':')
    if lib == 't1s_tap':
        s = flatten_u1()
    else:
        s, _ = load_symbol(LIB + lib + '.kicad_sym', name)
        s = copy.deepcopy(s)
        assert find1(s, 'extends') is None, lib_id
    libsyms[lib_id] = s
    return s

def pins_of(sym):
    out = []
    for u in find(sym, 'symbol'):
        for p in find(u, 'pin'):
            at = find1(p, 'at'); num = find1(p, 'number')[1]
            out.append((num, float(at[1]), float(at[2]), float(at[3]), p[1]))
    return out

# ---------------------------------------------------------------- placement
# ref: (x, y)  all symbols at rotation 0
def g(n): return round(n * 1.27, 2)   # schematic grid units (1.27 mm)
POS = {'U1': (g(70), g(70)), 'J1': (g(32), g(56)), 'J2': (g(102), g(48)), 'J3': (g(102), g(60)), 'R1': (g(118), g(52)),
       'JP1': (g(130), g(64)), 'C1': (g(56), g(96)), 'R4': (g(48), g(80)), 'R3': (g(94), g(88)), 'D1': (g(82), g(100)),
       'R2': (g(146), g(52)), 'J4': (g(158), g(68)), 'R5': (g(170), g(52)), 'R6': (g(178), g(52)), 'R7': (g(186), g(52)),
       'R8': (g(194), g(52)), 'J5': (g(206), g(80)), 'TP1': (g(56), g(112))}
# explicit routes for pins whose default stub would collide: list of waypoints after the pin
ROUTE = {
    ('U1', '2'):  [(-12.70, 0), (0, 20.32)],     # ~RE -> GND, around the DE/DI labels
    ('J1', '9'):  [(-10.16, 0), (0, 10.16)],     # GND
    ('J1', '11'): [(-7.62, 0), (0, 5.08)],       # +3V3 (symbol rotated 180, below)
    ('J1', '10'): [(10.16, 0), (0, 10.16)],
    ('J1', '12'): [(7.62, 0), (0, 5.08)],
    ('J3', '3'):  [(-7.62, 0), (0, 7.62)],
    ('J5', '5'):  [(-7.62, 0), (0, 7.62)],
}
POWER_ROT = {('J1', '11'): 180, ('J1', '12'): 180}

items = []     # schematic body entries (lists)
pwr_n = 0

def sym_instance(lib_id, ref, value, footprint, x, y, rot, uid_key):
    sym = get_lib_symbol(lib_id)
    node = [Sym('symbol'), [Sym('lib_id'), lib_id], [Sym('at'), x, y, rot], [Sym('unit'), 1],
            [Sym('exclude_from_sim'), Sym('no')], [Sym('in_bom'), Sym('no' if ref in ('JP1', 'TP1') else 'yes')], [Sym('on_board'), Sym('yes')],
            [Sym('dnp'), Sym('no')], [Sym('uuid'), uid(uid_key)]]
    import math
    th = math.radians(rot)
    def xf(px, py):
        rx = px * math.cos(th) - py * math.sin(th)
        ry = px * math.sin(th) + py * math.cos(th)
        return round(x + rx, 4), round(y - ry, 4)
    props = {p[1]: p for p in find(sym, 'property')}
    for name in ('Reference', 'Value', 'Footprint', 'Datasheet', 'Description'):
        src = props.get(name)
        at = find1(src, 'at') if src else [Sym('at'), 0, 0, 0]
        px, py = xf(float(at[1]), float(at[2]))
        val = {'Reference': ref, 'Value': value, 'Footprint': footprint}.get(name, src[2] if src else '')
        eff = copy.deepcopy(find1(src, 'effects')) if src and find1(src, 'effects') else [Sym('effects'), [Sym('font'), [Sym('size'), 1.27, 1.27]]]
        if name in ('Footprint', 'Datasheet', 'Description') and not find1(eff, 'hide'):
            eff.append([Sym('hide'), Sym('yes')])
        node.append([Sym('property'), name, val, [Sym('at'), px, py, (float(at[3]) + rot) % 360], eff])
    if ref in MPN:
        hidden = [Sym('effects'), [Sym('font'), [Sym('size'), 1.27, 1.27]], [Sym('hide'), Sym('yes')]]
        for name, val in zip(('Manufacturer', 'MPN'), MPN[ref]):
            node.append([Sym('property'), name, val, [Sym('at'), x, y, 0], copy.deepcopy(hidden)])
    for num, *_ in pins_of(sym):
        node.append([Sym('pin'), num, [Sym('uuid'), uid(uid_key, 'pin', num)]])
    node.append([Sym('instances'), [Sym('project'), PROJECT,
                 [Sym('path'), '/' + ROOT, [Sym('reference'), ref], [Sym('unit'), 1]]]])
    return node

def wire(a, b):
    items.append([Sym('wire'), [Sym('pts'), [Sym('xy'), a[0], a[1]], [Sym('xy'), b[0], b[1]]],
                  [Sym('stroke'), [Sym('width'), 0], [Sym('type'), Sym('default')]], [Sym('uuid'), uid('wire', a, b)]])

def label(net, p, direction):
    rot, just = {'L': (180, 'right bottom'), 'R': (0, 'left bottom'), 'D': (270, 'right bottom'), 'U': (90, 'left bottom')}[direction]
    items.append([Sym('label'), net, [Sym('at'), p[0], p[1], rot],
                  [Sym('effects'), [Sym('font'), [Sym('size'), 1.27, 1.27]], [Sym('justify')] + [Sym(j) for j in just.split()]],
                  [Sym('uuid'), uid('label', net, p)]])

def power(net, p, rot=0):
    global pwr_n
    pwr_n += 1
    lib_id = {'GND': 'power:GND', '+3V3': 'power:+3V3'}[net]
    items.append(sym_instance(lib_id, '#PWR%02d' % pwr_n, net, '', p[0], p[1], rot, ('pwr', pwr_n)))

def r(v): return round(v, 4)

for ref, (lib_id, value, fp, pins, _) in PARTS.items():
    x, y = POS[ref]
    items.append(sym_instance(lib_id, ref, value, fp, x, y, 0, ('part', ref)))
    for num, px, py, ang, _ in pins_of(get_lib_symbol(lib_id)):
        net = pins[num]
        p0 = (r(x + px), r(y - py))
        d = {0: 'L', 180: 'R', 90: 'D', 270: 'U'}[int(ang)]
        if (ref, num) in ROUTE:
            pts = [p0]
            for dx, dy in ROUTE[(ref, num)]:
                pts.append((r(pts[-1][0] + dx), r(pts[-1][1] + dy)))
        else:
            dx, dy = {'L': (-5.08, 0), 'R': (5.08, 0), 'D': (0, 5.08), 'U': (0, -5.08)}[d]
            pts = [p0, (r(p0[0] + dx), r(p0[1] + dy))]
            if net in ('GND', '+3V3') and d in ('L', 'R'):
                pts.append((pts[-1][0], r(pts[-1][1] + (5.08 if net == 'GND' else -5.08))))
        for a, b in zip(pts, pts[1:]):
            wire(a, b)
        end = pts[-1]
        if net in ('GND', '+3V3'):
            power(net, end, POWER_ROT.get((ref, num), 0))
        else:
            label(net, end, d if (ref, num) not in ROUTE else 'L')

# PWR_FLAGs so ERC knows the Pmod supplies 3.3 V and ground
for i, (net, x) in enumerate((('+3V3', g(118)), ('GND', g(134)))):
    items.append(sym_instance('power:PWR_FLAG', '#FLG%02d' % (i + 1), 'PWR_FLAG', '', x, g(104), 0, ('flag', i)))
    wire((x, g(104)), (round(x + 5.08, 2), g(104)))
    power(net, (round(x + 5.08, 2), g(104)))

# ---------------------------------------------------------------- write schematic
lib_symbols = [Sym('lib_symbols')]
for lib_id, s in libsyms.items():
    s2 = copy.deepcopy(s); s2[1] = lib_id
    lib_symbols.append(s2)
sch = [Sym('kicad_sch'), [Sym('version'), 20250114], [Sym('generator'), 'eeschema'], [Sym('generator_version'), '9.0'],
       [Sym('uuid'), ROOT], [Sym('paper'), 'A4'],
       [Sym('title_block'), [Sym('title'), '10BASE-T1S tap Pmod'], [Sym('date'), '2026-10-30'], [Sym('rev'), 'A'],
        [Sym('comment'), 1, 'RS-485 receiver as a high-impedance tap on a 10BASE-T1S bus, four trigger outputs'],
        [Sym('comment'), 2, 'Pmod: IO1=RX IO2..4=TRIG0..2 IO7=TRIG3 IO8=DE IO9=TXD IO10=spare']],
       lib_symbols] + items + [[Sym('sheet_instances'), [Sym('path'), '/', [Sym('page'), '1']]], [Sym('embedded_fonts'), Sym('no')]]
open(os.path.join(OUT, PROJECT + '.kicad_sch'), 'w').write(dumps(sch) + '\n')

# local symbol library with the transceiver symbol, and the project library table
u1 = copy.deepcopy(libsyms['t1s_tap:SN65HVD78'])
lib = [Sym('kicad_symbol_lib'), [Sym('version'), 20241209], [Sym('generator'), 'kicad_symbol_editor'], [Sym('generator_version'), '9.0'], u1]
open(os.path.join(OUT, PROJECT + '.kicad_sym'), 'w').write(dumps(lib) + '\n')
open(os.path.join(OUT, 'sym-lib-table'), 'w').write(
    '(sym_lib_table\n\t(version 7)\n\t(lib (name "t1s_tap")(type "KiCad")(uri "${KIPRJMOD}/t1s_tap.kicad_sym")(options "")(descr "project symbols"))\n)\n')

pro = {
    "board": {"design_settings": {
        "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "silk_line_width": 0.12,
                      "silk_text_size_h": 0.8, "silk_text_size_v": 0.8, "silk_text_thickness": 0.12},
        "rules": {"min_clearance": 0.2, "min_connection": 0.0, "min_copper_edge_clearance": 0.25,
                  "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2,
                  "min_microvia_drill": 0.1, "min_resolved_spokes": 2, "min_silk_clearance": 0.0,
                  "min_text_height": 0.6, "min_text_thickness": 0.08, "min_through_hole_diameter": 0.3,
                  "min_track_width": 0.2, "min_via_annular_width": 0.15, "min_via_diameter": 0.6,
                  "solder_mask_to_copper_clearance": 0.0, "use_height_for_length_calcs": True},
        "track_widths": [0.0, 0.25, 0.4], "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3}],
        "zones_allow_external_fillets": False}, "layer_presets": [], "viewports": []},
    "boards": [], "cvpcb": {"equivalence_files": []},
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "meta": {"filename": PROJECT + ".kicad_pro", "version": 1},
    "net_settings": {"classes": [{"bus_width": 12, "clearance": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                                  "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                                  "name": "Default", "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
                                  "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.25, "via_diameter": 0.6,
                                  "via_drill": 0.3, "wire_width": 6}], "meta": {"version": 4}},
    "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "", "specctra_dsn": "",
                              "step": "", "svg": "", "vrml": ""}, "page_layout_descr_file": ""},
    "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
    "sheets": [[ROOT, "Root"]], "text_variables": {}}
json.dump(pro, open(os.path.join(OUT, PROJECT + '.kicad_pro'), 'w'), indent=2)
print('wrote schematic with', len(items), 'items;', pwr_n, 'power symbols')
