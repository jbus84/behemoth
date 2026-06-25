"""Frequency comparison: 5m vs 15m vs 30m vs 1h walk-forward.

Uses the SAME fixed hyperparameters from the validated 15m model:
  * 2-factor PCA (causal, rolling)
  * 6–12 bps dislocation band
  * Liquid hours 7–16 UTC
  * Tight-3 pairs: EURUSD, GBPUSD, USDJPY
  * Pepperstone Razor cost
  * 2yr train / 1yr test / 5d purge

Tests whether faster (5m) or slower (1h) frequency improves the OOS edge.
"""

from __future__ import annotations

import numpy as np
import polars as pl

PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCAD": +1.0,
}
TRADE_PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]
TICK = "1000tick"
LIQUID_HOURS = list(range(7, 17))
DISLOC_BAND = (6.0, 12.0)
COST_BPS: dict[str, float] = {
    "EURUSD": 0.40,
    "GBPUSD": 0.50,
    "AUDUSD": 0.55,
    "USDJPY": 0.45,
    "USDCAD": 0.55,
}

# PCA window in wall-clock terms: 5 days
# At 5m: 5 * 24 * 60 / 5 = 1440 bars
# At 15m: 5 * 24 * 60 / 15 = 480 bars
# At 30m: 5 * 24 * 60 / 30 = 240 bars
# At 1h: 5 * 24 = 120 bars
PCA_WINDOW_DAYS = 5

WINDOWS = [
    ("2018-01-01", "2019-12-31", "2020-01-06", "2020-12-31"),
    ("2019-01-01", "2020-12-31", "2021-01-06", "2021-12-31"),
    ("2020-01-01", "2021-12-31", "2022-01-06", "2022-12-31"),
    ("2021-01-01", "2022-12-31", "2023-01-06", "2023-12-31"),
    ("2022-01-01", "2023-12-31", "2024-01-08", "2024-12-31"),
    ("2023-01-01", "2024-12-31", "2025-01-06", "2025-12-31"),
    ("2024-01-01", "2025-12-31", "2026-01-06", "2026-05-19"),
]


def bar_mid(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("timestamp").dt.truncate(freq).alias("bar_time"),
    )
    return (df.sort("timestamp").group_by("bar_time").agg(pl.col("mid").last().alias(f"mid_{sym}")).sort("bar_time"))


def fit_pca_2factor(R_train: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean_w = R_train.mean(axis=0)
    std_w = R_train.std(axis=0) + 1e-12
    X = (R_train - mean_w) / std_w
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    return mean_w, std_w, Vt


def project_residual(R: np.ndarray, mean_w: np.ndarray, std_w: np.ndarray, Vt: np.ndarray) -> np.ndarray:
    curr_std = (R - mean_w) / std_w
    pc1 = curr_std @ Vt[0]
    pc2 = curr_std @ Vt[1]
    expected_std = Vt[0] * pc1[:, None] + Vt[1] * pc2[:, None]
    return R - (expected_std * std_w[None, :] + mean_w[None, :])


def evaluate_window(R_all: np.ndarray, times_all: np.ndarray,
                    train_mask: np.ndarray, test_mask: np.ndarray) -> list[float] | None:
    R_train = R_all[train_mask]
    if len(R_train) < 100:
        return None
    mean_w, std_w, Vt = fit_pca_2factor(R_train)
    R_test = R_all[test_mask]
    res_test = project_residual(R_test, mean_w, std_w, Vt)
    res_entry = res_test[:-1]
    fwd = R_test[1:]
    hrs = times_all[test_mask][1:]
    hours = np.array([int(str(bt)[11:13]) for bt in hrs])
    liquid = np.isin(hours, LIQUID_HOURS)
    absbps = np.abs(res_entry) * 1e4
    syms = list(PAIRS)
    idx = [syms.index(s) for s in TRADE_PAIRS]
    costs = np.array([COST_BPS[s] for s in TRADE_PAIRS])

    rets = []
    for t in range(len(liquid)):
        if not liquid[t]:
            continue
        active = []
        for i, j in enumerate(idx):
            if DISLOC_BAND[0] <= absbps[t, j] < DISLOC_BAND[1]:
                cap = (-np.sign(res_entry[t, j]) * fwd[t, j]) * 1e4
                active.append(cap - costs[i])
        if active:
            rets.append(np.mean(active))
    return rets


def run_freq(freq: str, freq_label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  FREQUENCY: {freq_label}")
    print(f"{'='*60}")

    # Compute PCA window bars for this frequency
    freq_min = int(freq.replace("m", "").replace("h", "") * (60 if "h" in freq else 1))
    pca_window = PCA_WINDOW_DAYS * 24 * 60 // freq_min

    frames = [bar_mid(s, freq) for s in PAIRS]
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
    times_dt = np.array(bar_times, dtype="datetime64[ns]")

    print(f"  Bars: {len(R)}  span: {bar_times[0]} -> {bar_times[-1]}")
    print(f"  PCA window: {pca_window} bars ({PCA_WINDOW_DAYS} days wall-clock)")

    all_rets = []
    for train_s, train_e, test_s, test_e in WINDOWS:
        train_start = np.datetime64(train_s)
        train_end = np.datetime64(train_e) + np.timedelta64(23, "h")
        test_start = np.datetime64(test_s)
        test_end = np.datetime64(test_e) + np.timedelta64(23, "h")
        train_mask = (times_dt >= train_start) & (times_dt <= train_end)
        test_mask = (times_dt >= test_start) & (times_dt <= test_end)

        label = f"{train_s[:4]}-{train_e[:4]} -> {test_s[:4]}-{test_e[:4]}"
        r = evaluate_window(R, times_dt, train_mask, test_mask)
        if r and len(r) >= 30:
            arr = np.array(r)
            mu, sd = arr.mean(), arr.std()
            t = mu / (sd + 1e-12) * np.sqrt(len(arr))
            print(f"  [{label}]  n={len(arr):>5}  net={mu:+.3f}bps  t={t:+.1f}  win%={(arr>0).mean()*100:.1f}")
            all_rets.extend(r)
        else:
            print(f"  [{label}]  (insufficient trades)")

    if all_rets:
        all_arr = np.array(all_rets)
        mu = all_arr.mean()
        sd = all_arr.std()
        t = mu / (sd + 1e-12) * np.sqrt(len(all_arr))
        print(f"\n  === AGGREGATED OOS ({freq_label}) ===")
        print(f"    Trades:     {len(all_arr):,}")
        print(f"    Net/trade:  {mu:+.3f} bps")
        print(f"    T-stat:     {t:+.1f}")
        print(f"    Win rate:   {(all_arr>0).mean()*100:.1f}%")
    else:
        print(f"\n  No valid trades.")


def main() -> None:
    for freq, label in [("5m", "5m"), ("15m", "15m"), ("30m", "30m"), ("1h", "1h")]:
        run_freq(freq, label)


if __name__ == "__main__":
    main()
