"""Routing driver.

    python3 gen/route.py route         # fan-out (BGA escapes, plane vias), gen/router.py for everything else,
                                       #   planes filled, then KiCad's DRC in a loop until it is clean; saves
                                       #   artix_m2_canfd.kicad_pcb (the unrouted board is kept alongside)

The older Freerouting round trip is still here (prepare / import through a Specctra DSN/SES) but is no
longer used: it could not keep the PCIe pairs together or matched.
"""
import os, shutil, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PCB = os.path.join(ROOT, "artix_m2_canfd.kicad_pcb")
BUILD = os.path.join(ROOT, "build")
DSN = os.path.join(BUILD, "artix_m2_canfd.dsn")
SES = os.path.join(BUILD, "artix_m2_canfd.ses")

def fill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

def prepare():
    """Regenerated board -> fan-out vias -> filled planes -> DSN for the autorouter."""
    import fanout, pcb
    fanout.PLANES = pcb.PLANES
    os.makedirs(BUILD, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    added, skipped, esc = fanout.fanout(board)
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    print(f"BGA escapes: {esc['F']} on F.Cu, {esc['B']} via B.Cu; pairs kept together: {esc.get('pairs')}; not escaped: {esc['left']}")
    print(f"fan-out: {added} vias added; {len(skipped)} pads without a free spot: {skipped[:12]}")
    shutil.copy(PCB, os.path.join(ROOT, "artix_m2_canfd_unrouted.kicad_pcb"))
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        raise SystemExit("DSN export failed")
    print("wrote", DSN)

def export():
    os.makedirs(BUILD, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    fill(board)
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        raise SystemExit("DSN export failed")
    print("wrote", DSN, os.path.getsize(DSN), "bytes")

def do_import():
    board = pcbnew.LoadBoard(PCB)
    unrouted = os.path.join(ROOT, "artix_m2_canfd_unrouted.kicad_pcb")
    if not os.path.exists(unrouted):
        shutil.copy(PCB, unrouted)
    if not pcbnew.ImportSpecctraSES(board, SES):
        raise SystemExit("SES import failed")
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    tracks = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_TRACK")
    vias = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    print(f"imported: {tracks} track segments, {vias} vias; saved {PCB}")

def do_route():
    """Regenerated board -> fan-out -> gen/router.py for everything else -> filled, saved."""
    import fanout, pcb, router
    fanout.PLANES = pcb.PLANES
    os.makedirs(BUILD, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    added, skipped, esc = fanout.fanout(board)
    print(f"BGA escapes: {esc['F']} on F.Cu, {esc['B']} via B.Cu; pairs kept together: {esc.get('pairs')}; not escaped: {esc['left']}")
    print(f"fan-out: {added} vias added; {len(skipped)} pads left for the router: {[s.split('[')[0] for s in skipped]}")
    shutil.copy(PCB, os.path.join(ROOT, "artix_m2_canfd_unrouted.kicad_pcb"))
    r = router.route(board)
    stats = r.stats
    # KiCad's own DRC is the judge: fill the planes, save, run it, and let the router mend what it
    # reports: pieces the fill did not reach (a via in a crowded spot, a pad over no plane) are joined
    # with copper, and a track a few microns too close to a round obstacle is moved
    for attempt in range(8):
        fill(board)
        pcbnew.SaveBoard(PCB, board)
        todo, zones, viol, stubs = drc()
        print(f"DRC pass {attempt + 1}: {len(todo)} unconnected {sorted(set(t[0] for t in todo))}, {len(viol)} violations "
              f"{sorted(set(v[0] for v in viol))}, {len(stubs)} dangling" + (f", plane fragments {zones}" if zones else ""))
        if not todo and not viol:
            if not stubs or not r.remove_stubs(stubs):
                break
            r.cleanup()
            continue
        if viol:
            r.fix_violations(viol)
        if todo:
            r.repair(todo)
        r.drop_duplicates()
    print(f"routed: {r.stats['tracks']} track segments, {r.stats['vias']} vias, {r.stats['ripped']} rip-ups; saved {PCB}")
    if r.failed:
        print("NOT ROUTED:", r.failed)

def drc():
    """(unconnected [(net, (xa, ya), (xb, yb))], zone-to-zone entries, violations [(type, [nets], (x, y))])
    from kicad-cli's DRC of the saved board. Warnings about silkscreen and the like are left out."""
    import json, re, subprocess, tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="drc_"), "drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", out, PCB],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rep = json.load(open(out))
    net = lambda d: (re.search(r"\[([^\]]+)\]", d) or [None, ""])[1]
    todo, zones, viol, stubs = [], [], [], []
    for u in rep.get("unconnected_items", []):
        its = u["items"]
        if len(its) < 2 or not net(its[0]["description"]):
            continue
        if all(i["description"].startswith("Zone") for i in its):
            zones.append((net(its[0]["description"]), its[0]["pos"]["x"], its[0]["pos"]["y"]))
            continue
        todo.append((net(its[0]["description"]), (its[0]["pos"]["x"], its[0]["pos"]["y"]), (its[1]["pos"]["x"], its[1]["pos"]["y"])))
    for v in rep.get("violations", []):
        if v["type"] in ("clearance", "hole_clearance", "shorting_items", "tracks_crossing", "hole_to_hole", "copper_edge_clearance"):
            pos = v.get("pos") or v["items"][0]["pos"]
            viol.append((v["type"], [net(i["description"]) for i in v["items"]], (pos["x"], pos["y"])))
        elif v["type"] == "track_dangling":
            pos = v.get("pos") or v["items"][0]["pos"]
            m = re.search(r"length ([0-9.]+) mm", v["items"][0]["description"])
            stubs.append((net(v["items"][0]["description"]), (pos["x"], pos["y"]), float(m.group(1)) if m else 0.0))
    return todo, zones, viol, stubs

if __name__ == "__main__":
    {"export": export, "import": do_import, "prepare": prepare, "route": do_route}[sys.argv[1]]()
