# Running this model on macOS

Power BI Desktop is Windows-only, and **Excel for Mac does not include Power
Pivot or the Excel Data Model** — there is no add-in, hidden setting, or
supported workaround that enables it. That rules out the obvious "just use
Power Pivot on the Mac" path.

Three routes that do work, in the order I would try them.

---

## 1. Power BI Service in the browser

Works on any OS. Sign in at [app.powerbi.com](https://app.powerbi.com), upload
the two CSVs from `data/`, build the model in the web editor, and add the
measures from [`dax/measures.dax`](dax/measures.dax) one at a time.

**Prerequisite:** Power BI sign-up requires a **work or school email address**.
Personal addresses (gmail, outlook.com, yahoo) are refused at registration. A
university `.edu` address qualifies, so this is usually the free route for
students.

What you get: real DAX authoring, a published report with a shareable link.
What you give up: the model editor in the browser is more limited than Desktop,
and the PBIP in this folder cannot be opened there directly — you would rebuild
the model through the web UI using the M and DAX in this repo as the spec.

## 2. Windows in a VM

The faithful option, and the one that matches what job postings mean by
"Power BI".

- **UTM** — free, open source, runs Windows 11 ARM on Apple Silicon.
- **Parallels Desktop** — paid, noticeably smoother, free trial available.

Install Power BI Desktop inside Windows, then open `powerbi/GameZone.pbip` and
follow the setup in [README.md](README.md#opening-it). This is the only route
that opens the project in this folder as-is, with the report pages intact.

## 3. Author the DAX, verify the logic elsewhere

DAX measures are text. They can be written, reviewed, and reasoned about
without a running engine — which is what `dax/measures.dax` is: a complete,
annotated measure library that stands on its own in the repo.

To check that the *logic* is right without Windows, the SQL in
[`sql/gamezone_channel_region_analysis.sql`](../sql/gamezone_channel_region_analysis.sql)
computes the same aggregates and runs anywhere DuckDB does, including macOS:

```bash
brew install duckdb
duckdb -c ".read sql/gamezone_channel_region_analysis.sql"
```

Every measure in the model is pinned to those numbers by `[Model Check]`, so
agreement between the two is meaningful rather than circular.

---

## What to say about this in an interview

Do not claim daily Power BI Desktop use if the work was done this way. The
honest and stronger version:

> I built the semantic model in PBIP format — TMDL for the model, DAX for the
> measures — so it lives in git as reviewable text rather than a binary file.
> The cleaning logic is in Power Query and mirrors a SQL script in the same
> repo, and there's a DAX measure on the report that fails loudly if the two
> ever disagree.

That describes something most Power BI users have never done, and it is true.
