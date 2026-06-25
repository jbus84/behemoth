"""Pooled gross/cost/significance decomposition for hourly FX directional models.

Settles the duelling n=6 per-window-t-stat correlations by doing the test that
was actually missing:

  * window-clean labels + rolling WFO (6mo train / 1mo test)
  * for each window, collect EVERY trade's gross and net return (bps)
  * POOL all trades across windows into one series (not avg-of-6-t-stats)
  * decompose: gross mean vs cost vs net mean, positive-month %, pooled t-stat
  * moving-block bootstrap 95% CI on the pooled net mean (block=horizon, to
    respect overlapping-hold autocorrelation)

Models compared: MultiRocketHydra, QUANT, RDST (all aeon, multivariate 3D).
Each also run in a bagging variant (N bootstrap-resampled training fits,
majority vote) to test whether bagging stabilises a weak signal.

Usage:
    uv run python scripts/fx_coint/hourly_pooled_decomp.py --year 2024 --bags 5
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from aeon.classification.convolution_based import MultiRocketHydraClassifier
from aeon.classification.interval_based import QUANTClassifier
from aeon.classification.shapelet_based import RDSTClassifier

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    load_hourly,
)
from scripts.fx_coint.hourly_triple_barrier import label_hourly

EXCLUDE = {
    "flow_tick", "flow_ofi", "rvol_bps", "spread_bps",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
}

LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
HORIZON = 12


# ── per-trade collection (gross & net in bps, with entry month) ──────────────
def collect_trades(
    df: pd.DataFrame,
    preds: np.ndarray,
    cost_bps: float,
    barrier_bps: float,
    horizon: int,
    regime_gate: np.ndarray | None = None,
) -> pd.DataFrame:
    """Live-barrier walk. Returns one row per trade with gross_bps, net_bps, month."""
    n = len(df)
    asks = df["ask"].to_numpy()
    bids = df["bid"].to_numpy()
    bucket = df["bucket"].to_numpy()
    rows = []
    for i in range(n - 1):
        pred = preds[i]
        if pred == 0:
            continue
        if regime_gate is not None and regime_gate[i] == 2:
            continue
        entry_ask, entry_bid = asks[i + 1], bids[i + 1]
        entry_mid = (entry_ask + entry_bid) / 2.0
        target = entry_mid * barrier_bps / 10_000.0
        upper, lower = entry_ask + target, entry_bid - target

        exit_idx = None
        max_j = min(i + 1 + horizon, n)
        for j in range(i + 1, max_j):
            if pred == 1 and bids[j] >= upper:
                exit_idx = j
                break
            if pred == -1 and asks[j] <= lower:
                exit_idx = j
                break
        if exit_idx is None:
            exit_idx = max_j - 1

        gross = bids[exit_idx] - entry_ask if pred == 1 else entry_bid - asks[exit_idx]
        gross_bps = gross / entry_mid * 10_000.0
        rows.append((bucket[i + 1], gross_bps, gross_bps - cost_bps))
    return pd.DataFrame(rows, columns=["entry", "gross_bps", "net_bps"])


# ── pooled stats + moving-block bootstrap ───────────────────────────────────
def moving_block_bootstrap_ci(x: np.ndarray, block: int, n_boot: int = 5000,
                              seed: int = 0) -> tuple[float, float]:
    """95% CI on the mean via moving-block bootstrap (respects autocorrelation)."""
    rng = np.random.default_rng(seed)
    n = len(x)
    if n < block + 1:
        return (np.nan, np.nan)
    n_blocks = int(np.ceil(n / block))
    starts_max = n - block
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = x[idx].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(trades: pd.DataFrame, cost_bps: float, label: str) -> dict:
    if trades.empty:
        print(f"  {label:<22s}  NO TRADES")
        return {}
    net = trades["net_bps"].to_numpy()
    gross = trades["gross_bps"].to_numpy()
    n = len(net)
    t_stat = np.sqrt(n) * net.mean() / (net.std() + 1e-12)
    lo, hi = moving_block_bootstrap_ci(net, block=HORIZON)
    # positive-month %
    trades = trades.assign(month=trades["entry"].astype("datetime64[ns]").dt.to_period("M"))
    by_month = trades.groupby("month")["net_bps"].mean()
    pos_mo = (by_month > 0).mean() * 100
    out = {
        "label": label, "n": n,
        "gross_bps": gross.mean(), "cost_bps": cost_bps, "net_bps": net.mean(),
        "t": t_stat, "ci_lo": lo, "ci_hi": hi,
        "pos_trade_pct": (net > 0).mean() * 100, "pos_month_pct": pos_mo,
        "n_months": len(by_month),
    }
    sig = "SIG" if (lo > 0 or hi < 0) else "—"
    print(
        f"  {label:<22s} n={n:>5d}  gross={gross.mean():+6.3f}  cost={cost_bps:4.2f}  "
        f"net={net.mean():+6.3f}  t={t_stat:+5.2f}  CI95=[{lo:+.3f},{hi:+.3f}] {sig:>3s}  "
        f"pos_mo={pos_mo:4.0f}%"
    )
    return out


# ── model fitting (single + bagging) ────────────────────────────────────────
def make_model(name: str, seed: int):
    if name == "MRHydra":
        return MultiRocketHydraClassifier(n_jobs=1, random_state=seed)
    if name == "QUANT":
        return QUANTClassifier(random_state=seed)
    if name == "RDST":
        return RDSTClassifier(n_jobs=1, random_state=seed)
    raise ValueError(name)


SEEDS = [42, 7, 13, 99, 777]


def fit_members(name: str, X_tr, y_tr, X_te, seeds: list[int]) -> np.ndarray:
    """Fit one model type across N seeds. Returns (n_seeds, n_test) int8 votes."""
    votes = np.zeros((len(seeds), len(X_te)), dtype=np.int8)
    for s_idx, seed in enumerate(seeds):
        clf = make_model(name, seed)
        clf.fit(X_tr, y_tr)
        votes[s_idx] = clf.predict(X_te).astype(np.int8)
    return votes


def majority_vote(votes: np.ndarray) -> np.ndarray:
    """Hard majority vote over members for labels in {-1,0,1}; ties → 0 (flat)."""
    pos = (votes == 1).sum(0)
    neg = (votes == -1).sum(0)
    preds = np.zeros(votes.shape[1], dtype=np.int8)
    preds[pos > neg] = 1
    preds[neg > pos] = -1
    return preds


# ── WFO driver: returns pooled trade frames per model/variant ───────────────
def run(symbol: str, year: int, models: list[str], n_seeds: int) -> dict:
    print(f"\n{'='*94}\nSYMBOL={symbol}  YEAR={year}  lookback={LOOKBACK}  "
          f"horizon={HORIZON}  barrier={BARRIER_BPS}  seeds={n_seeds}\n{'='*94}")
    cost_bps = DEFAULT_COST_BPS[symbol]
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO

    # accumulate trades per (model, variant)
    pools: dict[str, list[pd.DataFrame]] = {}

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end

        margin = tr_s - pd.Timedelta(hours=LOOKBACK * 2)
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_hourly(pl.from_pandas(wdf), symbol, barrier_bps=BARRIER_BPS,
                           horizon=HORIZON).to_pandas()

        ts = wdf["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
        tr_mask = (ts >= tr_s) & (ts < tr_e)
        te_mask = (ts >= te_s) & (ts < te_e)
        tr_idx = np.where(tr_mask.to_numpy())[0]
        te_idx = np.where(te_mask.to_numpy())[0]
        if len(tr_idx) < 500 or len(te_idx) < 100:
            continue

        wdf["regime"] = classify_regime(wdf["rvol_bps"], tr_idx)
        X, y, regime = build_feature_panel(wdf, LOOKBACK, exclude_channels=EXCLUDE)
        X = X.astype(np.float64)  # RDST/numba kernels require float64
        regime_te = regime.iloc[te_idx].to_numpy()
        X_tr, y_tr, X_te = X[tr_idx], y[tr_idx], X[te_idx]
        if np.unique(y_tr).size < 2:
            continue

        base = wdf.iloc[LOOKBACK:].reset_index(drop=True)
        test_df = base.iloc[te_idx].reset_index(drop=True)

        seeds = SEEDS[:n_seeds] if n_seeds > 0 else SEEDS[:1]
        print(f"  [W{i+1}] train={tr_s:%Y-%m}..{tr_e:%Y-%m}  test={te_s:%Y-%m}  "
              f"n_tr={len(tr_idx)} n_te={len(te_idx)}  seeds={seeds}")

        all_votes = []  # accumulate every member's votes for the combined ensemble
        for name in models:
            votes = fit_members(name, X_tr, y_tr, X_te, seeds)
            all_votes.append(votes)

            # single (first seed, = 42) for reference
            tr_single = collect_trades(test_df, votes[0], cost_bps, BARRIER_BPS, HORIZON, regime_te)
            pools.setdefault(f"{name}[1seed]", []).append(tr_single)

            # per-model N-seed vote
            if len(seeds) > 1:
                tr_ens = collect_trades(test_df, majority_vote(votes), cost_bps,
                                        BARRIER_BPS, HORIZON, regime_te)
                pools.setdefault(f"{name}[{len(seeds)}seed]", []).append(tr_ens)

        # combined ensemble: all model-types × all seeds, one big vote
        if len(models) > 1:
            combined = np.vstack(all_votes)
            label = f"STACK[{len(models)}x{len(seeds)}={combined.shape[0]}]"
            tr_comb = collect_trades(test_df, majority_vote(combined), cost_bps,
                                     BARRIER_BPS, HORIZON, regime_te)
            pools.setdefault(label, []).append(tr_comb)

    return {k: pd.concat(v, ignore_index=True) for k, v in pools.items()}, cost_bps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--seeds", type=int, default=5, help="seeds per model type")
    ap.add_argument("--models", default="MRHydra,QUANT,RDST")
    args = ap.parse_args()

    models = args.models.split(",")
    pools, cost = run(args.symbol, args.year, models, args.seeds)

    print(f"\n{'='*94}\nPOOLED DECOMPOSITION  (all WFO trades concatenated; "
          f"block-bootstrap CI on net mean, bps/trade)\n{'='*94}")
    rows = []
    for label in sorted(pools):
        r = summarize(pools[label], cost, label)
        if r:
            rows.append(r)

    print(f"\n{'-'*94}\nVERDICT (net mean bps/trade, 95% CI):")
    for r in rows:
        verdict = "EDGE" if r["ci_lo"] > 0 else ("NEG" if r["ci_hi"] < 0 else "NOISE")
        print(f"  {r['label']:<22s} net={r['net_bps']:+.3f}  "
              f"CI=[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]  gross={r['gross_bps']:+.3f} "
              f"vs cost {r['cost_bps']:.2f}  →  {verdict}")


if __name__ == "__main__":
    main()
