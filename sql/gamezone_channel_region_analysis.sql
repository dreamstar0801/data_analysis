/* ============================================================================
   GameZone: Marketing Channel Contribution and Regional Revenue
   ----------------------------------------------------------------------------
   Purpose : Reproduce the channel-attribution and regional-revenue cuts from
             the Excel/Tableau analysis in SQL, so the numbers are auditable
             and re-runnable rather than locked inside pivot tables.

   Author  : Sohee Cho
   Source  : data_analysis/gamezone-orders-data.xlsx  (21,864 raw order rows,
             2019-01 through 2021-12, 150 country codes)
   Engine  : Written and tested on DuckDB (runs directly against the CSVs in
             /data with no setup). To run on Postgres / BigQuery / Snowflake,
             replace the two staging views in STEP 1 with your own tables and
             the rest of the script works unchanged, except:
               - try_strptime()  -> TO_TIMESTAMP / PARSE_DATETIME / TRY_TO_DATE
               - the || string concat and window functions are ANSI standard

   How to run:
       duckdb -c ".read sql/gamezone_channel_region_analysis.sql"
     or from the DuckDB CLI in the repo root:
       .read sql/gamezone_channel_region_analysis.sql

   Contents:
       STEP 1  Staging     - load raw orders and the country -> region lookup
       STEP 2  Cleaning    - dedupe, normalize, parse dates, attach region
       Q1      Revenue and order contribution by marketing channel
       Q2      Channel mix shift by year (is the mix moving?)
       Q3      Revenue by region, with unmapped revenue made visible
       Q4      Region x channel matrix (where each channel actually works)
       Q5      Top product per region by revenue
       Q6      Data quality audit (the checks behind the cleaning rules)
   ========================================================================== */


/* ============================================================================
   STEP 1 - STAGING
   Raw, untouched. Everything is read as text so that malformed timestamps
   fail loudly in STEP 2 instead of silently disappearing at load time.
   ========================================================================== */

CREATE OR REPLACE VIEW stg_orders AS
SELECT *
FROM read_csv('data/orders.csv', header = true, all_varchar = true);

CREATE OR REPLACE VIEW stg_region_lookup AS
SELECT *
FROM read_csv('data/region_lookup.csv', header = true, all_varchar = true);


/* ----------------------------------------------------------------------------
   Region patch.
   The source lookup has no region for the United States, and the value for
   Canada ("North America") is dropped during cleaning. Left alone, that sends
   roughly half of all revenue into an "Unmapped" bucket and makes EMEA look
   like the largest region, which is wrong. These six codes are patched to
   NAMER on geography alone. The remaining unmapped codes are all small
   Caribbean territories; they are deliberately NOT assigned, because bucketing
   them is a business decision (LATAM vs NAMER) rather than an analyst's, and
   Q6 reports exactly how much revenue is left sitting unassigned.
---------------------------------------------------------------------------- */
CREATE OR REPLACE VIEW region_patch AS
SELECT * FROM (VALUES
    ('US', 'NAMER'),
    ('CA', 'NAMER'),
    ('PR', 'NAMER'),
    ('VI', 'NAMER'),
    ('BM', 'NAMER'),
    ('GL', 'NAMER')
) AS t(country_code, region);


/* ============================================================================
   STEP 2 - CLEANING
   Mirrors the cleaning applied in the Excel workbook, stated as code:
     1. 145 order_ids appear more than once -> keep one row per order_id
     2. "27inches 4k gaming monitor" and "27in 4K gaming monitor" are the
        same SKU -> collapse to one name
     3. blank marketing_channel / account_creation_method -> 'unknown', so
        they show up in the output instead of vanishing from GROUP BY
     4. purchase_ts arrives in two formats (ISO, and 11 rows of MM-DD-YYYY,
        4 of which carry an impossible minute value "13:62") -> parse both,
        falling back to a date-only parse when the time component is invalid
     5. usd_price of 0 or NULL (34 rows) -> excluded from revenue, since a
        $0 order is a data artifact, not a sale
   ========================================================================== */

CREATE OR REPLACE VIEW orders_clean AS
WITH deduped AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_id
            ORDER BY o.purchase_ts, o.user_id
        ) AS rn
    FROM stg_orders o
),
typed AS (
    SELECT
        d.order_id,
        d.user_id,
        d.product_id,

        /* two timestamp formats + one impossible-minute variant */
        COALESCE(
            TRY_CAST(NULLIF(TRIM(d.purchase_ts), '') AS TIMESTAMP),
            try_strptime(NULLIF(TRIM(d.purchase_ts), ''), '%m-%d-%Y %H:%M:%S'),
            try_strptime(SUBSTR(TRIM(d.purchase_ts), 1, 10), '%m-%d-%Y')
        )                                              AS purchase_ts,
        TRY_CAST(NULLIF(TRIM(d.ship_ts),   '') AS TIMESTAMP)  AS ship_ts,
        TRY_CAST(NULLIF(TRIM(d.refund_ts), '') AS TIMESTAMP)  AS refund_ts,

        /* one SKU, two spellings */
        CASE LOWER(TRIM(d.product_name))
            WHEN '27inches 4k gaming monitor' THEN '27in 4K gaming monitor'
            ELSE TRIM(d.product_name)
        END                                            AS product_name,

        COALESCE(NULLIF(LOWER(TRIM(d.marketing_channel)), ''), 'unknown')
                                                       AS marketing_channel,
        COALESCE(NULLIF(LOWER(TRIM(d.account_creation_method)), ''), 'unknown')
                                                       AS account_creation_method,
        LOWER(TRIM(d.purchase_platform))               AS purchase_platform,
        UPPER(TRIM(d.country_code))                    AS country_code,
        TRY_CAST(d.usd_price AS DOUBLE)                AS usd_price
    FROM deduped d
    WHERE d.rn = 1
)
SELECT
    t.*,
    EXTRACT(YEAR FROM t.purchase_ts)                   AS purchase_year,
    (t.refund_ts IS NOT NULL)                          AS is_refunded,
    DATE_DIFF('day', t.purchase_ts, t.ship_ts)         AS days_to_ship,
    COALESCE(
        p.region,                                    -- analyst patch first
        CASE
            WHEN UPPER(TRIM(rl.region)) IN ('EMEA', 'APAC', 'LATAM')
                THEN UPPER(TRIM(rl.region))
            WHEN UPPER(TRIM(rl.region)) = 'NORTH AMERICA'
                THEN 'NAMER'
            ELSE NULL                                -- 'X.x' and blanks
        END,
        'Unmapped'
    )                                                  AS region
FROM typed t
LEFT JOIN stg_region_lookup rl ON rl.country_code = t.country_code
LEFT JOIN region_patch       p  ON p.country_code  = t.country_code;


/* Revenue-eligible orders: one row per order, real dollars only.
   Every revenue figure below is built off this view so the denominator
   is identical across all queries. */
CREATE OR REPLACE VIEW orders_revenue AS
SELECT *
FROM orders_clean
WHERE usd_price IS NOT NULL
  AND usd_price > 0;


/* ============================================================================
   Q1 - Marketing channel contribution
   Question: which channels carry the business, and do they differ in basket
   size or refund behaviour?
   Expected output (2019-2021, 21,685 revenue-eligible orders, $6.10M):
     direct 84.7% of revenue, email 9.9%, affiliate 3.6%, social media 1.1%.
   The reading: this is a direct-traffic business, not a paid-acquisition one.
   Affiliate carries the highest AOV ($311) on the smallest order base, which
   is where the incremental spend question actually sits.
   ========================================================================== */
SELECT
    'Q1 channel contribution'                                     AS query_name,
    marketing_channel,
    COUNT(*)                                                      AS orders,
    ROUND(SUM(usd_price), 2)                                      AS revenue_usd,
    ROUND(100.0 * SUM(usd_price) / SUM(SUM(usd_price)) OVER (), 2) AS pct_of_revenue,
    ROUND(100.0 * COUNT(*)       / SUM(COUNT(*))       OVER (), 2) AS pct_of_orders,
    ROUND(AVG(usd_price), 2)                                      AS avg_order_value,
    ROUND(100.0 * SUM(CASE WHEN is_refunded THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                                  AS refund_rate_pct,
    ROUND(SUM(CASE WHEN is_refunded THEN 0 ELSE usd_price END), 2) AS net_revenue_usd
FROM orders_revenue
GROUP BY marketing_channel
ORDER BY revenue_usd DESC;


/* ============================================================================
   Q2 - Channel mix by year
   Question: is the mix moving, or is the channel split stable and therefore
   not the thing to spend planning time on?
   Reads as a share-of-revenue trend per channel, 2019 -> 2021.
   ========================================================================== */
WITH by_year AS (
    SELECT
        purchase_year,
        marketing_channel,
        SUM(usd_price) AS revenue_usd,
        COUNT(*)       AS orders
    FROM orders_revenue
    WHERE purchase_year IS NOT NULL
    GROUP BY purchase_year, marketing_channel
),
shares AS (
    SELECT
        by_year.*,
        100.0 * revenue_usd
              / SUM(revenue_usd) OVER (PARTITION BY purchase_year)
                                                    AS pct_of_year_revenue
    FROM by_year
)
SELECT
    'Q2 channel mix by year'                        AS query_name,
    purchase_year,
    marketing_channel,
    orders,
    ROUND(revenue_usd, 2)                           AS revenue_usd,
    ROUND(pct_of_year_revenue, 2)                   AS pct_of_year_revenue,
    ROUND(pct_of_year_revenue - LAG(pct_of_year_revenue) OVER (
              PARTITION BY marketing_channel ORDER BY purchase_year), 2)
                                                    AS share_change_vs_prior_yr_pp
FROM shares
ORDER BY purchase_year, revenue_usd DESC;


/* ============================================================================
   Q3 - Revenue by region
   Question: where does the money come from geographically?
   Note the 'Unmapped' row is kept in the output on purpose. Hiding it would
   overstate every other region's share. See Q6 for how much is still there.

   avg_days_to_ship is averaged over valid rows only. About 9% of orders carry
   a ship_ts earlier than their purchase_ts, by as much as 149 days; averaging
   those in returns a negative shipping time, which is a source defect rather
   than a result. The share of affected rows is reported alongside it instead
   of being quietly dropped.
   ========================================================================== */
SELECT
    'Q3 revenue by region'                                        AS query_name,
    region,
    COUNT(DISTINCT country_code)                                  AS countries,
    COUNT(*)                                                      AS orders,
    ROUND(SUM(usd_price), 2)                                      AS revenue_usd,
    ROUND(100.0 * SUM(usd_price) / SUM(SUM(usd_price)) OVER (), 2) AS pct_of_revenue,
    ROUND(AVG(usd_price), 2)                                      AS avg_order_value,
    ROUND(AVG(CASE WHEN days_to_ship >= 0 THEN days_to_ship END), 1)
                                                                  AS avg_days_to_ship,
    ROUND(100.0 * SUM(CASE WHEN days_to_ship < 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                  AS invalid_ship_date_pct
FROM orders_revenue
GROUP BY region
ORDER BY revenue_usd DESC;


/* ============================================================================
   Q4 - Region x channel matrix
   Question: does the channel mix hold everywhere, or is a channel doing real
   work in one region and nothing in another? This is the cut that turns
   "direct is 85% of revenue" into a regional planning decision.
   pct_of_region_revenue reads down within each region and sums to 100.
   ========================================================================== */
SELECT
    'Q4 region x channel'                           AS query_name,
    region,
    marketing_channel,
    COUNT(*)                                        AS orders,
    ROUND(SUM(usd_price), 2)                        AS revenue_usd,
    ROUND(100.0 * SUM(usd_price)
          / SUM(SUM(usd_price)) OVER (PARTITION BY region), 2)
                                                    AS pct_of_region_revenue,
    ROUND(100.0 * SUM(usd_price)
          / SUM(SUM(usd_price)) OVER (PARTITION BY marketing_channel), 2)
                                                    AS pct_of_channel_revenue,
    ROUND(AVG(usd_price), 2)                        AS avg_order_value
FROM orders_revenue
GROUP BY region, marketing_channel
ORDER BY region, revenue_usd DESC;


/* ============================================================================
   Q5 - Top product per region
   Question: is the product story the same in every region, or is regional
   revenue being driven by different SKUs?
   ========================================================================== */
WITH ranked AS (
    SELECT
        region,
        product_name,
        COUNT(*)                        AS orders,
        SUM(usd_price)                  AS revenue_usd,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY SUM(usd_price) DESC
        )                               AS revenue_rank
    FROM orders_revenue
    GROUP BY region, product_name
)
SELECT
    'Q5 top products by region'         AS query_name,
    region,
    revenue_rank,
    product_name,
    orders,
    ROUND(revenue_usd, 2)               AS revenue_usd
FROM ranked
WHERE revenue_rank <= 3
ORDER BY region, revenue_rank;


/* ============================================================================
   Q6 - Data quality audit
   Every cleaning rule in STEP 2 exists because of a row count below. This is
   the query to run first on a refresh: if any of these move materially, the
   numbers above need a second look before they go in front of anyone.
   ========================================================================== */
WITH raw AS (SELECT * FROM stg_orders)
SELECT 'Q6 data quality' AS query_name, check_name, failing_rows, note
FROM (
    SELECT 1 AS ord,
           'duplicate order_id (extra rows dropped)'          AS check_name,
           (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM raw) AS failing_rows,
           'deduped in STEP 2'                               AS note
    UNION ALL
    SELECT 2,
           'purchase_ts unparseable or blank',
           (SELECT COUNT(*) FROM orders_clean WHERE purchase_ts IS NULL),
           'excluded from year-over-year cuts only'
    UNION ALL
    SELECT 3,
           'purchase_ts in non-ISO MM-DD-YYYY format',
           (SELECT COUNT(*) FROM raw
             WHERE TRY_CAST(NULLIF(TRIM(purchase_ts), '') AS TIMESTAMP) IS NULL
               AND NULLIF(TRIM(purchase_ts), '') IS NOT NULL),
           'recovered by fallback parse'
    UNION ALL
    SELECT 4,
           'usd_price is 0 or NULL',
           (SELECT COUNT(*) FROM orders_clean
             WHERE usd_price IS NULL OR usd_price = 0),
           'excluded from all revenue figures'
    UNION ALL
    SELECT 5,
           'marketing_channel blank or unknown',
           (SELECT COUNT(*) FROM orders_clean WHERE marketing_channel = 'unknown'),
           'bucketed as unknown, not dropped'
    UNION ALL
    SELECT 6,
           'product_name spelling variants collapsed',
           (SELECT COUNT(*) FROM raw
             WHERE LOWER(TRIM(product_name)) = '27inches 4k gaming monitor'),
           'merged into 27in 4K gaming monitor'
    UNION ALL
    SELECT 7,
           'ship_ts earlier than purchase_ts',
           (SELECT COUNT(*) FROM orders_clean WHERE days_to_ship < 0),
           'about 9% of orders, up to 149 days early: flag to data owner'
    UNION ALL
    SELECT 8,
           'country_code missing',
           (SELECT COUNT(*) FROM orders_clean WHERE country_code IS NULL),
           'falls into Unmapped region'
    UNION ALL
    SELECT 9,
           'country_code not in region lookup',
           (SELECT COUNT(*) FROM orders_clean c
             WHERE c.country_code IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM stg_region_lookup r
                                WHERE r.country_code = c.country_code)),
           'non-ISO codes AP and EU present in source'
    UNION ALL
    SELECT 10,
           'orders still in Unmapped region after patch',
           (SELECT COUNT(*) FROM orders_revenue WHERE region = 'Unmapped'),
           'small Caribbean territories, needs a business decision'
    UNION ALL
    SELECT 11,
           'revenue sitting in Unmapped region (whole dollars)',
           (SELECT CAST(ROUND(SUM(usd_price), 0) AS BIGINT)
              FROM orders_revenue WHERE region = 'Unmapped'),
           'size of the region-mapping gap in dollars'
) AS checks
ORDER BY ord;
