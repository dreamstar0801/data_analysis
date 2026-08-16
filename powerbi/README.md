# GameZone — Power BI semantic model and report

A star-schema semantic model and four-page report over the GameZone order data,
stored in **PBIP** (Power BI Project) format: plain-text TMDL for the model and
JSON for the report, so the DAX and the Power Query steps are reviewable in a
pull request instead of sealed inside a binary `.pbix`.

Every figure the report produces reconciles to
[`sql/gamezone_channel_region_analysis.sql`](../sql/gamezone_channel_region_analysis.sql).
That is enforced in the model, not just asserted — see [Validation](#validation).

---

## What is in here

```
powerbi/
├── GameZone.pbip                        open this in Power BI Desktop
├── GameZone.SemanticModel/
│   └── definition/
│       ├── model.tmdl                   model-level settings
│       ├── database.tmdl                compatibility level
│       ├── expressions.tmdl             the RepoPath parameter
│       ├── relationships.tmdl           Orders → Date, Orders → Country
│       └── tables/
│           ├── Orders.tmdl              fact table + all Power Query cleaning
│           ├── Country.tmdl             country → region dimension
│           ├── Date.tmdl                DAX calendar, marked as date table
│           └── _Measures.tmdl           36 measures
├── GameZone.Report/
│   └── report.json                      4 pages, 37 visuals
├── dax/
│   └── measures.dax                     the same measures as portable plain text
└── tools/
    ├── build_report.py                  generates report.json
    └── validate_report.py               checks every visual against the model
```

## Opening it

1. Clone the repo.
2. Open `powerbi/GameZone.pbip` in Power BI Desktop (July 2023 or later).
3. **Home → Transform data → Manage parameters → `RepoPath`** and set it to the
   absolute path of your clone, with no trailing slash
   (e.g. `C:\code\E_commerce_DA`). Every query repoints itself.
4. **Refresh.**

Power BI Desktop is Windows-only, and Excel for Mac has no Power Pivot or Data
Model. See [RUNNING_ON_MACOS.md](RUNNING_ON_MACOS.md) for the three routes that
do work on a Mac.

## The model

```
        ┌──────────┐          ┌──────────┐
        │   Date   │          │ Country  │
        └────┬─────┘          └────┬─────┘
             │ 1                 1 │
             │                     │
             │ *                 * │
        ┌────┴─────────────────────┴────┐
        │            Orders             │
        └───────────────────────────────┘
                       │
                 ┌─────┴──────┐
                 │ _Measures  │  (measure-only, no relationships)
                 └────────────┘
```

**Orders** — one row per `order_id`. 21,864 source rows in, 21,719 out after
removing 145 duplicate ids.

**Country** — built from the union of the source lookup and every country code
actually present in Orders, so no order can fall out of the model for want of a
dimension row. The lookup is complete: the US and Canada are both present and
both map to North America. The trap is the *value* — North America's region code
is the literal string `NA`, which pandas and most CSV loaders read as a missing
value. Power Query does not, which is why this model and the Tableau views were
always correct while the Python-exported CSVs were not. The query renames `NA`
to `NAMER` at load so the collision cannot travel downstream, and
`region_source` records whether a row needed that rename
(`source lookup (NA renamed)` / `source lookup` / `unmapped`), which makes the
exposure measurable rather than invisible.

**Date** — contiguous DAX calendar, Jan 2019 to Dec 2021, marked as the model's
date table so `SAMEPERIODLASTYEAR` and `TOTALYTD` have a gapless calendar.

## Cleaning rules, and why each one exists

The Power Query steps in `Orders.tmdl` mirror the SQL one for one:

| # | Rule | Rows | Reasoning |
|---|---|---|---|
| 1 | Keep one row per `order_id`, earliest first | 145 removed | Duplicate ids would double-count revenue |
| 2 | Parse `purchase_ts` from three formats | 10 non-ISO, 4 with an impossible `13:62` minute, 1 whitespace-only | A single-format parse would silently null out ~15 orders |
| 3 | Collapse `27inches 4k gaming monitor` into `27in 4K gaming monitor` | 61 | One SKU, two spellings, otherwise split across two bars |
| 4 | Blank channel / account method → `"unknown"` | 83 blank + 47 already `unknown` | Blanks vanish from a GROUP BY; `unknown` shows up and can be questioned |
| 5 | Flag `$0`/null price as not revenue-eligible | 34 | A $0 order is a data artifact, not a sale |
| 6 | Rename region `NA` → `NAMER` at load | 26 lookup rows, 52.2% of revenue | `NA` is North America's code **and** the default null token in pandas and most CSV loaders **and** Namibia's ISO country code. Renaming makes the collision structurally impossible downstream. There is no analyst patch — an earlier version of this model hand-patched six country codes to work around what was really a loading bug |

Rule 5 flags rather than filters. The 34 rows stay in the table so
`[Excluded Zero-Price Orders]` can still count them — a defect you removed at
load time is a defect nobody can audit.

The remaining unmapped codes are small Caribbean territories. They are
deliberately **not** assigned, because bucketing them is a business decision
(LATAM or NAMER?) rather than an analyst's, and `[Unmapped Revenue %]` reports
exactly how much revenue is left sitting unassigned.

## The report

| Page | What it answers |
|---|---|
| **Executive summary** | Revenue, orders, AOV, refund rate; revenue by month, region, and channel |
| **Channel** | Full channel scorecard, share by year, monthly trend by channel, and the year-over-year mix shift in percentage points |
| **Region and product** | Region scorecard with rank and top product, product-by-region matrix, and two cards quantifying how much of the regional view rests on reading `NA` as text (52.2%) |
| **Data quality** | The known defects as live measures, the country→region resolution table, and the model check |

## Measures

36 measures in `_Measures`, grouped as: core volume and value, refunds, share
and mix, time intelligence, ranking, fulfilment, data quality, and validation.
The full annotated list is in [`dax/measures.dax`](dax/measures.dax).

34 are placed on a page. Two — `[Revenue YTD]` and
`[Revenue % of Visible Total]` — are in the field list for ad-hoc use but not on
a default page.

Two worth calling out:

**`Channel Mix Shift (pp)`** expresses the year-over-year change in a channel's
revenue share in *percentage points*, not as a percentage change. A share that
moves from 8.2% to 14.3% has risen 6.1 points — reporting it as "+74%" is
technically true and reliably misleading.

**`Avg Days to Ship`** excludes the ~2,000 orders whose ship date precedes their
purchase date. Averaging a known-impossible negative into a fulfilment KPI would
quietly flatter it.

## Validation

The `[Model Check]` measure sits on a card on the Data quality page:

```dax
Model Check =
VAR ExpectedRevenue = 6103484.09
VAR ExpectedOrders = 21685
VAR ActualRevenue = ROUND ( CALCULATE ( [Total Revenue], ALL ( Orders ), ALL ( Country ), ALL ( 'Date' ) ), 2 )
VAR ActualOrders  = CALCULATE ( [Order Count], ALL ( Orders ), ALL ( Country ), ALL ( 'Date' ) )
RETURN
    IF (
        ActualRevenue = ExpectedRevenue && ActualOrders = ExpectedOrders,
        "OK - matches SQL baseline",
        "MISMATCH: " & FORMAT ( ActualRevenue, "$#,0.00" ) & " / " & FORMAT ( ActualOrders, "#,0" ) & " orders"
    )
```

If a Power Query step is ever edited in a way that changes the grain, the card
says MISMATCH on the next refresh instead of the number quietly drifting.

A second check runs outside the model. `tools/validate_report.py` parses the
TMDL and cross-references every field binding in `report.json` against it, so a
renamed measure surfaces as a build failure rather than as a blank visual:

```bash
python3 powerbi/tools/build_report.py
python3 powerbi/tools/validate_report.py
```

Baseline the model must reproduce:

| | |
|---|---|
| Revenue-eligible orders | 21,685 |
| Total revenue | $6,103,484.09 |
| AOV | $281.46 |
| Refund rate | 15.9% |
| direct / email / affiliate / social | 84.7% / 9.9% / 3.6% / 1.1% |
| NAMER / EMEA / APAC / LATAM / unmapped | 52.1% / 29.6% / 12.0% / 5.5% / 0.8% |

## Known limitations

- `RepoPath` is an absolute local path. Publishing this to the Power BI Service
  with scheduled refresh would need the CSVs behind a gateway or moved to cloud
  storage; as a portfolio artifact it refreshes locally.
- The Date table is hard-coded to 2019–2021. It is a fixed historical extract,
  so a dynamic `MIN`/`MAX` calendar would add moving parts for no benefit.
- Refund rate is order-weighted by default. `[Refund Rate by Value]` gives the
  dollar view; the two differ slightly because refunded orders skew higher in
  price.
