import json, sys, collections
d = json.load(open(sys.argv[1]))
tot_err = 0
for key in ("violations", "unconnected_items", "schematic_parity"):
    v = d.get(key, [])
    c = collections.Counter((x["severity"], x["type"]) for x in v)
    print(key, dict(c))
    tot_err += sum(1 for x in v if x["severity"] == "error")
    for x in v[:60]:
        print("  -", x["severity"], x["type"], ":", x["description"][:120], [(i.get("description", "")[:70], i.get("pos")) for i in x["items"]][:2])
print("TOTAL errors:", tot_err)
