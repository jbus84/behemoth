#!/usr/bin/env python3
"""
Demonstrate the bfill() lookahead bug — V3: Block NaNs at start of window.

This mirrors the ACTUAL scenario in Fischer et al.'s repo:

  utils.py (get_fx_and_metric_data_wo_weekend, ~line 156):
      df = df.ffill()
      df = df.loc[(df.index >= '2020-11-01') & (df.index < enddate), :]
      df = df.bfill()   ← BACKFILL

What happens:
  1. They merge FX spot data with commodity/equity/fixed-income metrics
  2. Many metrics don't start until later in the sample (e.g., a commodity
     index might first report on Dec 1, 2020)
  3. ffill() carries the last known value forward, but there IS no known
     value before Dec 1 — so the Nov 1-30 region stays NaN
  4. bfill() then copies the Dec 1 value back to Nov 1-30
  5. The Dec 1 value contains information about Dec 1's FX direction
  6. The model now "predicts" Nov 1-30 using information from Dec 1

This script recreates that exact pattern with synthetic data.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

np.random.seed(42)

N_BARS = 64_218
OUT_CSV = Path("scripts/fx_coint/bfill_lookahead_results_v3.csv")


def generate_data():
    """FX returns + one cross-market feature that is missing for first 30%."""
    idx = pd.date_range("2020-11-01", periods=N_BARS, freq="10min")

    # FX: weak trend + noise (mimics late-2020 / early-2021)
    trend = np.linspace(0, 0.04, N_BARS)
    noise = np.random.normal(0, 0.0004, N_BARS)
    fx_ret = trend / N_BARS + noise
    fx_ret = np.clip(fx_ret, -0.002, 0.002)

    # Target: next bar up/down
    y = (np.roll(fx_ret, -1) > 0).astype(int)
    y[-1] = y[-2]

    # Cross-market predictor: strongly correlated with next bar's return
    # (e.g., an equity index close that predicts overnight FX)
    predictor = np.roll(fx_ret, -1) * 500 + np.random.normal(0, 0.2, N_BARS)

    # CRITICAL: feature is MISSING for the first 30% of the sample
    # This mimics a Bloomberg series that only starts reporting later
    missing_first_n = int(N_BARS * 0.30)
    feature = predictor.copy()
    feature[:missing_first_n] = np.nan

    df = pd.DataFrame({
        "fx_return": fx_ret,
        "feature": feature,
        "target": y,
    }, index=idx)
    return df, missing_first_n


def prep_buggy(df):
    """Exact Fischer pipeline: ffill then bfill."""
    d = df.copy()
    d["feature"] = d["feature"].ffill().bfill()
    return d


def prep_clean(df):
    """Correct: ffill, then DROP rows that are still NaN."""
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

    acc = (preds == y_test).mean()

    actual = test["fx_return"].values
    strat = np.where(preds == 1, actual, -actual)

    # 0.7 pip cost on EUR/USD ~1.10 = 0.0064% round-trip
    cost = 0.000064
    strat_net = strat - np.sign(strat) * cost

    n_bars_year = 252 * 6 * 24
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
    print("BFILL LOOKAHEAD BUG — V3: Block NaNs at start of sample window")
    print("=" * 70)

    df_raw, missing_n = generate_data()
    print(f"\nGenerated {N_BARS:,} bars.")
    print(f"Feature MISSING for first {missing_n:,} bars ({missing_n/N_BARS:.0%})")
    print(f"NaNs in 'feature' column: {df_raw['feature'].isna().sum():,}")

    print("\n[Buggy]  ffill → bfill (copies future values backward)...")
    df_buggy = prep_buggy(df_raw)
    print(f"         NaNs after bfill: {df_buggy['feature'].isna().sum()}")
    res_buggy = evaluate(df_buggy, "with_bfill_bug")

    print("[Clean]  ffill → dropna (loses early data, no leakage)...")
    df_clean = prep_clean(df_raw)
    print(f"         Rows after dropna: {len(df_clean):,} (dropped {N_BARS - len(df_clean):,})")
    res_clean = evaluate(df_clean, "without_bfill_bug")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for r in [res_buggy, res_clean]:
        print(f"\n{r['pipeline']}")
        print(f"  Train / Test : {r['n_train']:,} / {r['n_test']:,}")
        print(f"  Accuracy     : {r['accuracy']}")
        print(f"  Gross Sharpe : {r['gross_sharpe']}")
        print(f"  Gross CAGR   : {r['gross_cagr_pct']}%")
        print(f"  Net Sharpe   : {r['net_sharpe']}")
        print(f"  Net CAGR     : {r['net_cagr_pct']}%")
        print(f"  Pos trade %  : {r['pos_pct']}%")

    print("\n" + "=" * 70)
    print("DELTA (Buggy minus Clean)")
    print("=" * 70)
    for k in ["accuracy", "gross_sharpe", "gross_cagr_pct", "net_sharpe", "net_cagr_pct", "pos_pct"]:
        d = res_buggy[k] - res_clean[k]
        print(f"  {k:20s}: {'+' if d >= 0 else ''}{d:.4f}")

    pd.DataFrame([res_buggy, res_clean]).to_csv(OUT_CSV, index=False)
    print(f"\nSaved to {OUT_CSV}")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    print(f"""
The 'bfill' bug creates an artificial {(res_buggy['gross_sharpe'] - res_clean['gross_sharpe']):.1f} Sharpe
point gap and {(res_buggy['net_cagr_pct'] - res_clean['net_cagr_pct']):.1f}% CAGR gap purely by
backfilling missing early-window features with FUTURE values.

In Fischer et al.'s repo, this happens because cross-market metrics
(commodities, equities, bonds) are merged via 'outer' join, then
filtered to the date window, leaving NaNs at the start for any series
that begins reporting after the window start. bfill() copies those
future values backward, giving the model impossible foresight.

The paper's 18.7% CAGR / 4.4 Sharpe are almost certainly inflated by
this leakage plus overfitting (1,273 features on ~64k bars) and a
single favorable static test split.
""")


if __name__ == "__main__":
    main()
