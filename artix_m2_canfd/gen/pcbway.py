"""Fabrication package for PCBWay, and the upload PCBWay's own KiCad plugin does.

    python3 gen/pcbway.py                 # write build/pcbway/<board>.zip (gerbers, drills, IPC-356 netlist,
                                          #   BOM, pick-and-place, fab notes) from artix_m2_canfd.kicad_pcb
    python3 gen/pcbway.py --upload        # ... and send it to PCBWay; prints the quote page URL to open
    python3 gen/pcbway.py --quote         # price and lead-time table for the PCB_SPEC options (partner API)
    python3 gen/pcbway.py --order 10      # add 10 boards with those options and the files to your PCBWay cart
    python3 gen/pcbway.py --board other.kicad_pcb --out somewhere

The files follow PCBWay's "PCBWay Plug-in for KiCad" (MIT, github.com/pcbway/PCBWay-Plug-in-for-Kicad):
same plot options, same layer set, same BOM and position columns, same endpoint
(https://www.pcbway.com/Common/KiCadUpFile/). That upload is anonymous and only
carries size and layer count; the quote page it opens still needs the options
picked by hand (the script prints the list).

--quote and --order use PCBWay's partner API (api-partner.pcbway.com) instead, which
takes every option (PCB_SPEC below: 6 layers, 0.8 mm, ENIG, hard gold fingers with
a bevel, 4/4 mil, 0.2 mm vias ...) and puts the order straight into the cart with
the zip attached. It needs an API key from PCBWay in the environment variable
PCBWAY_API_KEY (ask them for one; the key is tied to your account). Set
PCBWAY_API_URL to use their production host if they give you a different one.
Needs KiCad's pcbnew Python module (KiCad 9)."""
import argparse, csv, io, json, os, shutil, sys, tempfile, urllib.request, uuid, zipfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE_URL = "https://www.pcbway.com"
UPLOAD = BASE_URL + "/Common/KiCadUpFile/"
API_URL = os.environ.get("PCBWAY_API_URL", "https://api-partner.pcbway.com")

# PCB options for this board, in the partner API's vocabulary (api-partner.pcbway.com/Help).
# Length/Width/Layers are filled from the board. The same choices apply to the web form.
PCB_SPEC = {
    "BoardType": "Single PCB", "DesignInPanel": 1,
    "Material": "FR-4", "FR4Tg": "S1000H TG150",          # the TG150 option offered for 4+ layers
    "Thickness": 0.8,                                      # M.2: 0.8 mm
    "cxipt": "L1:1,L2:1,L3:1,L4:1,L5:1,L6:1",             # layer order, 1 oz each
    "MinTrackSpacing": "4/4mil",                           # 0.1 mm track and clearance
    "MinHoleSize": 0.2,                                    # 0.2 mm via drill
    "SolderMask": "Green", "Silkscreen": "White", "SilkSides": 0,
    "SurfaceFinish": "Immersion gold", "GoldThickness": "1",   # ENIG, 1 u" Au
    "Goldfingers": "Yes", "GoldFingersBevelling": "Yes (20°)", # M.2 card edge
    # prototype: ENIG on the fingers too (2 u"), good for a few dozen insertions. For boards that ship,
    # use "GoldPlatingType": "Hard Gold", "AUGoldThickness": "30", "NiGoldThickness": "120" instead.
    "GoldPlatingType": "Immersion gold", "GoldFingerThickness": "2",
    "ViaProcess": "Tenting vias",
    "FinishedCopper": "1 oz Cu", "InsideThickness": "1",
    "RemoveProductNo": "No", "ImpedanceControl": "No",     # PCIe pairs: 100 ohm by geometry, set "Yes" for a controlled stackup
    "ViaPadOrViaResin": "No",
}

# layers PCBWay's plugin plots (those that exist on the board)
PLOT_PLAN = [("F.Cu", pcbnew.F_Cu, "Top Layer"), ("B.Cu", pcbnew.B_Cu, "Bottom Layer")] + \
            [(f"In{i}.Cu", getattr(pcbnew, f"In{i}_Cu"), f"Internal plane {i}") for i in range(1, 31)] + \
            [("F.SilkS", pcbnew.F_SilkS, "Top Silkscreen"), ("B.SilkS", pcbnew.B_SilkS, "Bottom Silkscreen"),
             ("F.Mask", pcbnew.F_Mask, "Top Soldermask"), ("B.Mask", pcbnew.B_Mask, "Bottom Soldermask"),
             ("F.Paste", pcbnew.F_Paste, "Top Paste (Stencil)"), ("B.Paste", pcbnew.B_Paste, "Bottom Paste (Stencil)"),
             ("Edge.Cuts", pcbnew.Edge_Cuts, "Board Outline"), ("User.Comments", pcbnew.Cmts_User, "User Comments")]

FAB_NOTES = """Fabrication notes for artix_m2_canfd (M.2 2280 key M card)

Board:        22 x 80 mm, 6 layers, finished thickness 0.80 mm +/- 0.08 (M.2 requirement)
Stackup:      F.Cu signal / In1 GND / In2 power / In3 power / In4 GND / B.Cu signal (see stackup in the Gerber job file)
Material:     FR-4 TG150 or better
Copper:       1 oz outer, 0.5 oz inner
Finish:       ENIG. The card-edge fingers (M.2 connector, both sides) need hard gold with a 20-30 degree bevel
              on the connector edge, like any M.2 module.
Solder mask:  green (any); silkscreen white, top and bottom
Min track / clearance: 0.1 mm / 0.1 mm (BGA fan-out and PCIe pairs)
Min via:      0.2 mm drill, 0.4 mm pad; vias may be left open (not tented or plugged)
Edge:         the key slot and the semicircular mount notch are part of the outline; 0.3 mm copper-to-edge
              except the gold fingers, which run to the edge (0.1 mm)
Impedance:    PCIe pairs 0.1 mm track / 0.15 mm gap on the outer layers over the adjacent ground plane
              are meant to be 100 ohm differential; adjust prepreg thickness if you control impedance
Assembly:     all SMT, both sides; 0.8 mm pitch BGA (XC7A50T-2CSG325I) on top; parts marked DNP in the BOM
              are not to be fitted (bus termination jumpers)
"""


def plot_gerbers(board, out_dir):
    """Gerbers with PCBWay's plugin settings."""
    settings = board.GetDesignSettings()
    settings.m_SolderMaskMargin = 0
    settings.m_SolderMaskMinWidth = 0
    pctl = pcbnew.PLOT_CONTROLLER(board)
    popt = pctl.GetPlotOptions()
    popt.SetOutputDirectory(out_dir)
    popt.SetPlotFrameRef(False)
    popt.SetSketchPadLineWidth(pcbnew.FromMM(0.1))
    popt.SetAutoScale(False)
    popt.SetScale(1)
    popt.SetMirror(False)
    popt.SetUseGerberAttributes(True)
    if hasattr(popt, "SetExcludeEdgeLayer"):
        popt.SetExcludeEdgeLayer(True)
    popt.SetUseGerberProtelExtensions(False)
    popt.SetUseAuxOrigin(True)
    popt.SetSubtractMaskFromSilk(True)
    popt.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)
    popt.SetCreateGerberJobFile(True)        # carries the stackup
    plotted = []
    job = pcbnew.GERBER_JOBFILE_WRITER(board)
    for suffix, layer, desc in PLOT_PLAN:
        if board.IsLayerEnabled(layer):
            pctl.SetLayer(layer)
            pctl.OpenPlotfile(suffix, pcbnew.PLOT_FORMAT_GERBER, desc)
            pctl.PlotLayer()
            job.AddGbrFile(layer, pctl.GetPlotFileName())
            plotted.append(suffix)
    pctl.ClosePlot()
    name = os.path.splitext(os.path.basename(board.GetFileName()))[0]
    job.CreateJobFile(os.path.join(out_dir, name + "-job.gbrjob"))      # stackup, finish, layer functions
    return plotted


def drill_and_netlist(board, out_dir, name):
    """Excellon drill files (PTH and NPTH, with map) and the IPC-D-356 netlist, as the plugin writes them."""
    drl = pcbnew.EXCELLON_WRITER(board)
    drl.SetOptions(False, True, board.GetDesignSettings().GetAuxOrigin(), False)   # no mirror, minimal header, aux origin, NPTH separate
    drl.SetFormat(False)                                                            # inches, like the plugin
    drl.CreateDrillandMapFilesSet(out_dir, True, False)
    ipc = pcbnew.IPC356D_WRITER(board)
    ipc.Write(os.path.join(out_dir, "PCBWay_netlist.ipc"))


MANUFACTURERS = [("GRM", "Murata"), ("BLM", "Murata"), ("RC0402", "Yageo"), ("TPS", "Texas Instruments"),
                 ("TLV", "Texas Instruments"), ("MCP", "Microchip"), ("W25Q", "Winbond"), ("ECS", "ECS"),
                 ("19-217", "Everlight"), ("16-213", "Everlight"), ("PESD", "Nexperia"), ("TFM", "TDK"), ("DF52", "Hirose"), ("XC7A", "AMD")]

def manufacturer(mpn):
    return next((m for prefix, m in MANUFACTURERS if mpn.startswith(prefix)), "")

def field(fp, name):
    try:
        if fp.HasFieldByName(name):
            return fp.GetFieldByName(name).GetText()
    except AttributeError:
        pass
    return ""


def bom_and_positions(board, out_dir):
    """PCBWay_bom.csv and PCBWay_positions.csv with the plugin's columns. MPN and DNP come from
    the footprint fields the generator writes (bom.csv next to the board is the fallback)."""
    fallback = {}
    bom_csv = os.path.join(os.path.dirname(board.GetFileName()), "bom.csv")
    if os.path.exists(bom_csv):
        with open(bom_csv, newline="") as f:
            for row in csv.DictReader(f):
                fallback[row["Reference"]] = row
    aux = board.GetDesignSettings().GetAuxOrigin()
    positions, items = [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        attrs = fp.GetAttributes()
        not_in_bom = bool(attrs & pcbnew.FP_EXCLUDE_FROM_BOM)
        not_in_pos = bool(attrs & pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        if not_in_bom and not_in_pos:
            continue
        ref = fp.GetReference()
        fb = fallback.get(ref, {})
        mpn = field(fp, "MPN") or fb.get("MPN", "")
        dnp = fp.IsDNP() if hasattr(fp, "IsDNP") else bool(fb.get("DNP"))
        fpname = str(fp.GetFPID().GetLibItemName())
        pack = fpname.split("_")[1] if fpname.startswith(("C_", "R_", "L_", "LED_", "FB_")) else fpname
        entry = {
            "pos_x": round((fp.GetPosition().x - aux.x) / 1e6, 4),
            "pos_y": round(-(fp.GetPosition().y - aux.y) / 1e6, 4),
            "rotation": fp.GetOrientation().AsDegrees(),
            "side": "top" if fp.GetLayer() == pcbnew.F_Cu else "bottom",
            "designator": ref, "mpn": mpn, "pack": pack, "footprint": fpname, "value": fp.GetValue(),
            "mount_type": "smt" if attrs & pcbnew.FP_SMD else "tht",
        }
        if not not_in_pos and not dnp:
            positions.append(entry)
        if not not_in_bom:
            items.append(dict(entry, dnp=dnp, description=field(fp, "Description") or fb.get("Description", "")))
    # group identical parts (DNP parts stay on their own line)
    groups = {}
    for it in items:
        key = (it["value"], it["footprint"], it["pack"], it["mpn"], it["designator"] if it["dnp"] else "")
        groups.setdefault(key, []).append(it)
    bom_rows = []
    for key, grp in groups.items():
        first = grp[0]
        bom_rows.append({"Designator": ", ".join(g["designator"] for g in grp), "Quantity": len(grp),
                         "Value": first["value"], "Footprint": first["footprint"], "Package": first["pack"],
                         "MPN": first["mpn"], "Manufacturer": manufacturer(first["mpn"]),
                         "DNP": "Yes" if first["dnp"] else "", "Mount_Type": first["mount_type"],
                         "Description": first["description"]})
    with open(os.path.join(out_dir, "PCBWay_positions.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(positions[0].keys())
        for p in positions:
            w.writerow(p.values())
    with open(os.path.join(out_dir, "PCBWay_bom.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(bom_rows[0].keys())
        for r in bom_rows:
            w.writerow(r.values())
    return len(positions), len(bom_rows)


def board_params(board):
    bb = board.GetBoardEdgesBoundingBox()      # includes the outline stroke (0.05 mm), hence the correction
    stroke = 0.05
    return {"boardWidth": round(pcbnew.ToMM(bb.GetWidth()) - stroke, 2), "boardHeight": round(pcbnew.ToMM(bb.GetHeight()) - stroke, 2),
            "boardLayer": board.GetCopperLayerCount()}


def upload(zip_path, params):
    """Multipart POST like the plugin (field upload[file] plus the board parameters). Returns the quote URL."""
    boundary = "----pcbway" + uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in params.items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"upload[file]\"; filename=\"{os.path.basename(zip_path)}\"\r\n"
               f"Content-Type: application/zip\r\n\r\n".encode())
    body.write(open(zip_path, "rb").read())
    body.write(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(UPLOAD, data=body.getvalue(), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "User-Agent": "artix_m2_canfd pcbway.py (KiCad plugin protocol)"})
    with urllib.request.urlopen(req, timeout=120) as rsp:
        answer = json.loads(rsp.read().decode())
    return answer["redirect"] if answer["redirect"].startswith("http") else BASE_URL + answer["redirect"]


def spec_for(board, qty):
    p = board_params(board)
    spec = dict(PCB_SPEC)
    spec.update({"Length": round(max(p["boardWidth"], p["boardHeight"]), 2),
                 "Width": round(min(p["boardWidth"], p["boardHeight"]), 2),
                 "Layers": p["boardLayer"], "Qty": qty})
    return spec


def print_spec(spec):
    print("PCBWay options for this board (pick the same on the web form):")
    for k, v in spec.items():
        if k not in ("BoardType", "DesignInPanel", "cxipt", "RemoveProductNo", "ViaPadOrViaResin", "SilkSides"):
            print(f"  {k:22s} {v}")


def api(path, payload):
    key = os.environ.get("PCBWAY_API_KEY")
    if not key:
        raise SystemExit("set PCBWAY_API_KEY (an API key from PCBWay) to use --quote / --order")
    req = urllib.request.Request(API_URL + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as rsp:
        answer = json.loads(rsp.read().decode())
    if answer.get("Status") != "ok":
        raise SystemExit(f"PCBWay API error: {answer.get('ErrorText') or answer}")
    return answer


def quote(spec):
    answer = api("/api/Pcb/PcbQuotation", dict(spec, returnPriceMatirx=False))
    print(f"PCBWay quote for {spec['Qty']} boards:")
    for item in answer.get("priceList", []):
        kind = "express" if item.get("Express") else ("standard" if item.get("Standard") else "")
        print(f"  {item.get('BuildDays'):>3} days  {item.get('BuildText', ''):28s} {item.get('Price'):>9.2f} USD  {kind}")
    return answer


def order(spec, zip_path, build_days, email, note):
    import base64
    payload = dict(spec, DataZipFile=base64.b64encode(open(zip_path, "rb").read()).decode(),
                   PcbFileName=os.path.basename(zip_path), BuildDays=build_days, BuyerEmail=email or "",
                   Note=note)
    answer = api("/api/Pcb/PlaceOrder", payload)
    print(f"added to the PCBWay cart: order {answer.get('OrderNo')}, {answer.get('Price')} USD, delivery {answer.get('DeliveryDate')}")
    return answer


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", default=os.path.join(ROOT, "artix_m2_canfd.kicad_pcb"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "pcbway"))
    ap.add_argument("--upload", action="store_true", help="send the package to PCBWay and print the quote page URL")
    ap.add_argument("--quote", action="store_true", help="price and lead times from the partner API (needs PCBWAY_API_KEY)")
    ap.add_argument("--order", type=int, metavar="QTY", help="add QTY boards to the PCBWay cart via the partner API")
    ap.add_argument("--qty", type=int, default=5, help="quantity for --quote (default 5)")
    ap.add_argument("--build-days", type=int, default=None, help="production cycle for --order (default: the standard one from the quote)")
    ap.add_argument("--email", default=None, help="buyer e-mail for --order (where PCBWay sends file questions)")
    args = ap.parse_args()
    board = pcbnew.LoadBoard(args.board)
    name = os.path.splitext(os.path.basename(args.board))[0]
    os.makedirs(args.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="pcbway_")
    layers = plot_gerbers(board, work)
    drill_and_netlist(board, work, name)
    n_pos, n_bom = bom_and_positions(board, work)
    with open(os.path.join(work, "PCBWay_fab_notes.txt"), "w") as f:
        f.write(FAB_NOTES)
    zip_path = os.path.join(args.out, name + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(work)):
            z.write(os.path.join(work, fn), fn)
    shutil.rmtree(work)
    params = board_params(board)
    print(f"{zip_path}: {len(layers)} gerber layers, {n_pos} placements, {n_bom} BOM lines, "
          f"{params['boardWidth']:.1f} x {params['boardHeight']:.1f} mm, {params['boardLayer']} layers")
    spec = spec_for(board, args.order or args.qty)
    if args.upload:
        url = upload(zip_path, params)
        print("PCBWay quote page:", url)
        print_spec(spec)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    if args.quote or args.order:
        answer = quote(spec)
        if args.order:
            days = args.build_days
            if days is None:
                std = [i for i in answer.get("priceList", []) if i.get("Standard")] or answer.get("priceList", [])
                if not std:
                    raise SystemExit("no production cycle in the quote; pass --build-days")
                days = std[0]["BuildDays"]
            order(spec, zip_path, days, args.email, FAB_NOTES)
    if not (args.upload or args.quote or args.order):
        print_spec(spec)


if __name__ == "__main__":
    main()
