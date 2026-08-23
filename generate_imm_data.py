"""Synthetic IMM panel generator.

Implements the specification in claude.md, restricted to a balanced sample:
`--per-group` mandates for each exco_view1_level1 category, one row per mandate
per report_date.

Time-varying fields use a Gaussian-copula AR(1): persistence is applied to a
latent standard-normal series, which is then mapped through the target
truncated-normal (or discrete-uniform) quantile function. This gives smooth
month-over-month evolution per mandate while reproducing each field's specified
marginal distribution exactly at every report_date.
"""

import argparse
import os
from datetime import date
from math import erf, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

_ND = NormalDist()


def _phi(x):
    """Standard normal CDF (scalar)."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def norm_cdf(a):
    return np.frompyfunc(_phi, 1, 1)(a).astype(float)


def norm_ppf(a):
    return np.frompyfunc(_ND.inv_cdf, 1, 1)(a).astype(float)

REPORT_DATES = [date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31)]

EXCO_VIEW1 = [
    "1b. Fixed Income - Buy and Maintain",
    "1a. Fixed Income - Total Return",
    "4. ILP",
    "2. Global Equities",
    "5b. Advisory",
    "8a. Private Credit - IRR",
    "6. Private Equity / Venture Capital",
    "7. Real Estate",
    "10. Derivatives (MTM)",
    "11. Others",
    "3. Local Equities",
    "5a. Discretion",
]
EXCO_VIEW3 = ["GA", "ILP", "Entity A", "Entity B"]
REASONS = [
    "Small Size / Unfunded", "Non Discretionary", "Double Count",
    "Advisory Mandate", "Platform Exclusion", "Derivative Mandates",
    "New Mandate", "Undefined KPI Methodology", "Terminated",
]
FUND_ORR = ["3-", "3", "2+", "3+", "1", "4+", "2-", "4", "4-", "2"]

# name -> (mean, std, min, max, rho)
FLOAT_SPEC = {
    "aum_usd":                  (1.11322e09, 3.59347e09, -2.45390e09, 4.06966e10, 0.98),
    "port_gross_rtn_ytd":       (0.0236829, 0.0539686, -0.402877, 0.329283, 0.90),
    "port_gross_rtn_1y":        (0.105886, 0.120754, -0.422894, 0.584645, 0.93),
    "port_gross_rtn_3y_ann":    (0.130169, 0.0771328, -0.0566232, 0.492335, 0.97),
    "bmk_gross_rtn_ytd":        (0.0246298, 0.0561737, -0.18134, 0.279427, 0.90),
    "bmk_gross_rtn_1y":         (0.11195, 0.121149, -0.155559, 0.574531, 0.93),
    "bmk_gross_rtn_3y_ann":     (0.140616, 0.069158, 0.0203796, 0.265829, 0.97),
    "port_nett_rtn_ytd":        (0.0292676, 0.0599951, -0.168552, 0.214336, 0.90),
    "port_nett_rtn_1y":         (0.144438, 0.116953, -0.189058, 0.489958, 0.93),
    "port_nett_rtn_3y_ann":     (0.102784, 0.0509307, -0.000426706, 0.206753, 0.97),
    "bmk_nett_rtn_ytd":         (0.0390159, 0.0605655, -0.18134, 0.279427, 0.90),
    "bmk_nett_rtn_1y":          (0.163086, 0.11235, -0.169081, 0.574531, 0.93),
    "bmk_nett_rtn_3y_ann":      (0.130401, 0.0574591, 0.0270149, 0.265829, 0.97),
    "beta":                     (-20.592, 415.206, -11256.8, 124.728, 0.90),
    "bmk_var_para":             (0.00275156, 0.0226631, 0.0, 0.340163, 0.95),
    "port_total_risk":          (0.159702, 1.51641, 0.0, 56.8801, 0.95),
    "port_var_para":            (0.0033424, 0.0232233, -0.00114036, 0.355479, 0.95),
    "total_risk_dd":            (0.134216, 1.51778, 0.0, 56.8801, 0.95),
    "bmk_msci_carbon_emission": (266.539, 160.757, 1.78462, 713.787, 0.97),
    "port_msci_carbon_emission":(159.75, 199.818, 0.48, 1654.06, 0.97),
    "port_dur":                 (8.89368, 6.53502, 0.000200457, 30.0483, 0.97),
    "port_rtn_ytd":             (0.0392001, 0.0577204, -0.402877, 0.329283, 0.90),
    "port_rtn_1y":              (0.105478, 0.114447, -0.422894, 0.584645, 0.93),
    "port_rtn_3y_ann":          (0.110291, 0.0754529, -0.0566232, 0.492335, 0.97),
    "bmk_rtn_ytd":              (0.0413443, 0.0594712, -0.18134, 0.279427, 0.90),
    "bmk_rtn_1y":               (0.113366, 0.112612, -0.169081, 0.574531, 0.93),
    "bmk_rtn_3y_ann":           (0.12396, 0.058244, 0.0203796, 0.265829, 0.97),
    "excess_rtn_ytd":           (-0.00179225, 0.0291513, -0.670766, 0.246883, 0.90),
    "excess_rtn_1y":            (-0.0054535, 0.0558642, -0.812785, 0.245303, 0.93),
    "excess_rtn_3y_ann":        (-0.0123885, 0.0607288, -0.293336, 0.445172, 0.97),
    "relative_var_para":        (0.882581, 0.497116, 0.0, 3.60977, 0.95),
    "dv01_k_usd":               (711.004, 1702.77, 0.000535082, 17653.0, 0.95),
}

# name -> (min, max, rho)
INT_SPEC = {
    "new_pur_usd_ytd": (0, 398307221000, 0.85),
    "new_pur_usd_1y":  (0, 904327183000, 0.85),
    "peer_rank_1y":    (1, 4, 0.90),
    "peer_rank_3y":    (1, 4, 0.90),
}

COLUMNS = [
    "report_date", "mandate_id", "port_mandate_name", "exco_view1_level1",
    "exco_view3_level1", "kpi_in_scope", "reason", "aum_usd",
    "port_gross_rtn_ytd", "port_gross_rtn_1y", "port_gross_rtn_3y_ann",
    "bmk_gross_rtn_ytd", "bmk_gross_rtn_1y", "bmk_gross_rtn_3y_ann",
    "port_nett_rtn_ytd", "port_nett_rtn_1y", "port_nett_rtn_3y_ann",
    "bmk_nett_rtn_ytd", "bmk_nett_rtn_1y", "bmk_nett_rtn_3y_ann",
    "new_pur_usd_ytd", "new_pur_usd_1y", "peer_rank_1y", "peer_rank_3y",
    "beta", "bmk_var_para", "port_total_risk", "port_var_para",
    "total_risk_dd", "bmk_msci_carbon_emission", "port_msci_carbon_emission",
    "port_dur", "fund_orr", "port_rtn_ytd", "port_rtn_1y", "port_rtn_3y_ann",
    "bmk_rtn_ytd", "bmk_rtn_1y", "bmk_rtn_3y_ann", "excess_rtn_ytd",
    "excess_rtn_1y", "excess_rtn_3y_ann", "relative_var_para", "dv01_k_usd",
]


def latent_ar1(rng, n, t, rho):
    """Stationary AR(1) latent standard-normal paths, shape (n, t)."""
    z = np.empty((n, t))
    z[:, 0] = rng.standard_normal(n)
    for i in range(1, t):
        z[:, i] = rho * z[:, i - 1] + np.sqrt(1.0 - rho**2) * rng.standard_normal(n)
    return z


def ar1_truncnorm(rng, n, t, mean, std, lo, hi, rho):
    """Inverse-CDF sampling of truncnorm(mean, std, [lo, hi]) driven by an AR(1)
    latent series, so the marginal at each date is exactly the target."""
    u = np.clip(norm_cdf(latent_ar1(rng, n, t, rho)), 1e-12, 1 - 1e-12)
    pa, pb = _phi((lo - mean) / std), _phi((hi - mean) / std)
    p = np.clip(pa + u * (pb - pa), 1e-15, 1 - 1e-15)
    return mean + std * norm_ppf(p)


def ar1_randint(rng, n, t, lo, hi, rho):
    u = np.clip(norm_cdf(latent_ar1(rng, n, t, rho)), 1e-12, 1 - 1e-12)
    return np.clip(lo + np.floor(u * (hi - lo + 1)), lo, hi).astype("int64")


def short_label(group):
    """'1b. Fixed Income - Buy and Maintain' -> 'Fixed Income - Buy and Maintain'."""
    return group.split(". ", 1)[1]


def build(per_group, seed, derive_excess, reason_null_when_in_scope):
    rng = np.random.default_rng(seed)
    n = per_group * len(EXCO_VIEW1)
    t = len(REPORT_DATES)

    # --- static, one draw per mandate -------------------------------------
    groups = np.repeat(EXCO_VIEW1, per_group)
    mandate_id = np.array([f"MND-{i + 1:04d}" for i in range(n)])
    entity = rng.choice(EXCO_VIEW3, size=n)
    seq = np.tile(np.arange(1, per_group + 1), len(EXCO_VIEW1))
    port_mandate_name = np.array([
        f"{e} {short_label(g)} Portfolio {s:02d}"
        for e, g, s in zip(entity, groups, seq)
    ])
    kpi_in_scope = rng.integers(0, 2, size=n)
    reason = rng.choice(REASONS, size=n)
    fund_orr = rng.choice(FUND_ORR, size=n)

    static = {
        "mandate_id": mandate_id,
        "port_mandate_name": port_mandate_name,
        "exco_view1_level1": groups,
        "exco_view3_level1": entity,
        "kpi_in_scope": kpi_in_scope,
        "reason": reason,
        "fund_orr": fund_orr,
    }

    # --- time-varying, AR(1) across the 3 report_dates --------------------
    panels = {}
    for name, (mean, std, lo, hi, rho) in FLOAT_SPEC.items():
        panels[name] = ar1_truncnorm(rng, n, t, mean, std, lo, hi, rho)
    for name, (lo, hi, rho) in INT_SPEC.items():
        panels[name] = ar1_randint(rng, n, t, lo, hi, rho)

    if derive_excess:
        for h in ("ytd", "1y", "3y_ann"):
            panels[f"excess_rtn_{h}"] = panels[f"port_rtn_{h}"] - panels[f"bmk_rtn_{h}"]

    # --- assemble long panel ---------------------------------------------
    frames = []
    for i, d in enumerate(REPORT_DATES):
        block = {"report_date": np.repeat(pd.Timestamp(d), n)}
        block.update(static)
        for name, arr in panels.items():
            block[name] = arr[:, i]
        frames.append(pd.DataFrame(block))

    df = pd.concat(frames, ignore_index=True)
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values(["report_date", "mandate_id"], kind="stable").reset_index(drop=True)

    if reason_null_when_in_scope:
        df.loc[df["kpi_in_scope"] == 1, "reason"] = np.nan

    return df[COLUMNS]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--per-group", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/imm_data.xlsx")
    p.add_argument("--sheet-name", default="data")
    p.add_argument("--derive-excess", action="store_true",
                   help="Set excess_rtn_* = port_rtn_* - bmk_rtn_* instead of "
                        "drawing them from their own truncated normals.")
    p.add_argument("--reason-null-when-in-scope", action="store_true",
                   help="Null out `reason` where kpi_in_scope == 1.")
    args = p.parse_args()

    df = build(args.per_group, args.seed, args.derive_excess,
               args.reason_null_when_in_scope)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with pd.ExcelWriter(args.out, engine="openpyxl", datetime_format="YYYY-MM-DD") as xl:
        df.to_excel(xl, sheet_name=args.sheet_name, index=False)
        ws = xl.book[args.sheet_name]
        date_col = COLUMNS.index("report_date") + 1
        for (cell,) in ws.iter_rows(min_row=2, min_col=date_col, max_col=date_col):
            cell.number_format = "YYYY-MM-DD"

    print(f"wrote {args.out} [{args.sheet_name}] rows={len(df)} cols={df.shape[1]}")
    return df


if __name__ == "__main__":
    main()
