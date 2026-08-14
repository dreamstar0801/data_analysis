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
* Power BI

  * Star-schema semantic model (TMDL)
  * Power Query cleaning pipeline
  * DAX measure library, including time intelligence and mix-shift analysis
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

| Query | Question it answers |
|---|---|
| Q1 | Revenue and order contribution by marketing channel, with AOV and refund rate |
| Q2 | Is the channel mix shifting year over year? |
| Q3 | Revenue by region, with unmapped revenue kept visible |
| Q4 | Region x channel matrix: where each channel actually works |
| Q5 | Top three products per region by revenue |
| Q6 | Data quality audit behind every cleaning rule |

### What the SQL shows

Across 21,685 revenue-eligible orders and $6.10M in revenue (2019-2021):

* **This is a direct-traffic business.** Direct accounts for 84.7% of revenue, email 9.9%, affiliate 3.6%, social media 1.1%.
* **Affiliate carries the highest basket.** $311 AOV against a $299 direct average, on 3% of orders. That is where an incremental-spend question sits.
* **The mix is moving slowly.** Direct's revenue share fell from 85.6% in 2019 to 81.4% in 2021 while email rose from 8.2% to 14.3%.
* **North America is 52% of revenue**, EMEA 30%, APAC 12%, LATAM 5%.
* **The region lookup is broken for the largest market.** The source table has no region for the United States and drops Canada during cleaning, which sends roughly half of all revenue into an unmapped bucket and makes EMEA appear to be the leading region. The script patches six North American codes and reports the remaining $49K of unmapped revenue rather than hiding it.
* **9% of orders ship before they are purchased**, by up to 149 days. Average shipping time is computed over valid rows only and the affected share is reported alongside it.

### Cleaning rules applied

Each rule exists because of a row count in Q6:

| Issue | Rows | Treatment |
|---|---|---|
| Duplicate `order_id` | 145 | Deduplicated, one row per order |
| `purchase_ts` in MM-DD-YYYY, 4 with an impossible minute value | 11 | Fallback parse, 1 blank left null |
| `usd_price` of 0 or null | 34 | Excluded from revenue |
| Blank or unknown `marketing_channel` | 129 | Bucketed as `unknown`, not dropped |
| `27inches 4k gaming monitor` vs `27in 4K gaming monitor` | 61 | Collapsed to one SKU |
| `ship_ts` earlier than `purchase_ts` | ~2,000 | Flagged, excluded from ship-time averages |
| Country codes missing or absent from the lookup | 43 | Fall into `Unmapped`, reported |

## Power BI Model

The same analysis as a semantic model and four-page report, stored in **PBIP**
format: TMDL for the model and JSON for the report, so the DAX and the Power
Query steps are reviewable in a diff rather than sealed inside a binary `.pbix`.

**Folder:** [`powerbi/`](powerbi/) — open [`powerbi/GameZone.pbip`](powerbi/GameZone.pbip)
in Power BI Desktop and point the `RepoPath` parameter at your clone.

| | |
|---|---|
| Model | Star schema: `Orders` fact joined to `Country` and a marked `Date` table |
| Cleaning | Power Query steps mirroring the SQL script one for one |
| Measures | 35 in [`powerbi/dax/measures.dax`](powerbi/dax/measures.dax) — revenue, AOV, refund rate, share, YoY, ranking, fulfilment, data quality |
| Report | Executive summary, Channel, Region and product, Data quality |

Two design decisions worth naming:

* **The `$0` rows are flagged, not filtered.** All 21,719 deduplicated rows load; `is_revenue_eligible` marks the 34 artifacts and every revenue measure filters on that flag. A defect removed at load time is a defect nobody can audit.
* **The model tests itself.** `[Model Check]` sits on a card and returns OK only while the model reproduces `sql/gamezone_channel_region_analysis.sql` exactly — $6,103,484.09 across 21,685 orders. If a query step is ever edited in a way that changes the grain, the card says MISMATCH instead of the number quietly drifting.

Power BI Desktop is Windows-only and Excel for Mac has no Power Pivot; see
[`powerbi/RUNNING_ON_MACOS.md`](powerbi/RUNNING_ON_MACOS.md).

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

### Revenue by Region

![Revenue by Region](data_analysis/Tableau_deep_dive/usd_price_Region.png)

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
├── powerbi/
│   ├── GameZone.pbip                 # open this in Power BI Desktop
│   ├── README.md                     # model design, cleaning rules, validation
│   ├── RUNNING_ON_MACOS.md           # options when you do not have Windows
│   ├── GameZone.SemanticModel/       # TMDL: tables, relationships, measures
│   ├── GameZone.Report/              # report.json: 4 pages, 36 visuals
│   └── dax/
│       └── measures.dax              # the measure library as portable text
│
├── data/
│   ├── orders.csv            # extract of the orders sheet, raw and uncleaned
│   └── region_lookup.csv     # country code to region mapping
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

* Publish the Power BI report to the service with scheduled refresh, which means moving the CSVs behind a gateway or into cloud storage
* Extend the region lookup so North American and Caribbean country codes map cleanly, and retire the six-code analyst patch
* Perform deeper customer segmentation analysis, starting with repeat-purchase rate by acquisition channel
* Add a cohort view: does the channel a customer arrives through predict their second order?
