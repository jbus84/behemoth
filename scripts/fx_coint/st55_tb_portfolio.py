"""ST55 + TB reversion portfolio — do directional and mean-reversion hedge each other?

Builds two trade-level PnL streams:
  A. ST55: L=30 regime filter, selQ=0.02, ~33h directional holds
  B. TB reversion: L=10 daily fade, H=2 hold, causal decile, non-overlap

Aligns both to daily PnL buckets and reports:
  - Per-strategy daily PnL series (mean, std, Sharpe)
  - Correlation of daily PnL
  - Combined portfolio (50/50 weight) vs each alone
  - Drawdown profiles
  - Per-year combined net

Usage: uv run python scripts/fx_coint/st55_tb_portfolio.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier

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

# ── TB REVERSION CONFIG ──
rsh.FREQ_MINUTES["1d"] = 1440
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}


def cost_tb(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


# ═══════════════════════════════════════════════════════════════════════════════
# ST55 trades with timestamps
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
# TB reversion trades with timestamps
# ═══════════════════════════════════════════════════════════════════════════════
def daily_series(sym):
    # Worktrees may not have data; resolve to actual repo root if needed
    data_path = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not data_path.exists():
        # Try repo root (worktree is under .claude/worktrees/NAME)
        candidate = _REPO_ROOT
        while candidate.name != "behemoth" and candidate.parent != candidate:
            candidate = candidate.parent
        data_path = candidate / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = rsh.build_freq_bars(pl.read_parquet(data_path), "1d", session=(0, 24))
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def tb_trades(sym, L=10, H=2, warmup=60, q=0.90):
    """Return DataFrame of TB reversion trade-level PnL with entry timestamps."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)
    sig = (rs.rolling(L, min_periods=L // 2).sum() / (rs.rolling(20, min_periods=10).std() * np.sqrt(L))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (np.log(mid[H:]) - np.log(mid[:n - H])) * 1e4
    grid = np.arange(0, n, H)
    grid = grid[np.isfinite(sig[grid]) & np.isfinite(fwd[grid])]
    c = cost_tb(sym)
    hist = []
    records = []
    for gi in grid:
        s = sig[gi]
        if len(hist) >= warmup:
            hi = np.quantile(hist, q)
            lo = np.quantile(hist, 1 - q)
            if s >= hi:
                records.append({"sym": sym, "entry_ts": pd.Timestamp(bk[gi]), "pnl": -fwd[gi] - c, "gross": -fwd[gi], "direction": -1, "hold_bars": H})
            elif s <= lo:
                records.append({"sym": sym, "entry_ts": pd.Timestamp(bk[gi]), "pnl": fwd[gi] - c, "gross": fwd[gi], "direction": 1, "hold_bars": H})
        hist.append(s)
    return pd.DataFrame(records)


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio analysis
# ═══════════════════════════════════════════════════════════════════════════════
def daily_pnl(trades):
    """Bucket trade PnL to daily returns."""
    trades = trades.copy()
    trades["date"] = pd.to_datetime(trades["entry_ts"]).dt.floor("D")
    daily = trades.groupby("date")["pnl"].sum().reset_index().set_index("date")
    return daily["pnl"]


def analyze(st55, tb):
    st55_daily = daily_pnl(st55)
    tb_daily = daily_pnl(tb)
    # Align
    combined = pd.concat([st55_daily.rename("st55"), tb_daily.rename("tb")], axis=1).fillna(0)
    combined["combined"] = combined["st55"] + combined["tb"]

    print("=" * 90)
    print("PORTFOLIO COMBINATION: ST55 directional + TB reversion")
    print("=" * 90)
    print(f"\nST55: {len(st55)} trades, daily mean={st55_daily.mean():+.3f}, std={st55_daily.std():.3f}")
    print(f"TB:   {len(tb)} trades,   daily mean={tb_daily.mean():+.3f}, std={tb_daily.std():.3f}")

    # Sharpe (annualized, assuming ~250 trading days)
    for label, col in [("ST55", "st55"), ("TB", "tb"), ("Combined", "combined")]:
        mean = combined[col].mean()
        std = combined[col].std()
        sharpe = mean / std * np.sqrt(250) if std > 0 else 0
        print(f"{label:10s} daily mean={mean:+.3f}  std={std:.3f}  Sharpe(ann)={sharpe:.2f}")

    # Correlation
    corr = combined["st55"].corr(combined["tb"])
    print(f"\nDaily PnL correlation (st55 vs tb): {corr:.3f}")
    if corr < 0:
        print("  → NEGATIVE correlation = hedging benefit ✓")
    else:
        print("  → Positive correlation = no hedging benefit")

    # Drawdown
    for label, col in [("ST55", "st55"), ("TB", "tb"), ("Combined", "combined")]:
        cum = combined[col].cumsum()
        dd = cum - cum.cummax()
        max_dd = dd.min()
        print(f"{label:10s} max drawdown: {max_dd:+.2f} bps")

    # Per-year combined
    combined["year"] = combined.index.year
    yr = combined.groupby("year").agg(
        st55=("st55", "sum"),
        tb=("tb", "sum"),
        combined=("combined", "sum"),
        n_days=("st55", "count"),
    )
    print("\n" + "=" * 90)
    print("PER-YEAR COMBINED PnL (daily sum, bps)")
    print(f"{'Year':>6s} {'ST55':>8s} {'TB':>8s} {'Combined':>10s} {'Days':>6s}")
    print("-" * 90)
    for y, r in yr.iterrows():
        print(f"{int(y):>6d} {r['st55']:>+8.2f} {r['tb']:>+8.2f} {r['combined']:>+10.2f} {int(r['n_days']):>6d}")
    print("-" * 90)
    print(f"{'Mean':>6s} {yr['st55'].mean():>+8.2f} {yr['tb'].mean():>+8.2f} {yr['combined'].mean():>+10.2f}")


def main():
    rng = np.random.default_rng(0)
    print("Building ST55 trades...")
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    st55 = st55_trades(d, frames, rng)
    print(f"ST55: {len(st55)} trades")

    print("Building TB reversion trades...")
    tb_records = []
    for sym in TIGHT:
        tb_records.append(tb_trades(sym, L=10, H=2))
    tb = pd.concat(tb_records, ignore_index=True)
    print(f"TB: {len(tb)} trades")

    analyze(st55, tb)


if __name__ == "__main__":
    main()
