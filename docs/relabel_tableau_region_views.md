# Relabelling the region views from `NA` to `NAMER`

**Nothing here is a correctness fix.** Both region visuals are already right.
Tableau reads the workbook through Excel, and Excel's `VLOOKUP` returns `NA` as
a text string rather than coercing it to a null — which is exactly why the
dashboards survived a defect that broke the Python-exported CSVs. `usd_price/Region.png`
shows North America leading EMEA in every month, and the PDF's region legend
lists `NA` as a real category.

What is left is a label. The legend says `NA`, the rest of the repo says `NAMER`,
and the 42 unmapped orders show up as a bare `Null`. This fixes both.

Affected views (two, no others):

- `data_analysis/Tableau_deep_dive/usd_price_Region.png` — "usd_price/Region"
- `data_analysis/Strategy_manager_dash.pdf` — "Sales by Regions" and "Region Sales Mix"

---

## Recommended: a calculated field (about 2 minutes)

The Tableau workbook connects to the `orders_cleaned` sheet, which carries its
own `REGION` column (`NA` 11,305 rows, `EMEA` 6,693, `APAC` 2,581, `LATAM` 1,243,
blank 42). Nothing needs reconnecting — just derive a clean field from it.

1. In the data pane, **Analysis → Create Calculated Field**.
2. Name it `Region (NAMER)` and paste:

   ```
   IF TRIM([Region]) = "NA" OR TRIM([Region]) = "North America" THEN "NAMER"
   ELSEIF TRIM([Region]) = "" OR ISNULL([Region]) THEN "Unmapped"
   ELSE TRIM([Region])
   END
   ```

3. Open the **usd_price/Region** sheet. Drag `Region (NAMER)` onto **Colour**,
   replacing the old `Region` pill. The legend should now read
   `APAC, EMEA, LATAM, NAMER, Unmapped`.
4. Do the same on the **Sales by Regions** and **Region Sales Mix** sheets in the
   Strategy Manager dashboard.
5. Sanity check before exporting — hover the NAMER series at its December 2020
   peak. It should still lead EMEA, and a NAMER-only view should total
   **$3,184,070.17** across **11,214** revenue-eligible orders. If either number
   moved, stop: the calculated field is picking up the wrong column.
6. Export: **Worksheet → Export → Image** for the PNG (overwrite
   `usd_price_Region.png`), and **Dashboard → Export PDF** for
   `Strategy_manager_dash.pdf`.
7. Once both are regenerated, drop the caveat paragraph under "Revenue by Region"
   in the root `README.md` and remove the relabel line from Future Improvements.

Leave the workbook's own `REGION` column alone. It is the evidence for the
root-cause writeup — the whole story depends on the source really containing the
literal string `NA`.

---

## Alternative: connect a NAMER-labelled lookup

Use this if you would rather rebuild the region views against a proper region
dimension than derive one in the view.

`data/region_lookup_namer.csv` is generated from the workbook's `region_cleaned`
sheet with the North American label already resolved:

| country_code | region |
|---|---|
| `US` | `NAMER` |
| `CA` | `NAMER` |
| `NA` (Namibia) | `EMEA` |
| … | 192 rows: 100 EMEA, 44 APAC, 26 NAMER, 22 LATAM |

1. **Data → New Data Source → Text file**, pick `data/region_lookup_namer.csv`.
2. Join it to `orders_cleaned` on `COUNTRY_CODE = country_code`, **left join**, so
   the 37 orders with a blank country code survive the join.
3. Use the new `region` field in place of `REGION`. Blank joins come through as
   null — relabel them `Unmapped` with a calculated field or in the colour legend.
4. Same sanity check and export steps as above.

**Regenerate the CSV** whenever the workbook changes:

```bash
python3 scripts/export_workbook_to_csv.py     # refreshes data/region_lookup.csv first
```

Then rebuild `region_lookup_namer.csv` from it — it is the `region_cleaned`
column with `NA` and `North America` collapsed to `NAMER`, matching the
`stg_region` view in `sql/gamezone_channel_region_analysis.sql` rule for rule.

---

## Why `NAMER` and not `NA`

`NA` means three different things in this dataset: North America in the region
column, Namibia in the country column, and "missing" to pandas, most CSV
loaders, and Excel's own `NA()` function. Any downstream tool that reads it as
the third meaning silently deletes 52.2% of the business. Renaming the value is
the only fix that does not depend on every future reader remembering to be
careful. See the root-cause section of the main [`README.md`](../README.md).
