"""Autorouting round-trip through Freerouting using KiCad's Specctra export/import.

    python3 gen/route.py prepare       # fan-out vias for the BGA and plane nets, fill, write build/artix_m2_canfd.dsn
    python3 gen/route.py import        # reads build/artix_m2_canfd.ses into the board, refills zones, saves
                                       #   artix_m2_canfd.kicad_pcb (routed) and keeps the unrouted file
                                       #   as artix_m2_canfd_unrouted.kicad_pcb

Run Freerouting in between, e.g. with the container:
    docker run --rm -v "$PWD/build:/work" freerouting/freerouting \\
        -de /work/artix_m2_canfd.dsn -do /work/artix_m2_canfd.ses -mp 200
or the jar:  java -jar freerouting.jar -de build/artix_m2_canfd.dsn -do build/artix_m2_canfd.ses -mp 200
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
    print(f"BGA escapes: {esc['F']} on F.Cu, {esc['B']} via B.Cu; not escaped: {esc['left']}")
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

if __name__ == "__main__":
    {"export": export, "import": do_import, "prepare": prepare}[sys.argv[1]]()
