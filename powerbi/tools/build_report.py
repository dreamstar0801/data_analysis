#!/usr/bin/env python3
"""Generate GameZone.Report/report.json.

The report layout is generated rather than dragged out by hand so that page
structure, visual sizing and field bindings stay consistent, and so a change to
the layout shows up as a readable diff in this file instead of as an opaque
churn in report.json.

Run from the repo root:

    python3 powerbi/tools/build_report.py
    python3 powerbi/tools/validate_report.py

validate_report.py cross-checks every field reference in the generated report
against the TMDL model, so a measure rename cannot silently orphan a visual.
"""
import json, uuid, os

W, H = 1280, 720
ENTITY_ALIAS = {"Orders": "o", "Country": "c", "Date": "d", "_Measures": "m"}


def _guid():
    return str(uuid.uuid4())


def field(entity, prop, kind):
    """kind: 'column' | 'measure'"""
    return {"entity": entity, "prop": prop, "kind": kind,
            "ref": "%s.%s" % (entity, prop)}


def C(entity, prop):
    return field(entity, prop, "column")


def M(prop):
    return field("_Measures", prop, "measure")


def prototype_query(fields, order_by=None):
    entities = []
    seen = []
    for f in fields:
        if f["entity"] not in seen:
            seen.append(f["entity"])
    for e in seen:
        entities.append({"Name": ENTITY_ALIAS[e], "Entity": e, "Type": 0})
    select = []
    for f in fields:
        src = {"SourceRef": {"Source": ENTITY_ALIAS[f["entity"]]}}
        if f["kind"] == "column":
            item = {"Column": {"Expression": src, "Property": f["prop"]}}
        else:
            item = {"Measure": {"Expression": src, "Property": f["prop"]}}
        item["Name"] = f["ref"]
        item["NativeReferenceName"] = f["prop"]
        select.append(item)
    q = {"Version": 2, "From": entities, "Select": select}
    if order_by is not None:
        f = order_by
        src = {"SourceRef": {"Source": ENTITY_ALIAS[f["entity"]]}}
        expr = ({"Column": {"Expression": src, "Property": f["prop"]}}
                if f["kind"] == "column"
                else {"Measure": {"Expression": src, "Property": f["prop"]}})
        q["OrderBy"] = [{"Direction": 2, "Expression": expr}]
    return q


def visual(x, y, w, h, vtype, projections, fields, title=None,
           order_by=None, objects=None, z=0):
    single = {
        "visualType": vtype,
        "drillFilterOtherVisuals": True,
    }
    if fields:
        single["projections"] = {
            k: [{"queryRef": f["ref"]} for f in v] for k, v in projections.items()
        }
        single["prototypeQuery"] = prototype_query(fields, order_by)
    single["objects"] = objects or {}
    vc = {}
    if title is not None:
        vc["title"] = [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'%s'" % title.replace("'", "")}}},
            "fontSize": {"expr": {"Literal": {"Value": "11D"}}},
        }}]
    single["vcObjects"] = vc
    cfg = {
        "name": _guid(),
        "layouts": [{"id": 0, "position": {
            "x": x, "y": y, "z": z, "width": w, "height": h}}],
        "singleVisual": single,
    }
    return {"x": x, "y": y, "z": z, "width": w, "height": h,
            "config": json.dumps(cfg), "filters": "[]"}


def textbox(x, y, w, h, runs, z=0):
    text_runs = []
    for value, size, weight, color in runs:
        style = {"fontSize": size, "fontWeight": weight, "color": color}
        text_runs.append({"value": value, "textStyle": style})
    objects = {"general": [{"properties": {
        "paragraphs": [{"textRuns": text_runs}]}}]}
    return visual(x, y, w, h, "textbox", {}, None, objects=objects, z=z)


def card(x, y, w, h, measure, title):
    return visual(x, y, w, h, "card", {"Values": [M(measure)]},
                  [M(measure)], title=title)


def section(name, display, ordinal, visuals):
    return {
        "name": name,
        "displayName": display,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": visuals,
        "config": json.dumps({"visibility": 0}),
        "displayOption": 1,
        "height": float(H),
        "width": float(W),
    }


TITLE = ("#1B2A3D", "20pt", "bold")
SUB = ("#5A6B7D", "10pt", "normal")

# ---------------------------------------------------------------- page 1
p1 = []
p1.append(textbox(20, 16, 700, 34, [
    ("GameZone — executive summary", "20pt", "bold", "#1B2A3D")]))
p1.append(textbox(20, 48, 700, 26, [
    ("21,685 revenue-eligible orders, Jan 2019 – Dec 2021. "
     "Figures reconcile to sql/gamezone_channel_region_analysis.sql.",
     "10pt", "normal", "#5A6B7D")]))
p1.append(visual(1040, 16, 220, 120, "slicer",
                 {"Values": [C("Date", "Year")]}, [C("Date", "Year")],
                 title="Year",
                 objects={"data": [{"properties": {
                     "mode": {"expr": {"Literal": {"Value": "'Basic'"}}}}}]}))
p1.append(card(20, 150, 245, 110, "Total Revenue", "Total revenue"))
p1.append(card(275, 150, 245, 110, "Order Count", "Orders"))
p1.append(card(530, 150, 245, 110, "AOV", "Average order value"))
p1.append(card(785, 150, 245, 110, "Refund Rate", "Refund rate"))
p1.append(visual(20, 275, 620, 210, "lineChart",
                 {"Category": [C("Date", "Year Month")],
                  "Y": [M("Total Revenue")]},
                 [C("Date", "Year Month"), M("Total Revenue")],
                 title="Revenue by month"))
p1.append(visual(660, 275, 600, 210, "clusteredBarChart",
                 {"Category": [C("Country", "region")],
                  "Y": [M("Total Revenue")]},
                 [C("Country", "region"), M("Total Revenue")],
                 title="Revenue by region",
                 order_by=M("Total Revenue")))
p1.append(visual(20, 495, 620, 205, "clusteredBarChart",
                 {"Category": [C("Orders", "marketing_channel")],
                  "Y": [M("Total Revenue")]},
                 [C("Orders", "marketing_channel"), M("Total Revenue")],
                 title="Revenue by marketing channel",
                 order_by=M("Total Revenue")))
p1.append(visual(660, 495, 600, 205, "pivotTable",
                 {"Rows": [C("Orders", "marketing_channel")],
                  "Values": [M("Total Revenue"), M("Revenue % of Total"),
                             M("AOV"), M("Refund Rate"), M("Revenue YoY %")]},
                 [C("Orders", "marketing_channel"), M("Total Revenue"),
                  M("Revenue % of Total"), M("AOV"), M("Refund Rate"),
                  M("Revenue YoY %")],
                 title="Channel scorecard"))

# ---------------------------------------------------------------- page 2
p2 = []
p2.append(textbox(20, 16, 900, 34, [
    ("Marketing channel deep dive", "20pt", "bold", "#1B2A3D")]))
p2.append(textbox(20, 48, 900, 40, [
    ("This is a direct-traffic business: direct carries 84.7% of revenue. "
     "The movement worth watching is email, which grew from 8.2% to 14.3% of "
     "revenue while direct fell 4.2 points.",
     "10pt", "normal", "#5A6B7D")]))
p2.append(visual(20, 100, 620, 280, "pivotTable",
                 {"Rows": [C("Orders", "marketing_channel")],
                  "Values": [M("Total Revenue"), M("Revenue LY"),
                             M("Revenue YoY"), M("Revenue YoY %"),
                             M("Order Count"), M("AOV"), M("Refund Rate"),
                             M("Channel Share"), M("Channel Revenue Rank")]},
                 [C("Orders", "marketing_channel"), M("Total Revenue"),
                  M("Revenue LY"), M("Revenue YoY"), M("Revenue YoY %"),
                  M("Order Count"), M("AOV"), M("Refund Rate"),
                  M("Channel Share"), M("Channel Revenue Rank")],
                 title="Channel scorecard"))
p2.append(visual(660, 100, 600, 280, "columnChart",
                 {"Category": [C("Date", "Year")],
                  "Series": [C("Orders", "marketing_channel")],
                  "Y": [M("Channel Share")]},
                 [C("Date", "Year"), C("Orders", "marketing_channel"),
                  M("Channel Share")],
                 title="Revenue share by channel and year"))
p2.append(visual(20, 395, 620, 305, "lineChart",
                 {"Category": [C("Date", "Year Month")],
                  "Series": [C("Orders", "marketing_channel")],
                  "Y": [M("Total Revenue")]},
                 [C("Date", "Year Month"), C("Orders", "marketing_channel"),
                  M("Total Revenue")],
                 title="Monthly revenue by channel"))
p2.append(visual(660, 395, 600, 305, "pivotTable",
                 {"Rows": [C("Orders", "marketing_channel")],
                  "Columns": [C("Date", "Year")],
                  "Values": [M("Channel Share"), M("Channel Share LY"),
                             M("Channel Mix Shift (pp)")]},
                 [C("Orders", "marketing_channel"), C("Date", "Year"),
                  M("Channel Share"), M("Channel Share LY"),
                  M("Channel Mix Shift (pp)")],
                 title="Year-over-year mix shift, percentage points"))

# ---------------------------------------------------------------- page 3
p3 = []
p3.append(textbox(20, 16, 900, 34, [
    ("Region and product", "20pt", "bold", "#1B2A3D")]))
p3.append(textbox(20, 48, 900, 40, [
    ("NAMER is the largest region at 52.1% of revenue — but only after "
     "patching six country codes the source lookup leaves blank. The two cards "
     "on the right quantify how much of the regional view rests on that patch.",
     "10pt", "normal", "#5A6B7D")]))
p3.append(visual(20, 100, 620, 250, "pivotTable",
                 {"Rows": [C("Country", "region")],
                  "Values": [M("Total Revenue"), M("Net Revenue"),
                             M("Order Count"), M("Customers"),
                             M("Revenue per Customer"), M("Region Share"),
                             M("Refund Rate by Value"),
                             M("Region Revenue Rank"), M("Top Product"),
                             M("Top Product Revenue")]},
                 [C("Country", "region"), M("Total Revenue"), M("Net Revenue"),
                  M("Order Count"), M("Customers"), M("Revenue per Customer"),
                  M("Region Share"), M("Refund Rate by Value"),
                  M("Region Revenue Rank"), M("Top Product"),
                  M("Top Product Revenue")],
                 title="Region scorecard"))
p3.append(card(660, 100, 290, 120, "Unmapped Revenue %",
               "Revenue with no region"))
p3.append(card(970, 100, 290, 120, "Revenue on NA-Renamed Regions %",
               "Revenue resting on reading 'NA' as text"))
p3.append(visual(660, 230, 600, 120, "clusteredBarChart",
                 {"Category": [C("Country", "region_source")],
                  "Y": [M("Total Revenue")]},
                 [C("Country", "region_source"), M("Total Revenue")],
                 title="Revenue by how the region was resolved",
                 order_by=M("Total Revenue")))
p3.append(visual(20, 365, 620, 335, "clusteredBarChart",
                 {"Category": [C("Orders", "product_name")],
                  "Y": [M("Total Revenue")]},
                 [C("Orders", "product_name"), M("Total Revenue")],
                 title="Revenue by product",
                 order_by=M("Total Revenue")))
p3.append(visual(660, 365, 600, 335, "pivotTable",
                 {"Rows": [C("Orders", "product_name")],
                  "Columns": [C("Country", "region")],
                  "Values": [M("Total Revenue")]},
                 [C("Orders", "product_name"), C("Country", "region"),
                  M("Total Revenue")],
                 title="Product by region"))

# ---------------------------------------------------------------- page 4
p4 = []
p4.append(textbox(20, 16, 900, 34, [
    ("Data quality", "20pt", "bold", "#1B2A3D")]))
p4.append(textbox(20, 48, 1000, 44, [
    ("Known defects are reported as live measures rather than buried in a "
     "footnote. The Model Check card is a regression test: it returns OK only "
     "while the model still reproduces the SQL baseline exactly.",
     "10pt", "normal", "#5A6B7D")]))
p4.append(card(20, 105, 240, 110, "Total Rows", "Rows after de-duplication"))
p4.append(card(270, 105, 240, 110, "Excluded Zero-Price Orders",
               "Excluded: $0 or null price"))
p4.append(card(520, 105, 240, 110, "Orders Shipped Before Purchase",
               "Ship date precedes purchase"))
p4.append(card(770, 105, 240, 110, "% Shipped Before Purchase",
               "Share of rows affected"))
p4.append(card(1020, 105, 240, 110, "Orders Missing Purchase Date",
               "No parseable purchase date"))
p4.append(card(20, 230, 195, 110, "Unmapped Revenue", "Revenue with no region"))
p4.append(card(225, 230, 195, 110, "Revenue on NA-Renamed Regions",
               "Revenue resting on reading 'NA' as text"))
p4.append(visual(440, 230, 820, 110, "card",
                 {"Values": [M("Model Check")]}, [M("Model Check")],
                 title="Model check versus SQL baseline"))
p4.append(visual(20, 355, 620, 345, "tableEx",
                 {"Values": [C("Country", "country_code"),
                             C("Country", "region"),
                             C("Country", "region_source"),
                             M("Total Revenue")]},
                 [C("Country", "country_code"), C("Country", "region"),
                  C("Country", "region_source"), M("Total Revenue")],
                 title="Country to region resolution",
                 order_by=M("Total Revenue")))
p4.append(visual(660, 355, 600, 345, "pivotTable",
                 {"Rows": [C("Orders", "product_name")],
                  "Values": [M("Order Count"), M("Avg Days to Ship"),
                             M("Median Days to Ship"), M("Refunded Orders"),
                             M("Refund Rate"), M("Refunded Revenue")]},
                 [C("Orders", "product_name"), M("Order Count"),
                  M("Avg Days to Ship"), M("Median Days to Ship"),
                  M("Refunded Orders"), M("Refund Rate"),
                  M("Refunded Revenue")],
                 title="Fulfilment and refunds by product"))

sections = [
    section("ReportSectionExec01", "Executive summary", 0, p1),
    section("ReportSectionChan02", "Channel", 1, p2),
    section("ReportSectionRegn03", "Region and product", 2, p3),
    section("ReportSectionQual04", "Data quality", 3, p4),
]

report = {
    "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/report/1.0.0/schema.json"),
    "config": json.dumps({
        "version": "5.43",
        "activeSectionIndex": 0,
        "defaultDrillFilterOtherVisuals": True,
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": 1,
            "useNewFilterPaneExperience": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
        },
    }),
    "layoutOptimization": 0,
    "resourcePackages": [],
    "sections": sections,
}

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(BASE, "GameZone.Report", "report.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
print("wrote", out, os.path.getsize(out), "bytes,",
      len(sections), "pages,",
      sum(len(s["visualContainers"]) for s in sections), "visuals")
