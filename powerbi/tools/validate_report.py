#!/usr/bin/env python3
"""Cross-check report.json field references against the TMDL model."""
import json, re, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(BASE, "GameZone.SemanticModel", "definition")

measures, columns = set(), {}

for fname in os.listdir(os.path.join(MODEL, "tables")):
    path = os.path.join(MODEL, "tables", fname)
    text = open(path, encoding="utf-8").read()
    tbl = re.search(r"^table ('[^']+'|\S+)", text, re.M).group(1).strip("'")
    columns[tbl] = set()
    for line in text.splitlines():
        m = re.match(r"^\tcolumn ('[^']+'|\S+)\s*$", line)
        if m:
            columns[tbl].add(m.group(1).strip("'"))
        m = re.match(r"^\tmeasure ('[^']+'|[A-Za-z_][\w ]*?) =", line)
        if m:
            measures.add(m.group(1).strip("'").strip())

print("tables:", ", ".join(sorted(columns)))
print("measures found:", len(measures))

rel = open(os.path.join(MODEL, "relationships.tmdl"), encoding="utf-8").read()
for side in re.findall(r"(?:from|to)Column: (\S+)", rel):
    tbl, col = side.rsplit(".", 1)
    tbl = tbl.strip("'")
    if col not in columns.get(tbl, set()):
        print("  MISSING relationship column:", side)

report = json.load(open(os.path.join(BASE, "GameZone.Report", "report.json"),
                       encoding="utf-8"))

bad = []
seen_refs = set()
for sec in report["sections"]:
    for vc in sec["visualContainers"]:
        cfg = json.loads(vc["config"])
        sv = cfg["singleVisual"]
        pq = sv.get("prototypeQuery")
        if not pq:
            continue
        aliases = {f["Name"]: f["Entity"] for f in pq["From"]}
        for item in pq["Select"]:
            if "Measure" in item:
                ent = aliases[item["Measure"]["Expression"]["SourceRef"]["Source"]]
                prop = item["Measure"]["Property"]
                ok = ent == "_Measures" and prop in measures
            else:
                ent = aliases[item["Column"]["Expression"]["SourceRef"]["Source"]]
                prop = item["Column"]["Property"]
                ok = prop in columns.get(ent, set())
            ref = "%s.%s" % (ent, prop)
            seen_refs.add(ref)
            if not ok:
                bad.append((sec["displayName"], sv["visualType"], ref))
        # projections must all point at a Select name
        names = {i["Name"] for i in pq["Select"]}
        for role, fields in sv.get("projections", {}).items():
            for f in fields:
                if f["queryRef"] not in names:
                    bad.append((sec["displayName"], sv["visualType"],
                                "projection %s -> %s" % (role, f["queryRef"])))

print("distinct field references in report:", len(seen_refs))
if bad:
    print("\nBROKEN REFERENCES:")
    for b in bad:
        print("  ", " | ".join(b))
    sys.exit(1)
print("\nOK: every report reference resolves against the model.")

unused = sorted(m for m in measures if "_Measures." + m not in seen_refs)
print("\nmeasures defined but not placed on a page (%d):" % len(unused))
for m in unused:
    print("  ", m)
