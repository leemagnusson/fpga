import json, sys, collections
d = json.load(open(sys.argv[1]))
viol = [v for s in d.get("sheets", [d]) for v in s["violations"]]
c = collections.Counter((v["severity"], v["type"]) for v in viol)
for k, n in sorted(c.items()): print(f"{n:4d} {k[0]:8s} {k[1]}")
for v in viol:
    if v["type"] not in ("endpoint_off_grid",):
        print("  -", v["severity"], v["type"], ":", v["description"], [(i.get("description"), i.get("pos")) for i in v["items"]][:3])
print("total", len(viol), "errors", sum(1 for v in viol if v["severity"] == "error"))
