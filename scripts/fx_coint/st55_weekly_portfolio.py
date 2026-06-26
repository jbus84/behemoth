"""ST55 + WEEKLY mean-reversion portfolio — different timeframe, different mechanism.

The 2-day fade TB was too similar to ST55 (both intraday-ish, correlation -0.078).
This combines ST55 (~33h directional) with the validated WEEKLY mean-reversion
edge (H=5d, net +5.1p/trade) which is:
  - Longer hold (5 days vs ~33h)
  - Different mechanism (fade extended moves vs momentum continuation)
  - Cost-insensitive (weekly moves dwarf cost)

Expect: stronger diversification, negative or near-zero correlation.

Usage: uv run python scripts/fx_coint/st55_weekly_portfolio.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh
import scripts.fx_coint.st55_proven as base
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

# ── ST55 CONFIG ──
N_FOLDS = 5
COST_ST55 = base.COST
SEL_Q = 0.02
N_EVENTS = 60000
LOOKBACK = 30

# ── WEEKLY CONFIG ──
rsh.FREQ_MINUTES["1d"] = 1440
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
WEEKLY_FEATURES = ["r_1", "r_5", "r_20", "rvol_5d", "rvol_20d"]
RNG = np.random.default_rng(0)

COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


# ═══════════════════════════════════════════════════════════════════════════════
# ST55 trades (same as st55_tb_portfolio.py)
# ═══════════════════════════════════════════════════════════════════════════════
def _regime_features(oriented_returns, entry_idx, lookback):
    r = oriented_returns
    n = len(entry_idx)
    feats = np.full((n, 2), np.nan)
    for i, e in enumerate(entry_idx):
        lo = max(0, e - lookback)
        window = r[lo:e]
        if len(window) >= 20:
            feats[i, 0] = pd.Series(window).skew()
            feats[i, 1] = np.corrcoef(window[:-1], window[1:])[0, 1]
            if np.isnan(feats[i, 1]):
                feats[i, 1] = 0.0
    return feats


def build_regime_panel(d, frames, sym, n_tb, n_events, rng):
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], lookback=LOOKBACK)
    panel["regime"] = reg
    t = pd.DatetimeIndex(base._timestamps(sym)).to_numpy().astype("datetime64[ns]")
    panel["ts"] = t[panel["entry"]]
    return panel


def st55_trades(d, frames, rng):
    """Return DataFrame of ST55 trade-level PnL with timestamps."""
    records = []
    for s in base.POOL:
        panel = build_regime_panel(d, frames, s, base.N_TB, N_EVENTS, rng)
        all_entry = panel["entry"]
        edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))

        for fk in range(1, N_FOLDS):
            lo, hi = edges[fk], edges[fk + 1]
            Xtr, ytr, swtr = [], [], []
            tr_mask = panel["entry"] < lo
            gate = (panel["regime"][:, 0] > 0) & (panel["regime"][:, 1] < 0)
            tr = tr_mask & gate
            if tr.sum() < 1000:
                continue
            Xtr.append(panel["X"][tr])
            ytr.append((panel["ret"][tr] > 0).astype(int))
            swtr.append(panel["sw"][tr])
            yall = np.concatenate(ytr)
            if len(np.unique(yall)) < 2:
                continue
            clf = HistGradientBoostingClassifier(
                max_depth=3, max_iter=400, learning_rate=0.04,
                l2_regularization=1.0, random_state=0,
            )
            clf.fit(np.concatenate(Xtr), yall, sample_weight=np.concatenate(swtr))
            train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)
            thr = np.quantile(train_conf, 1 - SEL_Q)

            te = (panel["entry"] >= lo) & (panel["entry"] < hi)
            if te.sum() < 50:
                continue
            p = clf.predict_proba(panel["X"][te])[:, 1]
            conf = np.abs(p - 0.5)
            direction = np.sign(p - 0.5)
            gate_te = (panel["regime"][te][:, 0] > 0) & (panel["regime"][te][:, 1] < 0)
            sel = (conf >= thr) & gate_te
            if not sel.any():
                continue
            e = panel["entry"][te][sel]
            t1 = panel["t1"][te][sel]
            ts_entry = panel["ts"][te][sel]
            o = np.argsort(e)
            keep = greedy_nonoverlap(e[o], t1[o])
            for idx in np.where(keep)[0]:
                ii = o[idx]
                dd = direction[ii]
                rr = panel["ret"][te][sel][ii]
                records.append({
                    "sym": s,
                    "entry_ts": ts_entry[ii],
                    "pnl": dd * rr - COST_ST55,
                    "gross": dd * rr,
                    "direction": int(dd),
                    "hold_bars": int(base.N_TB),
                })
    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════════════════════════
# WEEKLY mean-reversion trades
# ═══════════════════════════════════════════════════════════════════════════════
def daily_series(sym):
    data_path = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not data_path.exists():
        candidate = _REPO_ROOT
        while candidate.name != "behemoth" and candidate.parent != candidate:
            candidate = candidate.parent
        data_path = candidate / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = rsh.build_freq_bars(
        pl.read_parquet(data_path),
        "1d", session=(0, 24)
    )
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def weekly_panel(sym):
    """Build weekly feature panel: momentum/vol features, target = forward 5d return."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)

    # Features
    f1 = rs.rolling(1, min_periods=1).sum()
    f5 = rs.rolling(5, min_periods=3).sum()
    f20 = rs.rolling(20, min_periods=10).sum()
    f60 = rs.rolling(60, min_periods=30).sum()
    f120 = rs.rolling(120, min_periods=60).sum()
    vol5 = rs.rolling(5, min_periods=3).std()
    vol20 = rs.rolling(20, min_periods=10).std()

    # Target = forward 5-day return
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[:n-5] = (np.log(mid[5:]) - np.log(mid[:n-5])) * 1e4

    df = pd.DataFrame({
        "bucket": pd.to_datetime(bk),
        "f1": f1.to_numpy(),
        "f5": f5.to_numpy(),
        "f20": f20.to_numpy(),
        "f60": f60.to_numpy(),
        "f120": f120.to_numpy(),
        "vol5": vol5.to_numpy(),
        "vol20": vol20.to_numpy(),
        "fwd": fwd,
    }).dropna()

    return df


def weekly_trades(sym, q=0.90, n_folds=5):
    """Fade past-10d extended move, hold 5 days, causal decile threshold."""
    df = weekly_panel(sym)
    if len(df) < 100:
        return pd.DataFrame()

    # Signal = past 10-day cumulative return (extended move)
    df["sig"] = df["f1"].rolling(10, min_periods=5).sum()
    df = df.dropna()

    # Walk-forward: train on first half, test on second half (expanding)
    n = len(df)
    records = []

    for k in range(1, n_folds):
        split = int(n * k / n_folds)
        train = df.iloc[:split]
        test = df.iloc[split:split + int(n / n_folds)]

        if len(train) < 50 or len(test) < 10:
            continue

        # Causal decile thresholds from training
        hi = train["sig"].quantile(q)
        lo = train["sig"].quantile(1 - q)

        for _, row in test.iterrows():
            s = row["sig"]
            c = cost(sym)
            if s >= hi:
                # Extended up -> fade short
                records.append({
                    "sym": sym,
                    "entry_ts": row["bucket"],
                    "pnl": -row["fwd"] - c,
                    "gross": -row["fwd"],
                    "direction": -1,
                    "hold_bars": 5,
                })
            elif s <= lo:
                # Extended down -> fade long
                records.append({
                    "sym": sym,
                    "entry_ts": row["bucket"],
                    "pnl": row["fwd"] - c,
                    "gross": row["fwd"],
                    "direction": 1,
                    "hold_bars": 5,
                })

    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio analysis
# ═══════════════════════════════════════════════════════════════════════════════
def weekly_ml_trades(sym, q=0.85, n_folds=5):
    """ML-based weekly: Ridge on momentum/vol features, select top-q long."""
    df = weekly_panel(sym)
    if len(df) < 100:
        return pd.DataFrame()

    feature_cols = ["f1", "f5", "f20", "f60", "f120", "vol5", "vol20"]

    n = len(df)
    records = []

    for k in range(1, n_folds):
        split = int(n * k / n_folds)
        train = df.iloc[:split]
        test = df.iloc[split:split + int(n / n_folds)]

        if len(train) < 50 or len(test) < 10:
            continue

        X_train = train[feature_cols].to_numpy()
        y_train = train["fwd"].to_numpy()
        X_test = test[feature_cols].to_numpy()

        sc = StandardScaler().fit(X_train)
        pred = Ridge(alpha=1.0).fit(sc.transform(X_train), y_train).predict(sc.transform(X_test))

        # Long top-q by predicted return
        thr = np.quantile(pred, q)
        for i, p in enumerate(pred):
            if p >= thr:
                c = cost(sym)
                records.append({
                    "sym": sym,
                    "entry_ts": test.iloc[i]["bucket"],
                    "pnl": test.iloc[i]["fwd"] - c,
                    "gross": test.iloc[i]["fwd"],
                    "direction": 1,
                    "hold_bars": 5,
                })

    return pd.DataFrame(records)


def daily_pnl(trades):
    """Bucket trade PnL to daily returns."""
    trades = trades.copy()
    trades["date"] = pd.to_datetime(trades["entry_ts"]).dt.floor("D")
    daily = trades.groupby("date")["pnl"].sum().reset_index().set_index("date")
    return daily["pnl"]


def analyze(st55, weekly):
    st55_daily = daily_pnl(st55)
    weekly_daily = daily_pnl(weekly)

    # Align to common dates
    combined = pd.concat([st55_daily.rename("st55"), weekly_daily.rename("weekly")], axis=1).fillna(0)
    combined["combined"] = combined["st55"] + combined["weekly"]

    print("=" * 90)
    print("PORTFOLIO: ST55 directional + WEEKLY mean-reversion")
    print("=" * 90)
    print(f"\nST55:   {len(st55)} trades, daily mean={st55_daily.mean():+.3f}, std={st55_daily.std():.3f}")
    print(f"Weekly: {len(weekly)} trades, daily mean={weekly_daily.mean():+.3f}, std={weekly_daily.std():.3f}")

    # Sharpe (annualized, ~250 trading days)
    for label, col in [("ST55", "st55"), ("Weekly", "weekly"), ("Combined", "combined")]:
        mean = combined[col].mean()
        std = combined[col].std()
        sharpe = mean / std * np.sqrt(250) if std > 0 else 0
        print(f"{label:10s} daily mean={mean:+.3f}  std={std:.3f}  Sharpe(ann)={sharpe:.2f}")

    # Correlation
    corr = combined["st55"].corr(combined["weekly"])
    print(f"\nDaily PnL correlation (st55 vs weekly): {corr:.3f}")
    if corr < -0.1:
        print("  → Negative correlation = hedging benefit ✓")
    elif corr < 0.1:
        print("  → Near-zero correlation = diversification benefit ✓")
    else:
        print("  → Positive correlation = limited diversification")

    # Drawdown
    for label, col in [("ST55", "st55"), ("Weekly", "weekly"), ("Combined", "combined")]:
        cum = combined[col].cumsum()
        dd = cum - cum.cummax()
        max_dd = dd.min()
        print(f"{label:10s} max drawdown: {max_dd:+.2f} bps")

    # Per-year
    combined["year"] = combined.index.year
    yr = combined.groupby("year").agg(
        st55=("st55", "sum"),
        weekly=("weekly", "sum"),
        combined=("combined", "sum"),
        n_days=("st55", "count"),
    )
    print("\n" + "=" * 90)
    print("PER-YEAR COMBINED PnL (daily sum, bps)")
    print(f"{'Year':>6s} {'ST55':>8s} {'Weekly':>8s} {'Combined':>10s} {'Days':>6s}")
    print("-" * 90)
    for y, r in yr.iterrows():
        print(f"{int(y):>6d} {r['st55']:>+8.2f} {r['weekly']:>+8.2f} {r['combined']:>+10.2f} {int(r['n_days']):>6d}")
    print("-" * 90)
    print(f"{'Mean':>6s} {yr['st55'].mean():>+8.2f} {yr['weekly'].mean():>+8.2f} {yr['combined'].mean():>+10.2f}")


def main():
    rng = np.random.default_rng(0)
    print("Building ST55 trades...")
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    st55 = st55_trades(d, frames, rng)
    print(f"ST55: {len(st55)} trades")

    print("Building weekly mean-reversion trades...")
    weekly_records = []
    for sym in TIGHT:
        weekly_records.append(weekly_ml_trades(sym, q=0.85, n_folds=5))
    weekly = pd.concat(weekly_records, ignore_index=True) if weekly_records else pd.DataFrame()
    print(f"Weekly: {len(weekly)} trades")

    if len(weekly) == 0:
        print("No weekly trades generated — check data.")
        return

    analyze(st55, weekly)


if __name__ == "__main__":
    main()
