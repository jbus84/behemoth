"""Causal residual selector for FX USD-factor hourly mean-reversion.

Trains lightweight supervised models to predict which 6–12 bps residual
dislocations will revert next hour, using only causal features known at entry.
Compares always-fade baseline vs logistic regression vs CatBoost (if LR
shows material gross lift).

Design (look-ahead-guarded):
  * Load 5min aligned panel from 1000tick bars.
  * Coarsen to hourly for signal / label construction.
  * Orient returns to USD-strength, compute equal-weighted factor, residuals.
  * Engineer causal features from: factor regime, residual volatility,
    cross-pair breadth, intra-hour path, autocorrelation, spread percentile,
    calendar dummies.
  * Label = 1 if fade wins (−sign(residual_t) * residual_{t+1} > 0).
  * Walk-forward: 2-year train → 1-year OOS, 5-day purge gap.
  * Evaluate gross lift, net lift after measured spread, positive-month %.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from scripts.fx_coint.instruments import MAJORS
from scripts.fx_coint.panels import coarsen, load_aligned, walk_forward_windows

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ORIENT: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,
    "USDCAD": +1.0,
}

BAND_LO_BPS: float = 6.0
BAND_HI_BPS: float = 12.0
# Cost model: Pepperstone-Razor-style FLAT round-trip commission (~0.3 pip/side
# x2 sides + near-zero raw spread), roughly UNIFORM across majors. This is the
# user's real execution cost. Do NOT use the parquet's Dukascopy quoted spread
# as cost -- it overstates the wide-spread majors (AUDUSD ~1.5bps) 2-4x vs the
# commission actually paid, which spuriously sinks those pairs.
COMMISSION_RT_BPS: float = 0.7
TICK_BAR: str = "1000tick"
FINE_FREQ: str = "5min"
COARSE_FREQ: str = "1h"

CAT_FEATURES: list[str] = ["hour", "dow"]


def _orient_idx(sym: str) -> int:
    return MAJORS.index(sym)


def _oriented_returns(hourly: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Compute oriented USD-strength log returns from hourly logmid panel.

    Returns (index[1:], returns) where returns shape = (T-1, 6).
    """
    idx = hourly.index
    rets = np.zeros((len(idx) - 1, len(MAJORS)), dtype=float)
    for sym in MAJORS:
        j = _orient_idx(sym)
        logmid = hourly[(sym, "logmid")].to_numpy()
        rets[:, j] = ORIENT[sym] * np.diff(logmid)
    return idx[1:], rets


def _residuals(oriented: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Factor (EW) and pair residuals.

    Returns (factor, residuals) with same shape (T, 6) as oriented.
    Note: oriented already has length T-1 (diffed), so factor/residuals
    also have length T-1 and are aligned to the *signal* timestamps.
    """
    factor = oriented.mean(axis=1)
    residuals = oriented - factor[:, None]
    return factor, residuals


def _intra_hour_features(fine: pd.DataFrame, hourly_idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Compute per-symbol intra-hour path stats from 5min bars.

    Returns DataFrame indexed by hourly_idx with columns:
      (sym, 'efficiency') and (sym, 'close_pos').
    """
    out = pd.DataFrame(index=hourly_idx)
    for sym in MAJORS:
        s5 = fine[(sym, "logmid")]
        # exact within-hour diffs via groupby
        tmp = pd.DataFrame({"val": s5, "hour": s5.index.floor("h")})
        tmp["ret"] = tmp.groupby("hour")["val"].diff().abs()
        hourly_open = tmp.groupby("hour")["val"].first()
        hourly_close = tmp.groupby("hour")["val"].last()
        hourly_high = tmp.groupby("hour")["val"].max()
        hourly_low = tmp.groupby("hour")["val"].min()
        sum_abs = tmp.groupby("hour")["ret"].sum()
        efficiency = (hourly_close - hourly_open).abs() / (sum_abs + 1e-12)
        rng = hourly_high - hourly_low
        cpos = (hourly_close - hourly_open) / (rng + 1e-12)
        cpos = cpos.clip(-1.0, 1.0)
        out[(sym, "efficiency")] = efficiency.reindex(hourly_idx)
        out[(sym, "close_pos")] = cpos.reindex(hourly_idx)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    return out


def _rolling_std(x: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling std, NaN until window filled."""
    s = pd.Series(x)
    return s.rolling(window, min_periods=window).std().to_numpy()


def _rolling_corr_pair(x: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling Pearson correlation."""
    s = pd.Series(x)
    t = pd.Series(y)
    return s.rolling(window, min_periods=window).corr(t).to_numpy()


def _build_features(
    hourly: pd.DataFrame,
    fine: pd.DataFrame,
    oriented: np.ndarray,
    residuals: np.ndarray,
    factor: np.ndarray,
) -> pd.DataFrame:
    """Build causal feature matrix per (hour, pair).

    Returns flat DataFrame with columns per feature and a MultiIndex
    (hour, pair) where pair is the symbol name.
    """
    T, n_pairs = residuals.shape
    hours = hourly.index[1:]  # aligned to residuals (diffed)

    # factor 5min series for factor-efficiency (hourly aggregation from fine)
    f5 = pd.Series(0.0, index=fine.index)
    for sym in MAJORS:
        j = _orient_idx(sym)
        f5 += ORIENT[sym] * fine[(sym, "logmid")]
    f5 /= len(MAJORS)
    # factor 5min returns (causal)
    f5_ret = f5.diff().to_numpy()
    f5_hours = f5.index.floor("h")
    # hourly factor efficiency
    tmp = pd.DataFrame({"ret": f5_ret, "hour": f5_hours})
    tmp = tmp.dropna()
    feff = tmp.groupby("hour")["ret"].agg(lambda x: np.abs(x.sum()) / (np.abs(x).sum() + 1e-12))
    factor_eff_s = feff.reindex(hourly.index).to_numpy()
    # shift so factor_eff[t] = efficiency of hour ending at t (which uses data within hour t)
    # feff is indexed by the hour; reindex to hourly.index gives efficiency for that hour.
    # Since residuals are at hours[1:], we need factor_eff aligned to hours.
    factor_eff = factor_eff_s[1:]  # drop first hour (no return)
    # rolling smoothed versions
    factor_eff_6 = pd.Series(factor_eff).rolling(6, min_periods=6).mean().to_numpy()
    factor_eff_12 = pd.Series(factor_eff).rolling(12, min_periods=12).mean().to_numpy()

    # intra-hour features
    intra = _intra_hour_features(fine, hourly.index)
    eff_intra = np.stack([intra[(sym, "efficiency")].to_numpy()[1:] for sym in MAJORS], axis=1)
    cpos_intra = np.stack([intra[(sym, "close_pos")].to_numpy()[1:] for sym in MAJORS], axis=1)

    # pre-allocate feature arrays (T, n_pairs)
    feat_arrays: dict[str, np.ndarray] = {}

    # 1. factor regime
    feat_arrays["factor_eff_6"] = np.broadcast_to(factor_eff_6[:, None], (T, n_pairs))
    feat_arrays["factor_eff_12"] = np.broadcast_to(factor_eff_12[:, None], (T, n_pairs))

    # 2. residual volatility
    res_vol_6 = np.stack([_rolling_std(residuals[:, j], 6) for j in range(n_pairs)], axis=1)
    res_vol_12 = np.stack([_rolling_std(residuals[:, j], 12) for j in range(n_pairs)], axis=1)
    feat_arrays["res_vol_6"] = res_vol_6
    feat_arrays["res_vol_12"] = res_vol_12

    # 3. cross-pair breadth: fraction of pairs whose |resid| > 1σ (24h rolling σ)
    sig_24 = np.stack([_rolling_std(residuals[:, j], 24) for j in range(n_pairs)], axis=1)
    # avoid divide-by-zero
    with np.errstate(divide="ignore", invalid="ignore"):
        breadth = np.mean(np.abs(residuals) > (sig_24 * 1.0), axis=1)
    feat_arrays["breadth"] = np.broadcast_to(breadth[:, None], (T, n_pairs))

    # 4. cross-sectional dispersion
    dispersion = np.std(residuals, axis=1)
    feat_arrays["dispersion"] = np.broadcast_to(dispersion[:, None], (T, n_pairs))

    # 5. intra-hour path
    feat_arrays["intra_efficiency"] = eff_intra
    feat_arrays["intra_close_pos"] = cpos_intra

    # 6. residual autocorrelation (24h window)
    ar1 = np.full((T, n_pairs), np.nan)
    for j in range(n_pairs):
        r = residuals[:, j]
        # lag-1 correlation over 24h windows: corr(r[t-23:t], r[t-22:t+1])
        # Implemented as rolling corr of series with its lag-1.
        s = pd.Series(r)
        ar1[:, j] = s.rolling(24, min_periods=24).apply(
            lambda x: np.corrcoef(x[:-1], x[1:])[0, 1] if len(x) > 1 else np.nan,
            raw=True,
        ).to_numpy()
    feat_arrays["res_ar1_24"] = ar1

    # 7. residual persistence (signed sums)
    pers_3 = np.stack(
        [pd.Series(residuals[:, j]).rolling(3, min_periods=3).sum().to_numpy() for j in range(n_pairs)],
        axis=1,
    )
    pers_6 = np.stack(
        [pd.Series(residuals[:, j]).rolling(6, min_periods=6).sum().to_numpy() for j in range(n_pairs)],
        axis=1,
    )
    feat_arrays["pers_3"] = pers_3
    feat_arrays["pers_6"] = pers_6

    # 8. spread percentile (current vs 24h median)
    spreads = np.stack([hourly[(sym, "spread")].to_numpy()[1:] for sym in MAJORS], axis=1)
    spr_med = np.stack(
        [pd.Series(spreads[:, j]).rolling(24, min_periods=24).median().to_numpy() for j in range(n_pairs)],
        axis=1,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        spr_pct = spreads / (spr_med + 1e-12)
    feat_arrays["spr_pct"] = spr_pct

    # 9. calendar
    hour_of_day = hours.hour.to_numpy()
    dow = hours.dayofweek.to_numpy()
    feat_arrays["hour"] = np.broadcast_to(hour_of_day[:, None], (T, n_pairs))
    feat_arrays["dow"] = np.broadcast_to(dow[:, None], (T, n_pairs))

    # 10. dislocation size (bps)
    feat_arrays["disloc_bps"] = np.abs(residuals) * 1e4

    # Assemble flat DataFrame
    rows: list[dict] = []
    feat_names = list(feat_arrays.keys())
    for t in range(T):
        h = hours[t]
        for j, sym in enumerate(MAJORS):
            row: dict = {"timestamp": h, "pair": sym}
            for name in feat_names:
                row[name] = feat_arrays[name][t, j]
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.set_index(["timestamp", "pair"]).sort_index()
    return df


def _build_labels_and_capture(
    residuals: np.ndarray, cost_bps: float = COMMISSION_RT_BPS
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Labels and captures for next-hour fade.

    residuals shape (T, 6) aligned to signal hours. Capture is measured
    mid-to-mid; round-trip taker cost referenced to mid = ONE full quoted
    spread, but here we charge a flat commission (`cost_bps`) instead because
    that is the real Pepperstone execution cost (see COMMISSION_RT_BPS).
    Returns flat arrays of length T*6:
      y: 1 if fade wins, 0 otherwise
      capture: gross capture in bps
      net: capture - cost_bps
    """
    s = residuals[:-1]          # signal at t
    fwd = residuals[1:]         # forward residual at t+1
    cap = -np.sign(s) * fwd
    y = (cap > 0).astype(int)
    capture_bps = cap * 1e4
    net_bps = capture_bps - cost_bps
    # Flatten pair-major order (t, pair)
    y_flat = y.ravel(order="C")
    capture_flat = capture_bps.ravel(order="C")
    net_flat = net_bps.ravel(order="C")
    return y_flat, capture_flat, net_flat


def _print_per_pair_baseline(residuals: np.ndarray) -> None:
    """Always-fade economics per pair on the 6-12bps band under flat commission."""
    s = residuals[:-1]
    fwd = residuals[1:]
    cap = -np.sign(s) * fwd
    absb = np.abs(s) * 1e4
    print(f"\nPer-pair always-fade baseline (6-12bps band, cost={COMMISSION_RT_BPS}bps RT flat):")
    print("  pair      n     gross    net    win%")
    for j, sym in enumerate(MAJORS):
        m = (absb[:, j] >= BAND_LO_BPS) & (absb[:, j] < BAND_HI_BPS)
        if m.sum() < 50:
            continue
        g = cap[m, j].mean() * 1e4
        print(f"  {sym}  {m.sum():>6}  {g:+.3f}  {g - COMMISSION_RT_BPS:+.3f}   {(cap[m, j] > 0).mean() * 100:.0f}")


def _monthly_stats(values: np.ndarray, months: pd.Series) -> dict[str, float]:
    """Aggregate flat values by month."""
    df = pd.DataFrame({"month": months.to_numpy(), "v": values})
    grouped = df.groupby("month")["v"].sum()
    pos_frac = (grouped > 0).mean()
    return {
        "mean": values.mean(),
        "t": values.mean() / values.std() * np.sqrt(len(values)) if values.std() > 0 else 0.0,
        "sharpe_h": values.mean() / values.std() if values.std() > 0 else 0.0,
        "pos_month_pct": pos_frac * 100,
        "n": len(values),
    }


def _evaluate_selection(
    capture: np.ndarray,
    net: np.ndarray,
    months: pd.Series,
    mask: np.ndarray,
    label: str,
) -> dict[str, float]:
    """Evaluate a boolean selection mask over the flat sample."""
    active = mask.sum() / len(mask)
    if mask.sum() < 30:
        return {"label": label, "active_pct": active * 100, "n": mask.sum()}
    c = capture[mask]
    n = net[mask]
    m = months[mask]
    gross_stats = _monthly_stats(c, m)
    net_stats = _monthly_stats(n, m)
    return {
        "label": label,
        "active_pct": active * 100,
        "n": mask.sum(),
        "gross_mean_bps": gross_stats["mean"],
        "gross_t": gross_stats["t"],
        "gross_sharpe_h": gross_stats["sharpe_h"],
        "pos_month_gross": gross_stats["pos_month_pct"],
        "net_mean_bps": net_stats["mean"],
        "net_t": net_stats["t"],
        "net_sharpe_h": net_stats["sharpe_h"],
        "pos_month_net": net_stats["pos_month_pct"],
        "win_pct": (c > 0).mean() * 100,
    }


def _print_results(results: list[dict[str, float]]) -> None:
    print(f"\n{'model':<22} {'active%':>7} {'n':>8} {'gross':>7} {'gross_t':>7} {'net':>7} {'net_t':>7} {'win%':>6} {'pos_mo':>6}")
    print("-" * 95)
    for r in results:
        print(
            f"{r['label']:<22} "
            f"{r.get('active_pct', 0):>7.1f} "
            f"{r.get('n', 0):>8} "
            f"{r.get('gross_mean_bps', 0):>+7.3f} "
            f"{r.get('gross_t', 0):>7.1f} "
            f"{r.get('net_mean_bps', 0):>+7.3f} "
            f"{r.get('net_t', 0):>7.1f} "
            f"{r.get('win_pct', 0):>6.1f} "
            f"{r.get('pos_month_net', 0):>6.0f}"
        )


def main() -> None:
    print("Loading aligned 5min panel ...")
    fine = load_aligned(FINE_FREQ, TICK_BAR, MAJORS)
    print(f"  fine panel: {fine.shape}")

    print("Coarsening to hourly ...")
    hourly = coarsen(fine, COARSE_FREQ)
    print(f"  hourly panel: {hourly.shape}")

    print("Computing oriented returns & residuals ...")
    hours, oriented = _oriented_returns(hourly)
    factor, residuals = _residuals(oriented)

    print("Building causal features ...")
    features_df = _build_features(hourly, fine, oriented, residuals, factor)

    print("Building labels & captures ...")
    y_flat, capture_flat, net_flat = _build_labels_and_capture(residuals, COMMISSION_RT_BPS)

    # Per-pair baseline economics on the 6-12bps band under flat commission.
    _print_per_pair_baseline(residuals)

    # Features have one extra hour (the last hour has no forward). Trim it.
    # _build_features always creates exactly 6 rows per hour, sorted by hour.
    features_df = features_df.iloc[:-6]

    # month strings for the flat index (hours repeated n_pairs times)
    signal_hours = hours[:-1]
    months_flat = pd.Series(np.repeat(signal_hours.strftime("%Y-%m").to_numpy(), len(MAJORS)))

    # Band mask: 6–12 bps on |residual|
    disloc_bps = np.abs(residuals[:-1].ravel(order="C")) * 1e4
    band_mask = (disloc_bps >= BAND_LO_BPS) & (disloc_bps < BAND_HI_BPS)

    # Drop rows with any NaN features
    feature_cols = [c for c in features_df.columns if c not in CAT_FEATURES]
    feat_mat = features_df[feature_cols].to_numpy()
    valid = np.isfinite(feat_mat).all(axis=1) & np.isfinite(y_flat) & np.isfinite(capture_flat)
    usable = band_mask & valid
    print(f"  usable band rows: {usable.sum():,} / {len(usable):,}")

    # Flat arrays restricted to usable rows
    X_all = features_df.loc[usable].copy()
    y_all = y_flat[usable]
    cap_all = capture_flat[usable]
    net_all = net_flat[usable]
    months_all = months_flat[usable]
    # reset index to simple positional for numpy slicing
    X_all = X_all.reset_index(drop=True)

    # Numeric / categorical split
    num_cols = [c for c in feature_cols]
    cat_cols = [c for c in CAT_FEATURES if c in X_all.columns]

    # Walk-forward windows on the hourly index (the original hours, not flat)
    # We need to map each flat row to its hour index for window assignment.
    n_signal = len(signal_hours)
    hour_index_for_flat = np.repeat(np.arange(n_signal), len(MAJORS))[usable]

    # Build windows from the hourly time series
    dummy_hourly = pd.DataFrame(index=hours)
    windows = list(walk_forward_windows(dummy_hourly, train_years=2, step_years=1, purge="5D"))
    print(f"  walk-forward windows: {len(windows)}")

    baseline_results: list[dict] = []
    lr_results: list[dict] = []
    cb_results: list[dict] = []

    for w_idx, (train_df, oos_df) in enumerate(windows, start=1):
        train_start, train_end = train_df.index.min(), train_df.index.max()
        oos_start, oos_end = oos_df.index.min(), oos_df.index.max()
        print(f"\nWindow {w_idx}: train {train_start.date()}–{train_end.date()}  OOS {oos_start.date()}–{oos_end.date()}")

        # map to flat positional indices
        train_mask = (hours[hour_index_for_flat] >= train_start) & (hours[hour_index_for_flat] <= train_end)
        oos_mask = (hours[hour_index_for_flat] >= oos_start) & (hours[hour_index_for_flat] <= oos_end)

        if train_mask.sum() < 500 or oos_mask.sum() < 200:
            print("  too few samples, skipping")
            continue

        X_train = X_all[num_cols].loc[train_mask].to_numpy()
        y_train = y_all[train_mask]
        X_oos = X_all[num_cols].loc[oos_mask].to_numpy()
        y_oos = y_all[oos_mask]
        cap_oos = cap_all[oos_mask]
        net_oos = net_all[oos_mask]
        months_oos = months_all[oos_mask]

        # --- Baseline: always fade in band ---
        baseline_results.append(
            _evaluate_selection(
                cap_oos, net_oos, months_oos,
                np.ones(len(y_oos), dtype=bool), "baseline",
            )
        )

        # --- Logistic Regression ---
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_oos_s = scaler.transform(X_oos)
        lr = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lr.fit(X_train_s, y_train)
        probs_lr = lr.predict_proba(X_oos_s)[:, 1]

        # threshold sweep on train to pick best net Sharpe
        probs_lr_train = lr.predict_proba(X_train_s)[:, 1]
        best_thr = 0.55
        best_score = -np.inf
        for thr in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
            sel = probs_lr_train >= thr
            if sel.sum() < 30:
                continue
            n_sel = net_all[train_mask][sel]
            score = n_sel.mean() / (n_sel.std() + 1e-12) * np.sqrt(sel.sum())
            if score > best_score:
                best_score = score
                best_thr = thr
        print(f"  LR selected threshold: {best_thr:.2f}  (train net t={best_score:.1f})")

        sel_lr = probs_lr >= best_thr
        lr_results.append(
            _evaluate_selection(
                cap_oos, net_oos, months_oos, sel_lr, "logistic",
            )
        )

        # --- CatBoost (only if LR shows gross lift) ---
        # Condition: LR gross mean > baseline gross mean on OOS
        lr_gross = cap_oos[sel_lr].mean() if sel_lr.sum() > 0 else -np.inf
        base_gross = cap_oos.mean()
        if lr_gross > base_gross + 0.01:
            print("  LR shows gross lift → running CatBoost")
            X_train_cb = X_all.loc[train_mask].copy()
            X_oos_cb = X_all.loc[oos_mask].copy()
            # catboost accepts DataFrames with categorical indices
            cat_feature_indices = [X_train_cb.columns.get_loc(c) for c in cat_cols]
            cb = CatBoostClassifier(
                depth=4,
                iterations=200,
                l2_leaf_reg=5,
                learning_rate=0.1,
                loss_function="Logloss",
                eval_metric="AUC",
                verbose=False,
                random_seed=42,
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cb.fit(
                    X_train_cb, y_train,
                    cat_features=cat_feature_indices,
                    verbose=False,
                )
            probs_cb = cb.predict_proba(X_oos_cb)[:, 1]

            # threshold on train
            probs_cb_train = cb.predict_proba(X_train_cb)[:, 1]
            best_thr_cb = 0.55
            best_score_cb = -np.inf
            for thr in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
                sel = probs_cb_train >= thr
                if sel.sum() < 30:
                    continue
                n_sel = net_all[train_mask][sel]
                score = n_sel.mean() / (n_sel.std() + 1e-12) * np.sqrt(sel.sum())
                if score > best_score_cb:
                    best_score_cb = score
                    best_thr_cb = thr
            print(f"  CB selected threshold: {best_thr_cb:.2f}  (train net t={best_score_cb:.1f})")

            sel_cb = probs_cb >= best_thr_cb
            cb_results.append(
                _evaluate_selection(
                    cap_oos, net_oos, months_oos, sel_cb, "catboost",
                )
            )
        else:
            print("  LR gross lift insufficient → skipping CatBoost")

    # Aggregate across windows (simple mean of per-window metrics)
    def _agg(res_list: list[dict]) -> dict:
        if not res_list:
            return {}
        keys = [k for k in res_list[0] if k not in ("label",)]
        out: dict = {"label": res_list[0]["label"]}
        for k in keys:
            vals = [r[k] for r in res_list if k in r]
            if vals:
                out[k] = np.mean(vals)
        return out

    print("\n" + "=" * 95)
    print("AGGREGATED ACROSS WALK-FORWARD WINDOWS")
    print("=" * 95)
    all_res = [_agg(baseline_results), _agg(lr_results)]
    if cb_results:
        all_res.append(_agg(cb_results))
    _print_results(all_res)

    # Feature importance (LR coefficients averaged across windows if possible)
    # Simplified: print LR coeffs from the last fitted model
    if "lr" in dir() and hasattr(lr, "coef_"):
        print("\nLR feature coefficients (last window):")
        for name, coef in zip(num_cols, lr.coef_[0]):
            print(f"  {name:<24} {coef:+.4f}")


if __name__ == "__main__":
    main()
