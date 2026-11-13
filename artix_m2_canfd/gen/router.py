"""Grid router for the board (replaces Freerouting). Run through gen/route.py:

    python3 gen/route.py route        # fan-out (escapes + plane vias), then route everything, fill, save

The board after fanout.py has every BGA ball escaped to a via one pitch outside the package
and every plane-net pad stitched to its plane; what is left are the signal nets, a few
plane-net pads that found no via spot or sit over no plane, and the power-section parts
that should be joined directly rather than through the planes. This router does them in
order of importance, the way a layout engineer would:

  1. PCIe pairs as pairs: one A* search for the centreline of each pair on a 0.1 mm grid
     (F.Cu and B.Cu, 45-degree moves, vias allowed at a high cost), then P and N offset
     0.125 mm either side (0.1 mm tracks, 0.15 mm gap, 100 ohm by geometry), symmetric
     lead-ins at both ends so the two halves stay the same length. Receive pairs go straight
     from the escape vias to the fingers on F.Cu; transmit pairs use the east corridor and
     a B.Cu run under the receive pairs to their AC-coupling capacitors.
  2. Transceiver supply tracks (0.4 mm) from the LDO outputs onto their In2 plane strips, and
     every plane-net pad the fan-out could not stitch: routed to the nearest copper of the
     net that already reaches the plane, or to a fresh via over the plane.
  3. Local power links (0.3 mm, same layer): each regulator or transceiver pin on a supply or
     ground net is joined directly to the nearest capacitor/inductor pad of that net within
     a few millimetres, so the decoupling loop does not run through two vias and a plane.
  4. Signal nets, short first, as Steiner-like trees (each pad joins the copper already
     routed), with a rip-up-and-retry pass for the ones that find no path.

Obstacles are rasterised with the clearance built in (0.1 mm for 0.1 mm tracks, 0.3 mm
for the wider power tracks and the pair centrelines), vias check a separate all-layer
raster, and the board edge, the key slot, the mount notch and the connector shoulders are
kept clear. Everything already on the board is locked and never moved; the router's own
tracks can be ripped up. Needs KiCad's pcbnew module (KiCad 9)."""
import array, heapq, math, re, sys, os
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fanout

GRID = 0.1
F, B = 0, 1
LAYER_ID = {F: pcbnew.F_Cu, B: pcbnew.B_Cu}
VIA_D, VIA_DRILL = 0.4, 0.2
EDGE = 0.35                 # track centre to board edge (0.3 mm copper-to-edge)
R_SIG = 0.15                # 0.1 mm track: half width + 0.1 clearance
R_Q = 0.20                  # 0.1 mm track of a power net: half width + 0.15 clearance
R_PWR = 0.30                # 0.3 mm track with 0.15 clearance (and the 0.35 mm pair centreline)
R_VIA = 0.35                # 0.4 mm via: radius + 0.15
PAIR_W, PAIR_GAP = 0.1, 0.15
PAIR_OFF = (PAIR_W + PAIR_GAP) / 2          # 0.125: P/N offset from the centreline
PAIR_SPACING = 0.3                           # edge to edge between two pairs on a layer (room for the tuning bumps, less crosstalk)
PAIR_VIA_OFF = 0.35                          # P/N via offset from the centreline at a layer change
MM = pcbnew.FromMM
to_mm = pcbnew.ToMM

PLANE_NETS = fanout.PLANE_NETS
POWER_RE = re.compile(r"^(VCC|VIN_3V3|MGTAV|SW_|GND$)")
PAIR_RE = re.compile(r"^(PCIE_(?:RX\d|TX\d|REFCLK))_([PN])$")

def net_class(name):
    """(track width, obstacle raster, via cost) by net."""
    if name.startswith("PCIE_"):
        return 0.1, "s", 300
    if POWER_RE.match(name):
        return 0.3, "p", 150
    return 0.1, "s", 120


# ---------------------------------------------------------------------------------------------
class Raster:
    """Per-layer obstacle maps on a GRID-spaced lattice of cell centres. own[r][layer][i] is 0
    (free), a net code (only that net's copper within reach) or -1 (two nets); r is 's' for
    0.1 mm tracks and 'p' for wide ones. via[i] is the same for a via (all layers). soft[]
    holds the router's own tracks (rippable), hard everything else."""
    def __init__(self, board):
        bb = board.GetBoardEdgesBoundingBox()
        # cell centres on absolute multiples of GRID: the BGA row/column gap lines and the
        # escape vias are on that lattice, so tracks sit exactly centred between them
        self.x0 = math.floor(to_mm(bb.GetLeft()) / GRID) * GRID - GRID
        self.y0 = math.floor(to_mm(bb.GetTop()) / GRID) * GRID - GRID
        self.W = int((to_mm(bb.GetRight()) - self.x0) / GRID) + 3
        self.H = int((to_mm(bb.GetBottom()) - self.y0) / GRID) + 3
        n = self.W * self.H
        # s: 0.1 mm signal track, q: 0.1 mm power track, p: 0.3 mm power track, d: pair centreline
        self.own = {k: [array.array("h", bytes(2 * n)), array.array("h", bytes(2 * n))] for k in "sqpd"}
        self.soft = {k: [array.array("h", bytes(2 * n)), array.array("h", bytes(2 * n))] for k in "sqpd"}
        self.via = array.array("h", bytes(2 * n))
        self.xmin, self.xmax = to_mm(bb.GetLeft()), to_mm(bb.GetRight())
        self.ymin, self.ymax = to_mm(bb.GetTop()), to_mm(bb.GetBottom())
        self.alias = {}          # net code -> id used in the rasters (both halves of a pair share one)
        self.power_net = {}      # net code -> True for the 0.15 mm clearance class
        self.pair_net = set()    # net codes of the differential pairs
        self._edges()

    def idx(self, cx, cy):
        return cy * self.W + cx

    def cell(self, x, y):
        return int(round((x - self.x0) / GRID)), int(round((y - self.y0) / GRID))

    def pos(self, cx, cy):
        return self.x0 + cx * GRID, self.y0 + cy * GRID

    def _edges(self):
        for cy in range(self.H):
            for cx in range(self.W):
                x, y = self.pos(cx, cy)
                i = self.idx(cx, cy)
                d = min(x - self.xmin, self.xmax - x, y - self.ymin, self.ymax - y)
                if d < EDGE or fanout.in_notch(x, y):
                    for r in "sqpd":
                        self.own[r][F][i] = -1; self.own[r][B][i] = -1
                    self.via[i] = -1
                elif d < EDGE + 0.15:
                    for r in "pd":
                        self.own[r][F][i] = -1; self.own[r][B][i] = -1
                    self.via[i] = -1
                elif d < 0.55:
                    self.via[i] = -1

    def _set(self, arr, i, net):
        net = self.alias.get(net, net)
        v = arr[i]
        if v == 0:
            arr[i] = net
        elif v != net:
            arr[i] = -1

    def _paint(self, layers, net, dist, bbox, via_too, soft=False):
        """Mark every cell whose centre is closer than `radius` to a shape: radius is R_SIG /
        R_PWR for the two track rasters and R_VIA for the via raster, 0.05 more when the
        shape belongs to a power or ground net (their netclass clearance is 0.15 mm).
        A cell exactly at the limit stays free (DRC passes at equality)."""
        x0, y0, x1, y1 = bbox
        extra = 0.05 if self.power_net.get(net, False) else 0.0
        rs, rq, rp, rv = R_SIG + extra, R_Q, R_PWR, R_VIA         # q, p and the via already hold the 0.15
        rd = R_PWR + extra                                        # a pair stays 0.15 from power copper ...
        if net in self.pair_net:
            rd += PAIR_SPACING - 0.125                            # ... and PAIR_SPACING (edge to edge) from other pairs
        cx0, cy0 = self.cell(x0 - rv - 0.05, y0 - rv - 0.05)
        cx1, cy1 = self.cell(x1 + rv + 0.05, y1 + rv + 0.05)
        tgt = self.soft if soft else self.own
        for cy in range(max(cy0, 0), min(cy1, self.H - 1) + 1):
            for cx in range(max(cx0, 0), min(cx1, self.W - 1) + 1):
                x, y = self.pos(cx, cy)
                d = dist(x, y)
                if d >= rv - 1e-5:
                    continue
                i = self.idx(cx, cy)
                for L in layers:
                    if d < rs - 1e-5:
                        self._set(tgt["s"][L], i, net)
                    if d < rq - 1e-5:
                        self._set(tgt["q"][L], i, net)
                    if d < rp - 1e-5:
                        self._set(tgt["p"][L], i, net)
                    if d < rd - 1e-5:
                        self._set(tgt["d"][L], i, net)
                if via_too:
                    self._set(self.via, i, net)

    def circle(self, layers, x, y, r, net, soft=False):
        self._paint(layers, net, lambda px, py: math.hypot(px - x, py - y) - r, (x - r, y - r, x + r, y + r), True, soft)

    def rect(self, layers, x, y, hx, hy, ang, net):
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        def dist(px, py):
            dx, dy = px - x, py - y
            u, v = dx * c + dy * s, -dx * s + dy * c
            ex, ey = max(abs(u) - hx, 0.0), max(abs(v) - hy, 0.0)
            return math.hypot(ex, ey)
        e = math.hypot(hx, hy)
        self._paint(layers, net, dist, (x - e, y - e, x + e, y + e), True)

    def segment(self, layers, x0, y0, x1, y1, hw, net, soft=False):
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy
        def dist(px, py):
            if l2 == 0:
                return math.hypot(px - x0, py - y0) - hw
            t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
            return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)) - hw
        self._paint(layers, net, dist, (min(x0, x1) - hw, min(y0, y1) - hw, max(x0, x1) + hw, max(y0, y1) + hw), True, soft)


# ---------------------------------------------------------------------------------------------
class Item:
    """A piece of copper: pad, track or via, with the geometry the connectivity needs."""
    def __init__(self, kind, net, layers, x, y, **geo):
        self.kind, self.net, self.layers, self.x, self.y = kind, net, layers, x, y
        self.geo = geo
        self.ref = None

    def contains(self, px, py, L):
        if L not in self.layers:
            return False
        if self.kind == "via":
            return math.hypot(px - self.x, py - self.y) <= VIA_D / 2 + 0.01
        if self.kind == "track":
            x0, y0, x1, y1, hw = self.geo["x0"], self.geo["y0"], self.geo["x1"], self.geo["y1"], self.geo["hw"]
            dx, dy = x1 - x0, y1 - y0
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
            return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)) <= hw + 0.01
        hx, hy, ang = self.geo["hx"], self.geo["hy"], self.geo["ang"]
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        dx, dy = px - self.x, py - self.y
        u, v = dx * c + dy * s, -dx * s + dy * c
        if self.geo.get("circle"):
            return math.hypot(u, v) <= hx + 0.01
        return abs(u) <= hx + 0.01 and abs(v) <= hy + 0.01

    def cells(self, R, shrink=0.0):
        """Grid cells (layer, cx, cy) whose centre lies inside the copper (shrunk a little)."""
        out = []
        if self.kind == "track":
            x0, y0, x1, y1 = self.geo["x0"], self.geo["y0"], self.geo["x1"], self.geo["y1"]
            bx0, by0, bx1, by1 = min(x0, x1) - 0.1, min(y0, y1) - 0.1, max(x0, x1) + 0.1, max(y0, y1) + 0.1
        elif self.kind == "via":
            bx0, by0, bx1, by1 = self.x - 0.3, self.y - 0.3, self.x + 0.3, self.y + 0.3
        else:
            e = math.hypot(self.geo["hx"], self.geo["hy"]) + 0.1
            bx0, by0, bx1, by1 = self.x - e, self.y - e, self.x + e, self.y + e
        cx0, cy0 = R.cell(bx0, by0); cx1, cy1 = R.cell(bx1, by1)
        for cy in range(max(cy0, 0), min(cy1, R.H - 1) + 1):
            for cx in range(max(cx0, 0), min(cx1, R.W - 1) + 1):
                x, y = R.pos(cx, cy)
                for L in self.layers:
                    if self._inside(x, y, shrink):
                        out.append((L, cx, cy))
        return out

    def _inside(self, px, py, shrink):
        if self.kind == "via":
            return math.hypot(px - self.x, py - self.y) <= VIA_D / 2 - shrink + 1e-9
        if self.kind == "track":
            return self.contains(px, py, self.layers[0]) and (self.geo["hw"] - shrink) >= 0.049 or \
                   (self.geo["hw"] >= 0.149 and self.contains(px, py, self.layers[0]))
        hx, hy, ang = self.geo["hx"] - shrink, self.geo["hy"] - shrink, self.geo["ang"]
        if hx <= 0 or hy <= 0:
            hx, hy = max(hx, 0.02), max(hy, 0.02)
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        dx, dy = px - self.x, py - self.y
        u, v = dx * c + dy * s, -dx * s + dy * c
        if self.geo.get("circle"):
            return math.hypot(u, v) <= hx + 1e-9
        return abs(u) <= hx + 1e-9 and abs(v) <= hy + 1e-9

    def dist(self, px, py):
        """Distance from (px, py) to the copper (negative inside)."""
        if self.kind == "via":
            return math.hypot(px - self.x, py - self.y) - VIA_D / 2
        if self.kind == "track":
            return _pt_seg(px, py, self.geo["x0"], self.geo["y0"], self.geo["x1"], self.geo["y1"]) - self.geo["hw"]
        hx, hy, ang = self.geo["hx"], self.geo["hy"], self.geo["ang"]
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        dx, dy = px - self.x, py - self.y
        u, v = dx * c + dy * s, -dx * s + dy * c
        if self.geo.get("circle"):
            return math.hypot(u, v) - hx
        ex, ey = abs(u) - hx, abs(v) - hy
        if ex <= 0 and ey <= 0:
            return max(ex, ey)
        return math.hypot(max(ex, 0.0), max(ey, 0.0))

    def centre_reach(self):
        """((x, y), r): a circle that contains the copper."""
        if self.kind == "via":
            return (self.x, self.y), VIA_D / 2
        if self.kind == "track":
            g = self.geo
            return ((g["x0"] + g["x1"]) / 2, (g["y0"] + g["y1"]) / 2), math.hypot(g["x1"] - g["x0"], g["y1"] - g["y0"]) / 2 + g["hw"]
        return (self.x, self.y), math.hypot(self.geo["hx"], self.geo["hy"])

    def nearest(self, px, py):
        """Closest point of the copper to (px, py): where a new track attaches."""
        if self.kind == "track":
            x0, y0, x1, y1 = self.geo["x0"], self.geo["y0"], self.geo["x1"], self.geo["y1"]
            dx, dy = x1 - x0, y1 - y0
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
            return x0 + t * dx, y0 + t * dy
        return self.x, self.y


class Board:
    """Copper items, their connectivity per net and the rasters."""
    def __init__(self, board):
        self.board = board
        self.R = Raster(board)
        self.items = []
        self.names = {}
        for code, net in board.GetNetInfo().NetsByNetcode().items():
            self.names[code] = net.GetNetname()
        self.codes = {v: k for k, v in self.names.items()}
        for code, name in self.names.items():
            m = re.match(r"^(PCIE_(?:RX\d|TX\d|REFCLK))_([PN])(_C)?$", name)
            if m:
                self.R.alias[code] = self.codes.get(m.group(1) + "_P" + (m.group(3) or ""), code)
                self.R.pair_net.add(code)
            if POWER_RE.match(name):
                self.R.power_net[code] = True
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                self._add_pad(fp, pad)
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                it = Item("via", t.GetNetCode(), (F, B), to_mm(p.x), to_mm(p.y))
                it.ref = t
                self.items.append(it)
                self.R.circle((F, B), it.x, it.y, VIA_D / 2, it.net)
            elif t.GetClass() == "PCB_TRACK":
                L = {pcbnew.F_Cu: F, pcbnew.B_Cu: B}.get(t.GetLayer())
                if L is None:
                    continue
                a, b = t.GetStart(), t.GetEnd()
                hw = to_mm(t.GetWidth()) / 2
                it = Item("track", t.GetNetCode(), (L,), to_mm(a.x), to_mm(a.y),
                          x0=to_mm(a.x), y0=to_mm(a.y), x1=to_mm(b.x), y1=to_mm(b.y), hw=hw)
                it.ref = t
                self.items.append(it)
                self.R.segment((L,), it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"], hw, it.net)

    def _add_pad(self, fp, pad):
        p = pad.GetPosition(); sz = pad.GetSize()
        x, y = to_mm(p.x), to_mm(p.y)
        hx, hy = to_mm(sz.x) / 2, to_mm(sz.y) / 2
        try:
            ang = pad.GetOrientation().AsDegrees()
        except AttributeError:
            ang = 0.0
        try:
            shape = pad.GetShape(pcbnew.F_Cu)
        except TypeError:
            shape = pad.GetShape()
        circle = shape == pcbnew.PAD_SHAPE_CIRCLE
        onF, onB = pad.IsOnLayer(pcbnew.F_Cu), pad.IsOnLayer(pcbnew.B_Cu)
        net = pad.GetNetCode()
        if pad.GetNumber() == "":                      # NPTH: hole plus a margin, blocks everything
            r = max(hx, hy) + 0.2
            self.R.circle((F, B), x, y, r, -1)
            return
        layers = tuple(L for L, on in ((F, onF), (B, onB)) if on)
        if not layers:
            return
        if net <= 0:
            net = -1                                   # no net: an obstacle for every net
        it = Item("pad", net, layers, x, y, hx=hx, hy=hy, ang=ang, circle=circle)
        it.ref = pad
        it.name = f"{fp.GetReference()}.{pad.GetNumber()}"
        self.items.append(it)
        if circle:
            self.R.circle(layers, x, y, hx, net)
        else:
            self.R.rect(layers, x, y, hx, hy, ang, net)

    # ---- connectivity ----
    def components(self, net):
        """Groups of items of `net` joined by overlap (planes not counted)."""
        items = [it for it in self.items if it.net == net]
        parent = list(range(len(items)))
        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
        pts = []
        for k, it in enumerate(items):
            if it.kind == "track":
                pts.append((k, it.geo["x0"], it.geo["y0"], it.layers[0]))
                pts.append((k, it.geo["x1"], it.geo["y1"], it.layers[0]))
            elif it.kind == "via":
                pts.append((k, it.x, it.y, F)); pts.append((k, it.x, it.y, B))
        for k, x, y, L in pts:
            for j, other in enumerate(items):
                if j == k:
                    continue
                if other.contains(x, y, L):
                    union(k, j)
        groups = {}
        for k, it in enumerate(items):
            groups.setdefault(find(k), []).append(it)
        return list(groups.values())

    @staticmethod
    def on_island(x, y, netname):
        import pcb
        r = pcb.ISLANDS.get(netname)
        if not r:
            return False
        dx, dy = fanout.to_design(x, y)
        return r[0] <= dx <= r[1] and r[2] <= dy <= r[3]

    def grounded(self, comp, netname):
        """True if the component reaches the main part of the net's plane through one of its
        vias (a via on a cut-off corner island does not count)."""
        for it in comp:
            if it.kind == "via" and fanout.plane_under(it.x, it.y, netname) and not self.on_island(it.x, it.y, netname):
                return True
        return False

    # ---- adding copper ----
    def add_track(self, L, x0, y0, x1, y1, w, net, soft=True):
        t = pcbnew.PCB_TRACK(self.board)
        t.SetStart(pcbnew.VECTOR2I(MM(x0), MM(y0))); t.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        t.SetWidth(MM(w)); t.SetLayer(LAYER_ID[L]); t.SetNetCode(net)
        self.board.Add(t)
        it = Item("track", net, (L,), x0, y0, x0=x0, y0=y0, x1=x1, y1=y1, hw=w / 2)
        it.ref = t; it.soft = soft
        self.items.append(it)
        self.R.segment((L,), x0, y0, x1, y1, w / 2, net, soft=soft)
        return it

    def add_via(self, x, y, net, soft=True):
        v = pcbnew.PCB_VIA(self.board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL)); v.SetNetCode(net)
        self.board.Add(v)
        it = Item("via", net, (F, B), x, y)
        it.ref = v; it.soft = soft
        self.items.append(it)
        self.R.circle((F, B), x, y, VIA_D / 2, net, soft=soft)
        return it

    def rip(self, net):
        """Remove the router's own copper of a net (rasters are rebuilt by the caller)."""
        keep = []
        n = 0
        for it in self.items:
            if it.net == net and getattr(it, "soft", False):
                self.board.Remove(it.ref); n += 1
            else:
                keep.append(it)
        self.items = keep
        return n

    def rebuild_soft(self):
        R = self.R
        n = R.W * R.H
        for r in "sqpd":
            for L in (F, B):
                R.soft[r][L] = array.array("h", bytes(2 * n))
        # vias of the router are in R.via as hard marks: rebuild R.via from scratch
        R.via = array.array("h", bytes(2 * n))
        R._edges()
        for it in self.items:
            soft = getattr(it, "soft", False)
            if it.kind == "via":
                R.circle((F, B), it.x, it.y, VIA_D / 2, it.net, soft=soft)
            elif it.kind == "track":
                R.segment(it.layers, it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"], it.geo["hw"], it.net, soft=soft)
            elif it.kind == "pad" and not soft:
                if it.geo.get("circle"):
                    R._paint(it.layers, it.net, lambda px, py, it=it: math.hypot(px - it.x, py - it.y) - it.geo["hx"],
                             (it.x - it.geo["hx"], it.y - it.geo["hx"], it.x + it.geo["hx"], it.y + it.geo["hx"]), True)
                else:
                    R.rect(it.layers, it.x, it.y, it.geo["hx"], it.geo["hy"], it.geo["ang"], it.net)


# ---------------------------------------------------------------------------------------------
# A* on the cell lattice
DIRS = [(1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10), (1, 1, 14), (-1, -1, 14), (1, -1, 14), (-1, 1, 14)]

def search(bd, nets, rkey, sources, targets, via_cost, width, allow_soft=None, layer_pref=None,
           via_targets=None, max_expand=600000, heur_pts=None, via_clear=0.0, via_excl=()):
    """Shortest path from any source cell to any target cell. nets: codes that count as own
    copper. rkey: 's' or 'p' raster. allow_soft: if a dict, rippable tracks of other nets may be
    crossed at cost allow_soft['cost'] per cell and the nets met are collected in allow_soft['hit'].
    via_targets: cells where ending with a via onto the plane counts as reaching the target.
    Returns (path as [(layer, cx, cy)], ends_with_via) or (None, None)."""
    R = bd.R
    W, H = R.W, R.H
    N = W * H
    own = R.own[rkey]; soft = R.soft[rkey]
    okset = {R.alias.get(n, n) for n in nets} | {0}
    netset = set(nets)
    own_vias = [(it.x, it.y) for it in bd.items if it.kind == "via" and it.net in netset]
    forbid = (allow_soft or {}).get("forbid", ())
    via_cache = {}
    def via_ok(r):
        """A new via here: nothing foreign within reach, no own via closer than 0.45 mm (an own
        via at this very spot is simply reused); with via_clear, nothing at all within that radius
        and not within 1 mm of either end of the pair."""
        v = via_cache.get(r)
        if v is None:
            vv = R.via[r]
            cy_, cx_ = divmod(r, W)
            if rv and any(abs(cx_ - ex) + abs(cy_ - ey) < 10 for ex, ey in via_excl):
                v = False
            elif rv:
                v = _via_clear(R, cx_, cy_, rv, {0})
            elif vv == 0:
                v = True
            elif vv in okset:
                x_, y_ = R.pos(cx_, cy_)
                v = all(not (0.03 < math.hypot(x_ - vx, y_ - vy) < 0.45) for vx, vy in own_vias)
            else:
                v = False
            via_cache[r] = v
        return v
    rv = int(round(via_clear / GRID))
    g = array.array("f", [1e30]) * (2 * N)
    prev = array.array("i", [-1]) * (2 * N)
    tgt = set(targets)
    vt = set(via_targets or ())
    heap = []
    if heur_pts:
        def h(cx, cy):
            best = 1e9
            for (tx, ty) in heur_pts:
                dx, dy = abs(cx - tx), abs(cy - ty)
                d = 10 * (dx + dy) - 6 * min(dx, dy)
                if d < best:
                    best = d
            return best
    else:
        h = lambda cx, cy: 0
    for (L, cx, cy) in sources:
        i = L * N + cy * W + cx
        if g[i] > 0:
            g[i] = 0.0
            heapq.heappush(heap, (h(cx, cy), i))
    soft_cost = allow_soft["cost"] if allow_soft else None
    expanded = 0
    found = None
    while heap:
        f, i = heapq.heappop(heap)
        gi = g[i]
        if f - h((i % N) % W, (i % N) // W) > gi + 1e-6:
            continue
        L = i // N; r = i % N; cy, cx = divmod(r, W)
        if (L, cx, cy) in tgt:
            found = (i, False); break
        if (L, cx, cy) in vt and via_ok(r):
            found = (i, True); break
        expanded += 1
        if expanded > max_expand:
            break
        pd = prev[i]
        pdir = None
        if pd >= 0 and pd // N == L:
            pr = pd % N
            pdir = (cx - pr % W, cy - pr // W)
        for dx, dy, c in DIRS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= W or ny >= H:
                continue
            nr = ny * W + nx
            o = own[L][nr]
            if o not in okset:
                continue
            so = soft[L][nr]
            extra = 0
            if so not in okset:
                if soft_cost is None or so in forbid or so == -1:
                    continue
                extra = soft_cost
            if layer_pref is not None and L != layer_pref:
                extra += 2
            if pdir is not None and (dx, dy) != pdir:
                extra += 4 if (dx * pdir[0] + dy * pdir[1]) > 0 else 12
            ng = gi + c + extra
            ni = L * N + nr
            if ng < g[ni]:
                g[ni] = ng; prev[ni] = i
                heapq.heappush(heap, (ng + h(nx, ny), ni))
        # layer change: a via here
        if via_ok(r):
            L2 = 1 - L
            o2 = own[L2][r]
            if o2 in okset:
                so2 = soft[L2][r]
                extra = 0
                if so2 not in okset:
                    if soft_cost is None or so2 in forbid or so2 == -1:
                        continue
                    extra = soft_cost
                ng = gi + via_cost + extra
                ni = L2 * N + r
                if ng < g[ni]:
                    g[ni] = ng; prev[ni] = i
                    heapq.heappush(heap, (ng + h(cx, cy), ni))
    if found is None:
        return None, None
    i, with_via = found
    path = []
    while i >= 0:
        L = i // N; r = i % N
        path.append((L, r % W, r // W))
        i = prev[i]
    path.reverse()
    if allow_soft is not None:
        hit = set()
        for (L, cx, cy) in path:
            so = soft[L][cy * W + cx]
            if so not in okset and so > 0:
                hit.add(so)
            elif so == -1:
                hit.add(-1)
        allow_soft["hit"] = hit
    return path, with_via


def _via_clear(R, cx, cy, rv, okset):
    for dy in range(-rv, rv + 1):
        for dx in range(-rv, rv + 1):
            if dx * dx + dy * dy > rv * rv:
                continue
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= R.W or ny >= R.H:
                return False
            if R.via[ny * R.W + nx] not in okset:
                return False
    return True


def simplify(path):
    """Merge collinear steps: [(L, cx, cy)] -> [(L, cx, cy)] corner points (layer changes kept)."""
    out = [path[0]]
    last = None
    for k in range(1, len(path)):
        L, cx, cy = path[k]
        pL, px, py = path[k - 1]
        if L != pL:
            out.append(path[k]); last = None; continue
        d = (cx - px, cy - py)
        if d == last:
            out[-1] = path[k]
        else:
            out.append(path[k]); last = d
    return out


# ---------------------------------------------------------------------------------------------
class Router:
    def __init__(self, board, log=print):
        self.bd = Board(board)
        self.log = log
        self.failed = []
        self.stats = {"tracks": 0, "vias": 0, "ripped": 0}
        self.mode = {}            # net -> kwargs of route_net, for re-routing after a rip-up
        self.ripped_by = {}       # net -> nets that ripped it up (it may not rip those in return)
        self.plane_cells = {}     # net name -> cells over the main part of its plane
        self.no_rip = set()       # raster ids never ripped (the PCIe pairs)

    # ---- helpers ----
    def comp_cells(self, comp, shrink=0.03):
        cells = []
        for it in comp:
            cells += it.cells(self.bd.R, shrink)
        return cells

    def attach(self, comp, L, x, y):
        """Point on the component's copper on layer L nearest to (x, y) (for the final stub)."""
        best = None
        for it in comp:
            if L not in it.layers:
                continue
            px, py = it.nearest(x, y)
            if it.kind == "pad" and not it.contains(x, y, L):
                px, py = it.x, it.y
            d = math.hypot(px - x, py - y)
            if best is None or d < best[0]:
                best = (d, px, py, it)
        return best

    def lay(self, path, net, width, comp_from=None, comp_to=None, end_via=False, netname="", widen=None):
        """Put the tracks and vias of a cell path on the board. widen(L, cx, cy) -> True where a
        0.3 mm track fits: those stretches are laid 0.3 mm wide."""
        R = self.bd.R
        pts = simplify(path)
        wide = {}
        if widen:
            flags = [widen(L, cx, cy) for (L, cx, cy) in path]
            pts, cur_dir, cur_w = [path[0]], None, None
            for k in range(1, len(path)):
                (L, cx, cy), (pL, px, py) = path[k], path[k - 1]
                if L != pL:
                    pts.append(path[k]); cur_dir = cur_w = None
                    continue
                d, w_ok = (cx - px, cy - py), flags[k] and flags[k - 1]
                if d == cur_dir and w_ok == cur_w:
                    pts[-1] = path[k]
                else:
                    pts.append(path[k]); wide[len(pts) - 1] = w_ok; cur_dir, cur_w = d, w_ok
        segs = []
        placed = set()
        for k in range(1, len(pts)):
            (L0, x0, y0), (L1, x1, y1) = pts[k - 1], pts[k]
            if L0 != L1:
                if (x0, y0) not in placed:
                    vx, vy = R.pos(x0, y0)
                    if not any(it.kind == "via" and it.net == net and math.hypot(it.x - vx, it.y - vy) < 0.03 for it in self.bd.items):
                        self.bd.add_via(vx, vy, net); self.stats["vias"] += 1
                    placed.add((x0, y0))
                continue
            ax, ay = R.pos(x0, y0); bx, by = R.pos(x1, y1)
            segs.append((L0, ax, ay, bx, by, 0.3 if wide.get(k) else width))
        # stubs from the exact copper to the first/last cell
        L, cx, cy = path[0]
        x, y = R.pos(cx, cy)
        if comp_from:
            a = self.attach(comp_from, L, x, y)
            if a and a[0] > 0.02:
                segs.insert(0, (L, a[1], a[2], x, y, width))
        L, cx, cy = path[-1]
        x, y = R.pos(cx, cy)
        if end_via:
            self.bd.add_via(x, y, net); self.stats["vias"] += 1
        elif comp_to:
            a = self.attach(comp_to, L, x, y)
            if a and a[0] > 0.02:
                segs.append((L, x, y, a[1], a[2], width))
        for (L, ax, ay, bx, by, w) in segs:
            if math.hypot(bx - ax, by - ay) < 0.005:
                continue
            self.bd.add_track(L, ax, ay, bx, by, w, net)
            self.stats["tracks"] += 1

    # ---- generic net routing (tree of components) ----
    def route_net(self, net, width=None, rkey=None, via_cost=None, allow_rip=True, plane=False, netname=None):
        bd = self.bd
        netname = netname or bd.names[net]
        w, rk, vc = net_class(netname)
        width = width or w; rkey = rkey or rk; via_cost = via_cost or vc
        self.mode[net] = dict(width=width, rkey=rkey, via_cost=via_cost, plane=plane)
        comps = bd.components(net)
        if plane:
            # everything with a via on a corner island is one group (joined by the island)
            isl = [c for c in comps if not bd.grounded(c, netname) and any(it.kind == "via" and bd.on_island(it.x, it.y, netname) for it in c)]
            if len(isl) > 1:
                comps = [c for c in comps if c not in isl] + [[it for c in isl for it in c]]
            grounded = [c for c in comps if bd.grounded(c, netname)]
            pending = [c for c in comps if not bd.grounded(c, netname)]
            if not pending:
                return True
            if grounded:
                tree = [it for c in grounded for it in c]
            else:
                tree = []
        else:
            if len(comps) <= 1:
                return True
            comps.sort(key=lambda c: -len(c))
            tree = list(comps[0]); pending = comps[1:]
        ok = True
        while pending:
            # nearest pending component to the tree (by item centres)
            def dist(c):
                if not tree:
                    return 0
                return min(math.hypot(a.x - b.x, a.y - b.y) for a in c for b in tree)
            pending.sort(key=dist)
            comp = pending.pop(0)
            if self.connect(net, netname, comp, tree, width, rkey, via_cost, allow_rip, plane):
                tree += comp
            else:
                ok = False
                self.failed.append((netname, [getattr(it, "name", it.kind) for it in comp]))
        return ok

    def connect(self, net, netname, comp, tree, width, rkey, via_cost, allow_rip, plane):
        bd = self.bd; R = bd.R
        thin = "q" if POWER_RE.match(netname) else "s"       # a 0.1 mm track of this net
        if any(getattr(it, "name", "").startswith("U1.") for it in comp):
            width, rkey = 0.1, thin
        sources = self.comp_cells(comp)
        targets = self.comp_cells(tree) if tree else []
        via_targets = None
        heur = [R.cell(it.x, it.y)[0:2] for it in tree][:40] if tree else None
        if plane:
            # any cell over the main part of the net's plane where a via fits
            if netname not in self.plane_cells:
                cells = []
                for cy in range(R.H):
                    for cx in range(R.W):
                        x, y = R.pos(cx, cy)
                        if fanout.plane_under(x, y, netname) and not bd.on_island(x, y, netname):
                            cells.append((F, cx, cy)); cells.append((B, cx, cy))
                self.plane_cells[netname] = cells
            via_targets = self.plane_cells[netname]
            mx, my = R.cell(sum(it.x for it in comp) / len(comp), sum(it.y for it in comp) / len(comp))
            near = sorted(via_targets[::40], key=lambda c: abs(c[1] - mx) + abs(c[2] - my))[:30]
            heur = (heur or []) + [(cx, cy) for (_, cx, cy) in near]
        if not sources or (not targets and not via_targets):
            return False
        path, with_via = search(bd, [net], rkey, sources, targets, via_cost, width, via_targets=via_targets,
                                heur_pts=heur, via_clear=0.0)
        if path is None and rkey == "p":                     # no room for a wide track: a thin one
            width, rkey = 0.1, thin
            path, with_via = search(bd, [net], rkey, sources, targets, via_cost, width, via_targets=via_targets,
                                    heur_pts=heur, via_clear=0.0)
        if path is None and allow_rip:
            soft = {"cost": 60, "forbid": self.no_rip | {R.alias.get(v, v) for v in self.ripped_by.get(net, ())}}
            path, with_via = search(bd, [net], rkey, sources, targets, via_cost, width, allow_soft=soft,
                                    via_targets=via_targets, heur_pts=heur)
            if path is not None and soft["hit"]:
                victims = [n for n in soft["hit"] if n > 0]
                if -1 in soft["hit"] or not victims:
                    return False
                self.log(f"    rip-up for {netname}: {[bd.names[v] for v in victims]}")
                for v in victims:
                    bd.rip(v); self.stats["ripped"] += 1
                    self.requeue.append(v)
                    self.ripped_by.setdefault(v, set()).add(net)
                bd.rebuild_soft()
        if path is None:
            return False
        widen = None
        if width < 0.3 and POWER_RE.match(netname):          # thin only where it has to be
            ok = {R.alias.get(net, net), 0}
            widen = lambda L, cx, cy: R.own["p"][L][R.idx(cx, cy)] in ok and R.soft["p"][L][R.idx(cx, cy)] in ok
        self.lay(path, net, width, comp_from=comp, comp_to=tree if not with_via else None, end_via=with_via, netname=netname, widen=widen)
        return True

    # ---- differential pairs ----
    def pair_specs(self):
        """[(label, netP, netN)]: the BGA-to-capacitor/finger halves and the capacitor-to-finger
        (_C) halves of the transmit pairs and REFCLK, each routed as one pair."""
        bd = self.bd
        specs = []
        for code, name in sorted(bd.names.items(), key=lambda kv: kv[1]):
            m = re.match(r"^(PCIE_(?:RX\d|TX\d|REFCLK))_P(_C)?$", name)
            if not m:
                continue
            nname = m.group(1) + "_N" + (m.group(2) or "")
            if nname in bd.codes:
                specs.append((name[:-2] if not m.group(2) else m.group(1) + "_C", code, bd.codes[nname]))
        return specs

    def route_pair(self, label, netP, netN):
        bd = self.bd; R = bd.R
        compsP, compsN = bd.components(netP), bd.components(netN)
        if len(compsP) != 2 or len(compsN) != 2:
            self.log(f"  {label}: expected 2 components per half, got {len(compsP)}/{len(compsN)}; routing singly")
            return self.route_net(netP) and self.route_net(netN)
        def center(c):
            return sum(it.x for it in c) / len(c), sum(it.y for it in c) / len(c)
        # pair up the P and N components by proximity
        pairs, used = [], set()
        for cp in compsP:
            k = min((k for k in range(2) if k not in used),
                    key=lambda k: math.hypot(center(cp)[0] - center(compsN[k])[0], center(cp)[1] - center(compsN[k])[1]))
            used.add(k); pairs.append((cp, compsN[k]))
        def terminal(c, other):
            vias = [it for it in c if it.kind == "via"]
            pads = [it for it in c if it.kind == "pad"]
            if vias and pads:                         # an escape: its end via, the one farthest from the ball
                return max(vias, key=lambda v: math.hypot(v.x - pads[0].x, v.y - pads[0].y))
            ox, oy = center(other)
            return min(c, key=lambda it: math.hypot(it.x - ox, it.y - oy))
        tP = [terminal(cp, cn) for cp, cn in pairs]
        tN = [terminal(cn, cp) for cp, cn in pairs]
        if any(math.hypot(a.x - b.x, a.y - b.y) > 1.7 for a, b in zip(tP, tN)):
            # the two halves do not start side by side (REFCLK): two single tracks, matched afterwards
            self.log(f"  {label}: routed as two single tracks")
            return self.route_net(netP, allow_rip=False) and self.route_net(netN, allow_rip=False)
        if tP[0].kind != "via" and tP[1].kind == "via":       # end 0 = the escape end if there is one
            pairs.reverse(); tP.reverse(); tN.reverse()
        (p0, n0), (p1, n1) = (tP[0], tN[0]), (tP[1], tN[1])
        m0 = ((p0.x + n0.x) / 2, (p0.y + n0.y) / 2); m1 = ((p1.x + n1.x) / 2, (p1.y + n1.y) / 2)
        ends = []
        u1 = next((fp.GetPosition() for fp in bd.board.GetFootprints() if fp.GetReference() == "U1"), None)
        for (p, n, m, om) in ((p0, n0, m0, m1), (p1, n1, m1, m0)):
            # leave square to the line joining the two terminals: away from the BGA for an
            # escape, towards the other end otherwise
            ref = (m[0] - to_mm(u1.x), m[1] - to_mm(u1.y)) if (p.kind == "via" and u1 is not None) else (om[0] - m[0], om[1] - m[1])
            if abs(p.x - n.x) >= abs(p.y - n.y):
                t = (0.0, 1.0 if (om[1] - m[1] if p.kind == "via" else ref[1]) > 0 else -1.0)
            else:
                t = (1.0 if ref[0] > 0 else -1.0, 0.0)
            d = math.hypot(p.x - n.x, p.y - n.y)
            def ext(it):                              # pad half-size along t
                if it.kind != "pad":
                    return 0.0
                hx, hy = it.geo["hx"], it.geo["hy"]
                if abs(((it.geo["ang"] + 45) % 180) - 45) > 1:
                    hx, hy = hy, hx
                return hy if t[0] == 0 else hx
            # straight out of a via, or to 0.2 mm beyond the pads, before the two halves converge
            straight = (1.0 if d > 1.0 else 0.3) if (p.kind == "via" or n.kind == "via") else max(ext(p), ext(n)) + 0.2
            conv = max(d / 2 - PAIR_OFF, 0.0)
            S = (m[0] + t[0] * (straight + conv), m[1] + t[1] * (straight + conv))
            ends.append(dict(p=p, n=n, m=m, t=t, straight=straight, S=S))
        e0, e1 = ends
        # which side of the travel direction P is on (left normal nL = (-ty, tx))
        def nL(t):
            return (-t[1], t[0])
        n0v = nL(e0["t"])
        sP = 1 if (e0["p"].x - e0["m"][0]) * n0v[0] + (e0["p"].y - e0["m"][1]) * n0v[1] > 0 else -1
        t1_arr = (-e1["t"][0], -e1["t"][1])           # travel direction when arriving at end 1
        n1v = nL(t1_arr)
        sP1 = 1 if (e1["p"].x - e1["m"][0]) * n1v[0] + (e1["p"].y - e1["m"][1]) * n1v[1] > 0 else -1
        if sP1 != sP:
            self.log(f"  {label}: P/N would have to cross (polarity order differs at the two ends)")
            self.failed.append((label, ["pair polarity"]))
            return False
        # the straight stubs out of the terminals, marked so the search keeps off them
        stubs = []
        for e in ends:
            for it in (e["p"], e["n"]):
                a = (it.x, it.y); b = (it.x + e["t"][0] * e["straight"], it.y + e["t"][1] * e["straight"])
                stubs.append((it.net, a, b))
        for net, a, b in stubs:
            R.segment((F, B), a[0], a[1], b[0], b[1], PAIR_W / 2, net, soft=True)
        c0 = R.cell(*e0["S"]); c1 = R.cell(*e1["S"])
        def layers_of(e):
            p = e["p"]
            if p.kind == "via":
                return (F, B)
            return tuple(L for L in (F, B) if L in p.layers)
        sources = [(L, c0[0], c0[1]) for L in layers_of(e0)]
        targets = [(L, c1[0], c1[1]) for L in layers_of(e1)]
        path, _ = search(bd, [netP, netN], "d", sources, targets, 320, 0.35, heur_pts=[c1], via_clear=0.4, via_excl=(c0, c1))
        bd.rebuild_soft()                             # drop the stub marks
        manh = abs(c0[0] - c1[0]) + abs(c0[1] - c1[1])
        if path is not None and len(path) > 1.8 * manh + 80:
            self.log(f"  {label}: only a {len(path) * GRID:.0f} mm detour found")
            path = None
        if path is None:
            self.log(f"  {label}: no path for the pair centreline")
            self.failed.append((label, ["pair"]))
            return False
        self.lay_pair(path, netP, netN, e0, e1, sP)
        return True

    def lay_pair(self, path, netP, netN, e0, e1, sP):
        """Centreline cell path -> P and N tracks offset +/-PAIR_OFF, stubs and 45-degree
        convergence at both ends, and at every layer change two vias PAIR_VIA_OFF either
        side of the centreline reached by 45-degree splays. sP = +1 when P is left of travel."""
        R = self.bd.R
        pts = simplify(path)
        runs, cur = [], [pts[0]]
        for p in pts[1:]:
            if p[0] != cur[-1][0]:
                runs.append(cur); cur = [p]
            else:
                cur.append(p)
        runs.append(cur)
        polys = []
        for k, run in enumerate(runs):
            poly = [R.pos(p[1], p[2]) for p in run]
            if k == 0:                                # start: a short piece along t ending on S
                t = e0["t"]; S = e0["S"]
                poly = [(S[0] - t[0] * 0.01, S[1] - t[1] * 0.01), S] + poly[1:]
            if k == len(runs) - 1:                    # end: arrive at S and carry on against t1
                t = e1["t"]; S = e1["S"]
                poly = poly[:-1] + [S, (S[0] - t[0] * 0.01, S[1] - t[1] * 0.01)]
            polys.append((run[0][0], _dedupe(poly)))
        def nL(d):
            l = math.hypot(d[0], d[1]) or 1.0
            return (-d[1] / l, d[0] / l)
        # vias between runs, offset perpendicular to the direction of travel into the via
        vias = []
        for k in range(len(polys) - 1):
            L, poly = polys[k]
            vx, vy = poly[-1]
            ax, ay = poly[-2]
            n = nL((vx - ax, vy - ay))
            vias.append({net: (vx + sgn * sP * n[0] * PAIR_VIA_OFF, vy + sgn * sP * n[1] * PAIR_VIA_OFF)
                         for net, sgn in ((netP, 1), (netN, -1))})
            for net in (netP, netN):
                self.bd.add_via(vias[-1][net][0], vias[-1][net][1], net); self.stats["vias"] += 1
        for k, (L, poly) in enumerate(polys):
            for net, sgn in ((netP, 1), (netN, -1)):
                off = sgn * sP * PAIR_OFF
                half = offset_polyline(poly, off)
                if k > 0:                             # splay out of the via
                    d = nL(nL((poly[1][0] - poly[0][0], poly[1][1] - poly[0][1])))   # = -direction; fix below
                    dx, dy = poly[1][0] - poly[0][0], poly[1][1] - poly[0][1]
                    l = math.hypot(dx, dy) or 1.0; dx, dy = dx / l, dy / l
                    n = nL((dx, dy))
                    sp = (poly[0][0] + dx * (PAIR_VIA_OFF - PAIR_OFF) + sgn * sP * n[0] * PAIR_OFF,
                          poly[0][1] + dy * (PAIR_VIA_OFF - PAIR_OFF) + sgn * sP * n[1] * PAIR_OFF)
                    half = [vias[k - 1][net], sp] + half[1:]
                if k < len(polys) - 1:                # splay into the via
                    dx, dy = poly[-1][0] - poly[-2][0], poly[-1][1] - poly[-2][1]
                    l = math.hypot(dx, dy) or 1.0; dx, dy = dx / l, dy / l
                    n = nL((dx, dy))
                    sp = (poly[-1][0] - dx * (PAIR_VIA_OFF - PAIR_OFF) + sgn * sP * n[0] * PAIR_OFF,
                          poly[-1][1] - dy * (PAIR_VIA_OFF - PAIR_OFF) + sgn * sP * n[1] * PAIR_OFF)
                    half = half[:-1] + [sp, vias[k][net]]
                if k == 0:                            # terminal stub and convergence
                    it = e0["p"] if net == netP else e0["n"]
                    t = e0["t"]
                    half = [(it.x, it.y), (it.x + t[0] * e0["straight"], it.y + t[1] * e0["straight"])] + half
                if k == len(polys) - 1:
                    it = e1["p"] if net == netP else e1["n"]
                    t = e1["t"]
                    half = half + [(it.x + t[0] * e1["straight"], it.y + t[1] * e1["straight"]), (it.x, it.y)]
                for (ax, ay), (bx, by) in zip(half, half[1:]):
                    if math.hypot(bx - ax, by - ay) < 0.005:
                        continue
                    self.bd.add_track(L, ax, ay, bx, by, PAIR_W, net); self.stats["tracks"] += 1

    # ---- length matching ----
    def pair_lengths(self):
        """{lane: (lenP, lenN)} over every track of the pair's nets, the _C halves included."""
        bd = self.bd
        out = {}
        for code, name in bd.names.items():
            m = re.match(r"^(PCIE_(?:RX\d|TX\d|REFCLK))_([PN])(_C)?$", name)
            if not m:
                continue
            lane, pol = m.group(1), m.group(2)
            l = sum(math.hypot(it.geo["x1"] - it.geo["x0"], it.geo["y1"] - it.geo["y0"])
                    for it in bd.items if it.kind == "track" and it.net == code)
            out.setdefault(lane, [0.0, 0.0])[0 if pol == "P" else 1] += l
        return out

    def tune_pairs(self, tol=0.1):
        """Serpentine bumps on the shorter half of each pair until the two are within tol."""
        report = {}
        for lane in sorted(self.pair_lengths()):
            report[lane] = self.tune_pair(lane, tol=tol)
        return report

    def tune_pair(self, lane, only=None, tol=0.1):
        """Balance one lane (all its nets, or just the two in `only`). Returns (lenP, lenN, bumps)."""
        bd = self.bd
        def lengths():
            lp = ln = 0.0
            for it in bd.items:
                if it.kind != "track":
                    continue
                if only and it.net not in only:
                    continue
                m = re.match(rf"^{lane}_([PN])(_C)?$", bd.names[it.net])
                if not m:
                    continue
                l = math.hypot(it.geo["x1"] - it.geo["x0"], it.geo["y1"] - it.geo["y0"])
                if m.group(1) == "P":
                    lp += l
                else:
                    ln += l
            return lp, ln
        lp, ln = lengths()
        delta = lp - ln
        bumps = 0
        need = abs(delta)
        while need > tol:
            short = "N" if delta > 0 else "P"
            short_nets = [c for c, n in bd.names.items() if re.match(rf"^{lane}_{short}(_C)?$", n) and (not only or c in only)]
            segs = [it for it in bd.items if it.kind == "track" and it.net in short_nets and getattr(it, "soft", False)
                    and math.hypot(it.geo["x1"] - it.geo["x0"], it.geo["y1"] - it.geo["y0"]) >= 0.8]
            # B.Cu runs first (more room beside them), then the longest
            segs.sort(key=lambda it: (it.layers[0] != B, -math.hypot(it.geo["x1"] - it.geo["x0"], it.geo["y1"] - it.geo["y0"])))
            done = False
            for it in segs:
                for h in (min(0.6, need / (2 * (math.sqrt(2) - 1))), 0.4, 0.25, 0.2, 0.15):
                    if 2 * (math.sqrt(2) - 1) * h > need + tol:
                        continue
                    if self.bump(it, h):
                        need -= 2 * (math.sqrt(2) - 1) * h; bumps += 1; done = True
                        break
                if done:
                    break
            if not done:
                break
        lp, ln = lengths()
        return lp, ln, bumps

    def bump(self, it, h, w=0.3):
        """Replace the middle of a straight track with a trapezoid detour of height h (45-degree
        ramps) on whichever side has room; the partner track and everything else must stay clear."""
        bd = self.bd; R = bd.R
        x0, y0, x1, y1 = it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"]
        L = it.layers[0]; net = it.net
        dx, dy = x1 - x0, y1 - y0
        s = math.hypot(dx, dy)
        if s < 2 * h + w + 0.4:
            return False
        dx, dy = dx / s, dy / s
        a = (s - 2 * h - w) / 2
        mx, my = x0 + dx * s / 2, y0 + dy * s / 2
        for sgn in (1, -1):
            nx, ny = -dy * sgn, dx * sgn
            # the partner track must not be on this side
            if not self._partner_clear(L, (mx + nx * 0.3, my + ny * 0.3), net) or \
               not self._partner_clear(L, (mx + nx * (h + 0.3), my + ny * (h + 0.3)), net):
                continue
            p1 = (x0 + dx * a, y0 + dy * a)
            p2 = (p1[0] + (dx + nx) * h, p1[1] + (dy + ny) * h)
            p3 = (p2[0] + dx * w, p2[1] + dy * w)
            p4 = (p3[0] + (dx - nx) * h, p3[1] + (dy - ny) * h)
            new = [(x0, y0), p1, p2, p3, p4, (x1, y1)]
            if not all(self._partner_clear(L, (pa[0] + (pb[0] - pa[0]) * k / 8, pa[1] + (pb[1] - pa[1]) * k / 8), net)
                       for pa, pb in zip(new[1:-1], new[2:-1]) for k in range(9)):
                continue
            if all(self.segment_free(L, pa, pb, net) for pa, pb in zip(new[1:-1], new[2:-1])):
                bd.board.Remove(it.ref); bd.items.remove(it)
                for pa, pb in zip(new, new[1:]):
                    bd.add_track(L, pa[0], pa[1], pb[0], pb[1], it.geo["hw"] * 2, net)
                bd.rebuild_soft()
                return True
        return False

    def _partner_clear(self, L, pt, net):
        """No track of the pair partner within 0.3 mm of pt on layer L."""
        R = self.bd.R
        a = R.alias.get(net, net)
        for it in self.bd.items:
            if it.kind != "track" or L not in it.layers or it.net == net or R.alias.get(it.net, it.net) != a:
                continue
            if _pt_seg(pt[0], pt[1], it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"]) < 0.24:
                return False
        for it in self.bd.items:                       # and its vias
            if it.kind == "via" and it.net != net and R.alias.get(it.net, it.net) == a and math.hypot(it.x - pt[0], it.y - pt[1]) < 0.4:
                return False
        return True

    def segment_free(self, L, a, b, net, strict=False):
        """No foreign copper (strict: no copper at all except the net's own locked items) within
        the signal clearance along the segment."""
        R = self.bd.R
        n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (GRID / 2)) + 1)
        alias = R.alias.get(net, net)
        for k in range(n + 1):
            t = k / n
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            cx, cy = R.cell(x, y)
            if cx < 0 or cy < 0 or cx >= R.W or cy >= R.H:
                return False
            i = R.idx(cx, cy)
            o = R.own["s"][L][i]; so = R.soft["s"][L][i]
            if o not in (0, alias) or so not in (0, alias):
                return False
        return True

    def _own_net_only(self, L, cx, cy, net):
        """True if the router copper near this cell belongs to `net` itself (not its pair partner)."""
        R = self.bd.R
        x, y = R.pos(cx, cy)
        for it in self.bd.items:
            if it.kind != "track" or L not in it.layers or not getattr(it, "soft", False):
                continue
            if R.alias.get(it.net, it.net) != R.alias.get(net, net) or it.net == net:
                continue
            if it.contains(x, y, L) or _pt_seg(x, y, it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"]) < 0.25:
                return False
        return True

    def drop_duplicates(self):
        """Tracks laid twice (same ends, layer and net)."""
        bd = self.bd
        seen, n = set(), 0
        for it in list(bd.items):
            if it.kind != "track":
                continue
            g = it.geo
            a, b = (round(g["x0"], 3), round(g["y0"], 3)), (round(g["x1"], 3), round(g["y1"], 3))
            key = (it.net, it.layers[0], min(a, b), max(a, b))
            if key in seen:
                bd.board.Remove(it.ref); bd.items.remove(it); n += 1
            else:
                seen.add(key)
        # ... and tracks lying wholly on top of a longer one
        tracks = [it for it in bd.items if it.kind == "track"]
        by = {}
        for it in tracks:
            by.setdefault((it.net, it.layers[0]), []).append(it)
        for group in by.values():
            for a in list(group):
                ga = a.geo
                for o in group:
                    if o is a or o not in bd.items:
                        continue
                    go = o.geo
                    if go["hw"] + 1e-6 >= ga["hw"] and \
                            _pt_seg(ga["x0"], ga["y0"], go["x0"], go["y0"], go["x1"], go["y1"]) < 1e-3 and \
                            _pt_seg(ga["x1"], ga["y1"], go["x0"], go["y0"], go["x1"], go["y1"]) < 1e-3 and \
                            math.hypot(ga["x1"] - ga["x0"], ga["y1"] - ga["y0"]) < math.hypot(go["x1"] - go["x0"], go["y1"] - go["y0"]):
                        bd.board.Remove(a.ref); bd.items.remove(a); n += 1
                        break
        return n

    def cleanup(self):
        n = m = 0
        self.drop_duplicates()
        while True:
            dv, dt = self.drop_unused_vias(), self.drop_dangling()
            n += dv; m += dt
            if not dv and not dt:
                return n, m

    def drop_dangling(self):
        """Tracks of signal nets with an end that touches nothing (what is left of an escape
        the route did not use)."""
        bd = self.bd
        n = 0
        by_net, whole = {}, {}
        for it in bd.items:
            by_net.setdefault(it.net, []).append(it)
        for it in list(bd.items):
            if it.kind != "track" or bd.names[it.net] in PLANE_NETS or bd.R.alias.get(it.net, it.net) in self.no_rip:
                continue
            L = it.layers[0]
            for (x, y) in ((it.geo["x0"], it.geo["y0"]), (it.geo["x1"], it.geo["y1"])):
                if not any(o is not it and L in o.layers and o.contains(x, y, L) for o in by_net[it.net]):
                    if it.net not in whole:
                        whole[it.net] = len(bd.components(it.net)) == 1
                    if not whole[it.net]:             # not routed yet: its escape stays
                        break
                    bd.board.Remove(it.ref); bd.items.remove(it); by_net[it.net].remove(it); n += 1
                    break
        if n:
            bd.rebuild_soft()
        return n

    def fix_violations(self, viol):
        """viol: [(type, [net names], (x, y))] from KiCad's DRC. A few microns can be lost where a
        track passes a round obstacle between two grid points: block that spot and route the
        net again."""
        bd = self.bd
        redo = []
        for typ, nets, (x, y) in viol:
            cand = [bd.codes[n] for n in nets if n in bd.codes]
            def near(c):                              # the router's own track of net c at the spot
                return any(it.net == c and it.kind == "track" and getattr(it, "soft", False) and
                           _pt_seg(x, y, it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"]) < it.geo["hw"] + 0.8 for it in bd.items)
            victim = next((c for c in cand if bd.R.alias.get(c, c) not in self.no_rip and near(c)), None)
            if victim is None:
                self.log(f"  {typ} at ({x:.2f}, {y:.2f}) between {nets}: nothing of the router's to move")
                continue
            # block the spot on the victim's track nearest the reported position
            best = None
            for it in bd.items:
                if it.net == victim and it.kind == "track" and getattr(it, "soft", False):
                    px, py = it.nearest(x, y)
                    d = math.hypot(px - x, py - y)
                    if best is None or d < best[0]:
                        best = (d, px, py, it.layers)
            bd.R.circle(best[3], best[1], best[2], 0.06, -1)
            if victim not in redo:
                redo.append(victim)
        for v in redo:
            bd.rip(v)
        bd.rebuild_soft()
        self.requeue = []
        queue, n = list(redo), 0
        while queue and n < 40:
            v = queue.pop(0); n += 1
            self.route_net(v, allow_rip=True, **dict(self.mode.get(v, {})))
            queue += [c for c in self.requeue if c not in queue]
            self.requeue = []
        return len(redo)

    def remove_stubs(self, spots):
        """spots: [(net name, (x, y))] of KiCad's dangling-track warnings: remove the track of
        that net with an end nearest the spot (the DRC pass after this one catches a mistake)."""
        bd = self.bd
        n = 0
        for name, (x, y), length in spots:
            net = bd.codes.get(name)
            if net is None or bd.R.alias.get(net, net) in self.no_rip:
                continue
            best = None
            for it in bd.items:
                if it.net == net and it.kind == "track":
                    if length and abs(math.hypot(it.geo["x1"] - it.geo["x0"], it.geo["y1"] - it.geo["y0"]) - length) > 0.002:
                        continue
                    d = min(math.hypot(it.geo["x0"] - x, it.geo["y0"] - y), math.hypot(it.geo["x1"] - x, it.geo["y1"] - y),
                            _pt_seg(x, y, it.geo["x0"], it.geo["y0"], it.geo["x1"], it.geo["y1"]))
                    if best is None or d < best[0]:
                        best = (d, it)
            if not best or best[0] > 0.2:
                continue
            it = best[1]
            L = it.layers[0]; g = it.geo
            same = [o for o in bd.items if o.net == net and o is not it and L in o.layers]
            ends = [(g["x0"], g["y0"]), (g["x1"], g["y1"])]
            free = [e for e in ends if not any(o.contains(e[0], e[1], L) for o in same)]
            if not free:
                continue
            if len(free) == 2:
                bd.board.Remove(it.ref); bd.items.remove(it); n += 1
                continue
            fe = free[0]
            oe = ends[1] if fe == ends[0] else ends[0]
            # where other copper of the net joins this track: trim the free end back to the nearest such point
            juncs = []
            for o in same:
                pts = [(o.geo["x0"], o.geo["y0"]), (o.geo["x1"], o.geo["y1"])] if o.kind == "track" else [(o.x, o.y)]
                for pt in pts:
                    if _pt_seg(pt[0], pt[1], g["x0"], g["y0"], g["x1"], g["y1"]) <= g["hw"] + 0.01:
                        juncs.append((math.hypot(pt[0] - fe[0], pt[1] - fe[1]), pt))
            juncs.sort()
            if not juncs or math.hypot(juncs[0][1][0] - oe[0], juncs[0][1][1] - oe[1]) < 0.03:
                bd.board.Remove(it.ref); bd.items.remove(it); n += 1
                continue
            j = juncs[0][1]
            if fe == ends[0]:
                g["x0"], g["y0"] = j; it.ref.SetStart(pcbnew.VECTOR2I(MM(j[0]), MM(j[1])))
            else:
                g["x1"], g["y1"] = j; it.ref.SetEnd(pcbnew.VECTOR2I(MM(j[0]), MM(j[1])))
            it.x, it.y = g["x0"], g["y0"]
            n += 1
        if n:
            bd.rebuild_soft()
        return n

    def repair(self, todo):
        """todo: [(net name, (xa, ya), (xb, yb))] from KiCad's unconnected list (after the zone
        fill): join the two pieces with copper."""
        bd = self.bd
        done = 0
        for name, a, b in todo:
            net = bd.codes.get(name)
            if net is None:
                continue
            comps = bd.components(net)
            def comp_at(pt):
                best = None
                for c in comps:
                    for it in c:
                        px, py = it.nearest(pt[0], pt[1])
                        d = math.hypot(px - pt[0], py - pt[1])
                        if best is None or d < best[0]:
                            best = (d, c)
                return best[1] if best else None
            ca, cb = comp_at(a), comp_at(b)
            if ca is None or cb is None or ca is cb:
                self.log(f"  repair {name}: nothing to join at {a} / {b}")
                continue
            w, rk, vc = net_class(name)
            self.requeue = []
            self.ripped_by.pop(net, None)             # a fresh start for this net
            if self.connect(net, name, ca, cb, w, rk, vc, True, False):
                done += 1
            else:
                self.log(f"  repair {name}: no path between {a} and {b}")
            queue, k = list(self.requeue), 0          # whatever had to make way is routed again
            self.requeue = []
            while queue and k < 40:
                v = queue.pop(0); k += 1
                self.route_net(v, allow_rip=True, **dict(self.mode.get(v, {})))
                queue += [c for c in self.requeue if c not in queue]
                self.requeue = []
        return done

    def drop_unused_vias(self):
        """Signal-net vias with copper on only one layer (an escape that carried on on the same layer)."""
        bd = self.bd
        n = 0
        whole = {}
        for it in list(bd.items):
            if it.kind != "via" or bd.names[it.net] in PLANE_NETS:
                continue
            if it.net not in whole:
                whole[it.net] = len(bd.components(it.net)) == 1
            if not whole[it.net]:
                continue
            touch = {F: False, B: False}
            for o in bd.items:
                if o is it or o.net != it.net or o.kind == "via":
                    continue
                for L in o.layers:
                    if o.kind == "track":
                        if _pt_seg(it.x, it.y, o.geo["x0"], o.geo["y0"], o.geo["x1"], o.geo["y1"]) <= o.geo["hw"] + 0.01:
                            touch[L] = True
                    elif o.contains(it.x, it.y, L):
                        touch[L] = True
            if not (touch[F] and touch[B]):
                bd.board.Remove(it.ref); bd.items.remove(it); n += 1
        if n:
            bd.rebuild_soft()
        return n

    # ---- local power links ----
    def exact_clear(self, L, pts, w, net, clr):
        """True if a track of width w along the polyline pts on layer L keeps clr from all
        copper of other nets (exact geometry, sampled every 20 um) and from the board edge."""
        bd = self.bd; R = bd.R
        need = w / 2 + clr + 0.002
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            ln = math.hypot(bx - ax, by - ay)
            n = max(1, int(ln / 0.02))
            samples = [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n + 1)]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            for (x, y) in samples[::5] + [samples[-1]]:
                cx, cy = R.cell(x, y)
                if not (0 <= cx < R.W and 0 <= cy < R.H) or R.own["p"][L][R.idx(cx, cy)] == -1 and \
                        min(x - R.xmin, R.xmax - x, y - R.ymin, R.ymax - y) < EDGE + w / 2:
                    return False
            for it in bd.items:
                if it.net == net or L not in it.layers:
                    continue
                (ix, iy), reach = it.centre_reach()
                if math.hypot(ix - mx, iy - my) > ln / 2 + reach + need:
                    continue
                for (x, y) in samples:
                    if it.dist(x, y) < need:
                        return False
        return True

    def fatten(self, items, widths=(0.6, 0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15)):
        """Make each of these tracks as wide as its surroundings allow. Returns the widest result."""
        bd = self.bd
        best = 0.0
        for it in list(items):
            if it.kind != "track":
                continue
            g = it.geo
            cur = 2 * g["hw"]
            for w in widths:
                if w <= cur + 1e-6:
                    break
                if self.exact_clear(it.layers[0], [(g["x0"], g["y0"]), (g["x1"], g["y1"])], w, it.net, 0.15):
                    it.ref.SetWidth(MM(w)); g["hw"] = w / 2
                    bd.R.segment(it.layers, g["x0"], g["y0"], g["x1"], g["y1"], w / 2, it.net, soft=True)
                    cur = w
                    break
            best = max(best, cur)
        return best

    @staticmethod
    def link_shapes(a, b):
        """Polylines from a to b: straight, the two 45-degree doglegs, the two right-angle ones."""
        (ax, ay), (bx, by) = a, b
        dx, dy = bx - ax, by - ay
        out = [[a, b]]
        if abs(dx) > 1e-6 and abs(dy) > 1e-6:
            sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
            d = min(abs(dx), abs(dy))
            if abs(dx) > abs(dy):
                out.append([a, (ax + sx * (abs(dx) - d), ay), b])
                out.append([a, (ax + sx * d, by), b])
            elif abs(dy) > abs(dx):
                out.append([a, (ax, ay + sy * (abs(dy) - d)), b])
                out.append([a, (bx, ay + sy * d), b])
            out.append([a, (bx, ay), b])
            out.append([a, (ax, by), b])
        return out

    def direct_link(self, a, b, L, clr=0.15):
        """Join pads a and b on layer L with the fattest straight or dog-leg track that clears
        everything else; where a pad is narrow the track necks down to the pad's width for the
        first 0.6 mm. Returns the width laid (0 if nothing fits)."""
        bd = self.bd
        def minw(it):
            return 2 * min(it.geo["hx"], it.geo["hy"])
        wa, wb = minw(a), minw(b)
        if wa > wb:                                   # a = the narrow pad
            a, b, wa, wb = b, a, wb, wa
        for pts in self.link_shapes((a.x, a.y), (b.x, b.y)):
            total = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(pts, pts[1:]))
            # neck: from pad a to 0.6 mm beyond its edge along the first leg
            (px, py), (qx, qy) = pts[0], pts[1]
            l0 = math.hypot(qx - px, qy - py)
            ux, uy = (qx - px) / l0, (qy - py) / l0
            ext = a.geo["hx"] if abs(ux) > abs(uy) else a.geo["hy"]
            if abs(((a.geo["ang"] + 45) % 180) - 45) > 1:
                ext = a.geo["hy"] if abs(ux) > abs(uy) else a.geo["hx"]
            neck = min(ext + 0.6, l0)
            for wn in [w for w in (0.5, 0.4, 0.3, 0.25, 0.2, 0.15) if w <= wa + 1e-6] or [min(wa, 0.15)]:
                first = [pts[0], (px + ux * neck, py + uy * neck)]
                if not self.exact_clear(L, first, wn, a.net, clr):
                    continue
                rest = [first[1]] + pts[1:] if neck < l0 - 1e-6 else pts[1:]
                if len(rest) < 2:
                    bd.add_track(L, first[0][0], first[0][1], first[1][0], first[1][1], wn, a.net); self.stats["tracks"] += 1
                    return wn
                for ww in [w for w in (0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15) if wn - 1e-6 <= w <= max(wb, wn) + 1e-6]:
                    if self.exact_clear(L, rest, ww, a.net, clr):
                        bd.add_track(L, first[0][0], first[0][1], first[1][0], first[1][1], wn, a.net); self.stats["tracks"] += 1
                        for p, q in zip(rest, rest[1:]):
                            bd.add_track(L, p[0], p[1], q[0], q[1], ww, a.net); self.stats["tracks"] += 1
                        return ww
        return 0

    def local_links(self, max_d=3.6):
        """Direct same-layer copper between the parts of each supply: every regulator or
        transceiver pin on a supply/ground net to the nearest capacitor or inductor pad of that
        net, the switch nodes to their inductors, each inductor's output to the nearest
        capacitor. Fat exact-geometry links first, the grid search where those do not fit."""
        bd = self.bd
        pads = [it for it in bd.items if it.kind == "pad" and it.net > 0]
        by_net = {}
        for it in pads:
            by_net.setdefault(it.net, []).append(it)
        ref = lambda it: it.name.split(".")[0]
        links = []
        for it in pads:
            name = bd.names[it.net]
            r = ref(it)
            if r == "U1":
                continue
            if name.startswith("SW_"):
                if r.startswith("U"):
                    for o in by_net[it.net]:
                        if ref(o).startswith("L") and set(o.layers) & set(it.layers):
                            links.append((name, it, o, math.hypot(o.x - it.x, o.y - it.y)))
                continue
            if name not in PLANE_NETS or not (r.startswith("U") or r.startswith("L")):
                continue
            kinds = "CL" if r.startswith("U") else "C"
            cands = [o for o in by_net[it.net] if ref(o)[0] in kinds and set(o.layers) & set(it.layers) and o is not it]
            if not cands:
                continue
            o = min(cands, key=lambda o: math.hypot(o.x - it.x, o.y - it.y))
            d = math.hypot(o.x - it.x, o.y - it.y)
            if d > max_d or (name == "GND" and d > 2.4):
                continue
            links.append((name, it, o, d))
        links.sort(key=lambda l: l[3])
        done, report = 0, []
        for name, a, b, d in links:
            L = a.layers[0] if len(a.layers) == 1 else (b.layers[0] if len(b.layers) == 1 else F)
            w = self.direct_link(a, b, L)
            if w:
                done += 1; report.append(f"{a.name}-{b.name} {name} {w:.2f}")
                continue
            src = [c for c in a.cells(bd.R, 0.03) if c[0] == L]
            tgt = [c for c in b.cells(bd.R, 0.03) if c[0] == L]
            if not src or not tgt:
                continue
            width = 0.3
            path, _ = search(bd, [a.net], "p", src, tgt, 10 ** 6, width, heur_pts=[bd.R.cell(b.x, b.y)], max_expand=40000)
            if path is None:
                width = 0.1
                path, _ = search(bd, [a.net], "q", src, tgt, 10 ** 6, width, heur_pts=[bd.R.cell(b.x, b.y)], max_expand=40000)
            if path is None or any(p[0] != L for p in path):
                self.log(f"    no direct link {a.name} -> {b.name} ({name})")
                continue
            n0 = len(bd.items)
            self.lay(path, a.net, width, comp_from=[a], comp_to=[b])
            wmax = self.fatten(bd.items[n0:])
            done += 1; report.append(f"{a.name}-{b.name} {name} {max(width, wmax):.2f} (grid)")
        self.log("    " + "; ".join(report))
        return done

    # ---- the whole job ----
    def run(self):
        bd = self.bd
        self.requeue = []
        names = bd.names
        # 1. PCIe pairs: receive pairs and REFCLK first (straight runs), then transmit, lane 0 first
        specs = self.pair_specs()
        def prio(sp):
            label = sp[0]
            return (3 if label.endswith("_C") else (0 if "RX" in label else (2 if "REFCLK" in label else 1)), label)
        self.log("PCIe pairs:")
        self.no_rip = {bd.R.alias.get(c, c) for _, pn, nn in specs for c in (pn, nn)}
        order = sorted(specs, key=prio)
        first = [sp for sp in order if sp[0].endswith("_C") or "RX" in sp[0]]      # short and straight, on F.Cu
        rest = [sp for sp in order if sp not in first]                              # REFCLK and the transmit pairs
        for sp in first:
            if not self.route_pair(*sp):
                self.log(f"  {sp[0]}: FAILED")
        # the other nets that leave the package between the receive pairs (CCLK, TCK, MGTRREF ...)
        # go next, along the package edge, before REFCLK and the transmit pairs shut them in
        u1 = next(fp for fp in bd.board.GetFootprints() if fp.GetReference() == "U1")
        bb = u1.GetBoundingBox(False, False) if hasattr(u1, "GetBoundingBox") else None
        ymax = max(to_mm(p.GetPosition().y) for p in u1.Pads())
        pv = [(it.x, it.y) for it in bd.items if it.kind == "via" and PAIR_RE.match(bd.names[it.net])]
        early = []
        for code, name in names.items():
            if code == 0 or name in PLANE_NETS or bd.R.alias.get(code, code) in self.no_rip:
                continue
            if any(it.kind == "via" and it.net == code and any(math.hypot(it.x - x, it.y - y) < 1.0 for x, y in pv) for it in bd.items):
                early.append(code)
        for code in early:
            ok = self.route_net(code, allow_rip=False)
            self.log(f"  {names[code]} (leaves between the pairs): {'ok' if ok else 'FAILED'}")
        base = [it for it in bd.items if getattr(it, "soft", False)]
        for attempt in range(8):
            bad = None
            for label, netP, netN in rest:
                if not self.route_pair(label, netP, netN):
                    bad = (label, netP, netN); break
            if bad is None or attempt == 7:
                break
            # start again with the pair that found no way put first
            self.log(f"  attempt {attempt + 1}: {bad[0]} failed, retrying with it first")
            for _, pn, nn in rest:
                bd.rip(pn); bd.rip(nn)
            bd.rebuild_soft()
            self.failed = [f for f in self.failed if not any(f[0] == sp[0] for sp in rest)]
            rest = [bad] + [sp for sp in rest if sp is not bad]
        for label, netP, netN in first + rest:
            lp, ln, nb = self.tune_pair(label.replace("_C", ""), only=(netP, netN))
            self.log(f"  {label}: P {lp:.2f} / N {ln:.2f} mm, {nb} bumps")
        # 2. plane nets: everything not yet on its plane
        self.log("plane-net stragglers:")
        for name in sorted(PLANE_NETS, key=lambda n: (n != "MGTAVCC", n != "MGTAVTT", n)):
            net = bd.codes.get(name)
            if net is None:
                continue
            w = 0.3
            ok = self.route_net(net, width=w, rkey="p", via_cost=120, plane=True, allow_rip=False)
            self.log(f"  {name}: {'ok' if ok else 'INCOMPLETE'}")
        # 3. local power links
        n = self.local_links()
        self.log(f"local power links: {n}")
        # 4. signal nets, short first
        sig = []
        pair_nets = {c for _, p, n in specs for c in (p, n)}
        for code, name in names.items():
            if code == 0 or name in PLANE_NETS or code in pair_nets or code in early:
                continue
            comps = bd.components(code)
            if len(comps) <= 1:
                continue
            xs = [it.x for c in comps for it in c]; ys = [it.y for c in comps for it in c]
            sig.append(((max(xs) - min(xs)) + (max(ys) - min(ys)), code, name))
        sig.sort()
        self.log(f"signal nets: {len(sig)}")
        queue = [code for _, code, _ in sig]
        passes = 0
        while queue and passes < 12:
            passes += 1
            nxt = []
            for code in queue:
                kw = dict(self.mode.get(code, {}))
                ok = self.route_net(code, allow_rip=(passes >= 2), **kw)
                if not ok:
                    nxt.append(code)
                if self.requeue:
                    nxt += [c for c in self.requeue if c not in nxt]
                    self.requeue = []
            queue = nxt
            if queue:
                self.log(f"  pass {passes}: {len(queue)} nets to retry: {[names[c] for c in queue]}")
                # the failed list is rebuilt on the next pass
                self.failed = [f for f in self.failed if bd.codes.get(f[0]) not in queue]
        # 5. escape end vias the route did not use for a layer change come out again
        n, m = self.cleanup()
        self.log(f"unused escape vias removed: {n}, dangling stubs: {m}")
        # 6. length matching inside each pair
        rep = self.tune_pairs()
        self.log("pair lengths (P / N mm, bumps added):")
        for lane, (lp, ln, nb) in rep.items():
            self.log(f"  {lane:12s} {lp:6.2f} / {ln:6.2f}  mismatch {abs(lp - ln):.2f}  bumps {nb}")
        return self.stats


def _collinear(a, b, c):
    """Cells a, b, c (layer, cx, cy) on one straight line, c continuing a -> b."""
    return (b[1] - a[1]) * (c[2] - b[2]) == (b[2] - a[2]) * (c[1] - b[1]) and \
        ((c[1] - b[1]) * (b[1] - a[1]) >= 0 and (c[2] - b[2]) * (b[2] - a[2]) >= 0)


def _dedupe(poly):
    out = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def _pt_seg(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return math.hypot(x - x0, y - y0)
    t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


def offset_polyline(poly, off):
    """Parallel polyline at signed distance `off` (left of travel for positive off)."""
    if len(poly) < 2:
        return list(poly)
    segs = []
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        l = math.hypot(dx, dy)
        if l == 0:
            continue
        nx, ny = -dy / l, dx / l
        segs.append(((ax + nx * off, ay + ny * off), (bx + nx * off, by + ny * off), (dx / l, dy / l)))
    if not segs:
        return list(poly)
    out = [segs[0][0]]
    for s1, s2 in zip(segs, segs[1:]):
        p = _intersect(s1[0], s1[2], s2[0], s2[2])
        out.append(p if p else s1[1])
    out.append(segs[-1][1])
    return out


def _intersect(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + d[0] * t, p[1] + d[1] * t)


def route(board, log=print):
    """Route everything; returns the Router (keeps what it laid, for the repair passes)."""
    r = Router(board, log)
    r.run()
    return r
