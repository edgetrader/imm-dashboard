# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A synthetic investment-mandate monitoring (IMM) panel and a static dashboard that reads it.

    generate_imm_data.py  ->  data/imm_data.xlsx        (the panel, 360 rows x 44 columns)
    index.html            <-  data/imm_data.xlsx        (parsed in the browser, no build step)
                          <-  config/settings.json      (fetched at runtime)
                          <-  config/orr-mapping.xlsx   (ORR grade -> order -> band)

There is no generated data file and no bundler. `index.html` contains a dependency-free
.xlsx reader: it unzips the workbook with `DecompressionStream('deflate-raw')` and parses
the sharedStrings / styles / sheet XML with `DOMParser`. `build_dashboard.py` still exists
as an optional JSON dump but the page does not use it.

The layout is modelled on `reference/dashboard-screenshot.png`. Colours and geometry were
sampled from that PNG rather than eyeballed — taupe `#B0A99F`, brick `#B0392E`, gold
`#B39140`, lavender `#9A9AC2`, rows `#F4F5F6`/`#EAECEE`, selected row `#FFF8E8`, cell
outline `#2E5AAC`, title `#B08D3F`; 56px header band, 25px rows. Preserve these.

## Commands

Use `.venv/bin/python` for anything touching pandas. There is no test suite.
Dependencies are pinned in `requirements.txt` (numpy, pandas, openpyxl — no scipy);
rebuild with `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

```bash
.venv/bin/python generate_imm_data.py     # rewrite data/imm_data.xlsx
python3.11 -m http.server 8321            # serve from the PROJECT ROOT
```

Open http://localhost:8321/. The server root must be the project root so `data/` and
`config/` resolve; this also matches a GitHub Pages layout. Editing the workbook or the
config needs no rebuild — just refresh.

Generator flags: `--per-group` (mandates per team, default 10), `--seed` (default 42),
`--derive-excess`, `--reason-null-when-in-scope`, `--out`, `--sheet-name`.

## Environment constraints

Load-bearing; ignoring these wastes a lot of time.

- **Use `/usr/local/bin/python3.11`.** The system `/usr/bin/python3` is a broken 3.7 from
  Command Line Tools and dies with `pymain_compute_path0: memory allocation failed`.
- **Do not import scipy.** It is installed but `from scipy.stats import ...` stalls for
  minutes while macOS Gatekeeper scans its many `.so` files. `generate_imm_data.py`
  deliberately builds the truncated-normal quantile from `math.erf` and
  `statistics.NormalDist`. Keep it that way.
- **The preview launcher cannot bind a port here.** `.claude/launch.json` exists but its
  process starts without ever listening. Start the server with Bash instead.
- **`index.html` is browser-cached.** The workbook and `config/settings.json` are fetched
  `no-store`, the page is not. After editing it, hard-reload or append `?v=N` — a stale
  page silently renders old markup.
- **`buildHead()` replaces the header row every render.** A held `<th>` reference goes
  stale; re-query before dispatching a second click in any test script.

## How the page is organised

`index.html` is one self-contained file: CSS, markup, and an ES5-style IIFE. It holds no
column knowledge — every column, colour, header, format, width and aggregation comes from
`config/settings.json`, merged over a `FALLBACK` object used only when opened over
`file://`. The parsed workbook is exposed as `window.IMM` for console inspection.

`config/settings.json` carries its own `_readme` documenting every key; that block is the
authority, so update it alongside any config change. Blocks, in reading order:
`dataset` (which workbook, and which columns drive the furniture), `defaultGroup` /
`defaultReportMonth` / `labels` (opening view and picker captions), `analytics` (colour and
label per group), `columns` (workbook column -> analytics group -> header -> format),
`groups` (the Team picker, each able to override columns/analytics/name), `table`
(aggregation, sorting, paging, month order).

Behaviours worth preserving when editing:

- The Total row aggregates the **whole selection**, never just the visible page.
- Sorting uses **what the cell displays** — a value hidden by `showWhen` sorts as blank,
  and blanks always sort last in both directions.
- Column widths are **not predicted**. Each render lays the table out once with
  `table-layout:auto`, lets the browser size every column against the text on screen
  (text columns wrap, numerics stay `nowrap`), then reads the widths back and pins them
  so `table-layout:fixed` governs — which is what makes drag-to-resize exact. Do not
  reintroduce canvas text measurement here; it was removed because every estimate in it
  (raw vs formatted values, cell padding, font) had been wrong at least once.
- A column dragged by the user is remembered in `localStorage` and wins over measurement;
  the `flex` column, if any, must never be one the user has sized, or the drag is undone.
- A coded column can aggregate through a mapping workbook — see `total: "band"` below.
- A group's `columns` list wins over analytics show/hide, and may only name columns
  already defined in the top-level `columns`.
- Bad config surfaces in the amber banner rather than being swallowed.

### ORR aggregation (`total: "band"`)

A column of grade codes cannot be averaged as text, so `fund_orr` aggregates through
`config/orr-mapping.xlsx`:

    grade -> order -> AUM-weighted mean -> band lookup -> grade

The mapping is a workbook, not JSON, so it stays editable in Excel; the page reads it with
the same `.xlsx` reader it uses for the panel, once at startup. The mode is general — any
coded column can use it by naming a mapping workbook and its label/value/min/max columns.

Rules, all load-bearing and all decided deliberately:

- Bands share endpoints, so they are **lower-inclusive**: 0.85 reads as `2`, not `2+`.
- Bands are scanned **in file order and the first match wins**. The source table has two
  quirks this resolves: rows `7` and `8` overlap (7 ends at 62.79, 8 starts at 62.76), and
  `8` and `NR` share an identical band. So 62.77 gives `7` and 70.0 gives `8`.
- Labels in `exclude` carry **no weight**. `NR` is excluded — "not rated" is a missing
  assessment, not a rating of 75.19.
- Rows with non-positive AUM carry no weight, matching `wavg`.
- An unreadable mapping blanks the cell and reports it in the banner; the table still works.

Only the team that shows analytics group `risk2` displays this column; the calculation
itself is team-independent.

## Working with settings.json

The user edits `config/settings.json` directly and has overwritten agent edits mid-session
more than once. Back it up before touching it, preserve their `groups`, `analytics` and
`columns` verbatim unless asked, re-read before writing, and diff afterwards. Do not write
a "temporary" value into a key that may already exist.

## Known data caveats

Faithful to the spec below, but restate these before anyone reads the numbers as real:

- `excess_rtn_*` is drawn independently, so it does **not** equal
  `port_rtn_* - bmk_rtn_*`. `--derive-excess` fixes it.
- Tightly truncated fields do not reproduce their stated mean/std — the listed moments
  describe the pre-truncation normal. `beta` is worst (-20.6 becomes about -240);
  `aum_usd`, `port_total_risk` and `dv01_k_usd` also shift materially.
- `aum_usd` may be negative. AUM-weighted averages count positive weights only, and only
  where the analytic itself is non-null.
- `port_total_risk` / `total_risk_dd` render as 60-230% where the reference shows 0.1-10%.

---

# Synthetic Data Generation Specification for imm_data.xlsx

## Panel Structure

- report_date: **date** | Fixed set of 3 monthly report dates: 31 May 2026, 30 Jun 2026, 31 Jul 2026.
- Mandates per report_date: 330.
- Mandate universe is the same 330 mandate_id values across all 3 report_dates (a panel, not independently resampled each month) — every mandate has exactly one row per report_date, for 990 rows total.
- Time-varying fields (returns, risk, AUM, carbon, duration, DV01, VaR, etc.) must evolve consistently month over month per mandate, rather than being redrawn independently each month — e.g. month-over-month changes should be small/smoothly correlated rather than i.i.d. draws from the full distribution each time.
- Slow-moving/static fields per mandate (exco_view1_level1, exco_view3_level1, fund_orr, port_mandate_name, reason, kpi_in_scope) should stay constant across a mandate's 3 rows unless there is a specific reason to change (not required for this generation).

## Dataset Schema

- mandate_id: **string** | String/text. Generate realistic values matching observed pattern.
- port_mandate_name: **string** | String/text. Generate realistic values matching observed pattern.
- exco_view1_level1: **string** | Categorical. Sample from observed categories: 1b. Fixed Income - Buy and Maintain, 1a. Fixed Income - Total Return, 4. ILP, 2. Global Equities, 5b. Advisory, 8a. Private Credit - IRR, 6. Private Equity / Venture Capital, 7. Real Estate, 10. Derivatives (MTM), 11. Others, 3. Local Equities, 5a. Discretion
- exco_view3_level1: **string** | Categorical. Sample from observed categories: GA, ILP, Entity A, Entity B
- kpi_in_scope: **integer** | Random integer using min=0, max=1.
- reason: **string** | Categorical. Sample from observed categories: Small Size / Unfunded, Non Discretionary, Double Count, Advisory Mandate, Platform Exclusion, Derivative Mandates, New Mandate, Undefined KPI Methodology, Terminated
- aum_usd: **float** | Generate using truncated normal(mean=1.11322e+09, std=3.59347e+09, min=-2.4539e+09, max=4.06966e+10).
- port_gross_rtn_ytd: **float** | Generate using truncated normal(mean=0.0236829, std=0.0539686, min=-0.402877, max=0.329283).
- port_gross_rtn_1y: **float** | Generate using truncated normal(mean=0.105886, std=0.120754, min=-0.422894, max=0.584645).
- port_gross_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.130169, std=0.0771328, min=-0.0566232, max=0.492335).
- bmk_gross_rtn_ytd: **float** | Generate using truncated normal(mean=0.0246298, std=0.0561737, min=-0.18134, max=0.279427).
- bmk_gross_rtn_1y: **float** | Generate using truncated normal(mean=0.11195, std=0.121149, min=-0.155559, max=0.574531).
- bmk_gross_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.140616, std=0.069158, min=0.0203796, max=0.265829).
- port_nett_rtn_ytd: **float** | Generate using truncated normal(mean=0.0292676, std=0.0599951, min=-0.168552, max=0.214336).
- port_nett_rtn_1y: **float** | Generate using truncated normal(mean=0.144438, std=0.116953, min=-0.189058, max=0.489958).
- port_nett_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.102784, std=0.0509307, min=-0.000426706, max=0.206753).
- bmk_nett_rtn_ytd: **float** | Generate using truncated normal(mean=0.0390159, std=0.0605655, min=-0.18134, max=0.279427).
- bmk_nett_rtn_1y: **float** | Generate using truncated normal(mean=0.163086, std=0.11235, min=-0.169081, max=0.574531).
- bmk_nett_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.130401, std=0.0574591, min=0.0270149, max=0.265829).
- new_pur_usd_ytd: **integer** | Random integer using min=0, max=398307221000.
- new_pur_usd_1y: **integer** | Random integer using min=0, max=904327183000.
- peer_rank_1y: **integer** | Random integer using min=1, max=4.
- peer_rank_3y: **integer** | Random integer using min=1, max=4.
- beta: **float** | Generate using truncated normal(mean=-20.592, std=415.206, min=-11256.8, max=124.728).
- bmk_var_para: **float** | Generate using truncated normal(mean=0.00275156, std=0.0226631, min=0, max=0.340163).
- port_total_risk: **float** | Generate using truncated normal(mean=0.159702, std=1.51641, min=0, max=56.8801).
- port_var_para: **float** | Generate using truncated normal(mean=0.0033424, std=0.0232233, min=-0.00114036, max=0.355479).
- total_risk_dd: **float** | Generate using truncated normal(mean=0.134216, std=1.51778, min=0, max=56.8801).
- bmk_msci_carbon_emission: **float** | Generate using truncated normal(mean=266.539, std=160.757, min=1.78462, max=713.787).
- port_msci_carbon_emission: **float** | Generate using truncated normal(mean=159.75, std=199.818, min=0.48, max=1654.06).
- port_dur: **float** | Generate using truncated normal(mean=8.89368, std=6.53502, min=0.000200457, max=30.0483).
- fund_orr: **string** | Categorical. Sample from observed categories: 3-, 3, 2+, 3+, 1, 4+, 2-, 4, 4-, 2
- port_rtn_ytd: **float** | Generate using truncated normal(mean=0.0392001, std=0.0577204, min=-0.402877, max=0.329283).
- port_rtn_1y: **float** | Generate using truncated normal(mean=0.105478, std=0.114447, min=-0.422894, max=0.584645).
- port_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.110291, std=0.0754529, min=-0.0566232, max=0.492335).
- bmk_rtn_ytd: **float** | Generate using truncated normal(mean=0.0413443, std=0.0594712, min=-0.18134, max=0.279427).
- bmk_rtn_1y: **float** | Generate using truncated normal(mean=0.113366, std=0.112612, min=-0.169081, max=0.574531).
- bmk_rtn_3y_ann: **float** | Generate using truncated normal(mean=0.12396, std=0.058244, min=0.0203796, max=0.265829).
- excess_rtn_ytd: **float** | Generate using truncated normal(mean=-0.00179225, std=0.0291513, min=-0.670766, max=0.246883).
- excess_rtn_1y: **float** | Generate using truncated normal(mean=-0.0054535, std=0.0558642, min=-0.812785, max=0.245303).
- excess_rtn_3y_ann: **float** | Generate using truncated normal(mean=-0.0123885, std=0.0607288, min=-0.293336, max=0.445172).
- relative_var_para: **float** | Generate using truncated normal(mean=0.882581, std=0.497116, min=0, max=3.60977).
- dv01_k_usd: **float** | Generate using truncated normal(mean=711.004, std=1702.77, min=0.000535082, max=17653).

## Python Simulation Rules

1. Preserve null rates per column.
2. Datetime columns: sample from empirical distribution.
3. Integer columns: sample discrete values bounded by observed min/max.
4. Float columns: sample from a truncated normal distribution using the observed mean/std/min/max.
5. Categorical columns: sample using observed category frequencies.
6. Identifier fields such as mandate_id should preserve format and uniqueness.
7. Panel consistency: generate 330 mandates once, then produce one row per mandate per report_date (31 May 2026, 30 Jun 2026, 31 Jul 2026). Static/categorical fields carry forward unchanged per mandate across report_dates; time-varying numeric fields should be generated with month-over-month persistence (e.g. an AR(1)-style step from the prior month's value, still respecting each field's overall mean/std/min/max) rather than fully independent redraws at each report_date.
