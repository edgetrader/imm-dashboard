# IMM Dashboard

A synthetic investment-mandate monitoring panel and a static dashboard that reads it.

The dataset is generated from a specification — no real portfolio data is involved. The
dashboard reproduces the layout in `reference/dashboard-screenshot.png`, reads the
spreadsheet directly in the browser, and is driven entirely by one JSON config file.

![layout reference](reference/dashboard-screenshot.png)

## Quick start

```bash
python3.11 -m http.server 8321
```

Open <http://localhost:8321/>. Nothing needs building — **the page parses
`data/imm_data.xlsx` in the browser**, so editing the workbook or the config and
refreshing is enough.

To regenerate the data itself:

```bash
.venv/bin/python generate_imm_data.py     # -> data/imm_data.xlsx
```

## Layout

```
index.html                 the dashboard (self-contained CSS + JS, incl. an .xlsx reader)
config/settings.json       everything configurable, with its own inline reference
data/imm_data.xlsx         360 rows x 44 columns
generate_imm_data.py       panel generator (spec -> xlsx)
build_dashboard.py         optional JSON dump of the workbook (not used by the page)
reference/                 the layout this is modelled on
claude.md                  data specification + guidance for Claude Code
```

The server root must be the project root so `data/` and `config/` resolve. That is also a
GitHub Pages layout, so the same files can be served as a live site with no build step.

## The data

Twelve teams x 10 mandates x 3 month-ends (31 May, 30 Jun, 31 Jul 2026) = **360 rows**.

It is a genuine panel, not three independent samples. Static fields (name, team, entity,
fund ORR, KPI scope) are constant across a mandate's three rows; time-varying fields evolve
with month-to-month persistence via a **Gaussian-copula AR(1)** — persistence is applied to
a latent normal series which is then pushed through each field's truncated-normal quantile
function, so every field still matches its specified marginal distribution exactly at every
report date. Month-over-month correlation runs 0.90 (YTD returns) to 0.98 (AUM, 3-year
returns). Generation is seeded (`--seed 42`) and reproducible.

Column distributions are defined in [claude.md](claude.md).

> **These are synthetic numbers with known artefacts.** `excess_rtn_*` does not reconcile
> to portfolio minus benchmark, heavily truncated fields do not reproduce their stated mean
> and standard deviation, `aum_usd` can be negative, and the risk columns render far larger
> than the reference screenshot suggests. See *Known data caveats* in [claude.md](claude.md).

## Using the dashboard

- **Sort** — click a header to sort by that column; click again to flip. **Shift-click**
  adds a further sort key (▼ → ▲ → removed); a small number on the arrow shows its
  priority. Sorting uses what the cell *displays*, so values hidden by `showWhen` sort as
  blank, and blanks always sort last.
- **Paginate** — the rows-per-page select and pager sit under the table. The **Total row
  always covers the whole selection**, not just the visible page.
- **Inspect** — click any numeric cell to highlight it and its row.

## Configuring

Everything lives in [`config/settings.json`](config/settings.json), which carries a
`_readme` block documenting every key. That block is the reference; this is the tour.

| Block | What it controls |
|---|---|
| `dataset` | which workbook and sheet, and which columns drive the pickers, row identity and weighting |
| `defaultGroup` / `defaultReportMonth` / `labels` | the opening view and the captions above each picker |
| `analytics` | a colour and label per analytics group |
| `columns` | which workbook columns appear, in what order, with what header and format |
| `groups` | the Team picker, and per-team overrides |
| `table` | aggregation, default sort, paging, default column width |

### Columns

Each entry maps one workbook column onto the dashboard, reading left to right:

```json
{ "column": "excess_rtn_ytd", "analytics": "perf", "header": "Excess|Return|(YTD)", "format": "pct1" }
```

`column` supplies the values, `analytics` sets the header colour, `header` is the label
(`|` starts a new line), and `format` is one of `text`, `musd`, `pct1`, `num2`, `int`,
`tick`. Array order is display order, and **any** of the workbook's 44 columns may be used.

Optional per column, each defaulting sensibly from `format`: `width`, `flex`, `wrap`,
`align`, `total`, and `showWhen` — e.g. `"showWhen": {"kpi_in_scope": 0}` shows the
exclusion reason only for mandates that are actually excluded.

### Teams

`groups` is the Team picker, in order. Any entry may override the blocks above it, for that
team only:

```json
{ "group": "4. ILP",
  "name": "Investment-Linked Products",
  "columns": ["port_mandate_name", "aum_usd", "peer_rank_1y"],
  "analytics": { "esg": false, "risk": { "colour": "#7A6BA8" } } }
```

`group` must match a value in the workbook; `name` is display-only. A team's `columns` list
wins over analytics show/hide, and may only name columns already defined above.

### Column widths

By default every column **measures itself** — the widest of its header lines, its formatted
values, and its Total cell. Spare table width goes to a single `flex` column (the first by
default) rather than inflating every column. `table.defaultWidth: "format"` restores fixed
per-format weights, and an explicit `width` on any column always wins.

### Pointing at a different workbook

Set `dataset.workbook`, or override per visit from the URL:

```
http://localhost:8321/?data=data/other.xlsx&sheet=data
```

## Requirements

Python 3.11+ with `numpy`, `pandas` and `openpyxl`. A `.venv` is already set up; to build
one from scratch:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Only the generator needs these. **Serving the dashboard needs no third-party packages** —
it is a static page served by the standard library.

Two notes specific to this machine: use `/usr/local/bin/python3.11`, since the system
`python3` is a broken 3.7; and do not import `scipy` — its first load stalls for minutes
under macOS Gatekeeper, which is why the generator builds its truncated-normal quantile
from `math.erf` and `statistics.NormalDist` instead.

After editing `index.html`, hard-reload (⇧⌘R) — the page itself is browser-cached even
though the workbook and config are not.
