"""Generate t1s_tap.kicad_pcb with the pcbnew API from tools/netlist.py.
Board: 20 x 40 mm, origin (100,100), Pmod header on the bottom edge, bus connectors on the top edge,
SMA on the left edge, trigger header on the right edge."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
from pcbnew import FromMM, VECTOR2I
from netlist import PARTS, MPN, nets

OUT = os.path.join(os.path.dirname(__file__), '..', 't1s_tap.kicad_pcb')
FPLIB = '/usr/share/kicad/footprints/'
X0, Y0, W, H = 100.0, 100.0, 20.0, 40.0
TW = 0.25          # signal track width
PW = 0.4           # power track width

def mm(x, y): return VECTOR2I(FromMM(x), FromMM(y))

board = pcbnew.CreateEmptyBoard()
board.SetCopperLayerCount(2)
ds = board.GetDesignSettings()
ds.m_MinClearance = FromMM(0.2); ds.m_TrackMinWidth = FromMM(0.2); ds.m_ViasMinSize = FromMM(0.6)
ds.m_MinThroughDrill = FromMM(0.3); ds.m_CopperEdgeClearance = FromMM(0.25); ds.m_HoleClearance = FromMM(0.25)
ds.m_HoleToHoleMin = FromMM(0.25); ds.m_ViasMinAnnularWidth = FromMM(0.15)
nc = ds.m_NetSettings.GetDefaultNetclass()
nc.SetClearance(FromMM(0.2)); nc.SetTrackWidth(FromMM(TW)); nc.SetViaDiameter(FromMM(0.6)); nc.SetViaDrill(FromMM(0.3))
tb = board.GetTitleBlock(); tb.SetTitle('10BASE-T1S tap Pmod'); tb.SetRevision('A'); tb.SetDate('2026-10-30'); board.SetTitleBlock(tb)

NET = {}
for name in nets():
    # local labels in the schematic become "/NAME" nets; power symbols stay global
    ni = pcbnew.NETINFO_ITEM(board, name if name in ('+3V3', 'GND') else '/' + name); board.Add(ni); NET[name] = ni

# ref: (x, y, rot)
PLACE = {
    'J1': (116.35, 133.0, 270), 'J2': (108.7, 105.0, 180), 'J3': (118.0, 105.0, 270), 'J5': (118.75, 109.0, 0),
    'J4': (102.79, 123.0, 180), 'U1': (108.0, 114.5, 180), 'C1': (106.7, 119.0, 90),
    'R1': (111.6, 110.1, 180), 'JP1': (108.2, 110.1, 180), 'R2': (107.8, 123.0, 270), 'R3': (110.9, 120.5, 0),
    'D1': (114.0, 120.5, 180), 'R4': (118.6, 122.5, 270), 'R5': (113.81, 127.0, 270), 'R6': (111.27, 127.0, 270),
    'R7': (108.73, 127.0, 270), 'R8': (119.1, 128.0, 270), 'TP1': (101.6, 130.0, 0),
}
FP = {}
for ref, (lib_id, value, fpid, pins, _) in PARTS.items():
    lib, name = fpid.split(':')
    fp = pcbnew.FootprintLoad(FPLIB + lib + '.pretty', name)
    assert fp, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref); fp.SetValue(value)
    x, y, rot = PLACE[ref]
    fp.SetPosition(mm(x, y)); fp.SetOrientationDegrees(rot)
    fp.Reference().SetLayer(pcbnew.F_Fab)      # keep silkscreen clear of pads; refs stay on the fab layer
    fp.Reference().SetVisible(True)
    if ref in MPN:
        fp.SetField('Manufacturer', MPN[ref][0]); fp.SetField('MPN', MPN[ref][1])
        for f in fp.GetFields():
            if f.GetName() in ('Manufacturer', 'MPN'): f.SetVisible(False); f.SetLayer(pcbnew.F_Fab)
    else:                                   # solder jumper, test point: not a part
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    board.Add(fp)
    for pad in fp.Pads():
        pad.SetNet(NET[pins[pad.GetNumber()]])
    # 3D models: point at the project-local copies in 3dmodels/ (STEP files from
    # kicad-packages3D) so the board renders without the global 3D library.
    models = fp.Models()
    new_models = []
    for m in models:                       # elements come back as copies; rebuild the list
        base = m.m_Filename.rsplit('/', 1)[-1]
        assert os.path.exists(os.path.join(os.path.dirname(OUT), '3dmodels', base)), (ref, base)
        n = pcbnew.FP_3DMODEL()
        n.m_Filename = '${KIPRJMOD}/3dmodels/' + base
        n.m_Scale, n.m_Rotation, n.m_Offset = m.m_Scale, m.m_Rotation, m.m_Offset
        n.m_Opacity, n.m_Show = m.m_Opacity, m.m_Show
        new_models.append(n)
    models.clear()
    for n in new_models:
        models.push_back(n)
    FP[ref] = fp

def P(ref, pad):
    p = FP[ref].FindPadByNumber(pad).GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

# sanity: pads where the hand-routed coordinates assume a position
for ref, pad, ex, ey in [('J1', '1', 116.35, 133.0), ('J1', '12', 103.65, 135.54), ('U1', '1', 110.48, 116.41),
                         ('U1', '8', 105.52, 116.41), ('J2', '2', 105.2, 105.0), ('J3', '3', 112.92, 105.0),
                         ('J5', '5', 118.75, 119.16), ('C1', '1', 106.7, 119.775), ('R1', '1', 112.42, 110.1),
                         ('JP1', '2', 107.55, 110.1), ('R2', '1', 107.8, 122.18), ('D1', '1', 114.79, 120.5),
                         ('R4', '1', 118.6, 121.68), ('R5', '2', 113.81, 127.82), ('R8', '1', 119.1, 127.18)]:
    px, py = P(ref, pad)
    assert abs(px - ex) < 0.02 and abs(py - ey) < 0.02, (ref, pad, px, py, ex, ey)

def track(net, pts, layer=pcbnew.F_Cu, w=TW):
    pts = [P(*p) if isinstance(p[0], str) else p for p in pts]
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board); t.SetStart(mm(*a)); t.SetEnd(mm(*b)); t.SetWidth(FromMM(w))
        t.SetLayer(layer); t.SetNet(NET[net]); board.Add(t)

def via(net, x, y):
    v = pcbnew.PCB_VIA(board); v.SetPosition(mm(x, y)); v.SetDrill(FromMM(0.3))
    try:
        v.SetWidth(pcbnew.PADSTACK.ALL_LAYERS, FromMM(0.6))
    except Exception:
        v.SetWidth(FromMM(0.6))
    v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(NET[net]); board.Add(v)

B = pcbnew.B_Cu
# ---- bus side
track('A', [('J2', '1'), (108.7, 108.3), (112.42, 108.3), ('R1', '1')])
track('A', [('J3', '1'), (118.0, 106.9), (112.42, 106.9), (112.42, 108.3)])
track('A', [('R1', '1'), (112.42, 111.3), (103.6, 111.3), (103.6, 113.86), ('U1', '6')])
track('B', [('U1', '7'), (100.9, 115.14), (100.9, 102.0), (115.46, 102.0), ('J3', '2')])
track('B', [(105.2, 102.0), ('J2', '2'), (105.2, 108.5), (107.55, 108.5), ('JP1', '2')])
track('TERM', [('JP1', '1'), ('R1', '2')])
# ---- power
track('+3V3', [('U1', '8'), (106.2, 117.1), (107.8, 117.1), (107.8, 119.775), ('C1', '1')], w=PW)
via('+3V3', 107.8, 120.6); track('+3V3', [(107.8, 119.775), (107.8, 120.6)], w=PW)
track('+3V3', [('J1', '12'), ('J1', '11'), (106.6, 130.0), (106.6, 121.8), (107.8, 120.6)], B, PW)
via('+3V3', 110.08, 119.0); track('+3V3', [(107.8, 120.6), (110.08, 119.0)], B, PW)
track('+3V3', [(110.08, 119.0), ('R3', '1')])
track('GND', [('C1', '2'), (105.3, 118.6)])   # straight into the SMA ground pad
# the SMA ground pads are separate top/bottom SMD pads (no hole), so the top island here needs its own via
via('GND', 105.7, 118.75)
for net, (ref, pad), (vx, vy) in [('GND', ('U1', '5'), (104.45, 112.0)), ('GND', ('U1', '2'), (112.4, 115.14)),
                                   ('GND', ('R4', '2'), (119.4, 124.6))]:
    via(net, vx, vy); track(net, [(ref, pad), (vx, vy)])
for vx, vy in [(101.0, 101.0), (119.0, 101.5), (101.2, 139.0), (118.8, 139.0), (114.0, 123.0)]:
    via('GND', vx, vy)
# J5 pin 5 sits in a copper island walled in by the DE trace: tie it to the R4 ground via
track('GND', [('J5', '5'), (119.45, 119.16), (119.45, 124.6), (119.4, 124.6)])
# the strip right of the DE trace is enclosed on top (DE) and bottom (T3); these vias reach the main bottom pour
via('GND', 118.35, 131.3); via('GND', 118.35, 133.1)
# ---- receiver / LED
track('LEDA', [('R3', '2'), ('D1', '2')])
track('RX', [('J1', '1'), (116.35, 116.41), ('U1', '1')])
track('RX', [(116.35, 120.5), ('D1', '1')])
track('DE', [('J1', '4'), (115.08, 134.27), (117.6, 134.27), (117.6, 122.4), (117.3, 122.1), (117.3, 113.86), ('U1', '3')])
track('DE', [(117.3, 121.68), ('R4', '1')])
track('TXD', [('J1', '6'), (110.0, 134.27), (110.0, 123.0), (108.9, 123.0), (108.9, 112.59), ('U1', '4')])
track('SPARE', [('J1', '8'), (108.73, 137.3), (101.6, 137.3), (101.6, 131.4)], B)
via('SPARE', 101.6, 131.4); track('SPARE', [(101.6, 131.4), ('TP1', '1')])
# ---- triggers
track('TRIG0', [('J1', '3'), ('R5', '2')]); track('TRIG1', [('J1', '5'), ('R6', '2')]); track('TRIG2', [('J1', '7'), ('R7', '2')])
track('TRIG3', [('J1', '2'), (119.1, 135.54), ('R8', '2')])
via('TRIG0', 113.81, 131.0); via('TRIG0', 107.8, 131.0)
track('TRIG0', [(113.81, 131.0), (107.8, 131.0)], B); track('TRIG0', [(107.8, 131.0), ('R2', '2')])
track('SMA', [('R2', '1'), (106.2, 123.0), ('J4', '1')])
via('T0', 113.81, 124.8); track('T0', [('R5', '1'), (113.81, 124.8)])
track('T0', [(113.81, 124.8), (113.81, 128.9), (115.4, 128.9), (115.4, 109.0), ('J5', '1')], B)
via('T1', 111.27, 124.8); track('T1', [('R6', '1'), (111.27, 124.8)])
track('T1', [(111.27, 124.8), (111.27, 129.6), (116.4, 129.6), (116.4, 111.54), ('J5', '2')], B)
via('T2', 108.73, 124.8); track('T2', [('R7', '1'), (108.73, 124.8)])
track('T2', [(108.73, 124.8), (108.73, 130.3), (116.9, 130.3), (116.9, 114.08), ('J5', '3')], B)
via('T3', 119.1, 125.6); track('T3', [('R8', '1'), (119.1, 125.6)])
track('T3', [(119.1, 125.6), (117.4, 123.9), (117.4, 116.62), ('J5', '4')], B)

# ---- outline
for a, b in [((X0, Y0), (X0 + W, Y0)), ((X0 + W, Y0), (X0 + W, Y0 + H)), ((X0 + W, Y0 + H), (X0, Y0 + H)), ((X0, Y0 + H), (X0, Y0))]:
    s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(mm(*a)); s.SetEnd(mm(*b))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FromMM(0.1)); board.Add(s)

# ---- silkscreen
def text(s, x, y, layer=pcbnew.F_SilkS, size=0.7, rot=0):
    t = pcbnew.PCB_TEXT(board); t.SetText(s); t.SetPosition(mm(x, y)); t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size))); t.SetTextThickness(FromMM(0.12))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS: t.SetMirrored(True)
    board.Add(t)
text('1', 118.5, 131.5, size=0.8); text('6', 101.0, 133.0, size=0.8); text('7', 118.5, 137.4, size=0.8); text('12', 101.0, 135.5, size=0.8)
text('PMOD', 110.0, 138.6, size=0.8)
text('A', 108.7, 102.7, size=0.8); text('B', 105.2, 102.7, size=0.8)
text('A', 118.0, 107.0, size=0.8); text('B', 115.46, 107.0, size=0.8); text('G', 112.92, 107.0, size=0.8)
for i, s_ in enumerate(('T0', 'T1', 'T2', 'T3', 'G')): text(s_, 116.2, 109.0 + 2.54 * i, size=0.8)
text('TRIG0', 102.6, 120.7, size=0.8); text('RX', 114.0, 122.1, size=0.8)
text('TERM', 108.2, 110.1, pcbnew.B_SilkS, 0.8)
text('T1S TAP rev A', 111.0, 124.0, pcbnew.B_SilkS, 1.0)
text('JP1 = 100R term', 111.0, 112.0, pcbnew.B_SilkS, 0.8)
text('1', 118.5, 131.5, pcbnew.B_SilkS, 0.8); text('7', 118.5, 137.4, pcbnew.B_SilkS, 0.8)

# ---- ground pours
for layer, name in ((pcbnew.F_Cu, 'GND_top'), (pcbnew.B_Cu, 'GND_bottom')):
    z = pcbnew.ZONE(board); z.SetLayer(layer); z.SetNet(NET['GND']); z.SetZoneName(name)
    o = z.Outline(); o.NewOutline()
    for x, y in [(X0 + 0.3, Y0 + 0.3), (X0 + W - 0.3, Y0 + 0.3), (X0 + W - 0.3, Y0 + H - 0.3), (X0 + 0.3, Y0 + H - 0.3)]:
        o.Append(FromMM(x), FromMM(y))
    z.SetLocalClearance(FromMM(0.25)); z.SetMinThickness(FromMM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(FromMM(0.3)); z.SetThermalReliefSpokeWidth(FromMM(0.4))
    board.Add(z)
pcbnew.SaveBoard(OUT, board)
# Filling zones on a board built in memory crashes the SWIG filler; reload from disk first.
board = pcbnew.LoadBoard(OUT)
board.BuildConnectivity()
filler = pcbnew.ZONE_FILLER(board)
ok = filler.Fill(board.Zones())
for z in board.Zones():
    print('zone', z.GetZoneName(), 'filled', z.IsFilled(), 'polys', z.GetFilledPolysList(z.GetFirstLayer()).OutlineCount())
print('fill ok', ok, 'vias', sum(1 for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)))
pcbnew.SaveBoard(OUT, board)
print('saved', OUT, 'footprints', len(list(board.GetFootprints())), 'tracks', len(list(board.GetTracks())))
