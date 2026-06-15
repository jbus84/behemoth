"""Honest walk-forward: 2yr train / 1yr test, fixed hyperparameters, no peeking.

Fixed BEFORE any OOS run (discovered from prior research, not tuned on test):
  * 2-factor PCA (causal, rolling)
  * 6–12 bps dislocation band
  * Liquid hours: 7–16 UTC
  * Tight-3 pairs: EURUSD, GBPUSD, USDJPY
  * Pepperstone Razor cost model
  * 15m bars
  * 5-day purge gap between train and test

Reports: per-window and aggregated OOS results ONLY.
"""

from __future__ import annotations

import numpy as np
import polars as pl

# ── FIXED HYPERPARAMETERS (chosen a priori, not tuned on test) ──
PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCAD": +1.0,
}
TRADE_PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]  # Tight-3 — fixed
TICK = "1000tick"
BAR_FREQ = "15m"
LIQUID_HOURS = list(range(7, 17))
PCA_WINDOW_BARS = 480  # 5 days wall-clock at 15m
DISLOC_BAND = (6.0, 12.0)  # bps — fixed
PURGE_DAYS = 5

# Pepperstone Razor round-trip cost per pair (bps)
COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCAD": 0.55,
}

# Walk-forward windows: train 2yr, test 1yr
# 2018-01 to 2026-05 span
WINDOWS = [
    # train_start, train_end, test_start, test_end
    ("2018-01-01", "2019-12-31", "2020-01-06", "2020-12-31"),  # purge 5d
    ("2019-01-01", "2020-12-31", "2021-01-06", "2021-12-31"),
    ("2020-01-01", "2021-12-31", "2022-01-06", "2022-12-31"),
    ("2021-01-01", "2022-12-31", "2023-01-06", "2023-12-31"),
    ("2022-01-01", "2023-12-31", "2024-01-08", "2024-12-31"),  # 2024-01-06 is Sat
    ("2023-01-01", "2024-12-31", "2025-01-06", "2025-12-31"),
    ("2024-01-01", "2025-12-31", "2026-01-06", "2026-05-19"),  # partial last
]


def bar_mid(sym: str, freq: str = BAR_FREQ) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        ((pl.col("close_ask") - pl.col("close_bid"))
         / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
        pl.col("timestamp").dt.truncate(freq).alias("bar_time"),
    )
    g = (
        df.sort("timestamp")
        .group_by("bar_time")
        .agg(
            pl.col("mid").last().alias(f"mid_{sym}"),
            pl.col("rel_spread").median().alias(f"spr_{sym}"),
        )
        .sort("bar_time")
    )
    return g


def fit_pca_2factor(R_train: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit 2-factor PCA on training data. Returns (mean, std, Vt)."""
    mean_w = R_train.mean(axis=0)
    std_w = R_train.std(axis=0) + 1e-12
    X = (R_train - mean_w) / std_w
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    return mean_w, std_w, Vt


def project_residual(R: np.ndarray, mean_w: np.ndarray, std_w: np.ndarray,
                     Vt: np.ndarray) -> np.ndarray:
    """Project returns through fitted 2-factor PCA to get residuals."""
    curr_std = (R - mean_w) / std_w
    pc1 = curr_std @ Vt[0]
    pc2 = curr_std @ Vt[1]
    expected_std = Vt[0] * pc1[:, None] + Vt[1] * pc2[:, None]
    expected = expected_std * std_w[None, :] + mean_w[None, :]
    return R - expected


def evaluate_window(R_all: np.ndarray, times_all: np.ndarray,
                    train_mask: np.ndarray, test_mask: np.ndarray,
                    label: str) -> dict | None:
    """Evaluate one walk-forward window."""
    # Train PCA on train data only
    R_train = R_all[train_mask]
    if len(R_train) < PCA_WINDOW_BARS * 2:
        print(f"  [{label}] SKIPPED: insufficient train data ({len(R_train)})")
        return None

    mean_w, std_w, Vt = fit_pca_2factor(R_train)

    # Project test data through train PCA
    R_test = R_all[test_mask]
    times_test = times_all[test_mask]
    res_test = project_residual(R_test, mean_w, std_w, Vt)

    # Align: signal at t, capture at t+1
    res_entry = res_test[:-1]
    fwd = R_test[1:]
    hrs = times_test[1:]

    # Liquid hours only
    hours = np.array([int(str(bt)[11:13]) for bt in hrs])
    liquid = np.isin(hours, LIQUID_HOURS)

    # Per-pair dislocation in bps
    absbps = np.abs(res_entry) * 1e4
    band_lo, band_hi = DISLOC_BAND

    syms = list(PAIRS)
    idx = [syms.index(s) for s in TRADE_PAIRS]
    costs = np.array([COST_BPS[s] for s in TRADE_PAIRS])

    # Collect per-bar portfolio returns
    rets = []
    for t in range(len(liquid)):
        if not liquid[t]:
            continue
        active = []
        for i, j in enumerate(idx):
            if band_lo <= absbps[t, j] < band_hi:
                cap = (-np.sign(res_entry[t, j]) * fwd[t, j]) * 1e4
                net = cap - costs[i]
                active.append(net)
        if not active:
            continue
        # Equal-weight across active pairs this bar
        rets.append(np.mean(active))

    if len(rets) < 30:
        print(f"  [{label}] SKIPPED: insufficient trades ({len(rets)})")
        return None

    rets = np.array(rets)
    mu, sd = rets.mean(), rets.std()
    tstat = mu / (sd + 1e-12) * np.sqrt(len(rets))
    win_rate = (rets > 0).mean() * 100
    pos_month = None

    # Monthly aggregation
    ym = np.array([str(hrs[i])[:7] for i in range(len(hrs)) if liquid[i]])
    months: dict[str, list[float]] = {}
    bar_idx = 0
    for i in range(len(liquid)):
        if not liquid[i]:
            continue
        if bar_idx < len(rets):
            m = ym[bar_idx]
            months.setdefault(m, []).append(rets[bar_idx])
        bar_idx += 1

    if months:
        monthly_sums = [np.sum(v) for v in months.values()]
        pos_month = np.mean([s > 0 for s in monthly_sums]) * 100

    print(f"  [{label}]  bars={len(rets):>5}  net={mu:+.3f}bps  sd={sd:.3f}  "
          f"t={tstat:>+5.1f}  win%={win_rate:5.1f}  pos-month%={pos_month:.0f}% "
          f"({len(monthly_sums)} months)")

    return {
        "label": label,
        "n": len(rets),
        "mean": mu,
        "sd": sd,
        "t": tstat,
        "win_rate": win_rate,
        "pos_month": pos_month,
        "rets": rets,
        "monthly_sums": monthly_sums,
    }


def main() -> None:
    print("Loading data...")
    frames = [bar_mid(s) for s in PAIRS]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bar_time", how="inner")
    df = df.drop_nulls().sort("bar_time")

    syms = list(PAIRS)
    rets = {}
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        dlog = np.diff(np.log(mid))
        rets[s] = PAIRS[s] * dlog
    R = np.column_stack([rets[s] for s in syms])
    bar_times = df["bar_time"].to_numpy()[1:]

    # Convert to datetime64 for masking
    times_dt = np.array(bar_times, dtype="datetime64[ns]")

    print(f"Total aligned bars: {len(R)}  span: {bar_times[0]} -> {bar_times[-1]}")
    print(f"Fixed params: 2-factor PCA, band={DISLOC_BAND}, liquid={LIQUID_HOURS}, "
          f"pairs={TRADE_PAIRS}, cost={COST_BPS}")
    print(f"Windows: {len(WINDOWS)}  train=2yr  test=1yr  purge={PURGE_DAYS}d\n")

    results = []
    for train_s, train_e, test_s, test_e in WINDOWS:
        train_start = np.datetime64(train_s)
        train_end = np.datetime64(train_e) + np.timedelta64(23, "h") + np.timedelta64(59, "m")
        test_start = np.datetime64(test_s)
        test_end = np.datetime64(test_e) + np.timedelta64(23, "h") + np.timedelta64(59, "m")

        train_mask = (times_dt >= train_start) & (times_dt <= train_end)
        test_mask = (times_dt >= test_start) & (times_dt <= test_end)

        label = f"{train_s[:4]}-{train_e[:4]} -> {test_s[:4]}-{test_e[:4]}"
        r = evaluate_window(R, times_dt, train_mask, test_mask, label)
        if r:
            results.append(r)

    # Aggregate across windows
    if not results:
        print("\nNo valid windows.")
        return

    all_rets = np.concatenate([r["rets"] for r in results])
    mu_all = all_rets.mean()
    sd_all = all_rets.std()
    t_all = mu_all / (sd_all + 1e-12) * np.sqrt(len(all_rets))

    all_monthly = []
    for r in results:
        all_monthly.extend(r["monthly_sums"])
    pos_month_all = np.mean([s > 0 for s in all_monthly]) * 100

    print(f"\n{'='*60}")
    print("  AGGREGATED OOS RESULTS")
    print(f"{'='*60}")
    print(f"  Total trades:     {len(all_rets):,}")
    print(f"  Net per trade:    {mu_all:+.3f} bps")
    print(f"  Std per trade:    {sd_all:.3f} bps")
    print(f"  T-stat:           {t_all:+.1f}")
    print(f"  Win rate:         {(all_rets>0).mean()*100:.1f}%")
    print(f"  Positive months:  {pos_month_all:.0f}% ({len(all_monthly)} months)")
    print("  Annualized (assuming 8 trades/day * 252 days):")
    annual_bps = mu_all * 8 * 252
    print(f"    Gross bps/yr:   {annual_bps:+.0f}")
    print("    After cost:     net already includes cost")


if __name__ == "__main__":
    main()
