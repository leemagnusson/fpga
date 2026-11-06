"""Find isolated GND clusters: islands of the two pours + vias + pads + GND tracks, union-find by overlap."""
import pcbnew, itertools
b = pcbnew.LoadBoard('t1s_tap.kicad_pcb'); b.BuildConnectivity()
zt = [z for z in b.Zones() if z.GetZoneName() == 'GND_top'][0]; zb = [z for z in b.Zones() if z.GetZoneName() == 'GND_bottom'][0]
islands = []   # (name, layer, polygon SHAPE_LINE_CHAIN)
for z, layer in ((zt, pcbnew.F_Cu), (zb, pcbnew.B_Cu)):
    pl = z.GetFilledPolysList(layer)
    for i in range(pl.OutlineCount()):
        sub = pcbnew.SHAPE_POLY_SET(); sub.NewOutline()
        o = pl.Outline(i)
        for k in range(o.PointCount()): sub.Append(o.CPoint(k))
        for h in range(pl.HoleCount(i)):
            sub.NewHole(); hh = pl.Hole(i, h)
            for k in range(hh.PointCount()): sub.Append(hh.CPoint(k), 0, h)
        bb = o.BBox()
        islands.append((f"{z.GetZoneName()}#{i} bbox({pcbnew.ToMM(bb.GetLeft()):.1f},{pcbnew.ToMM(bb.GetTop()):.1f},{pcbnew.ToMM(bb.GetRight()):.1f},{pcbnew.ToMM(bb.GetBottom()):.1f})", layer, sub))
items = []  # (name, shape per layer dict)
for v in b.GetTracks():
    if v.GetNetname() != 'GND': continue
    if isinstance(v, pcbnew.PCB_VIA):
        items.append((f"via({pcbnew.ToMM(v.GetPosition().x)},{pcbnew.ToMM(v.GetPosition().y)})", {pcbnew.F_Cu: v.GetEffectiveShape(pcbnew.F_Cu), pcbnew.B_Cu: v.GetEffectiveShape(pcbnew.B_Cu)}))
    else:
        items.append((f"track({pcbnew.ToMM(v.GetStart().x)},{pcbnew.ToMM(v.GetStart().y)})-({pcbnew.ToMM(v.GetEnd().x)},{pcbnew.ToMM(v.GetEnd().y)})", {v.GetLayer(): v.GetEffectiveShape(v.GetLayer())}))
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() != 'GND': continue
        shapes = {}
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if pad.IsOnLayer(layer): shapes[layer] = pad.GetEffectiveShape(layer)
        items.append((f"pad {fp.GetReference()}.{pad.GetNumber()}@{'+'.join(pcbnew.LayerName(l) for l in shapes)}", shapes))
# union-find
parent = {}
def find(x):
    while parent.setdefault(x, x) != x: x = parent[x]
    return x
def union(a, b): parent[find(a)] = find(b)
names = [n for n, _, _ in islands] + [n for n, _ in items]
for n in names: find(n)
for (iname, layer, poly) in islands:
    for (name, shapes) in items:
        if layer in shapes and poly.Collide(shapes[layer], pcbnew.FromMM(0.01)):
            union(iname, name)
for (n1, s1), (n2, s2) in itertools.combinations(items, 2):
    for layer in s1:
        if layer in s2 and s1[layer].Collide(s2[layer], pcbnew.FromMM(0.01)):
            union(n1, n2)
# vias and THT pads connect their own two layers implicitly (one node each) -> done
groups = {}
for n in names: groups.setdefault(find(n), []).append(n)
print(len(groups), 'GND clusters')
for g in groups.values():
    print(' ---', len(g), 'members:', ', '.join(g[:12]), '...' if len(g) > 12 else '')
