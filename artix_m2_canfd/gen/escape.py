"""Deterministic escape routing for the BGA (U1, CSG325: 18x18 balls, 0.8 mm pitch).

The autorouter cannot get signals out of the ball field once the plane vias are
in, so every used signal ball is taken to a point one pitch outside the package
before Freerouting runs:

  * ring 1 (outer row/column): straight out on F.Cu along its own row/column line;
  * ring 2 (second column): a short diagonal into the free row gap next to it and
    out along that gap on F.Cu (plane vias only ever sit in the other row gaps);
  * anything deeper: a dog-bone via into an adjacent cell, then a Manhattan path
    on B.Cu along the pad-row/pad-column lines, which pass every via at exactly
    0.4 mm (0.15 mm clearance to a 0.4 mm via with a 0.1 mm track).

Grid lines and nodes are single-net resources; vias of any net may sit at any
cell centre without disturbing the grid, so the plane fan-out that follows is
unconstrained by the escapes (it just has to avoid the cells the tracks pass
through, which the occupancy model enforces). Deep escapes are planned with
retries (failed balls go first) before anything is committed to the board."""
import re
from collections import deque
import pcbnew

ROWS = "ABCDEFGHJKLMNPRTUV"
W = 0.1                                   # escape track width

def _is_pcie(name):
    return name.startswith("PCIE_RX") or name.startswith("PCIE_REFCLK")

def escape_bga(board, fp, occ, plane_nets):
    from fanout import add_via, add_track, plane_under
    allp, sig = {}, {}
    for pad in fp.Pads():
        m = re.match(r"([A-Z])(\d+)$", pad.GetName())
        if not m:
            continue
        key = (int(m.group(2)), ROWS.index(m.group(1)) + 1)
        allp[key] = pad
        if pad.GetNetCode() > 0 and pad.GetNetname() not in plane_nets:
            sig[key] = pad
    p1 = allp[(1, 1)].GetPosition(); p18 = allp[(18, 18)].GetPosition()
    x1, y1 = pcbnew.ToMM(p1.x), pcbnew.ToMM(p1.y)
    dx = (pcbnew.ToMM(p18.x) - x1) / 17; dy = (pcbnew.ToMM(p18.y) - y1) / 17
    X = lambda c: round(x1 + (c - 1) * dx, 4)       # c, r in 0..19; 0 and 19 are one pitch outside
    Y = lambda r: round(y1 + (r - 1) * dy, 4)
    east_is_c0 = X(0) > X(19)
    south_is_r0 = Y(0) > Y(19)
    xmid = (X(1) + X(18)) / 2

    def side(n):
        c, r = n
        if c == 0:  return "E" if east_is_c0 else "W"
        if c == 19: return "W" if east_is_c0 else "E"
        if r == 0:  return "S" if south_is_r0 else "N"
        if r == 19: return "N" if south_is_r0 else "S"
        return None

    def lane_gap(r):            # the row gap next to row r that never holds plane vias
        return r if r % 2 == 0 else r - 1          # gap g lies between rows g and g+1
    gap_y = lambda g: round((Y(g) + Y(g + 1)) / 2, 4)
    gap_x = lambda k: round((X(k) + X(k + 1)) / 2, 4)

    actions = []            # ("via", x, y, net) / ("track", layer, ltag, pts, net)

    def occupy(items):
        for a in items:
            if a[0] == "via":
                occ.add(a[1], a[2], a[3])
            else:
                for (ax, ay), (bx, by) in zip(a[3], a[3][1:]):
                    occ.add_seg(ax, ay, bx, by, W, a[4], a[2])

    def f_free(pts, net):
        return all(occ.segment_free(ax, ay, bx, by, net, W, "F") for (ax, ay), (bx, by) in zip(pts, pts[1:]))

    stats = {"F": 0, "B": 0, "left": []}
    lanes = {}
    deep = []
    # Every escape ends on a via: Freerouting loops forever in its trace normalisation
    # when it starts a route from a bare trace end. Second-ring escapes stop 0.6 mm
    # further out so their end vias clear the first-ring ones (0.4 mm apart otherwise).
    sx_out = lambda out: 1.0 if X(out) > xmid else -1.0
    sy_out = lambda out: 1.0 if Y(out) > (Y(1) + Y(18)) / 2 else -1.0
    for (c, r), pad in sorted(sig.items()):
        net, name = pad.GetNetCode(), pad.GetNetname()
        ring_c, ring_r = min(c, 19 - c), min(r, 19 - r)
        px, py = X(c), Y(r)
        pts = None
        if ring_r == 1:                                     # straight out along the column line
            out = 0 if r == 1 else 19
            pts = [(px, py), (px, Y(out))]
            step = (0.0, 0.4 * sy_out(out))
        elif ring_c == 1:                                   # straight out along the row line
            out = 0 if c == 1 else 19
            pts = [(px, py), (X(out), py)]
            step = (0.4 * sx_out(out), 0.0)
        elif ring_c == 2:                                   # along the free row gap, F.Cu
            g = lane_gap(r); out = 0 if c == 2 else 19
            k = 1 if c == 2 else 17                         # cell column between this ball and the outer one
            if (g, out) not in lanes:
                pts = [(px, py), (gap_x(k), gap_y(g)), (X(out) + 0.6 * sx_out(out), gap_y(g))]
                step = (0.4 * sx_out(out), 0.0)
        placed = False
        if pts:
            for n_ext in range(3):                          # push the end out if the via spot is taken
                ex, ey = pts[-1][0] + n_ext * step[0], pts[-1][1] + n_ext * step[1]
                cand = pts[:-1] + [(round(ex, 4), round(ey, 4))]
                if occ.why_blocked(ex, ey, net) is None and f_free(cand, net):
                    items = [("track", pcbnew.F_Cu, "F", cand, net), ("via", round(ex, 4), round(ey, 4), net)]
                    actions += items; occupy(items); stats["F"] += 1; placed = True
                    if ring_c == 2:
                        lanes[(g, out)] = net
                    break
        if not placed:
            deep.append((c, r, pad))

    # ---- deep balls: via + Manhattan path on B.Cu, planned with retries ----
    def sides_for(c, name):
        near = "E" if (X(c) > xmid) == east_is_c0 else "W"
        if _is_pcie(name):
            return [{"S", "E"}, {"S", "E", "W"}, {"S", "E", "W", "N"}]
        return [{"N", near}, {"N", "E", "W"}, {"N", "E", "W", "S"}]

    def dist_out(c, r, name):
        if _is_pcie(name):
            return min(r if south_is_r0 else 19 - r, c if east_is_c0 else 19 - c)
        return min(19 - r if south_is_r0 else r, c, 19 - c)

    ball_net = {key: pad.GetNetCode() for key, pad in allp.items() if pad.GetNetCode() > 0}

    def bfs(sources, net, ok, node_net, edge_net, at_side=True):
        """Shortest grid path from any source to a node accepted by ok(). Signals end on
        the boundary ring (at_side); plane balls may end on any interior node. Nodes
        under a ball of the same net are avoided: Freerouting takes a bottom-layer
        corner under a same-net pad as a zero-length connection and crashes on it."""
        sources = [s for s in sources if ball_net.get(s) != net]
        prev = {s: None for s in sources}
        dq = deque(sources)
        while dq:
            n = dq.popleft()
            if at_side == bool(side(n)):
                hit = ok(n)
                if hit:
                    path = []
                    while n is not None:
                        path.append(n); n = prev[n]
                    return path[::-1], hit
            if side(n):
                continue
            c, r = n
            for nb in ((c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)):
                if not (0 <= nb[0] <= 19 and 0 <= nb[1] <= 19) or nb in prev:
                    continue
                # grid nodes and edges are exclusive even within a net: two same-net runs
                # sharing a line would overlap, and Freerouting's trace normalisation loops forever on that
                if nb in node_net or frozenset((n, nb)) in edge_net:
                    continue
                if ball_net.get(nb) == net:
                    continue
                if side(nb):     # the escape ends on a via there: the spot must be free on all layers
                    if not at_side or occ.why_blocked(X(nb[0]), Y(nb[1]), net):
                        continue
                prev[nb] = n; dq.append(nb)
        return None, None

    def plan(order):
        """Returns (actions, failed); leaves occ extended by the planned items."""
        node_net, edge_net = {}, {}
        planned, failed = [], []
        def plane_cell(n, net, name, avoid):
            """A free cell next to node n whose centre lies over the net's plane."""
            for k in (n[0] - 1, n[0]):
                for g in (n[1] - 1, n[1]):
                    if (k, g) == avoid or not (0 <= k <= 18 and 0 <= g <= 18):
                        continue
                    vx, vy = gap_x(k), gap_y(g)
                    if plane_under(vx, vy, name) and occ.why_blocked(vx, vy, net) is None \
                            and occ.segment_free(X(n[0]), Y(n[1]), vx, vy, net, W, "B"):
                        return (k, g)
            return None
        for c, r, pad in order:
            net, name = pad.GetNetCode(), pad.GetNetname()
            to_plane = name in plane_nets
            px, py = X(c), Y(r)
            best = None
            why = []
            for k in (c - 1, c):
                for g in (r - 1, r):
                    vx, vy = gap_x(k), gap_y(g)
                    w = occ.why_blocked(vx, vy, net)
                    if w is None and not occ.segment_free(px, py, vx, vy, net, W, "F"):
                        w = "stub crosses"
                    if w:
                        why.append(f"cell({k},{g}): {w}"); continue
                    corners = [n for n in ((k, g), (k + 1, g), (k, g + 1), (k + 1, g + 1))
                               if node_net.get(n) is None and not side(n)]
                    if to_plane:
                        path, hit = bfs(corners, net, lambda n: plane_cell(n, net, name, (k, g)),
                                        node_net, edge_net, at_side=False)
                        if path:
                            cost = (0, len(path), 0)
                            if best is None or cost < best[0]:
                                best = (cost, k, g, path, hit)
                        else:
                            why.append(f"cell({k},{g}): no path to a plane cell from {corners}")
                        continue
                    for rank, allowed in enumerate(sides_for(c, name)):
                        path, _ = bfs(corners, net, lambda n: side(n) in allowed, node_net, edge_net)
                        if path:
                            cost = (rank, len(path), g % 2 == 1)      # free lane cells are the tie-break
                            if best is None or cost < best[0]:
                                best = (cost, k, g, path, None)
                            break
                    else:
                        why.append(f"cell({k},{g}): no path from {corners}")
            if best is None:
                failed.append((c, r, pad, why)); continue
            _, k, g, path, hit = best
            vx, vy = gap_x(k), gap_y(g)
            items = [("via", vx, vy, net), ("track", pcbnew.F_Cu, "F", [(px, py), (vx, vy)], net)]
            pts = [(vx, vy), (X(path[0][0]), Y(path[0][1]))]
            node_net[path[0]] = net
            for a, b in zip(path, path[1:]):
                node_net[b] = net; edge_net[frozenset((a, b))] = net
                pts.append((X(b[0]), Y(b[1])))
            merged = [pts[0], pts[1]]
            for p in pts[2:]:
                (ax, ay), (bx, by) = merged[-2], merged[-1]
                if (ax == bx == p[0]) or (ay == by == p[1]):
                    merged[-1] = p
                else:
                    merged.append(p)
            if hit:                                   # plane ball: a second via over its plane
                hx, hy = gap_x(hit[0]), gap_y(hit[1])
                merged.append((hx, hy))
                items.append(("via", hx, hy, net))
            else:                                     # signal: end via outside the package
                items.append(("via", merged[-1][0], merged[-1][1], net))
            items.append(("track", pcbnew.B_Cu, "B", merged, net))
            occupy(items); planned += items
        return planned, failed

    deep.sort(key=lambda t: (-dist_out(t[0], t[1], t[2].GetNetname()), t[2].GetNetname()))
    # plane balls that sit over another net's plane island: via, grid, via over their own plane
    for (c, r), pad in sorted(allp.items()):
        name = pad.GetNetname()
        if pad.GetNetCode() <= 0 or name not in plane_nets:
            continue
        if not any(plane_under(gap_x(k), gap_y(g), name) for k in (c - 1, c) for g in (r - 1, r)):
            deep.append((c, r, pad))
    n_items, n_segs = len(occ.items), len(occ.segs)
    best = None
    order = deep
    for attempt in range(8):
        planned, failed = plan(order)
        del occ.items[n_items:]; del occ.segs[n_segs:]
        if best is None or len(failed) < len(best[1]):
            best = (planned, failed)
        if not failed:
            break
        front = [(c, r, pad) for c, r, pad, _ in failed]
        order = front + [t for t in order if t not in front]
    occupy(best[0])
    actions += best[0]
    stats["B"] = sum(1 for a in best[0] if a[0] == "track" and a[2] == "B")
    stats["vias"] = sum(1 for a in actions if a[0] == "via")
    stats["left"] = [f"{pad.GetName()}[{pad.GetNetname()}] {why}" for c, r, pad, why in best[1]]

    for a in actions:
        if a[0] == "via":
            add_via(board, a[1], a[2], a[3])
        else:
            _, layer, _, pts, net = a
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                add_track(board, ax, ay, bx, by, W, layer, net)
    return stats
