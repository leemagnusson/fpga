"""Generate t1s_tap.kicad_pcb with the pcbnew API from tools/netlist.py.
Board: 20 x 46 mm, origin (100,100), Pmod header on the bottom edge, bus connectors on the top edge,
SMA on the left edge, trigger header on the right edge."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
from pcbnew import FromMM, VECTOR2I
from netlist import PARTS, MPN, nets

OUT = os.path.join(os.path.dirname(__file__), '..', 't1s_tap.kicad_pcb')
FPLIB = '/usr/share/kicad/footprints/'
X0, Y0, W, H = 100.0, 100.0, 20.0, 46.0
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
tb = board.GetTitleBlock(); tb.SetTitle('10BASE-T1S tap Pmod'); tb.SetRevision('C'); tb.SetDate('2026-10-31'); board.SetTitleBlock(tb)

NET = {}
for name in nets():
    # local labels in the schematic become "/NAME" nets; power symbols stay global
    ni = pcbnew.NETINFO_ITEM(board, name if name in ('+3V3', 'GND') else '/' + name); board.Add(ni); NET[name] = ni

# ref: (x, y, rot)
# Pmod J1: pads at y=139 (odd, upper row) and y=141.54 (even, lower row), x = 116.35 - 2.54*k. Pmod pin 1 (RX)
# is pad 11 at the left (103.65), VCC pads 1/2 at the right (116.35). See netlist.py.
# U2 (second receiver) sits where U1 was in rev B; U1 and everything below moved down 6 mm.
PLACE = {
    'J1': (116.35, 139.0, 270), 'J2': (108.7, 105.0, 180), 'J3': (118.0, 105.0, 270), 'J5': (118.75, 109.0, 0),
    'J4': (102.79, 129.0, 180), 'U1': (108.0, 120.5, 180), 'U2': (108.0, 114.5, 180),
    'C1': (106.7, 125.0, 90), 'C2': (102.5, 116.6, 180),
    'R1': (112.1, 110.1, 180), 'JP1': (108.64, 110.2, 270), 'R2': (105.875, 135.9, 0), 'R3': (108.4, 128.0, 0),
    'D1': (111.7, 128.0, 180), 'R4': (114.6, 121.3, 270), 'R5': (106.7, 133.0, 270), 'R6': (109.0, 133.0, 270),
    'R7': (111.27, 133.0, 270), 'R8': (119.1, 134.5, 270),
}
FP = {}
for ref, (lib_id, value, fpid, pins, _) in PARTS.items():
    lib, name = fpid.split(':')
    fp = pcbnew.FootprintLoad(FPLIB + lib + '.pretty', name)
    assert fp, fpid
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref); fp.SetValue(value)
    x, y, rot = PLACE[ref]
    if ref == 'J1':
        # The library footprint marks its pad 1 (square pad plus a silkscreen tick) at what is Pmod pin 6 on this
        # board (see netlist.py): make pad 11 (Pmod pin 1) the square one and drop the tick; the board silkscreen
        # draws its own marker next to Pmod pin 1.
        for pad in fp.Pads():
            shape = pcbnew.PAD_SHAPE_RECT if pad.GetNumber() == '11' else pcbnew.PAD_SHAPE_CIRCLE
            try:
                pad.SetShape(pcbnew.PADSTACK.ALL_LAYERS, shape)
            except Exception:
                pad.SetShape(shape)
        for it in list(fp.GraphicalItems()):
            bb = it.GetBoundingBox()
            if it.GetLayer() == pcbnew.F_SilkS and abs(pcbnew.ToMM(bb.GetCenter().x)) < 1.6 and abs(pcbnew.ToMM(bb.GetCenter().y)) < 1.6:
                fp.Remove(it)
    if ref == 'JP1':
        # The library courtyard of the 1x2 header carries a 0.5 mm margin that would collide with the terminal
        # block and U1. Replace it with the physical body (2.54 x 5.08 mm) plus the usual 0.25 mm.
        for it in list(fp.GraphicalItems()):
            if it.GetLayer() == pcbnew.F_CrtYd: fp.Remove(it)
        cy = pcbnew.PCB_SHAPE(fp)
        cy.SetShape(getattr(pcbnew, 'SHAPE_T_RECTANGLE', getattr(pcbnew, 'SHAPE_T_RECT', 1)))
        cy.SetStart(mm(-1.52, -1.52)); cy.SetEnd(mm(1.52, 4.06)); cy.SetLayer(pcbnew.F_CrtYd); cy.SetWidth(FromMM(0.05))
        fp.Add(cy)
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
        if ref == 'J1' and pins[pad.GetNumber()] == 'GND':
            # boxed in by the neighbouring pads and the DE/TXD tracks, these only get one thermal spoke per layer
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
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
for ref, pad, ex, ey in [('J1', '1', 116.35, 139.0), ('J1', '11', 103.65, 139.0), ('J1', '12', 103.65, 141.54),
                         ('U1', '1', 110.48, 122.41), ('U1', '8', 105.52, 122.41), ('U2', '1', 110.48, 116.41),
                         ('U2', '8', 105.52, 116.41), ('U2', '6', 105.52, 113.87), ('J2', '2', 105.2, 105.0),
                         ('J3', '3', 112.92, 105.0), ('J5', '5', 118.75, 119.16), ('C1', '1', 106.7, 125.775),
                         ('C2', '1', 103.275, 116.6), ('C2', '2', 101.725, 116.6),
                         ('R1', '1', 112.925, 110.1), ('JP1', '1', 108.64, 110.2), ('JP1', '2', 106.1, 110.2),
                         ('R2', '1', 105.05, 135.9), ('R2', '2', 106.7, 135.9), ('R3', '1', 107.575, 128.0),
                         ('R3', '2', 109.225, 128.0), ('D1', '1', 112.487, 128.0), ('D1', '2', 110.913, 128.0),
                         ('R4', '1', 114.6, 120.475), ('R4', '2', 114.6, 122.125), ('R5', '1', 106.7, 132.175),
                         ('R5', '2', 106.7, 133.825), ('R8', '1', 119.1, 133.675), ('R8', '2', 119.1, 135.325)]:
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
# ---- bus side. A reaches U2 pin 7 and U1 pin 6 through a short bottom-layer run down the left side; B runs
# down the left edge and branches to U2 pin 6 and U1 pin 7.
track('A', [('J2', '1'), (108.7, 108.3), (112.925, 108.3), ('R1', '1')])
track('A', [('J3', '1'), (118.0, 106.9), (112.925, 106.9), (112.925, 108.3)])
track('A', [('R1', '1'), (112.925, 111.65), (103.2, 111.65), (103.2, 112.6)])
via('A', 103.2, 112.6); via('A', 103.2, 115.5); via('A', 103.2, 119.6)
track('A', [(103.2, 112.6), (103.2, 119.6)], B)
track('A', [(103.2, 115.5), (104.0, 115.135), ('U2', '7')])
track('A', [(103.2, 119.6), (104.0, 119.865), ('U1', '6')])
track('B', [('U1', '7'), (100.9, 121.135), (100.9, 102.0), (115.46, 102.0), ('J3', '2')])
track('B', [(100.9, 113.865), ('U2', '6')])
track('B', [(105.2, 102.0), ('J2', '2'), (105.2, 108.3), ('JP1', '2')])
track('TERM', [('JP1', '1'), ('R1', '2')])
# ---- power
# 3.3 V enters at the right end of the Pmod header (pads 1 and 2), runs on the bottom layer along y=132.5
# under the trigger resistors, comes up at x=107.8 and runs between the pad rows of U1 to feed both receivers.
track('+3V3', [('U1', '8'), (106.2, 123.1), (107.8, 123.1), (107.8, 125.775), ('C1', '1')], w=PW)
track('+3V3', [(107.8, 125.775), (107.8, 132.5)], w=PW)
via('+3V3', 107.8, 132.5)
track('+3V3', [(107.8, 132.5), (116.35, 132.5), ('J1', '1'), ('J1', '2')], B, PW)
track('+3V3', [(107.8, 128.0), ('R3', '1')])
track('+3V3', [(107.8, 123.1), (107.8, 117.1), (106.9, 116.405), ('U2', '8')], w=PW)
track('+3V3', [('U2', '8'), ('C2', '1')])
track('GND', [('C1', '2'), (105.3, 124.6)])   # straight into the SMA ground pad
# the SMA ground pads are separate top/bottom SMD pads (no hole), so the top island here needs its own via
via('GND', 104.0, 126.5); track('GND', [(104.0, 126.5), (104.0, 125.3)])
for net, (ref, pad), (vx, vy) in [('GND', ('U1', '5'), (104.0, 117.9)), ('GND', ('U1', '2'), (112.0, 121.135)),
                                   ('GND', ('R4', '2'), (114.4, 123.8)), ('GND', ('U2', '5'), (104.0, 112.9)),
                                   ('GND', ('C2', '2'), (101.9, 118.0))]:
    via(net, vx, vy); track(net, [(ref, pad), (vx, vy)])
# U2 driver pins (~RE, DE, DI) all to ground
track('GND', [('U2', '4'), (112.0, 112.595), (112.0, 115.135), ('U2', '2')])
track('GND', [('U2', '3'), (112.0, 113.865), (112.4, 113.865)]); via('GND', 112.4, 113.865)
for vx, vy in [(101.0, 101.0), (119.0, 101.5), (101.2, 145.0), (118.8, 145.0), (114.5, 130.4), (119.4, 132.4)]:
    via('GND', vx, vy)
# J5 pin 5 sits in a copper island walled in by the DE/TXD traces on top and the T3 trace underneath: run it
# down the edge to a via below the T3 via, where the bottom pour is continuous
track('GND', [('J5', '5'), (119.45, 119.16), (119.45, 132.4), (119.4, 132.4)])
# ---- receivers / LED
# RX (line negative, U1): Pmod pin 1 is the bottom-left pad. Bottom layer up the strip between the SMA ground
# pads and the trigger resistors, across under U1, then a via next to U1 pin 1. The LED hangs off the same via.
track('RX', [('J1', '11'), (103.65, 137.0), (105.85, 134.8), (105.85, 123.9), (106.45, 123.3), (111.9, 123.3),
             (112.2, 123.0), (112.2, 122.405)], B)
via('RX', 112.2, 122.405)
track('RX', [(112.2, 122.405), ('U1', '1')])
track('RX', [(112.2, 122.405), (112.2, 128.0), ('D1', '1')])
track('LEDA', [('R3', '2'), ('D1', '2')])
# RXN (line positive, U2): bottom layer past U1's right-hand pins (DE/TXD leave U1 to the right on top),
# top layer down to the header, bottom layer between the header pads into Pmod pin 10.
track('RXN', [('U2', '1'), (112.4, 116.405), (113.0, 117.0)])
via('RXN', 113.0, 117.0)
track('RXN', [(113.0, 117.0), (113.0, 124.8), (113.4, 125.2)], B)
via('RXN', 113.4, 125.2)
track('RXN', [(113.4, 125.2), (113.4, 137.6)])
via('RXN', 113.4, 137.6)
track('RXN', [(113.4, 137.6), (112.54, 138.46), (112.54, 140.27), ('J1', '6')], B)
# DE and TXD leave the receiver to the right, run down the right edge past the trigger header and come back
# along the bottom: DE between the two header rows, TXD below the lower row (under the header body).
track('DE', [('U1', '3'), (117.0, 119.865), (117.0, 120.6), (117.55, 121.15), (117.55, 140.27), (107.46, 140.27), ('J1', '10')])
track('DE', [('R4', '1'), (114.6, 119.865)])
track('TXD', [('U1', '4'), (117.5, 118.595), (117.5, 120.0), (118.05, 120.55), (118.05, 144.5), (108.73, 144.5), ('J1', '8')])
# ---- triggers
# TRIG0..2 go straight up from the header to the series resistors; T0..T2 then run on the bottom layer, nested
# horizontals at y=127.5/128.2/128.9, to the trigger header on the right edge.
track('TRIG0', [('J1', '9'), (106.7, 138.49), ('R2', '2'), ('R5', '2')])   # straight through R2's pad
track('TRIG1', [('J1', '7'), (109.0, 138.73), ('R6', '2')])
track('TRIG2', [('J1', '5'), ('R7', '2')])
track('SMA', [('R2', '1'), (105.85, 135.1), (105.85, 129.3), ('J4', '1')])
via('T0', 106.7, 130.9); track('T0', [('R5', '1'), (106.7, 130.9)])
track('T0', [(106.7, 130.9), (106.7, 127.5), (115.4, 127.5), (115.4, 109.0), ('J5', '1')], B)
via('T1', 109.0, 131.0); track('T1', [('R6', '1'), (109.0, 131.0)])
track('T1', [(109.0, 131.0), (109.0, 128.2), (116.4, 128.2), (116.4, 111.54), ('J5', '2')], B)
via('T2', 111.27, 130.8); track('T2', [('R7', '1'), (111.27, 130.8)])
track('T2', [(111.27, 130.8), (111.27, 128.9), (116.9, 128.9), (116.9, 114.08), ('J5', '3')], B)
# TRIG3 (Pmod pin 7, bottom-left pad) runs along the bottom edge on the bottom layer to R8 at the right edge
track('TRIG3', [('J1', '12'), (103.65, 143.8), (119.1, 143.8), (119.1, 137.5)], B)
via('TRIG3', 119.1, 137.5); track('TRIG3', [(119.1, 137.5), ('R8', '2')])
via('T3', 118.75, 131.6); track('T3', [('R8', '1'), (118.75, 133.0), (118.75, 131.6)])
track('T3', [(118.75, 131.6), (117.4, 130.25), (117.4, 116.62), ('J5', '4')], B)

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
# Pmod pin numbers at the row ends: 1 and 7 on the left, 6 and 12 on the right (header pointing down)
text('1', 101.6, 139.0, size=0.8); text('6', 118.3, 139.0, size=0.8); text('7', 101.6, 141.54, size=0.8); text('12', 118.4, 141.54, size=0.8)
for a_, b_ in [((102.3, 137.85), (103.0, 137.85)), ((102.3, 137.85), (102.3, 138.55))]:   # pin 1 tick
    ln = pcbnew.PCB_SHAPE(board); ln.SetShape(pcbnew.SHAPE_T_SEGMENT); ln.SetStart(mm(*a_)); ln.SetEnd(mm(*b_))
    ln.SetLayer(pcbnew.F_SilkS); ln.SetWidth(FromMM(0.15)); board.Add(ln)
text('A', 108.7, 102.7, size=0.8); text('B', 105.2, 102.7, size=0.8)
text('A', 118.0, 107.0, size=0.8); text('B', 115.46, 107.0, size=0.8); text('G', 112.92, 107.0, size=0.8)
for i, s_ in enumerate(('T0', 'T1', 'T2', 'T3', 'G')): text(s_, 116.2, 109.0 + 2.54 * i, size=0.8)
text('TRIG0', 102.6, 126.7, size=0.8); text('RX', 111.7, 129.4, size=0.8); text('TERM', 103.0, 110.2, size=0.8)
text('PMOD', 110.0, 144.3, pcbnew.B_SilkS, 0.8)
text('T1S TAP rev C', 110.0, 126.3, pcbnew.B_SilkS, 1.0)
text('JP1 shunt: 100R', 111.0, 112.0, pcbnew.B_SilkS, 0.8)
text('1', 101.6, 139.0, pcbnew.B_SilkS, 0.8); text('7', 101.6, 141.54, pcbnew.B_SilkS, 0.8)

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
