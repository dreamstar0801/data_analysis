# GameZone Sales Analysis

## Overview

This project analyzes GameZone sales data using Excel Pivot Tables and Tableau dashboards to identify sales trends, customer behavior, and product performance.

The analysis focuses on understanding:

* Revenue distribution across products
* Regional sales performance
* Marketing channel effectiveness
* Customer account creation methods
* Order volume trends

## Tools Used

* Microsoft Excel

  * Data Cleaning
  * Pivot Tables
  * Pivot Charts
* Tableau

  * Dashboard Creation
  * Data Visualization
* SQL (DuckDB)

  * Reproducible channel and regional analysis
  * Data quality auditing
* Git & GitHub

  * Version Control
  * Project Documentation

## SQL Analysis

The channel and regional cuts from the Tableau dashboards are reproduced in SQL so the numbers are auditable and re-runnable rather than locked inside pivot tables.

**File:** [`sql/gamezone_channel_region_analysis.sql`](sql/gamezone_channel_region_analysis.sql)

```bash
duckdb -c ".read sql/gamezone_channel_region_analysis.sql"
```

The script runs end to end with no setup against the CSV extracts in [`data/`](data/). To run it on a warehouse instead, swap the two staging views at the top for your own tables; the rest is standard SQL.

The extracts themselves are regenerated from the workbook with:

```bash
python3 scripts/export_workbook_to_csv.py
```

That script disables pandas' default null coercion, which is load-bearing here — see [Root cause](#root-cause-a-region-code-that-collides-with-the-null-token).

| Query | Question it answers |
|---|---|
| Q1 | Revenue and order contribution by marketing channel, with AOV and refund rate |
| Q2 | Is the channel mix shifting year over year? |
| Q3 | Revenue by region, with unmapped revenue kept visible |
| Q4 | Region x channel matrix: where each channel actually works |
| Q5 | Top three products per region by revenue |
| Q6 | Data quality audit behind every cleaning rule |
| Q7 | Region mapping guard: a PASS/FAIL regression test on the bug described below |

### What the SQL shows

Across 21,685 revenue-eligible orders and $6.10M in revenue (2019-2021):

* **This is a direct-traffic business.** Direct accounts for 84.7% of revenue, email 9.9%, affiliate 3.6%, social media 1.1%.
* **Affiliate carries the highest basket.** $311 AOV against a $299 direct average, on 3% of orders. That is where an incremental-spend question sits.
* **The mix is moving slowly.** Direct's revenue share fell from 85.6% in 2019 to 81.4% in 2021 while email rose from 8.2% to 14.3%.
* **NAMER is 52.2% of revenue** ($3,184,070), EMEA 30.3% ($1,849,772), APAC 12.0% ($731,391), LATAM 5.5% ($334,724).
* **The region column carries a code that reads as a null.** North America's region code in this source is the literal string `NA`, which most loaders treat as a missing value. Read naively, 52.2% of revenue disappears into a null bucket and EMEA looks like the largest region. See [Root cause](#root-cause-a-region-code-that-collides-with-the-null-token) below; Q7 is the regression test.
* **$3,527 of revenue is genuinely unmapped**, across 42 orders: 37 with a blank country code and 5 coded `AP` or `EU` — region abbreviations that leaked into a country column. It is kept visible in the output rather than hidden.
* **9% of orders ship before they are purchased**, by up to 149 days. Average shipping time is computed over valid rows only and the affected share is reported alongside it.

### Root cause: a region code that collides with the null token

The regional revenue split reported EMEA as the largest market. It is not. North America is 52.2% of revenue.

The lookup table is not missing the United States or Canada; both are present and correctly mapped:

| `COUNTRY_CODE` | `REGION` | `REGION_CLEANED` |
|---|---|---|
| `US` | `NA` | `NA` |
| `CA` | `North America` | `NA` |

The defect is that North America's region code is the literal string `NA`, which pandas and most CSV loaders treat as a missing value by default. Loading the region column without disabling null coercion voids every North American row, moving $3,184,070 of $6,103,484 into a null bucket and promoting EMEA to apparent first place.

The same two characters are also Namibia's ISO 3166-1 alpha-2 country code, present in the `COUNTRY_CODE` column of this dataset, where it maps to EMEA. A default read of that column returns 150 distinct codes rather than the true 151, for the same reason. One string, three meanings, two columns.

A third factor made it easy to miss: in `region_uncleaned`, North America is written two ways — `NA` on 21 rows and `North America` on 5. The cleaning step collapsed both to `NA`, which is the right normalization onto the wrong target value, because it standardized on the colliding token.

**The fix is structural, not careful parsing.** Two changes, both in the repo:

1. Every read of the workbook uses `keep_default_na=False, na_values=[""]` (see [`scripts/export_workbook_to_csv.py`](scripts/export_workbook_to_csv.py)); the DuckDB reads set `nullstr = ''` explicitly.
2. The `stg_region` staging view renames the value to `NAMER`, so the collision cannot recur downstream regardless of how the next reader loads it. `NAMER` is used everywhere after that point — SQL, dashboards, and this README.

Parsing carefully depends on every future reader remembering to parse carefully. Eliminating the token does not.

**Note on the original diagnosis.** This repo previously attributed the error to a lookup table with no United States entry, and patched six country codes by hand to work around it. That was wrong. The mapping existed; the value was evaporating on load. The corrected diagnosis was confirmed by re-reading the source with `keep_default_na=False`, at which point `US → NA` was plainly present. The hand patch has been removed, the CSV extracts in [`data/`](data/) — which had the same defect baked into them at export time — have been regenerated, and unmapped revenue fell from a reported $49K to the true $3,527. *(Corrected August 2026.)*

### Cleaning rules applied

Each rule exists because of a row count in Q6:

| Issue | Rows | Treatment |
|---|---|---|
| Duplicate `order_id` | 145 | Deduplicated, one row per order |
| `purchase_ts` in MM-DD-YYYY, 4 with an impossible minute value | 10 | Fallback parse |
| `purchase_ts` blank | 1 | Left null, excluded from year-over-year cuts |
| `usd_price` of 0 or null | 34 | Excluded from revenue (29 zero, 5 null) |
| Blank or unknown `marketing_channel` | 129 | Bucketed as `unknown`, not dropped |
| `27inches 4k gaming monitor` vs `27in 4K gaming monitor` | 61 | Collapsed to one SKU |
| `ship_ts` earlier than `purchase_ts` | 2,000 | Flagged, excluded from ship-time averages |
| Country code blank | 37 | Falls into `Unmapped`, reported |
| Country code absent from the lookup (`AP`, `EU`) | 5 | Falls into `Unmapped`, reported |
| Region value `NA` (North America) | 26 lookup rows | Renamed `NAMER` in staging so it cannot be read as null |

The dataset carries **151 distinct country codes** (a default pandas read reports 150, because Namibia's code is `NA`), 21,864 raw order rows, 21,719 after deduplication, and 21,685 revenue-eligible orders totalling $6,103,484.09.

## Dataset

The dataset contains customer orders, product information, regions, marketing channels, and pricing data.

Key fields include:

* Product Name
* Order Count
* Marketing Channel
* Region
* USD Price
* Account Creation Method

## Key Insights

### Product Performance

* Compared order volume across products.
* Identified top-performing products based on sales activity.

### Revenue Analysis

* Analyzed product pricing and revenue distribution.
* Examined average selling prices by product category.

### Regional Trends

* Compared sales performance across regions.
* Highlighted regions generating the highest revenue.

### Marketing Channel Analysis

* Evaluated sales contribution by marketing channel.
* Compared order volume and pricing metrics across channels.

### Customer Acquisition

* Analyzed account creation methods to understand customer onboarding preferences.

## Dashboard Screenshots

### Account Creation Method

![Account Creation Method](data_analysis/Tableau_deep_dive/acount_create_method.png)

### Product Order Count

![Product Order Count](data_analysis/Tableau_deep_dive/product_order_count.png)

### Product Order Count by Marketing Channel

![Product Order Count by Marketing Channel](data_analysis/Tableau_deep_dive/product_order_count_per_channel.png)

### Average Product Price

![Average Product Price](data_analysis/Tableau_deep_dive/usd_avg_price_product.png)

### Product Price Distribution

![Product Price Distribution](data_analysis/Tableau_deep_dive/usd_price.png)

### Revenue by Region (NAMER leads throughout)

![Revenue by Region](data_analysis/Tableau_deep_dive/usd_price_Region.png)

*This view is correct: it was built on the workbook through Excel's `VLOOKUP`, which returns `NA` as text and does not coerce it to null, so North America is present and leading in every month. The legend still reads `NA`; that series is **NAMER**. The `Null` series at the bottom is the 42 unmapped orders ($3,527). The chart is a Tableau export and cannot be relabelled in place — it is queued for regeneration with the `NAMER` label.*

### Revenue by Marketing Channel

![Revenue by Marketing Channel](data_analysis/Tableau_deep_dive/usd_price_marketing_channel.png)

### Revenue by Product

![Revenue by Product](data_analysis/Tableau_deep_dive/usd_price_product.png)

## Repository Structure

```text
E_commerce_DA/
│
├── README.md
│
├── sql/
│   └── gamezone_channel_region_analysis.sql
│
├── scripts/
│   └── export_workbook_to_csv.py   # regenerates data/ with null coercion disabled
│
├── data/
│   ├── orders.csv            # extract of the orders sheet, raw and uncleaned
│   └── region_lookup.csv     # country code to region mapping (raw + cleaned)
│
└── data_analysis/
    ├── Tableau_deep_dive/
    │   ├── acount_create_method.png
    │   ├── product_order_count.png
    │   ├── product_order_count_per_channel.png
    │   ├── usd_avg_price_product.png
    │   ├── usd_price.png
    │   ├── usd_price_Region.png
    │   ├── usd_price_marketing_channel.png
    │   └── usd_price_product.png
    │
    ├── gamezone-orders-data.xlsx
    └── Strategy_manager_dash.pdf
```

## Future Improvements

* Build an interactive Tableau dashboard
* Add KPI summary metrics
* Regenerate the region chart and `Strategy_manager_dash.pdf` with the `NAMER` label (both are currently correct but still show the legacy `NA` legend)
* Decide with the business how the 5 `AP` / `EU` orders and the 37 blank country codes should be attributed
* Perform deeper customer segmentation analysis
