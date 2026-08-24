#!/usr/bin/env python3
"""Build a deliberately hostile test panel for the dashboard.

Ten month-ends of the same 12-team / 10-mandate universe as the production
panel, then a set of *named scenarios* injected at known (team, month) cells so
every null-handling and aggregation path in index.html can be exercised and
checked against an expectation.

    .venv/bin/python generate_test_data.py       # -> data/imm_test_data.xlsx

View it without touching the real workbook:

    http://localhost:8321/?data=data/imm_test_data.xlsx

Scenarios cover, per aggregation mode:
  sum   (aum_usd)          all-null, all-negative, zero, text, error cells
  wavg  (pct1/num2/int)    all-null column, null weights, non-positive weights
  share (peer_rank_*)      no ranks, no weight, 100%/0% shares, junk ranks
  band  (fund_orr)         all null, all excluded, unknown grade, numeric grade
  none  (tick/text)        null kpi_in_scope, null + blank reason (showWhen)
plus text sentinels ("N/A"), Excel error cells (#N/A), empty strings and
extreme magnitudes sprinkled through the numeric columns.
"""
import argparse
import json
import re
from datetime import date

import numpy as np
import pandas as pd

import generate_imm_data as gen

# Ten consecutive month-ends ending on the production panel's last date.
MONTHS = [date(2025, 10, 31), date(2025, 11, 30), date(2025, 12, 31),
          date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31),
          date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30),
          date(2026, 7, 31)]

# The columns config/settings.json actually puts on screen.
NUMERIC = ["aum_usd", "excess_rtn_ytd", "port_rtn_ytd", "excess_rtn_3y_ann",
           "port_rtn_3y_ann", "peer_rank_1y", "peer_rank_3y", "total_risk_dd",
           "relative_var_para", "port_dur", "port_msci_carbon_emission",
           "bmk_msci_carbon_emission"]
ANALYTICS = [c for c in NUMERIC if c != "aum_usd"]

# Teams that appear in the Team picker, and which of the odd columns they show.
# openpyxl cannot write a true empty string -- it emits a blank cell, which the
# reader turns into null. Real Excel can hold one (a formula returning ""), so
# these are written as a sentinel and patched into `t="str"` cells afterwards.
EMPTY = "ZZ_EMPTY_CELL_ZZ"

ORR_TEAM = "1b. Fixed Income - Buy and Maintain"   # the only team showing ORR
PEER_TEAM = "4. ILP"                               # the only team showing peer rank

manifest = []


def note(team, month, scenario, expect):
    manifest.append({"team": team, "month": str(MONTHS[month]),
                     "scenario": scenario, "expect": expect})


def sel(df, team, month):
    return (df["exco_view1_level1"] == team) & \
           (df["report_date"] == pd.Timestamp(MONTHS[month]))


def put(df, team, month, cols, value, rows=None):
    """Write `value` into `cols` for a (team, month) cell, optionally only the
    first/selected `rows` of it."""
    m = sel(df, team, month)
    idx = df.index[m]
    if rows is not None:
        idx = idx[rows]
    for c in cols if isinstance(cols, (list, tuple)) else [cols]:
        if df[c].dtype != object:
            df[c] = df[c].astype(object)
        df.loc[idx, c] = value


def build(seed):
    gen.REPORT_DATES = [d for d in MONTHS]
    df = gen.build(per_group=10, seed=seed, derive_excess=True,
                   reason_null_when_in_scope=False)
    df = df.copy()
    rng = np.random.default_rng(seed + 1)

    # ---- background: ~7% of every displayed analytic goes missing ---------
    for c in ANALYTICS:
        df[c] = df[c].astype(object)
        hit = rng.random(len(df)) < 0.07
        df.loc[hit, c] = None
    # AUM goes missing more rarely; it is the weight for everything else.
    df["aum_usd"] = df["aum_usd"].astype(object)
    df.loc[rng.random(len(df)) < 0.03, "aum_usd"] = None
    manifest.append({"team": "(all)", "month": "(all)",
                     "scenario": "background 7% nulls in analytics, 3% in aum_usd",
                     "expect": "totals stay numeric; blank cells sort last"})

    T = "1a. Fixed Income - Total Return"

    # ---- sum / wavg edge cases -------------------------------------------
    put(df, T, 0, ANALYTICS, None)
    note(T, 0, "every displayed analytic is null",
         "all analytic totals blank; AUM total still sums")

    put(df, T, 1, "aum_usd", None)
    note(T, 1, "aum_usd entirely null",
         "AUM total blank (not 0M); wavg falls back to a simple mean")

    put(df, T, 2, "aum_usd", None)
    put(df, T, 2, "aum_usd", [-4.4e9, -1.1e9, 0.0, -9.9e8, -3.3e9,
                              0.0, -7.7e8, -2.2e9, 0.0, -5.5e8],
        rows=slice(0, 10))
    note(T, 2, "aum_usd all negative or zero",
         "no positive weight anywhere; wavg falls back to a simple mean")

    put(df, T, 3, "aum_usd", 0.0)
    note(T, 3, "aum_usd all exactly zero",
         "AUM total 0M; wavg falls back to a simple mean")

    # ---- text sentinels in numeric columns -------------------------------
    G = "2. Global Equities"
    put(df, G, 3, ["port_rtn_ytd", "aum_usd"], "N/A", rows=[0, 1])
    put(df, G, 3, ["excess_rtn_ytd", "total_risk_dd"], "NA", rows=[2, 3])
    put(df, G, 3, ["relative_var_para", "port_msci_carbon_emission"], "-", rows=[4, 5])
    put(df, G, 3, "port_rtn_3y_ann", "n.a.", rows=[6])
    note(G, 3, 'text sentinels ("N/A", "NA", "-", "n.a.") in numeric columns',
         "cells render blank, not NaN; totals ignore them entirely")

    # ---- real Excel error cells ------------------------------------------
    L = "3. Local Equities"
    put(df, L, 4, ["port_rtn_ytd", "aum_usd"], "#N/A", rows=[0, 1])
    put(df, L, 4, ["excess_rtn_ytd", "relative_var_para"], "#DIV/0!", rows=[2, 3])
    put(df, L, 4, ["total_risk_dd", "bmk_msci_carbon_emission"], "#VALUE!", rows=[4, 5])
    note(L, 4, "Excel error cells (#N/A, #DIV/0!, #VALUE!)",
         "reader maps error cells to null; cells blank, totals unaffected")

    # ---- empty strings ----------------------------------------------------
    D = "5a. Discretion"
    put(df, D, 5, ["port_rtn_ytd", "aum_usd", "relative_var_para",
                   "port_msci_carbon_emission"], EMPTY, rows=[0, 1, 2])
    put(df, D, 5, "port_mandate_name", EMPTY, rows=[3])
    note(D, 5, "empty-string cells in numeric columns and the name column",
         "blank cells must not be counted as zero in the weighted average")

    # ---- extreme magnitudes ----------------------------------------------
    A = "5b. Advisory"
    put(df, A, 6, "aum_usd", 9.9e14, rows=[0])
    put(df, A, 6, "aum_usd", -9.9e14, rows=[1])
    put(df, A, 6, "port_rtn_ytd", 1e-18, rows=[2])
    put(df, A, 6, "port_rtn_ytd", 12345.678, rows=[3])
    put(df, A, 6, "relative_var_para", 1e15, rows=[4])
    put(df, A, 6, "port_msci_carbon_emission", 1e12, rows=[5])
    note(A, 6, "extreme magnitudes (±9.9e14 AUM, 1e-18, 1e15)",
         "no overflow or exponent notation leaking into the table")

    # ---- tick / showWhen --------------------------------------------------
    O = "11. Others"
    put(df, O, 7, "kpi_in_scope", None, rows=[0, 1, 2])
    put(df, O, 7, "kpi_in_scope", EMPTY, rows=[3])
    put(df, O, 7, "kpi_in_scope", 0, rows=[4, 5, 6])
    put(df, O, 7, "reason", None, rows=[4, 5])
    put(df, O, 7, "reason", EMPTY, rows=[6])
    note(O, 7, "null/blank kpi_in_scope; null and blank reason where out of scope",
         "tick blank for null; reason blank without breaking showWhen or sorting")

    put(df, O, 8, "port_rtn_ytd", "pending", rows=[0])
    put(df, O, 8, "relative_var_para", "TBD", rows=[1])
    put(df, O, 8, "port_msci_carbon_emission", "twelve", rows=[2])
    put(df, O, 8, "aum_usd", "see note", rows=[3])
    note(O, 8, 'unrecognised text ("pending", "TBD", "twelve", "see note")',
         "cells blank AND the banner names the column and the offending text")

    # ---- ORR / band -------------------------------------------------------
    put(df, ORR_TEAM, 0, "fund_orr", None)
    note(ORR_TEAM, 0, "fund_orr entirely null", "ORR total blank, no banner error")

    put(df, ORR_TEAM, 1, "fund_orr", "ZZ", rows=[0, 1])
    put(df, ORR_TEAM, 1, "fund_orr", "10", rows=[2])
    note(ORR_TEAM, 1, 'grades absent from the mapping ("ZZ", "10")',
         "banner names the unknown grade; the rest still aggregate")

    put(df, ORR_TEAM, 2, "fund_orr", "NR")
    note(ORR_TEAM, 2, "every grade is NR (the excluded label)",
         "ORR total blank — NR carries no weight and there is nothing left")

    put(df, ORR_TEAM, 3, "fund_orr", "NR", rows=[0, 1, 2, 3, 4])
    put(df, ORR_TEAM, 3, "aum_usd", None)
    note(ORR_TEAM, 3, "mixed NR + valid grades with no AUM at all",
         "falls back to the plain mean of the non-excluded orders")

    put(df, ORR_TEAM, 4, "fund_orr", EMPTY, rows=[0, 1, 2])
    note(ORR_TEAM, 4, "empty-string grades",
         'blank must not be reported as an unknown grade ""')

    put(df, ORR_TEAM, 5, "fund_orr", 3, rows=[0, 1])
    note(ORR_TEAM, 5, "numeric 3 where a grade string is expected",
         'matches the "3" row of the mapping rather than erroring')

    put(df, ORR_TEAM, 6, "fund_orr", "1")
    put(df, ORR_TEAM, 6, "aum_usd", None)
    put(df, ORR_TEAM, 6, "aum_usd", 5.0e9, rows=[0])
    note(ORR_TEAM, 6, "one weighted mandate, all grade 1",
         "ORR total is exactly 1")

    # ---- peer rank / share ------------------------------------------------
    put(df, PEER_TEAM, 0, ["peer_rank_1y", "peer_rank_3y"], None)
    note(PEER_TEAM, 0, "no peer ranks at all",
         "share blank, not 0.0% — there is no denominator")

    put(df, PEER_TEAM, 1, "aum_usd", None)
    note(PEER_TEAM, 1, "ranks present but no AUM",
         "share blank — every row carries zero weight")

    put(df, PEER_TEAM, 2, ["peer_rank_1y", "peer_rank_3y"], "N/A", rows=[0, 1, 2])
    note(PEER_TEAM, 2, "text ranks", "junk ranks ignored by the share")

    put(df, PEER_TEAM, 3, "peer_rank_1y", 0, rows=[0])
    put(df, PEER_TEAM, 3, "peer_rank_1y", 5, rows=[1])
    put(df, PEER_TEAM, 3, "peer_rank_1y", 9, rows=[2])
    note(PEER_TEAM, 3, "out-of-range ranks (0, 5, 9)",
         "counted in the denominator, never in the numerator")

    put(df, PEER_TEAM, 4, ["peer_rank_1y", "peer_rank_3y"], 1)
    note(PEER_TEAM, 4, "every rank is 1", "share is exactly 100.0%")

    put(df, PEER_TEAM, 5, ["peer_rank_1y", "peer_rank_3y"], 4)
    note(PEER_TEAM, 5, "no rank is 1 or 2", "share is exactly 0.0%")

    put(df, PEER_TEAM, 6, ["peer_rank_1y", "peer_rank_3y"], EMPTY, rows=[0, 1, 2])
    note(PEER_TEAM, 6, "empty-string ranks", "blank ranks ignored by the share")

    put(df, PEER_TEAM, 7, ["peer_rank_1y", "peer_rank_3y"], 2)
    put(df, PEER_TEAM, 7, "aum_usd", -1.0e9)
    put(df, PEER_TEAM, 7, "aum_usd", 2.0e9, rows=[0])
    note(PEER_TEAM, 7, "all rank 2, only one positive AUM among negatives",
         "share is 100.0% off the single positive weight")

    return df


def patch_empty_strings(path):
    """Turn the sentinel cells into genuine empty-string cells (`t="str"` with
    an empty <v>), which is what Excel writes for a formula returning ""."""
    import zipfile
    src = zipfile.ZipFile(path)
    parts = {n: src.read(n) for n in src.namelist()}
    src.close()
    pat = re.compile(
        r'<c r="([A-Z]+\d+)"([^>]*?)t="inlineStr"([^>]*?)>\s*<is><t[^>]*>'
        + re.escape(EMPTY) + r'</t></is>\s*</c>')
    total = 0
    for name in list(parts):
        if not name.startswith("xl/worksheets/"):
            continue
        text = parts[name].decode("utf-8")
        text, k = pat.subn(r'<c r="\1"\2t="str"\3><v></v></c>', text)
        total += k
        parts[name] = text.encode("utf-8")
    out = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
    for name, blob in parts.items():
        out.writestr(name, blob)
    out.close()
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default="data/imm_test_data.xlsx")
    p.add_argument("--sheet-name", default="data")
    p.add_argument("--manifest", default="")
    a = p.parse_args()

    df = build(a.seed)
    df.to_excel(a.out, sheet_name=a.sheet_name, index=False)
    blanks = patch_empty_strings(a.out)
    print(f"patched {blanks} genuine empty-string cells")
    print(f"wrote {a.out}  {len(df)} rows x {len(df.columns)} cols  "
          f"{df['report_date'].nunique()} months  "
          f"{df['mandate_id'].nunique()} mandates")
    if a.manifest:
        with open(a.manifest, "w") as fh:
            json.dump(manifest, fh, indent=2)
        print(f"wrote {a.manifest}  {len(manifest)} scenarios")
    for m in manifest:
        print(f"  {m['month']}  {m['team'][:34]:34}  {m['scenario']}")


if __name__ == "__main__":
    main()
