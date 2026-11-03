"""Deterministic fan-out before autorouting (needs KiCad's pcbnew module):

  * every used BGA signal ball is escaped to one pitch outside the package
    (see escape.py);
  * every BGA ball on a plane net gets a dog-bone via (0.4/0.2) in one of the
    four cells around it, or hops on F.Cu to a neighbouring ball of its net;
  * every other SMD pad on a plane net (GND, VCC*, VIN_3V3, MGTAV*) gets a
    stitching via next to it.

Planes then connect by zone fill, everything added here is locked, and the
autorouter only has to route the signal nets outside the BGA. Run via
gen/route.py prepare."""
import math
import pcbnew

PLANE_NETS = {"GND", "VCC3V3", "VCC1V0", "VCC1V8", "VIN_3V3", "VCC5V_CAN", "MGTAVTT", "MGTAVCC"}
VIA_D, VIA_DRILL = 0.4, 0.2
CLEAR = 0.15
MM = pcbnew.FromMM

# design-coordinate helpers (see pcb.py): kx = x + 31, ky = 80 - y + 20
def to_design(kx, ky):
    return kx - 31.0, 80.0 - (ky - 20.0)

from footprints import M2_KEY_C as KEY_C, M2_KEY_W, M2_KEY_D, M2_TONGUE_HALF, M2_TONGUE_H, M2_MOUNT_R
PLANES = None   # filled from pcb.PLANES at import time

def plane_under(x, y, netname):
    """True if the highest-priority plane covering (x, y) on some inner layer is `netname`."""
    dx, dy = to_design(x, y)
    by_layer = {}
    for net, layer, prio, x0, x1, y0, y1 in PLANES:
        if x0 <= dx <= x1 and y0 <= dy <= y1:
            if layer not in by_layer or prio > by_layer[layer][0]:
                by_layer[layer] = (prio, net)
    return any(net == netname for _, net in by_layer.values())

def in_notch(x, y):
    dx, dy = to_design(x, y)
    if abs(dx - KEY_C) < M2_KEY_W / 2 + 0.6 and dy < M2_KEY_D + 0.8:   # key-M slot
        return True
    if abs(dx) > M2_TONGUE_HALF - 0.8 and dy < M2_TONGUE_H + 0.8:        # shoulders beside the tongue
        return True
    if math.hypot(dx, dy - 80.0) < M2_MOUNT_R + 0.8:                     # mount semicircle
        return True
    return False

class Occupancy:
    """Pads (circles or axis-aligned rectangles) and vias that new copper must stay clear of."""
    def __init__(self, board):
        self.segs = []      # (x0, y0, x1, y1, half_width, net, layer) stubs added so far
        self.items = []     # (x, y, kind, hx, hy, net): kind 'c' circle (hx = radius) or 'r' rectangle half-sizes
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                p = pad.GetPosition(); sz = pad.GetSize()
                sx, sy = pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)
                try:
                    ang = pad.GetOrientation().AsDegrees()
                except AttributeError:
                    ang = 0.0
                if abs(((ang + 45) % 180) - 45) > 1e-3:   # rotated by ~90: swap
                    sx, sy = sy, sx
                extra = 0.15 if pad.GetNumber() == "" else 0.0    # NPTH: keep the drill clear too
                try:
                    circ = pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE
                except TypeError:
                    circ = pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
                onF = pad.IsOnLayer(pcbnew.F_Cu); onB = pad.IsOnLayer(pcbnew.B_Cu)
                lay = "*" if (onF and onB) or pad.GetNumber() == "" else ("F" if onF else "B")
                if circ:
                    self.items.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), "c", sx / 2 + extra, 0.0, pad.GetNetCode(), lay))
                else:
                    self.items.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), "r", sx / 2 + extra, sy / 2 + extra, pad.GetNetCode(), lay))
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                try:
                    wv = t.GetWidth(pcbnew.F_Cu)      # KiCad 9 API
                except TypeError:
                    wv = t.GetWidth()
                self.items.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), "c", pcbnew.ToMM(wv) / 2, 0.0, t.GetNetCode(), "*"))
            elif t.GetClass() == "PCB_TRACK":
                a, b = t.GetStart(), t.GetEnd()
                lay = "F" if t.GetLayer() == pcbnew.F_Cu else ("B" if t.GetLayer() == pcbnew.B_Cu else None)
                if lay:
                    self.segs.append((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y), pcbnew.ToMM(b.x), pcbnew.ToMM(b.y),
                                      pcbnew.ToMM(t.GetWidth()) / 2, t.GetNetCode(), lay))
        bb = board.GetBoardEdgesBoundingBox()
        self.xmin, self.xmax = pcbnew.ToMM(bb.GetLeft()) + 0.55, pcbnew.ToMM(bb.GetRight()) - 0.55
        self.ymin, self.ymax = pcbnew.ToMM(bb.GetTop()) + 0.55, pcbnew.ToMM(bb.GetBottom()) - 0.55

    @staticmethod
    def _dist(item, x, y):
        ix, iy, kind, hx, hy, _, _ = item
        if kind == "c":
            return math.hypot(ix - x, iy - y) - hx
        dx = max(abs(x - ix) - hx, 0.0); dy = max(abs(y - iy) - hy, 0.0)
        return math.hypot(dx, dy)

    def why_blocked(self, x, y, net, r=VIA_D / 2):
        if not (self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax):
            return "bounds"
        if in_notch(x, y):
            return "notch"
        for item in self.items:
            d = self._dist(item, x, y)
            need = r + (0.05 if item[5] == net else CLEAR)
            if d < need - 1e-6:
                return f"item {item[2]} net={item[5]} d={d:.2f}<{need:.2f}"
        for sx0, sy0, sx1, sy1, hw, snet, slay in self.segs:     # a via is on every layer
            if snet != net and self._pt_seg(x, y, sx0, sy0, sx1, sy1) < hw + r + CLEAR - 1e-6:
                return f"stub net={snet}"
        return None

    def free(self, x, y, net, r=VIA_D / 2):
        return self.why_blocked(x, y, net, r) is None

    def add(self, x, y, net, r=VIA_D / 2):
        self.items.append((x, y, "c", r, 0.0, net, "*"))

    @staticmethod
    def _pt_seg(x, y, x0, y0, x1, y1):
        dx, dy = x1 - x0, y1 - y0
        if dx == 0 and dy == 0:
            return math.hypot(x - x0, y - y0)
        t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))

    def segment_free(self, x0, y0, x1, y1, net, width, layer):
        """The stitch stub (on `layer`, 'F' or 'B') must not cross pads, vias or
        other stubs of other nets on that layer."""
        for k in range(0, 9):
            t = k / 8
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for item in self.items:
                if item[5] == net or (item[6] != "*" and item[6] != layer):
                    continue
                if self._dist(item, x, y) < width / 2 + CLEAR - 1e-6:
                    return False
            for sx0, sy0, sx1, sy1, hw, snet, slay in self.segs:
                if snet == net or slay != layer:
                    continue
                if self._pt_seg(x, y, sx0, sy0, sx1, sy1) < hw + width / 2 + CLEAR - 1e-6:
                    return False
        return True

    def add_seg(self, x0, y0, x1, y1, width, net, layer):
        self.segs.append((x0, y0, x1, y1, width / 2, net, layer))

    def same_net_via_near(self, x, y, net, dist=0.6):
        for ix, iy, kind, hx, hy, inet, _ in self.items:
            if inet == net and kind == "c" and abs(hx - VIA_D / 2) < 1e-6 and math.hypot(ix - x, iy - y) <= dist:
                return ix, iy
        return None

def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNetCode(net)
    board.Add(v)

def add_track(board, x0, y0, x1, y1, width, layer, net):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(MM(x0), MM(y0))); t.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(y1)))
    t.SetWidth(MM(width)); t.SetLayer(layer); t.SetNetCode(net)
    board.Add(t)

def fanout_fingers(board, fp, occ):
    """M.2 fingers: runs of consecutive same-net fingers in a row are joined by a
    bus track along the pads and share one via above the row (above both rows'
    pad ends, where there is room every few fingers)."""
    pads = {int(p.GetNumber()): p for p in fp.Pads() if p.GetNumber().isdigit()}
    added = 0
    for row_layer, first in ((pcbnew.F_Cu, 1), (pcbnew.B_Cu, 2)):
        ltag = "F" if row_layer == pcbnew.F_Cu else "B"
        nums = [n for n in sorted(pads) if n % 2 == first % 2]
        groups = []
        for n in nums:
            net = pads[n].GetNetCode()
            name = pads[n].GetNetname()
            if net <= 0 or name not in PLANE_NETS:
                continue
            if groups and groups[-1][0] == net and groups[-1][1][-1] == n - 2:
                groups[-1][1].append(n)
            else:
                groups.append((net, [n], name))
        for net, members, name in groups:
            pts = [(pcbnew.ToMM(pads[n].GetPosition().x), pcbnew.ToMM(pads[n].GetPosition().y)) for n in members]
            sz = pads[members[0]].GetSize(); half = pcbnew.ToMM(sz.y) / 2
            ybus = pts[0][1] - half + 0.3            # inside the pads, near their inner end
            if len(pts) > 1:
                add_track(board, pts[0][0], ybus, pts[-1][0], ybus, 0.25, row_layer, net)
                occ.add_seg(pts[0][0], ybus, pts[-1][0], ybus, 0.25, net, ltag)
                added += 1
            mid = pts[len(pts) // 2]
            placed = False
            for dy in (1.3, 1.9, 2.5, 3.1):
                for dx in (0.0, 0.25, -0.25, 0.5, -0.5):
                    vx, vy = mid[0] + dx, pts[0][1] - half - dy
                    if plane_under(vx, vy, name) and occ.free(vx, vy, net) and occ.segment_free(mid[0], mid[1], vx, vy, net, 0.25, ltag):
                        add_via(board, vx, vy, net)
                        add_track(board, mid[0], mid[1], vx, vy, 0.25, row_layer, net)
                        occ.add(vx, vy, net)
                        occ.add_seg(mid[0], mid[1], vx, vy, 0.25, net, ltag)
                        added += 1; placed = True
                        break
                if placed:
                    break
    return added

def add_links(board, occ, skipped):
    """Explicit locked links from pcb.LINKS (island-to-island bridges the planes cannot make)."""
    import pcb as _pcb
    codes = {str(name): item.GetNetCode() for name, item in board.GetNetInfo().NetsByName().items()}
    for netname, items in _pcb.LINKS:
        net = codes[netname]
        ok = True
        for it in items:
            if it[0] == "via":
                kx, ky = it[1] + 31.0, 100.0 - it[2]
                ok = ok and occ.free(kx, ky, net)
            else:
                pts = [(x + 31.0, 100.0 - y) for x, y in it[3]]
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    ok = ok and occ.segment_free(x0, y0, x1, y1, net, it[2], it[1])
        if not ok:
            print(f"LINK BLOCKED: {netname}")
            skipped.append(f"link[{netname}] blocked")
            continue
        for it in items:
            if it[0] == "via":
                kx, ky = it[1] + 31.0, 100.0 - it[2]
                add_via(board, kx, ky, net); occ.add(kx, ky, net)
            else:
                layer = pcbnew.B_Cu if it[1] == "B" else pcbnew.F_Cu
                pts = [(x + 31.0, 100.0 - y) for x, y in it[3]]
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    add_track(board, x0, y0, x1, y1, it[2], layer, net); occ.add_seg(x0, y0, x1, y1, it[2], net, it[1])

def fanout(board):
    occ = Occupancy(board)
    netnames = {code: name for name, code in board.GetNetInfo().NetsByName().items()} if False else None
    added = 0
    skipped = []
    escape_stats = None
    bga_connected, bga_todo, bga_fp = set(), [], None
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        is_bga = ref == "U1"
        if ref == "J1":
            added += fanout_fingers(board, fp, occ)
            continue
        if is_bga:
            import escape
            bga_fp = fp
            escape_stats = escape.escape_bga(board, fp, occ, PLANE_NETS)   # signals out first
            add_links(board, occ, skipped)                                  # then the island links
        c = fp.GetPosition(); cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        pads = list(fp.Pads())
        if is_bga:
            # signals first (they need the channels most), then the rarer rails, GND last (shares vias)
            counts = {}
            for pad in pads:
                counts[pad.GetNetname()] = counts.get(pad.GetNetname(), 0) + 1
            pads.sort(key=lambda pad: (pad.GetNetname() in PLANE_NETS, counts[pad.GetNetname()], pad.GetNetname()))
        for pad in pads:
            net = pad.GetNetCode()
            if net <= 0:
                continue
            name = pad.GetNetname()
            if name not in PLANE_NETS:
                continue                      # BGA signals were escaped above; other signals are the router's
            p = pad.GetPosition(); px, py = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            ltag = "F" if layer == pcbnew.F_Cu else "B"
            if is_bga:
                sx = 1 if px >= cx else -1
                sy = 1 if py >= cy else -1
                # any of the four cell centres around the ball: the escapes (escape.py) run on
                # the pad-row/column lines, which every cell-centre via clears by 0.15 mm
                cands = [(sx * 0.4, sy * 0.4), (-sx * 0.4, sy * 0.4), (sx * 0.4, -sy * 0.4), (-sx * 0.4, -sy * 0.4)]
                width = 0.1
                # a neighbouring ball on the same net may already own a via in a shared channel
                near = occ.same_net_via_near(px, py, net, dist=1.25)   # also a via one channel further away
                if near and occ.segment_free(px, py, near[0], near[1], net, width, ltag):
                    add_track(board, px, py, near[0], near[1], width, layer, net)
                    occ.add_seg(px, py, near[0], near[1], width, net, ltag)
                    added += 1; bga_connected.add(pad.GetNumber())
                    continue
            else:
                if name not in PLANE_NETS:
                    continue
                sz = pad.GetSize(); sx_, sy_ = pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)
                # outward along the pad's long axis, away from the footprint centre
                ang = pad.GetOrientation().AsRadians() if hasattr(pad.GetOrientation(), "AsRadians") else 0.0
                long_x = sx_ >= sy_
                ax = math.cos(ang) if long_x else -math.sin(ang)
                ay = math.sin(ang) if long_x else math.cos(ang)
                if (px - cx) * ax + (py - cy) * ay < 0:
                    ax, ay = -ax, -ay
                ang0 = math.atan2(ay, ax)
                d = max(sx_, sy_) / 2 + VIA_D / 2 + 0.2
                cands = [(k * d * math.cos(ang0), k * d * math.sin(ang0)) for k in (1.0, 1.3, 1.6, 2.0, 2.4)]
                cands += [(k * d * math.cos(ang0 + a), k * d * math.sin(ang0 + a)) for k in (1.0, 1.5) for a in (0.5, -0.5, 1.0, -1.0, 1.57, -1.57)]
                width = min(0.2, sx_, sy_)
            placed = False
            reasons = []
            for dx, dy in cands:
                vx, vy = px + dx, py + dy
                if name in PLANE_NETS and not plane_under(vx, vy, name):
                    reasons.append("no plane"); continue            # leave it to the router
                why = occ.why_blocked(vx, vy, net)
                if why is None and not occ.segment_free(px, py, vx, vy, net, width, ltag):
                    why = "stub crosses"
                if why:
                    reasons.append(why); continue
                if True:
                    add_via(board, vx, vy, net)
                    add_track(board, px, py, vx, vy, width, layer, net)
                    occ.add(vx, vy, net)
                    occ.add_seg(px, py, vx, vy, width, net, ltag)
                    added += 1; placed = True
                    break
            if placed and is_bga:
                bga_connected.add(pad.GetNumber())
            elif not placed and is_bga:
                bga_todo.append((pad, reasons))
            elif not placed:
                skipped.append(f"{ref}.{pad.GetNumber()}[{name}] {reasons}")
    # BGA plane balls with no free cell hop on F.Cu to an adjacent same-net ball that is
    # connected (0.8 mm along the row or column: every via is 0.4 mm off that line)
    if bga_fp is not None:
        info = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), p.GetNetCode())
                for p in bga_fp.Pads()}
        progress = True
        while progress and bga_todo:
            progress = False
            for pad, reasons in list(bga_todo):
                px, py, net = info[pad.GetNumber()]
                for other, (ox, oy, onet) in info.items():
                    if onet != net or other not in bga_connected or abs(math.hypot(ox - px, oy - py) - 0.8) > 1e-3:
                        continue
                    if occ.segment_free(px, py, ox, oy, net, 0.1, "F"):
                        add_track(board, px, py, ox, oy, 0.1, pcbnew.F_Cu, net)
                        occ.add_seg(px, py, ox, oy, 0.1, net, "F")
                        bga_connected.add(pad.GetNumber()); bga_todo.remove((pad, reasons))
                        added += 1; progress = True
                        break
        for pad, reasons in bga_todo:
            skipped.append(f"U1.{pad.GetNumber()}[{pad.GetNetname()}] {reasons}")
    for t in board.GetTracks():       # exported as fixed wires: Freerouting must not rip them up
        t.SetLocked(True)
    return added, skipped, escape_stats
