"""Per-hour Ridge diagnostic: does explicit hour-stratification reveal
session-specific signal that a pooled Ridge misses?

Tests three architectures on the same walk-forward folds:
  1. Pooled-Ridge (baseline) — current features, single model
  2. Per-Hour-Ridge (baseline) — current features, separate model per hour
  3. Per-Hour-Ridge (enhanced) — adds bar-range proxy, vol-ratio, fix-window dummy

All models scored on identical OOS observations so the grid comparison is fair.

Usage:
    uv run python scripts/fx_coint/per_hour_ridge_diagnostic.py
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
from scripts.fx_coint.reg_signal_hunt import (
    COST_BPS,
    FEATURE_COLS,
    FREQ_MINUTES,
    PAIRS,
    build_panel,
)

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})

UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY"]
HORIZONS = ["1h", "2h", "3h", "4h"]
ALPHA_RIDGE = 1.0
Q_TAIL = 0.95
N_FOLDS = 5

# Corrected Razor costs
_COMMISSION_BPS = 0.60
_SPREAD_PIP = {
    "EURUSD": 0.1,
    "USDJPY": 0.1,
    "GBPUSD": 0.2,
    "AUDUSD": 0.1,
    "USDCAD": 0.3,
    "USDCHF": 0.3,
}
_PX = {
    "EURUSD": 1.08,
    "USDJPY": 150.0,
    "GBPUSD": 1.27,
    "AUDUSD": 0.65,
    "USDCAD": 1.36,
    "USDCHF": 0.89,
}


def razor_cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    spr_bps = (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4
    return _COMMISSION_BPS + spr_bps


COST_MAP = {s: razor_cost(s) for s in UNIVERSE}

# ---------------------------------------------------------------------------
# Enhanced bar builder — adds bar-range proxy, spread proxy from 1m source
# ---------------------------------------------------------------------------

def build_freq_bars_enhanced(
    df_1m: pl.DataFrame, freq: str, session: tuple[int, int] = (7, 21)
) -> pd.DataFrame:
    """Like reg_signal_hunt.build_freq_bars but with range/spread aggregates."""
    step_min = FREQ_MINUTES[freq]
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
    hour = bars["bucket"].dt.hour
    keep = (hour >= session[0]) & (hour < session[1]) & (bars["bucket"].dt.dayofweek < 5)
    bars = bars[keep].reset_index(drop=True)
    step = np.timedelta64(step_min, "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step
    bars.loc[0, "contig"] = False
    return bars


# ---------------------------------------------------------------------------
# Enhanced panel builder with new features
# ---------------------------------------------------------------------------

def build_panel_enhanced(bars: pd.DataFrame, vol_lookback: int = 24) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    mid = b["mid_last"].to_numpy()  # use last-mid for consistency
    r = np.empty(len(b))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~b["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    feats = pd.DataFrame({"bucket": b["bucket"]})
    feats["r_1"] = rs.to_numpy()
    feats["mom_short"] = rs.rolling(5, min_periods=3).sum().to_numpy()
    feats["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feats["rvol_24"] = (
        rs.rolling(vol_lookback, min_periods=vol_lookback // 2).std().shift(1).to_numpy()
    )
    feats["hour"] = b["bucket"].dt.hour.astype(float).to_numpy()
    feats["sigma_h"] = feats["rvol_24"]

    # Enhanced features
    feats["range_bps"] = np.clip((b["lr_max"] - b["lr_min"]).to_numpy(), 0.0, 100.0)
    # vol ratio: intrabar activity vs trailing bar volatility
    feats["vol_ratio"] = np.clip(
        (b["rvol_bps"] / feats["rvol_24"].replace(0, np.nan)).to_numpy(), 0.0, 20.0
    )
    # London fix window 15:00–16:00 UTC
    feats["near_fix"] = ((feats["hour"] == 15) | (feats["hour"] == 16)).astype(float)
    feats["spr_bps"] = np.clip(b["spr_bps"].to_numpy(), 0.0, 20.0)

    ret_next = rs.shift(-1).to_numpy()
    feats["ret_next_bps"] = ret_next
    feats["target_z"] = ret_next / feats["sigma_h"].to_numpy()

    # ---- determine which columns are finite ---------------------------------
    base_cols = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]
    enh_cols = ["range_bps", "vol_ratio", "near_fix", "spr_bps"]
    all_feat_cols = base_cols + enh_cols
    finite = np.isfinite(feats[all_feat_cols].to_numpy()).all(axis=1)
    finite &= np.isfinite(feats["target_z"].to_numpy())
    finite &= feats["sigma_h"].to_numpy() > 0
    feats = feats[finite].copy()

    # Drop rows immediately after gaps to preserve shift relationships
    if len(feats) > 1:
        idx = feats.index.to_numpy()
        gaps = np.where(np.diff(idx) != 1)[0] + 1
        feats = feats.drop(feats.index[gaps])

    return feats.reset_index(drop=True)


# ---------------------------------------------------------------------------
# WFO engines
# ---------------------------------------------------------------------------

def wfo_pooled(panel: pd.DataFrame, feat_cols: list[str], q: float = Q_TAIL, n_folds: int = N_FOLDS) -> pd.DataFrame:
    """Standard pooled Ridge WFO; returns prediction table."""
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


def wfo_per_hour(
    panel: pd.DataFrame, feat_cols: list[str], q: float = Q_TAIL, n_folds: int = N_FOLDS
) -> pd.DataFrame:
    """Per-hour stratified Ridge: train and predict within each hour bucket.
    Hours absent from training fold are skipped for that fold.
    """
    n = len(panel)
    hour_vec = panel["hour"].to_numpy().astype(int)
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
        X_train, yz_train = X[:split], yz[:split]
        h_train = hour_vec[:split]
        X_test, act_test, bk_test = X[lo:hi], act[lo:hi], bk[lo:hi]
        h_test = hour_vec[lo:hi]
        sc_global = StandardScaler().fit(X_train)
        X_train_s = sc_global.transform(X_train)
        X_test_s = sc_global.transform(X_test)
        for hr in np.unique(h_test):
            tr_mask = h_train == hr
            te_mask = h_test == hr
            if tr_mask.sum() < 10 or te_mask.sum() < 3:
                continue
            beta = Ridge(alpha=ALPHA_RIDGE).fit(X_train_s[tr_mask], yz_train[tr_mask])
            mu_hr = beta.predict(X_test_s[te_mask])
            df = pd.DataFrame({"mu": mu_hr, "act": act_test[te_mask], "bucket": pd.to_datetime(bk_test[te_mask])})
            df = df[df["mu"] >= df["mu"].quantile(q)]
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Grid evaluation helpers
# ---------------------------------------------------------------------------

def day_clustered_t(vals: pd.Series, bucket: pd.Series) -> tuple[float, float, int]:
    daily = vals.groupby(bucket.dt.date).mean()
    daily = daily[np.isfinite(daily)]
    if len(daily) < 3:
        return np.nan, np.nan, 0
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p), len(daily)


def bh_fdr(pvals: pd.Series, alpha: float = 0.10) -> pd.Series:
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


def evaluate_grid(pred_df: pd.DataFrame, label: str, freq: str) -> pd.DataFrame:
    pred_df = pred_df.copy()
    pred_df["net"] = pred_df["act"] - pred_df.get("sym", pd.Series("UNK", index=pred_df.index)).map(COST_MAP).fillna(0.7)
    pred_df["hour"] = pred_df["bucket"].dt.hour
    pred_df["year"] = pred_df["bucket"].dt.year
    rows = []
    for hr in sorted(pred_df["hour"].unique()):
        cell = pred_df[pred_df["hour"] == hr]
        if len(cell) < 10:
            continue
        t, p, nd = day_clustered_t(cell["net"], cell["bucket"])
        yr = cell.groupby("year")["net"].mean()
        rows.append(
            {
                "label": label,
                "freq": freq,
                "hour": hr,
                "n": len(cell),
                "mean": cell["net"].mean(),
                "t": t,
                "p": p,
                "ndays": nd,
                "pos_years": (yr > 0).sum(),
                "nyears": len(yr),
                "years_str": f"{(yr > 0).sum()}/{len(yr)}",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main diagnostic loop
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("PER-HOUR RIDGE DIAGNOSTIC")
    print(f"Universe: {UNIVERSE} | Horizons: {HORIZONS} | Cost: {COST_MAP}")
    print("=" * 80)

    grids = []
    all_pred_tables = {}
    # Accumulate predictions per (label, freq) across symbols before evaluating
    accum: dict[tuple[str, str], list[pd.DataFrame]] = {}

    for freq in HORIZONS:
        print(f"\n--- Horizon {freq} ---")
        for sym in UNIVERSE:
            src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
            if not src.exists():
                continue
            # Build both base and enhanced panels from same source
            df_1m = pl.read_parquet(src)
            bars_enh = build_freq_bars_enhanced(df_1m, freq)
            panel_enh = build_panel_enhanced(bars_enh)
            if len(panel_enh) < 200:
                print(f"  {sym}: panel too short ({len(panel_enh)}), skipping")
                continue

            base_feats = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]
            enh_feats = base_feats + ["range_bps", "vol_ratio", "near_fix", "spr_bps"]

            # ---- 1. Pooled baseline ----
            preds_base_pooled = wfo_pooled(panel_enh, base_feats)
            # ---- 2. Per-hour baseline ----
            preds_base_hour = wfo_per_hour(panel_enh, base_feats)
            # ---- 3. Per-hour enhanced ----
            preds_enh_hour = wfo_per_hour(panel_enh, enh_feats)

            for lbl, df in [
                ("pooled_base", preds_base_pooled),
                ("perhour_base", preds_base_hour),
                ("perhour_enh", preds_enh_hour),
            ]:
                if df.empty:
                    continue
                df = df.copy()
                df["sym"] = sym
                key = f"{lbl}_{freq}_{sym}"
                all_pred_tables[key] = df
                accum.setdefault((lbl, freq), []).append(df)
        print(f"  Finished {freq}")

    # Pool across symbols and evaluate once per (label, freq)
    for (lbl, freq), frames in accum.items():
        pooled = pd.concat(frames, ignore_index=True)
        grids.append(evaluate_grid(pooled, lbl, freq))

    master = pd.concat(grids, ignore_index=True) if grids else pd.DataFrame()
    if master.empty:
        print("\nNo predictions generated across any architecture.")
        return

    # ---- BH-FDR per architecture ----
    for lbl in master["label"].unique():
        sub = master[master["label"] == lbl].copy()
        sub["reject_bh"] = bh_fdr(sub["p"], alpha=0.10)
        sub_sorted = sub.sort_values("p")
        print(f"\n{'='*60}")
        print(f"ARCHITECTURE: {lbl}  |  {len(sub)} cells  |  BH survivors: {sub['reject_bh'].sum()}")
        print(f"{'freq':>5} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'years':>6} {'BH':>3}")
        print("-" * 45)
        for _, r in sub_sorted.iterrows():
            bh = "*" if r["reject_bh"] else " "
            print(
                f"{r['freq']:>5} {r['hour']:>3} {r['n']:>5} {r['mean']:>+7.2f} "
                f"{r['t']:>+6.2f} {r['p']:>7.4f} {r['years_str']:>6} {bh:>3}"
            )
        # ---- best cell per architecture per freq ----
        for freq in HORIZONS:
            fsub = sub[sub["freq"] == freq]
            if fsub.empty:
                continue
            best = fsub.loc[fsub["t"].abs().idxmax()]
            print(f"  >>> Best {freq}: hr={best['hour']} t={best['t']:+.2f} p={best['p']:.4f} mean={best['mean']:+.2f}")

    # ---- Direct comparison: same (freq,hour) across architectures ----
    print(f"\n{'='*80}")
    print("HEAD-TO-HEAD: same (freq, hour) cell compared across architectures")
    print(f"{'='*80}")
    comp_rows = []
    for freq in HORIZONS:
        for hr in range(7, 22):
            pivot = {}
            for lbl in ["pooled_base", "perhour_base", "perhour_enh"]:
                hit = master[(master["label"] == lbl) & (master["freq"] == freq) & (master["hour"] == hr)]
                pivot[lbl] = hit.iloc[0].to_dict() if len(hit) == 1 else None
            if any(v is not None for v in pivot.values()):
                # show cells where at least one arch has t > 1.5 or < -1.5
                ts = [abs(v["t"]) for v in pivot.values() if v is not None]
                if ts and max(ts) >= 1.5:
                    print(f"\n{freq} @ {hr:02d}:00")
                    for lbl in ["pooled_base", "perhour_base", "perhour_enh"]:
                        v = pivot[lbl]
                        if v:
                            print(
                                f"  {lbl:16s} n={v['n']} mean={v['mean']:+.2f} t={v['t']:+.2f} p={v['p']:.4f} {v['years_str']}"
                            )
                        else:
                            print(f"  {lbl:16s} — no data")

    # ---- Yearly stability for any BH survivor ----
    survivors = master[master.groupby("label")["p"].transform(lambda x: bh_fdr(x, alpha=0.10))].copy()
    if not survivors.empty:
        print(f"\n{'='*80}")
        print("YEARLY MEANS FOR BH-FDR SURVIVORS")
        print(f"{'='*80}")
        for _, r in survivors.iterrows():
            freq, hr, lbl = r["freq"], r["hour"], r["label"]
            # reconstruct subset
            key_candidates = [k for k in all_pred_tables if k.startswith(f"{lbl}_{freq}_")]
            yr_list = []
            for k in key_candidates:
                df = all_pred_tables[k]
                cell = df[df["bucket"].dt.hour == hr]
                if not cell.empty:
                    for yr, gy in cell.groupby(cell["bucket"].dt.year):
                        yr_list.append((k.split("_")[-1], yr, gy["net"].mean()))
            if yr_list:
                ydf = pd.DataFrame(yr_list, columns=["sym", "year", "net"])
                print(f"\n>>> {lbl} {freq} @ {hr:02d}:00  pooled mean={r['mean']:+.2f}")
                for sym in UNIVERSE:
                    sub = ydf[ydf["sym"] == sym]
                    if not sub.empty:
                        vals = sub.set_index("year")["net"].to_dict()
                        print(f"    {sym}: {vals}")


if __name__ == "__main__":
    main()
