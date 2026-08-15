#!/usr/bin/env python3
"""
Export the GameZone workbook to the CSV extracts in data/.

Run from the repo root:

    python3 scripts/export_workbook_to_csv.py

WHY THIS SCRIPT EXISTS
----------------------
The region code for North America in this source is the literal two-character
string "NA". That is also the default missing-value token in pandas, in most
CSV loaders, and in Excel's NA() function -- and it is Namibia's ISO 3166-1
alpha-2 country code, which appears in the COUNTRY_CODE column of the same
workbook.

A default `pd.read_excel(path)` therefore turns every North American region
value into NaN and every Namibian country code into NaN. Exported to CSV, both
come out as empty strings, and the defect is baked into the extract before any
analysis runs. That is exactly how an earlier version of this repo came to
report that the lookup had "no United States entry": the entry was there, the
value evaporated on load.

`keep_default_na=False` stops that. `na_values=[""]` keeps genuinely empty
cells null. Do not remove either argument.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "data_analysis" / "gamezone-orders-data.xlsx"
OUT = ROOT / "data"

# The only safe way to read this workbook. See module docstring.
READ_OPTS = dict(keep_default_na=False, na_values=[""])


def main() -> None:
    orders = pd.read_excel(WORKBOOK, sheet_name="orders", dtype=str, **READ_OPTS)
    orders.columns = [c.lower() for c in orders.columns]
    orders.to_csv(OUT / "orders.csv", index=False)

    region = pd.read_excel(WORKBOOK, sheet_name="region_cleaned", dtype=str, **READ_OPTS)
    region.columns = [c.lower() for c in region.columns]
    region.to_csv(OUT / "region_lookup.csv", index=False)

    # Loud, cheap regression check: if either of these prints the "naive" value,
    # null coercion has crept back in.
    codes = orders["country_code"].dropna().nunique()
    namer = (region["region_cleaned"].fillna("").str.upper() == "NA").sum()
    print(f"orders.csv         : {len(orders):,} rows, {codes} distinct country codes (expect 151)")
    print(f"region_lookup.csv  : {len(region):,} rows, {namer} rows coded NA/North America (expect 26)")
    if codes != 151 or namer != 26:
        raise SystemExit("FAIL: null coercion detected on load -- check keep_default_na")
    print("PASS: 'NA' survived the read as a literal string")


if __name__ == "__main__":
    main()
