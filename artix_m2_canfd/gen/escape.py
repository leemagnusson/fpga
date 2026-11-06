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
        if name == "MGTRREF":                               # placed after the pairs (see below)
            pass
        elif ring_r == 1:                                   # straight out along the column line
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

    def build_items(c, r, pad, k, g, path, hit, node_net, edge_net):
        """Via in cell (k, g), F.Cu stub from the ball, B.Cu run along `path`; marks the grid."""
        net = pad.GetNetCode()
        px, py = X(c), Y(r)
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
        return items

    def cell_ok(c, r, net, k, g):
        """Via cell (k, g) usable for ball (c, r): free spot and a clean F.Cu stub."""
        vx, vy = gap_x(k), gap_y(g)
        if occ.why_blocked(vx, vy, net):
            return False
        return occ.segment_free(X(c), Y(r), vx, vy, net, W, "F")

    def plan(order, node_net0=None, edge_net0=None):
        """Returns (actions, failed); leaves occ extended by the planned items."""
        node_net = dict(node_net0 or {}); edge_net = dict(edge_net0 or {})
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
            items = build_items(c, r, pad, k, g, path, hit, node_net, edge_net)
            occupy(items); planned += items
        return planned, failed

    # ---- differential pairs: both halves leave on the same side on adjacent lines ----
    # Depth-first search over the pairs (deepest first): for each pair try every
    # pair of adjacent exit nodes (south column lines first, then east/west row
    # lines two rows apart, i.e. either side of a TX pair) and every via cell of
    # each half, route both halves on the grid, and backtrack when a later pair
    # cannot be placed. REFCLK goes last and may fall back to the general planner.
    def pair_key(name):
        m = re.match(r"(PCIE_(?:RX\d|REFCLK))_([PN])$", name)
        return (m.group(1), m.group(2)) if m else None

    def exit_pairs():
        s_r = 0 if south_is_r0 else 19
        e_c = 0 if east_is_c0 else 19
        w_c = 19 - e_c
        out = []
        for c in range(1, 18):                                    # south, adjacent column lines
            out.append((0, (c, s_r), (c + 1, s_r))); out.append((0, (c + 1, s_r), (c, s_r)))
        for r in range(1, 17):                                    # east/west row lines, 2 apart (a TX pair between)
            for cc in (e_c, w_c):
                out.append((1, (cc, r), (cc, r + 2))); out.append((1, (cc, r + 2), (cc, r)))
        for r in range(1, 18):                                    # adjacent row lines (west side has no TX ladder)
            for cc in (e_c, w_c):
                out.append((2, (cc, r), (cc, r + 1))); out.append((2, (cc, r + 1), (cc, r)))
        return out

    def plan_pairs(pair_list, node_net, edge_net, others):
        """Returns the list of items or None. Mutates node_net/edge_net and occ on success.
        At the leaves the other signal balls of the corner (`others`) must still find
        an escape, otherwise the candidate is rejected and the search backtracks."""
        if not pair_list:
            n_i, n_s = len(occ.items), len(occ.segs)
            _, failed = plan(others, node_net, edge_net)
            del occ.items[n_i:]; del occ.segs[n_s:]
            return [] if not failed else None
        (ca, ra, pa), (cb, rb, pb) = pair_list[0]
        na, nb = pa.GetNetCode(), pb.GetNetCode()
        tried = []
        for rank, ea, eb in exit_pairs():
            if occ.why_blocked(X(ea[0]), Y(ea[1]), na) or occ.why_blocked(X(eb[0]), Y(eb[1]), nb):
                continue
            if ea in node_net or eb in node_net:
                continue
            best = None
            for ka in (ca - 1, ca):
                for ga in (ra - 1, ra):
                    if not cell_ok(ca, ra, na, ka, ga):
                        continue
                    corners_a = [n for n in ((ka, ga), (ka + 1, ga), (ka, ga + 1), (ka + 1, ga + 1))
                                 if node_net.get(n) is None and not side(n)]
                    path_a, _ = bfs(corners_a, na, lambda n: n == ea, node_net, edge_net)
                    if not path_a:
                        continue
                    nn, ee = dict(node_net), dict(edge_net)
                    items_a = build_items(ca, ra, pa, ka, ga, path_a, None, nn, ee)
                    n_i, n_s = len(occ.items), len(occ.segs)
                    occupy(items_a)
                    for kb in (cb - 1, cb):
                        for gb in (rb - 1, rb):
                            if not cell_ok(cb, rb, nb, kb, gb):
                                continue
                            corners_b = [n for n in ((kb, gb), (kb + 1, gb), (kb, gb + 1), (kb + 1, gb + 1))
                                         if nn.get(n) is None and not side(n)]
                            path_b, _ = bfs(corners_b, nb, lambda n: n == eb, nn, ee)
                            if not path_b:
                                continue
                            cost = (rank, len(path_a) + len(path_b))
                            if best is None or cost < best[0]:
                                best = (cost, ka, ga, path_a, kb, gb, path_b)
                    del occ.items[n_i:]; del occ.segs[n_s:]
            if best is None:
                continue
            tried.append(best)
        # try candidates best-first, recursing into the remaining pairs
        per_rank = {}
        for t in sorted(tried, key=lambda t: t[0]):
            per_rank.setdefault(t[0][0], []).append(t)
        shortlist = [t for rank in sorted(per_rank) for t in per_rank[rank][:6]]
        for cost, ka, ga, path_a, kb, gb, path_b in shortlist:
            nn, ee = dict(node_net), dict(edge_net)
            n_i, n_s = len(occ.items), len(occ.segs)
            items = build_items(ca, ra, pa, ka, ga, path_a, None, nn, ee)
            occupy(items)
            items_b = build_items(cb, rb, pb, kb, gb, path_b, None, nn, ee)
            occupy(items_b)
            # prune early: the other corner signals must still be able to leave
            m_i, m_s = len(occ.items), len(occ.segs)
            _, failed = plan(others, nn, ee)
            del occ.items[m_i:]; del occ.segs[m_s:]
            if failed:
                del occ.items[n_i:]; del occ.segs[n_s:]
                continue
            rest = plan_pairs(pair_list[1:], nn, ee, others)
            if rest is not None:
                node_net.clear(); node_net.update(nn); edge_net.clear(); edge_net.update(ee)
                return items + items_b + rest
            del occ.items[n_i:]; del occ.segs[n_s:]
        return None

    deep.sort(key=lambda t: (-dist_out(t[0], t[1], t[2].GetNetname()), t[2].GetNetname()))
    # plane balls that sit over another net's plane island: via, grid, via over their own plane
    for (c, r), pad in sorted(allp.items()):
        name = pad.GetNetname()
        if pad.GetNetCode() <= 0 or name not in plane_nets:
            continue
        if not any(plane_under(gap_x(k), gap_y(g), name) for k in (c - 1, c) for g in (r - 1, r)):
            deep.append((c, r, pad))
    pairs = {}
    for t in deep:
        k = pair_key(t[2].GetNetname())
        if k:
            pairs.setdefault(k[0], {})[k[1]] = t
    pair_list = [(v["P"], v["N"]) for name, v in pairs.items() if len(v) == 2 and name != "PCIE_REFCLK"]
    pair_list.sort(key=lambda ab: -dist_out(ab[0][0], ab[0][1], ab[0][2].GetNetname()))   # deepest first
    if "PCIE_REFCLK" in pairs and len(pairs["PCIE_REFCLK"]) == 2:
        pair_list.append((pairs["PCIE_REFCLK"]["P"], pairs["PCIE_REFCLK"]["N"]))
    node_net0, edge_net0 = {}, {}
    in_pairs = {(t[0], t[1]) for ab in pair_list for t in ab}
    cmax = 12 if east_is_c0 else 7; rmax = 10 if south_is_r0 else 9
    others = [t for t in deep if (t[0], t[1]) not in in_pairs and t[2].GetNetname() not in plane_nets
              and t[2].GetNetname() != "MGTRREF"
              and (t[0] <= cmax if east_is_c0 else t[0] >= cmax) and (t[1] <= rmax if south_is_r0 else t[1] >= rmax)]
    pair_items = plan_pairs(pair_list, node_net0, edge_net0, others)
    if pair_items is None and pair_list and pair_list[-1][0][2].GetNetname().startswith("PCIE_REFCLK"):
        others = others + list(pair_list[-1])                                   # REFCLK falls back to the planner,
        pair_items = plan_pairs(pair_list[:-1], node_net0, edge_net0, others)   # but must stay escapable
        pair_list = pair_list[:-1]
    if pair_items is None:
        pair_items = []; pair_list = []
    paired = {(t[0], t[1]) for ab in pair_list for t in ab}
    stats["pairs"] = [ab[0][2].GetNetname()[:-2] for ab in pair_list]
    actions += pair_items
    deep = [t for t in deep if (t[0], t[1]) not in paired]
    # MGTRREF (outer row, 100 ohm to ground): straight out if the pairs left its
    # line free, otherwise a diagonal into the free cell just outside the package
    # ending on a via; the router carries on from there between the pair lines.
    for t in list(deep):
        c, r, pad = t
        if pad.GetNetname() != "MGTRREF":
            continue
        net = pad.GetNetCode(); px, py = X(c), Y(r)
        out = 0 if r == 1 else 19
        cands = [[(px, py), (px, Y(out))]] + [[(px, py), (gap_x(k), gap_y(g))] for k in (c - 1, c) for g in ((0,) if out == 0 else (18,))]
        for pts in cands:
            ex, ey = pts[-1]
            if occ.why_blocked(ex, ey, net) is None and f_free(pts, net):
                items = [("track", pcbnew.F_Cu, "F", pts, net), ("via", ex, ey, net)]
                actions += items; occupy(items); stats["F"] += 1
                deep.remove(t)
                break
    n_items, n_segs = len(occ.items), len(occ.segs)
    best = None
    order = deep
    for attempt in range(8):
        planned, failed = plan(order, node_net0, edge_net0)
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
