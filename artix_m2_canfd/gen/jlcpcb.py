"""Fabrication package for JLCPCB: gerbers, BOM and pick-and-place in JLCPCB's formats, with LCSC part lookup.

    python3 gen/jlcpcb.py                 # write build/jlcpcb/<board>.zip (gerbers + drills), <board>_bom.csv, <board>_cpl.csv
    python3 gen/jlcpcb.py --lookup        # refresh gen/data/lcsc.json from JLCPCB's parts search: MPN -> LCSC code,
                                          #   basic/extended, stock, price; then write the files
    python3 gen/jlcpcb.py --qty 5         # ... and estimate the parts cost for 5 boards from JLCPCB's price ladders
    python3 gen/jlcpcb.py --open          # ... and open the JLCPCB quote page (upload is by hand, see below)
    python3 gen/jlcpcb.py --board other.kicad_pcb --out somewhere

JLCPCB has no public upload API: on https://cart.jlcpcb.com/quote drag the zip in, pick the options the
script prints (6 layers, 0.8 mm, ENIG, gold fingers with bevel ...), turn on "PCB Assembly" and at the
"Add BOM and CPL" step upload <board>_bom.csv and <board>_cpl.csv. JLCPCB matches parts by the
"LCSC Part #" column, which comes from gen/data/lcsc.json. The json is keyed by MPN; a record with
"manual": true is kept as is by --lookup, so a hand-picked LCSC code can override the search result.
Parts marked DNP are left out of both files. JLCPCB shows the placement with the footprints of its own
library before you pay: check the rotation of polarised parts (ICs, LEDs, diodes) there and use their
rotate button if a footprint is turned differently from KiCad's. Needs KiCad's pcbnew Python module."""
import argparse, csv, json, os, shutil, sys, tempfile, urllib.request, zipfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pcbway import plot_gerbers, drill_and_netlist, field, manufacturer

LCSC_JSON = os.path.join(HERE, "data", "lcsc.json")
SEARCH_URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
QUOTE_URL = "https://cart.jlcpcb.com/quote"

# the JLCPCB order form options for this board (same choices as PCB_SPEC in pcbway.py, in JLCPCB's words)
PCB_OPTIONS = [
    ("Base material", "FR-4"), ("Layers", "6"), ("PCB thickness", "0.8 mm"),
    ("PCB color", "Green"), ("Silkscreen", "White"), ("Surface finish", "ENIG"),
    ("Outer copper weight", "1 oz"), ("Inner copper weight", "0.5 oz"),
    ("Via covering", "Tented"), ("Min via hole size/diameter", "0.2 mm / (0.4 mm)"),
    ("Board outline tolerance", "±0.2 mm"), ("Gold fingers", "Yes"), ("30° finger chamfered", "Yes"),
    ("Impedance control", "No (PCIe pairs are 100 ohm by geometry; choose a JLC06161H-xxxx stackup to control it)"),
    ("Remove order number", "Specify a location (or No)"),
    ("PCB assembly", "Yes, both sides; add the BOM and CPL files from build/jlcpcb"),
]


def norm(mpn):
    """JLCPCB drops the hyphens in some manufacturers' numbers (TDK TFM201610ALMA-R47MTAA is listed as TFM201610ALMAR47MTAA)."""
    return mpn.replace(" ", "").replace("-", "").upper()


def search(mpn):
    """JLCPCB parts search; the record whose model matches the MPN exactly, else None."""
    payload = json.dumps({"keyword": mpn, "currentPage": 1, "pageSize": 20, "searchSource": "search"}).encode()
    req = urllib.request.Request(SEARCH_URL, data=payload, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (artix_m2_canfd jlcpcb.py)"})
    with urllib.request.urlopen(req, timeout=60) as rsp:
        answer = json.loads(rsp.read().decode())
    items = (answer.get("data") or {}).get("componentPageInfo", {}).get("list") or []
    exact = [it for it in items if norm(it.get("componentModelEn", "")) == norm(mpn)]
    if not exact:
        return None
    it = sorted(exact, key=lambda i: (i.get("componentLibraryType") != "base", -(i.get("stockCount") or 0)))[0]
    ladder = sorted((p["startNumber"], p["productPrice"]) for p in it.get("componentPrices") or [])
    return {"code": it.get("componentCode"), "brand": it.get("componentBrandEn"),
            "type": "basic" if it.get("componentLibraryType") == "base" else "extended",
            "stock": it.get("stockCount"), "price": ladder, "package": it.get("componentSpecificationEn"),
            "description": it.get("describe") or it.get("erpComponentName")}


def load_lcsc():
    if os.path.exists(LCSC_JSON):
        with open(LCSC_JSON) as f:
            return json.load(f)
    return {}


def lookup(mpns):
    """Refresh gen/data/lcsc.json for these MPNs (manual records are kept)."""
    table = load_lcsc()
    for mpn in sorted(set(mpns)):
        if not mpn or table.get(mpn, {}).get("manual"):
            continue
        try:
            rec = search(mpn)
        except Exception as e:
            print(f"  {mpn}: search failed ({e}); keeping the old record")
            continue
        if rec:
            table[mpn] = rec
        else:
            table.setdefault(mpn, {})["code"] = table.get(mpn, {}).get("code", "")
            table[mpn]["stock"] = 0
            table[mpn].setdefault("type", "")
            print(f"  {mpn}: not found at JLCPCB")
    os.makedirs(os.path.dirname(LCSC_JSON), exist_ok=True)
    with open(LCSC_JSON, "w") as f:
        json.dump(table, f, indent=1, sort_keys=True)
        f.write("\n")
    return table


def price_at(ladder, qty):
    price = None
    for start, p in ladder or []:
        if qty >= start:
            price = p
    return price


def parts(board):
    """One entry per fitted footprint, from the board plus bom.csv for the MPN/DNP fallback."""
    fallback = {}
    bom_csv = os.path.join(os.path.dirname(board.GetFileName()), "bom.csv")
    if os.path.exists(bom_csv):
        with open(bom_csv, newline="") as f:
            for row in csv.DictReader(f):
                fallback[row["Reference"]] = row
    aux = board.GetDesignSettings().GetAuxOrigin()
    out = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        attrs = fp.GetAttributes()
        if attrs & pcbnew.FP_EXCLUDE_FROM_BOM or attrs & pcbnew.FP_EXCLUDE_FROM_POS_FILES:
            continue
        ref = fp.GetReference()
        fb = fallback.get(ref, {})
        dnp = fp.IsDNP() if hasattr(fp, "IsDNP") else bool(fb.get("DNP"))
        if dnp:
            continue
        mpn = field(fp, "MPN") or fb.get("MPN", "")
        if not mpn:          # pads only (Tag-Connect etc.)
            continue
        out.append({"ref": ref, "value": fp.GetValue(), "footprint": str(fp.GetFPID().GetLibItemName()), "mpn": mpn,
                    "x": round((fp.GetPosition().x - aux.x) / 1e6, 4), "y": round(-(fp.GetPosition().y - aux.y) / 1e6, 4),
                    "rot": round(fp.GetOrientation().AsDegrees(), 2),
                    "layer": "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom"})
    return out


def write_files(items, table, out_dir, name):
    groups = {}
    for it in items:
        groups.setdefault((it["value"], it["footprint"], it["mpn"]), []).append(it["ref"])
    bom = os.path.join(out_dir, f"{name}_bom.csv")
    with open(bom, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN", "Manufacturer", "Quantity"])
        for (value, footprint, mpn), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            w.writerow([value, ",".join(refs), footprint, table.get(mpn, {}).get("code", ""), mpn, manufacturer(mpn), len(refs)])
    cpl = os.path.join(out_dir, f"{name}_cpl.csv")
    with open(cpl, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for it in items:
            w.writerow([it["ref"], f"{it['x']}mm", f"{it['y']}mm", it["layer"], it["rot"]])
    return bom, cpl, len(groups)


def report(items, table, qty):
    """Part table with LCSC codes, stock and the per-board cost at qty boards."""
    counts = {}
    for it in items:
        counts[it["mpn"]] = counts.get(it["mpn"], 0) + 1
    total, missing, short, extended = 0.0, [], [], 0
    print(f"{'MPN':28s} {'LCSC':10s} {'type':8s} {'stock':>8s} {'per board':>10s} {'unit @qty':>10s}")
    for mpn, n in sorted(counts.items()):
        rec = table.get(mpn, {})
        code = rec.get("code") or ""
        unit = price_at(rec.get("price"), n * qty)
        line = unit * n if unit is not None else None
        if not code:
            missing.append(mpn)
        elif (rec.get("stock") or 0) < n * qty:
            short.append(mpn)
        if rec.get("type") == "extended":
            extended += 1
        if line is not None:
            total += line
        print(f"{mpn:28s} {code:10s} {rec.get('type', ''):8s} {str(rec.get('stock', '')):>8s} "
              f"{('%.2f' % line) if line is not None else '':>10s} {('%.4f' % unit) if unit is not None else '':>10s}")
    print(f"parts cost per board at {qty} boards: about {total:.2f} USD (JLCPCB price ladders, no loading fees)"
          f"; {extended} extended-part lines (each adds a loading fee)")
    if missing:
        print("no LCSC part for:", ", ".join(missing), "-> run --lookup or add a manual record to gen/data/lcsc.json")
    if short:
        print("short on stock for", qty, "boards:", ", ".join(short))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", default=os.path.join(ROOT, "artix_m2_canfd.kicad_pcb"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "jlcpcb"))
    ap.add_argument("--lookup", action="store_true", help="refresh gen/data/lcsc.json from JLCPCB's parts search")
    ap.add_argument("--qty", type=int, default=5, help="board count for the cost estimate (default 5)")
    ap.add_argument("--open", action="store_true", help="open the JLCPCB quote page")
    args = ap.parse_args()
    board = pcbnew.LoadBoard(args.board)
    name = os.path.splitext(os.path.basename(args.board))[0]
    os.makedirs(args.out, exist_ok=True)
    items = parts(board)
    table = lookup([it["mpn"] for it in items]) if args.lookup else load_lcsc()
    work = tempfile.mkdtemp(prefix="jlcpcb_")
    layers = plot_gerbers(board, work)
    drill_and_netlist(board, work, name)
    zip_path = os.path.join(args.out, name + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(work)):
            z.write(os.path.join(work, fn), fn)
    shutil.rmtree(work)
    bom, cpl, lines = write_files(items, table, args.out, name)
    print(f"{zip_path}: {len(layers)} gerber layers; {bom}: {lines} lines; {cpl}: {len(items)} placements")
    report(items, table, args.qty)
    print("JLCPCB order options:")
    for k, v in PCB_OPTIONS:
        print(f"  {k:30s} {v}")
    if args.open:
        import webbrowser
        webbrowser.open(QUOTE_URL)


if __name__ == "__main__":
    main()
