"""Optional JSON export of data/imm_data.xlsx.

NOT required by the dashboard — dashboard/index.html reads the .xlsx directly
in the browser. Kept as a way to dump the workbook as JSON, or to validate that
it parses, without opening the page.

Original purpose:

Every column of the workbook is exported under its own name, so
dashboard/config/settings.json can address any of them directly. No values are
reshaped or blanked here — presentation rules belong in the config.

Emits `window.IMM = {...}` as a plain <script> payload so dashboard/index.html
works when opened directly from disk (file:// blocks fetch()).
"""

import argparse
import json
import math
import os
import re
from datetime import datetime

import pandas as pd

MONTH_ABBR = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
              7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

DATE_COL = "report_date"
GROUP_COL = "exco_view1_level1"


def group_label(g):
    """'1a. Fixed Income - Total Return' -> 'Fixed Income – Total Return'."""
    body = g.split(". ", 1)[1] if ". " in g else g
    return body.replace(" - ", " – ")


def group_sort_key(g):
    m = re.match(r"^(\d+)([a-z]?)\.", g)
    return (int(m.group(1)), m.group(2)) if m else (99, g)


def clean(v, sig=6):
    """JSON-safe value; floats trimmed to `sig` significant digits."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, float):
        if v == 0:
            return 0.0
        return round(v, sig - 1 - int(math.floor(math.log10(abs(v)))))
    if hasattr(v, "item"):          # numpy scalar
        v = v.item()
    return v


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", default="data/imm_data.xlsx")
    p.add_argument("--sheet-name", default="data")
    p.add_argument("--out", default="dashboard/data.js")
    args = p.parse_args()

    df = pd.read_excel(args.src, sheet_name=args.sheet_name)
    df[DATE_COL] = pd.to_datetime(df[DATE_COL])

    months = [{"key": d.strftime("%Y-%m-%d"),
               "label": f"{MONTH_ABBR[d.month]} {d.year}"}
              for d in sorted(df[DATE_COL].unique())]
    groups = [{"key": g, "label": group_label(g)}
              for g in sorted(df[GROUP_COL].unique(), key=group_sort_key)]

    out_df = df.copy()
    out_df[DATE_COL] = out_df[DATE_COL].dt.strftime("%Y-%m-%d")
    rows = [{c: clean(v) for c, v in rec.items()}
            for rec in out_df.to_dict(orient="records")]

    payload = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": os.path.basename(args.src),
        "dateColumn": DATE_COL,
        "groupColumn": GROUP_COL,
        "columns": list(df.columns),
        "months": months,
        "groups": groups,
        "rows": rows,
    }

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        f.write("window.IMM = ")
        json.dump(payload, f, separators=(",", ":"))
        f.write(";\n")

    kb = os.path.getsize(args.out) / 1024
    print(f"wrote {args.out}: {len(rows)} rows x {len(df.columns)} columns, "
          f"{len(groups)} groups, {len(months)} months ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
