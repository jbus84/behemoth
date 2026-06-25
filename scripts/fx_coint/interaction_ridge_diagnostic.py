"""Fair test of hour-conditioned slopes: same pooled Ridge, same data,
same global top-5% selection, but with explicit hour-dummy interactions.

Variants:
  1. BASE    — r_1, mom_short, mom_long, rvol_24, hour (scalar)
  2. ENH     — BASE + range_bps, vol_ratio, near_fix, spr_bps
  3. DUMMY   — BASE + 14 session dummies (hour treated as category)
  4. INTERACT— BASE + dummies + dummy×mom_short, dummy×mom_long, dummy×rvol_24

All trained pooled on full data. Selection = global top-5% across all hours.

Usage:
    uv run python scripts/fx_coint/interaction_ridge_diagnostic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh
from scripts.fx_coint.reg_signal_hunt import FREQ_MINUTES, PAIRS, build_panel

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})

UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY"]
ALPHA_RIDGE = 1.0
Q_TAIL = 0.95
N_FOLDS = 5
SESSION_HOURS = list(range(7, 21))

_COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": 0.1, "USDJPY": 0.1, "GBPUSD": 0.2,
               "AUDUSD": 0.1, "USDCAD": 0.3, "USDCHF": 0.3}
_PX = {"EURUSD": 1.08, "USDJPY": 150.0, "GBPUSD": 1.27,
       "AUDUSD": 0.65, "USDCAD": 1.36, "USDCHF": 0.89}


def razor_cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    spr_bps = (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4
    return _COMMISSION_BPS + spr_bps


COST_MAP = {s: razor_cost(s) for s in UNIVERSE}


def build_freq_bars(df_1m: pl.DataFrame, freq: str, session=(7, 21)) -> pd.DataFrame:
    step = FREQ_MINUTES[freq]
    t = df_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        pl.col("bucket").dt.truncate(freq).alias("bf"),
    )
    bars = (
        t.group_by("bf")
        .agg(
            pl.col("mid").last().alias("mid_last"),
            pl.col("n_ticks").sum().alias("n_ticks"),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("lr1").max() * 1e4).alias("lr_max"),
            (pl.col("lr1").min() * 1e4).alias("lr_min"),
            ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 1e4).mean().alias("spr_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    h = bars["bucket"].dt.hour
    bars = bars[(h >= session[0]) & (h < session[1]) & (bars["bucket"].dt.dayofweek < 5)].reset_index(drop=True)
    step_td = np.timedelta64(step, "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step_td
    bars.loc[0, "contig"] = False
    return bars


def build_panel_interactive(bars: pd.DataFrame, variant: str, vol_lb: int = 24) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    mid = b["mid_last"].to_numpy()
    r = np.empty(len(b))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~b["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    feats = pd.DataFrame({"bucket": b["bucket"]})
    feats["r_1"] = rs.to_numpy()
    feats["mom_short"] = rs.rolling(5, min_periods=3).sum().to_numpy()
    feats["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feats["rvol_24"] = rs.rolling(vol_lb, min_periods=vol_lb // 2).std().shift(1).to_numpy()
    feats["hour"] = b["bucket"].dt.hour.astype(float).to_numpy()
    feats["sigma_h"] = feats["rvol_24"]

    # enhanced
    feats["range_bps"] = np.clip((b["lr_max"] - b["lr_min"]).to_numpy(), 0.0, 100.0)
    feats["vol_ratio"] = np.clip((b["rvol_bps"] / feats["rvol_24"].replace(0, np.nan)).to_numpy(), 0.0, 20.0)
    feats["near_fix"] = ((feats["hour"] == 15) | (feats["hour"] == 16)).astype(float)
    feats["spr_bps"] = np.clip(b["spr_bps"].to_numpy(), 0.0, 20.0)

    ret_next = rs.shift(-1).to_numpy()
    feats["ret_next_bps"] = ret_next
    feats["target_z"] = ret_next / feats["sigma_h"].to_numpy()

    # dummies
    for hh in SESSION_HOURS:
        feats[f"hd_{hh}"] = (feats["hour"] == hh).astype(float)

    # interactions
    for hh in SESSION_HOURS:
        feats[f"momS_x_{hh}"] = feats["mom_short"] * feats[f"hd_{hh}"]
        feats[f"momL_x_{hh}"] = feats["mom_long"] * feats[f"hd_{hh}"]
        feats[f"rvol_x_{hh}"] = feats["rvol_24"] * feats[f"hd_{hh}"]

    # assemble per-variant feature list
    cols_needed = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]
    if variant in ("ENH", "DUMMY", "INTERACT"):
        cols_needed += ["range_bps", "vol_ratio", "near_fix", "spr_bps"]
    if variant in ("DUMMY", "INTERACT"):
        cols_needed += [f"hd_{h}" for h in SESSION_HOURS]
    if variant == "INTERACT":
        for hh in SESSION_HOURS:
            cols_needed += [f"momS_x_{hh}", f"momL_x_{hh}", f"rvol_x_{hh}"]

    finite = np.isfinite(feats[cols_needed].to_numpy()).all(axis=1)
    finite &= np.isfinite(feats["target_z"].to_numpy())
    finite &= feats["sigma_h"].to_numpy() > 0
    feats = feats[finite].copy()
    if len(feats) > 1:
        idx = feats.index.to_numpy()
        gaps = np.where(np.diff(idx) != 1)[0] + 1
        feats = feats.drop(feats.index[gaps])
    feats["feature_cols"] = pd.Series([cols_needed] * len(feats), index=feats.index)
    return feats.reset_index(drop=True)


def wfo_variant(panel: pd.DataFrame, feat_cols: list[str], q=Q_TAIL, n_folds=N_FOLDS) -> pd.DataFrame:
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[feat_cols].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    frames = []
    for k in range(n_folds):
        split, lo, hi = edges[k], edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        beta = Ridge(alpha=ALPHA_RIDGE).fit(sc.transform(X[:split]), yz[:split])
        mu = beta.predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"mu": mu, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        df = df[df["mu"] >= df["mu"].quantile(q)]
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def day_clustered_t(vals, bucket) -> tuple[float, float, int]:
    daily = vals.groupby(bucket.dt.date).mean()
    daily = daily[np.isfinite(daily)]
    if len(daily) < 3:
        return np.nan, np.nan, 0
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p), len(daily)


def bh_fdr(pvals, alpha=0.10):
    m = len(pvals)
    if m == 0:
        return pd.Series(False, index=pvals.index)
    sorted_p = pvals.sort_values()
    ranks = np.arange(1, len(sorted_p) + 1)
    threshold = (ranks / len(sorted_p)) * alpha
    below = sorted_p.values <= threshold
    if not below.any():
        return pd.Series(False, index=pvals.index)
    crit_rank = np.where(below)[0][-1]
    crit_p = sorted_p.iloc[crit_rank]
    return pvals <= crit_p


def evaluate_hourly(pred_df, label, freq):
    pred_df = pred_df.copy()
    pred_df["net"] = pred_df["act"] - pred_df["sym"].map(COST_MAP)
    pred_df["hour"] = pred_df["bucket"].dt.hour
    pred_df["year"] = pred_df["bucket"].dt.year
    rows = []
    for hr in sorted(pred_df["hour"].unique()):
        cell = pred_df[pred_df["hour"] == hr]
        if len(cell) < 10:
            continue
        t, p, nd = day_clustered_t(cell["net"], cell["bucket"])
        yr = cell.groupby("year")["net"].mean()
        rows.append({
            "label": label, "freq": freq, "hour": hr, "n": len(cell),
            "mean": cell["net"].mean(), "t": t, "p": p, "ndays": nd,
            "pos_years": (yr > 0).sum(), "nyears": len(yr),
            "years_str": f"{(yr > 0).sum()}/{len(yr)}",
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("INTERACTION RIDGE DIAGNOSTIC")
    print("Fair test: same data, same selection, explicit hour interactions")
    print(f"Universe: {UNIVERSE} | Costs: {COST_MAP}")
    print("=" * 80)

    variants = ["BASE", "ENH", "DUMMY", "INTERACT"]
    grids = {v: [] for v in variants}

    for sym in UNIVERSE:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        df_1m = pl.read_parquet(src)
        bars = build_freq_bars(df_1m, "2h")
        for variant in variants:
            panel = build_panel_interactive(bars, variant)
            if len(panel) < 200:
                continue
            feat_cols = panel["feature_cols"].iloc[0]
            preds = wfo_variant(panel, feat_cols)
            if preds.empty:
                continue
            preds = preds.copy()
            preds["sym"] = sym
            grids[variant].append(preds)

    master_rows = []
    for v in variants:
        if not grids[v]:
            print(f"\n{v}: no predictions")
            continue
        pooled = pd.concat(grids[v], ignore_index=True)
        ev = evaluate_hourly(pooled, v, "2h")
        ev["reject_bh"] = bh_fdr(ev["p"], alpha=0.10)
        master_rows.append(ev)
        print(f"\n{'='*60}")
        print(f"VARIANT: {v}  | {len(ev)} cells  | BH survivors: {ev['reject_bh'].sum()}")
        print(f"{'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'years':>6} {'BH':>3}")
        print("-" * 40)
        for _, r in ev.sort_values("p").iterrows():
            bh = "*" if r["reject_bh"] else " "
            print(
                f"{r['hour']:>3} {r['n']:>5} {r['mean']:>+7.2f} "
                f"{r['t']:>+6.2f} {r['p']:>7.4f} {r['years_str']:>6} {bh:>3}"
            )
        best = ev.loc[ev["t"].abs().idxmax()]
        print(f"  >>> Best: hr={best['hour']} t={best['t']:+.2f} p={best['p']:.4f} mean={best['mean']:+.2f} {best['years_str']}")

    # head-to-head for key hours
    if master_rows:
        master = pd.concat(master_rows, ignore_index=True)
        print(f"\n{'='*60}")
        print("HEAD-TO-HEAD: 2h @ 14:00 across variants")
        print(f"{'='*60}")
        for v in variants:
            hit = master[(master["label"] == v) & (master["hour"] == 14)]
            if not hit.empty:
                r = hit.iloc[0]
                print(f"  {v:12s} n={r['n']} mean={r['mean']:+.2f} t={r['t']:+.2f} p={r['p']:.4f} {r['years_str']}")
            else:
                print(f"  {v:12s} — no data")

        # report all cells where |t| > 1.5 for any variant
        print(f"\n{'='*60}")
        print("ALL STRONG CELLS (|t| > 1.5) by variant")
        print(f"{'='*60}")
        for v in variants:
            sub = master[(master["label"] == v) & (master["t"].abs() > 1.5)]
            if not sub.empty:
                print(f"\n{v}:")
                for _, r in sub.iterrows():
                    print(f"  hr={r['hour']:02d} mean={r['mean']:+.2f} t={r['t']:+.2f} p={r['p']:.4f} {r['years_str']}")
            else:
                print(f"\n{v}: none")


if __name__ == "__main__":
    main()
