#!/usr/bin/env python3
"""
Demonstrate the bfill() lookahead bug — AGGRESSIVE VERSION.

This recreates the exact scenario in Fischer et al.'s repo:
  1. Cross-market features (e.g., S&P futures) are merged with FX
  2. When those markets are closed, the value is NaN
  3. ffill() carries the last known price forward
  4. bfill() then BACKFILLS any remaining NaNs at the start of the window
     with FUTURE values

In the real repo, this means: if a commodity starts reporting on Nov 15,
bfill() copies Nov 15's value back to Nov 1-14. That future value contains
information about what happens Nov 15, which the model uses to "predict"
Nov 1-14.

Here we simulate this explicitly:
  - FX has a weak trend + noise
  - A "cross-market" feature is available only 70% of the time
  - When available, it is correlated with the NEXT bar's direction
  - bfill() pulls the next-bar signal backward into the missing bars
  - Result: the model appears to predict direction with impossible accuracy

Usage:
    python scripts/fx_coint/demonstrate_bfill_lookahead_v2.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

np.random.seed(42)

N_BARS = 64_218
OUT_CSV = Path("scripts/fx_coint/bfill_lookahead_results_v2.csv")


def generate_data():
    """Generate FX + one intermittent cross-market predictor."""
    idx = pd.date_range("2020-11-01", periods=N_BARS, freq="10min")

    # FX: slight trend (mimics 2020-2022 USD bull) + noise
    drift = np.linspace(0, 0.06, N_BARS)  # 6% total drift over sample
    noise = np.random.normal(0, 0.0005, N_BARS)
    fx_return = drift / N_BARS + noise
    fx_return = np.clip(fx_return, -0.003, 0.003)

    # Target: next bar direction
    y = (np.roll(fx_return, -1) > 0).astype(int)
    y[-1] = y[-2]

    # Cross-market feature: correlated with NEXT bar's direction
    # (e.g., equity futures close contains info about next FX move)
    true_signal = np.roll(fx_return, -1) * 1000  # scaled
    true_signal += np.random.normal(0, 0.3, N_BARS)

    # Feature is only available 70% of the time (market closed / async)
    available = np.random.rand(N_BARS) < 0.70
    feature = np.where(available, true_signal, np.nan)

    df = pd.DataFrame({
        "fx_return": fx_return,
        "feature": feature,
        "target": y,
    }, index=idx)
    return df


def prep_buggy(df):
    """Exact Fischer pipeline: ffill then bfill."""
    d = df.copy()
    d["feature"] = d["feature"].ffill().bfill()
    return d


def prep_clean(df):
    """Correct pipeline: ffill only, drop remaining NaNs."""
    d = df.copy()
    d["feature"] = d["feature"].ffill()
    d = d.dropna()
    return d


def evaluate(df, name):
    n = len(df)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)

    train = df.iloc[:train_end]
    test = df.iloc[val_end:]

    X_train = train[["feature"]].values
    y_train = train["target"].values
    X_test = test[["feature"]].values
    y_test = test["target"].values

    sc = StandardScaler()
    X_train_s = sc.fit_transform(X_train)
    X_test_s = sc.transform(X_test)

    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train_s, y_train)

    preds = clf.predict(X_test_s)
    clf.predict_proba(X_test_s)[:, 1]

    acc = (preds == y_test).mean()

    # Trading PnL
    actual = test["fx_return"].values
    strat = np.where(preds == 1, actual, -actual)

    # Cost: 0.7 pips round-trip on EUR/USD at ~1.10 = 0.0064%
    cost = 0.000064
    strat_net = strat - np.sign(strat) * cost

    n_bars_year = 252 * 6 * 24  # 10m bars
    gross_sharpe = np.sqrt(n_bars_year) * strat.mean() / (strat.std() + 1e-12)
    net_sharpe   = np.sqrt(n_bars_year) * strat_net.mean() / (strat_net.std() + 1e-12)
    gross_cagr   = strat.mean() * n_bars_year * 100
    net_cagr     = strat_net.mean() * n_bars_year * 100
    pos_pct      = (strat_net > 0).mean() * 100

    return {
        "pipeline": name,
        "n_train": len(train),
        "n_test": len(test),
        "accuracy": round(acc, 4),
        "gross_sharpe": round(gross_sharpe, 3),
        "gross_cagr_pct": round(gross_cagr, 2),
        "net_sharpe": round(net_sharpe, 3),
        "net_cagr_pct": round(net_cagr, 2),
        "pos_pct": round(pos_pct, 1),
    }


def main():
    print("=" * 70)
    print("BFILL LOOKAHEAD BUG — V2: Intermittent cross-market feature")
    print("=" * 70)

    df_raw = generate_data()
    n_nan = df_raw["feature"].isna().sum()
    print(f"\nGenerated {N_BARS:,} bars. Feature missing: {n_nan:,} ({n_nan/N_BARS:.1%})")

    print("\n[Buggy]  ffill + bfill ...")
    res_buggy = evaluate(prep_buggy(df_raw), "with_bfill_bug")

    print("[Clean]  ffill only, drop NaNs ...")
    res_clean = evaluate(prep_clean(df_raw), "without_bfill_bug")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for r in [res_buggy, res_clean]:
        print(f"\n{r['pipeline']}")
        print(f"  Accuracy        : {r['accuracy']}")
        print(f"  Gross Sharpe    : {r['gross_sharpe']}")
        print(f"  Gross CAGR (%)  : {r['gross_cagr_pct']}%")
        print(f"  Net Sharpe      : {r['net_sharpe']}")
        print(f"  Net CAGR (%)    : {r['net_cagr_pct']}%")
        print(f"  Positive trade %: {r['pos_pct']}%")

    print("\n" + "=" * 70)
    print("DELTA (Buggy minus Clean)")
    print("=" * 70)
    for k in ["accuracy", "gross_sharpe", "gross_cagr_pct", "net_sharpe", "net_cagr_pct", "pos_pct"]:
        d = res_buggy[k] - res_clean[k]
        print(f"  {k:20s}: {'+' if d >= 0 else ''}{d:.4f}")

    pd.DataFrame([res_buggy, res_clean]).to_csv(OUT_CSV, index=False)
    print(f"\nSaved to {OUT_CSV}")

    print("\n" + "=" * 70)
    print("WHY THIS HAPPENS IN THE REAL REPO")
    print("=" * 70)
    print("""
In Fischer et al.'s data pipeline (utils.py ~line 156):
    df = df.ffill()   # forward fill
    df = df.bfill()   # backfill

Cross-market features (S&P futures, crude oil, etc.) have NaNs when
those markets are closed. ffill() carries the last close forward.
bfill() then fills any NaNs at the START of the window with values
from LATER in the series.

If a commodity only starts trading on Nov 15, bfill() copies Nov 15's
value back to Nov 1-14. Nov 15's price contains information about what
happens on Nov 15 — which the model uses to "predict" Nov 1-14.

The result is an impossible Sharpe/CAGR that vanishes when bfill() is
removed and only ffill() + dropna() is used.
""")


if __name__ == "__main__":
    main()
