"""Walk-forward confirmation of the PR #340 tail edge: long-only top-decile,
no-look-ahead decile gating, decile-level significance net of real cost.

Usage:
    uv run python scripts/fx_coint/tail_wfo.py --symbol all --freq all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import scipy.special as sp
from scipy.stats import spearmanr, ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    bh_reject,
    build_freq_bars,
    build_panel,
)

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]
UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
FREQS = ["2h", "3h"]


def walk_forward(
    panel: pd.DataFrame,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
    alpha: float = 1.0,
    feature_cols: list[str] | None = None,
) -> list[dict]:
    """Expanding-window WFO.  If feature_cols is None, uses global FEATURE_COLS."""
    cols = feature_cols if feature_cols is not None else FEATURE_COLS
    n = len(panel)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    X = panel[cols].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    hour = panel["hour"].to_numpy()
    bucket = panel["bucket"].to_numpy()

    folds: list[dict] = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=alpha).fit(scaler.transform(X[:split]), yz[:split])
        folds.append({
            "train_pred": model.predict(scaler.transform(X[:split])),
            "test_pred": model.predict(scaler.transform(X[test_lo:test_hi])),
            "test_target_z": yz[test_lo:test_hi],
            "test_actual_bps": act[test_lo:test_hi],
            "test_hour": hour[test_lo:test_hi],
            "test_bucket": bucket[test_lo:test_hi],
        })
    return folds


def add_trailing_regime_features(
    panel: pd.DataFrame, window: int = 30
) -> pd.DataFrame:
    """Add no-look-ahead trailing regime / meta features to the panel.

    All features are computed from PAST returns only (shift(1)) so they are
    observable at decision time.  Key features:
        - skew_ret: trailing skew of next-bar returns (trending = positive skew)
        - auto_ret: lag-1 autocorrelation of next-bar returns (trend = positive)
        - vol_ret: trailing std of next-bar returns
        - hit_ret: trailing hit rate (fraction of positive returns)
        - payoff_ret: trailing payoff ratio (mean win / mean |loss|)
    """
    panel = panel.copy()
    r = panel["ret_next_bps"]
    # Use shift(1) so the feature at bar t only uses returns ending at bar t,
    # never the future return t→t+1.
    rs = r.shift(1)
    panel["skew_ret"] = rs.rolling(window, min_periods=window // 2).skew()
    panel["vol_ret"] = rs.rolling(window, min_periods=window // 2).std()
    panel["auto_ret"] = rs.rolling(window + 1, min_periods=window // 2).apply(
        lambda x: x.autocorr(lag=1) if len(x.dropna()) > 2 else np.nan, raw=False
    )
    wins = rs.where(rs > 0)
    losses = rs.where(rs <= 0).abs()
    panel["hit_ret"] = (rs > 0).rolling(window, min_periods=window // 2).mean()
    panel["payoff_ret"] = (
        wins.rolling(window, min_periods=window // 2).mean()
        / losses.rolling(window, min_periods=window // 2).mean()
    )
    return panel


def build_enhanced_panel(sym: str, freq: str, window: int = 30) -> pd.DataFrame | None:
    """Build panel with original 5 features + regime features + interaction terms.

    Regime features (computed from past returns only):
        skew_ret, auto_ret, vol_ret, hit_ret, payoff_ret

    Interaction terms (regime × original features):
        r_1×skew, mom_short×skew, mom_long×skew, r_1×payoff, mom_short×payoff

    These let the linear Ridge model learn that momentum features have DIFFERENT
    weights in trending vs choppy regimes — the core failure of the baseline model."""
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = add_trailing_regime_features(
        build_panel(build_freq_bars(pl.read_parquet(src), freq)), window=window
    )
    if len(panel) < 200:
        return None

    # Add interaction terms — the key to regime-aware linear models
    orig = ["r_1", "mom_short", "mom_long"]
    regime = ["skew_ret", "payoff_ret"]
    for o in orig:
        for r in regime:
            panel[f"{o}_x_{r}"] = panel[o] * panel[r]

    # Drop any rows with NaN in the new interaction columns
    all_cols = FEATURE_COLS + ["skew_ret", "auto_ret", "vol_ret", "hit_ret", "payoff_ret"]
    all_cols += [f"{o}_x_{r}" for o in orig for r in regime]
    finite = np.isfinite(panel[all_cols].to_numpy()).all(axis=1)
    panel = panel[finite].reset_index(drop=True)
    return panel


# Feature columns for the enhanced model
ENHANCED_FEATURE_COLS = FEATURE_COLS + [
    "skew_ret", "auto_ret", "vol_ret", "hit_ret", "payoff_ret",
    "r_1_x_skew_ret", "mom_short_x_skew_ret", "mom_long_x_skew_ret",
    "r_1_x_payoff_ret", "mom_short_x_payoff_ret", "mom_long_x_payoff_ret",
]


def walk_forward_regime_aware(
    panel: pd.DataFrame,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
    alpha: float = 1.0,
) -> list[dict]:
    """Expanding-window WFO that forwards regime / meta features for post-hoc filtering.
    Uses the ORIGINAL 5-feature model."""
    n = len(panel)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    hour = panel["hour"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    regime_cols = ["skew_ret", "auto_ret", "vol_ret", "hit_ret", "payoff_ret"]
    regime = {c: panel[c].to_numpy() for c in regime_cols}

    folds: list[dict] = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=alpha).fit(scaler.transform(X[:split]), yz[:split])
        fd: dict = {
            "train_pred": model.predict(scaler.transform(X[:split])),
            "test_pred": model.predict(scaler.transform(X[test_lo:test_hi])),
            "test_target_z": yz[test_lo:test_hi],
            "test_actual_bps": act[test_lo:test_hi],
            "test_hour": hour[test_lo:test_hi],
            "test_bucket": bucket[test_lo:test_hi],
        }
        for c in regime_cols:
            fd[f"test_{c}"] = regime[c][test_lo:test_hi]
        folds.append(fd)
    return folds


def walk_forward_enhanced(
    panel: pd.DataFrame,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
    alpha: float = 1.0,
) -> list[dict]:
    """Expanding-window WFO with ENHANCED features: original 5 + regime features +
    interaction terms. The model itself learns regime-aware weights."""
    n = len(panel)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    X = panel[ENHANCED_FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    hour = panel["hour"].to_numpy()
    bucket = panel["bucket"].to_numpy()
    regime_cols = ["skew_ret", "auto_ret", "vol_ret", "hit_ret", "payoff_ret"]
    regime = {c: panel[c].to_numpy() for c in regime_cols}

    folds: list[dict] = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=alpha).fit(scaler.transform(X[:split]), yz[:split])
        fd: dict = {
            "train_pred": model.predict(scaler.transform(X[:split])),
            "test_pred": model.predict(scaler.transform(X[test_lo:test_hi])),
            "test_target_z": yz[test_lo:test_hi],
            "test_actual_bps": act[test_lo:test_hi],
            "test_hour": hour[test_lo:test_hi],
            "test_bucket": bucket[test_lo:test_hi],
        }
        for c in regime_cols:
            fd[f"test_{c}"] = regime[c][test_lo:test_hi]
        folds.append(fd)
    return folds


def gate_trades(
    folds: list[dict], q: float, cost_bps: float, side: str = "long"
) -> dict:
    nets: list[np.ndarray] = []
    fids: list[np.ndarray] = []
    hours: list[np.ndarray] = []
    buckets: list[np.ndarray] = []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        if side == "long":
            thr = np.quantile(f["train_pred"], q)
            sel = tp >= thr
            net = f["test_actual_bps"][sel] - cost_bps
        elif side == "short":
            thr = np.quantile(f["train_pred"], 1.0 - q)
            sel = tp <= thr
            net = -f["test_actual_bps"][sel] - cost_bps
        else:
            raise ValueError(f"side must be 'long' or 'short', got {side!r}")
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
            buckets.append(f["test_bucket"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int),
                "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
    net_all = np.concatenate(nets)
    return {
        "net": net_all,
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "bucket": np.concatenate(buckets),
        "n": len(net_all),
    }


def gate_trades_regime(
    folds: list[dict],
    q: float,
    cost_bps: float,
    side: str = "long",
    regime_col: str = "test_skew_ret",
    min_regime: float = 0.0,
) -> dict:
    """Gate trades by a trailing regime feature computed from past data.
    Only takes top-q trades when the regime indicator >= min_regime."""
    nets, fids, hours, buckets = [], [], [], []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        if side == "long":
            thr = np.quantile(f["train_pred"], q)
            sel = tp >= thr
        elif side == "short":
            thr = np.quantile(f["train_pred"], 1.0 - q)
            sel = tp <= thr
        else:
            raise ValueError(f"side must be 'long' or 'short', got {side!r}")
        # Regime gate: require past-data regime indicator above threshold
        if regime_col in f:
            regime_ok = f[regime_col] >= min_regime
            sel = sel & regime_ok
        net = f["test_actual_bps"][sel] - cost_bps
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
            buckets.append(f["test_bucket"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int),
                "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
    return {
        "net": np.concatenate(nets),
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "bucket": np.concatenate(buckets),
        "n": len(np.concatenate(nets)),
    }


def gate_trades_meta(
    folds: list[dict],
    q: float,
    cost_bps: float,
    side: str = "long",
    meta_col: str = "test_payoff_ret",
    min_payoff: float = 1.2,
) -> dict:
    """Gate trades by trailing payoff ratio (win_avg / |loss_avg|).
    Only takes top-q trades when the past payoff asymmetry >= min_payoff."""
    nets, fids, hours, buckets = [], [], [], []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        if side == "long":
            thr = np.quantile(f["train_pred"], q)
            sel = tp >= thr
        elif side == "short":
            thr = np.quantile(f["train_pred"], 1.0 - q)
            sel = tp <= thr
        else:
            raise ValueError(f"side must be 'long' or 'short', got {side!r}")
        if meta_col in f:
            payoff_ok = f[meta_col] >= min_payoff
            sel = sel & payoff_ok
        net = f["test_actual_bps"][sel] - cost_bps
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
            buckets.append(f["test_bucket"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int),
                "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
    return {
        "net": np.concatenate(nets),
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "bucket": np.concatenate(buckets),
        "n": len(np.concatenate(nets)),
    }


def cell_stats(net: np.ndarray, fold_id: np.ndarray) -> dict:
    net = np.asarray(net, float)
    n = len(net)
    if n == 0:
        return {"n": 0, "mean_net_bps": float("nan"), "t_stat": float("nan"),
                "p_value": float("nan"), "pos_fold_pct": float("nan"),
                "hit_rate": float("nan"), "total_net_bps": 0.0}
    if n >= 3:
        tt = ttest_1samp(net, 0.0)
        t_stat, p_value = float(tt.statistic), float(tt.pvalue)
    else:
        t_stat = p_value = float("nan")
    folds = np.unique(fold_id)
    if len(folds) > 0:
        pos = np.mean([net[fold_id == fk].mean() > 0 for fk in folds])
    else:
        pos = float("nan")
    return {
        "n": n,
        "mean_net_bps": float(net.mean()),
        "t_stat": t_stat,
        "p_value": p_value,
        "pos_fold_pct": float(pos),
        "hit_rate": float((net > 0).mean()),
        "total_net_bps": float(net.sum()),
    }


def run_cell_wfo(
    sym: str, freq: str, side: str = "long", q: float = 0.9, n_folds: int = 5
) -> dict | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    folds = walk_forward(panel, n_folds=n_folds)
    trades = gate_trades(folds, q=q, cost_bps=cost, side=side)
    s = cell_stats(trades["net"], trades["fold_id"])
    return {"symbol": sym, "freq": freq, "side": side, "q": q, **s}


def run_cell_wfo_enhanced(
    sym: str, freq: str, side: str = "long", q: float = 0.95, n_folds: int = 5
) -> dict | None:
    """Run WFO with ENHANCED features (original 5 + regime + interactions).
    The model itself learns regime-aware weights."""
    panel = build_enhanced_panel(sym, freq)
    if panel is None or len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    folds = walk_forward_enhanced(panel, n_folds=n_folds)
    trades = gate_trades(folds, q=q, cost_bps=cost, side=side)
    s = cell_stats(trades["net"], trades["fold_id"])
    return {"symbol": sym, "freq": freq, "side": side, "q": q, **s}


def run_cell_wfo_regime(
    sym: str,
    freq: str,
    side: str = "long",
    q: float = 0.95,
    n_folds: int = 5,
    regime_col: str = "test_skew_ret",
    min_regime: float = 0.0,
    meta_col: str = "test_payoff_ret",
    min_payoff: float = 0.0,
) -> dict | None:
    """Run WFO with regime-aware and/or meta-rule gating.  Set min_regime > 0 or
    min_payoff > 0 to activate the respective filter."""
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = add_trailing_regime_features(
        build_panel(build_freq_bars(pl.read_parquet(src), freq)), window=30
    )
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    folds = walk_forward_regime_aware(panel, n_folds=n_folds)
    # If both filters requested, apply directly on fold data (both must pass)
    if min_regime > 0 and min_payoff > 0:
        nets, fids, hours, buckets = [], [], [], []
        for i, f in enumerate(folds):
            tp = f["test_pred"]
            if side == "long":
                thr = np.quantile(f["train_pred"], q)
                sel = tp >= thr
            else:
                thr = np.quantile(f["train_pred"], 1.0 - q)
                sel = tp <= thr
            if regime_col in f:
                sel = sel & (f[regime_col] >= min_regime)
            if meta_col in f:
                sel = sel & (f[meta_col] >= min_payoff)
            net = f["test_actual_bps"][sel] - cost
            if sel.any():
                nets.append(net)
                fids.append(np.full(int(sel.sum()), i))
                hours.append(f["test_hour"][sel])
                buckets.append(f["test_bucket"][sel])
        trades = {"net": np.array([]), "fold_id": np.array([], int),
                  "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
        if nets:
            trades = {
                "net": np.concatenate(nets),
                "fold_id": np.concatenate(fids),
                "hour": np.concatenate(hours),
                "bucket": np.concatenate(buckets),
                "n": len(np.concatenate(nets)),
            }
    elif min_regime > 0:
        trades = gate_trades_regime(
            folds, q=q, cost_bps=cost, side=side,
            regime_col=regime_col, min_regime=min_regime,
        )
    elif min_payoff > 0:
        trades = gate_trades_meta(
            folds, q=q, cost_bps=cost, side=side,
            meta_col=meta_col, min_payoff=min_payoff,
        )
    else:
        trades = gate_trades(folds, q=q, cost_bps=cost, side=side)
    s = cell_stats(trades["net"], trades["fold_id"])
    return {"symbol": sym, "freq": freq, "side": side, "q": q, **s}


TIGHT_2H_Q_SWEEP = (0.80, 0.90, 0.95)


def day_clustered_tstat(net: np.ndarray, bucket: np.ndarray) -> dict:
    """One-sample t-test on per-calendar-day mean net, absorbing same-day cross-pair
    and intraday autocorrelation. Naive per-trade t overstates significance when trades
    are correlated; clustering by day is the conservative correction."""
    net = np.asarray(net, float)
    if len(net) == 0:
        return {"n_days": 0, "daily_mean": float("nan"), "t_stat": float("nan"),
                "p_value": float("nan")}
    dates = pd.to_datetime(pd.Series(bucket)).dt.date.to_numpy()
    daily = pd.Series(net).groupby(dates).mean().to_numpy()
    if len(daily) >= 3:
        tt = ttest_1samp(daily, 0.0)
        t_stat, p_value = float(tt.statistic), float(tt.pvalue)
    else:
        t_stat = p_value = float("nan")
    return {"n_days": len(daily), "daily_mean": float(daily.mean()),
            "t_stat": t_stat, "p_value": p_value}


def pooled_long_test(
    pairs: list[str], freq: str, q: float, n_folds: int = 5
) -> dict | None:
    """Pool long top-(1-q) trades across `pairs` at `freq`, return pooled per-trade mean,
    naive t, and day-clustered t. Pooling lifts power via breadth; day-clustering keeps
    the significance honest against cross-pair correlation."""
    nets, buckets = [], []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=n_folds)
        tr = gate_trades(folds, q=q, cost_bps=COST_BPS[sym], side="long")
        if tr["n"] > 0:
            nets.append(tr["net"])
            buckets.append(tr["bucket"])
    if not nets:
        return None
    net = np.concatenate(nets)
    bucket = np.concatenate(buckets)
    naive = ttest_1samp(net, 0.0) if len(net) >= 3 else None
    dc = day_clustered_tstat(net, bucket)
    return {
        "pairs": pairs, "freq": freq, "q": q, "n": len(net),
        "mean_net_bps": float(net.mean()), "hit_rate": float((net > 0).mean()),
        "naive_t": float(naive.statistic) if naive else float("nan"),
        "naive_p": float(naive.pvalue) if naive else float("nan"),
        "day_n": dc["n_days"], "day_t": dc["t_stat"], "day_p": dc["p_value"],
    }


OOS_PAIRS = ["AUDUSD", "USDCHF", "USDCAD"]


def _long_trades_with_buckets(sym: str, freq: str, q: float, cost_bps: float,
                              n_folds: int = 5) -> dict:
    """Helper: long top-(1-q) WFO trades for one pair, returning net + buckets. cost_bps=0
    gives the GROSS signal (used for the out-of-sample-pairs generalization test)."""
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return {"net": np.array([]), "bucket": np.array([], "datetime64[ns]")}
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return {"net": np.array([]), "bucket": np.array([], "datetime64[ns]")}
    folds = walk_forward(panel, n_folds=n_folds)
    tr = gate_trades(folds, q=q, cost_bps=cost_bps, side="long")
    return {"net": tr["net"], "bucket": tr["bucket"]}


def oos_pairs_test(freq: str = "2h", q: float = 0.95, n_folds: int = 5) -> dict:
    """Generalization test: apply the identical long-top-decile rule to pairs EXCLUDED from
    the selected edge (OOS_PAIRS). Reports per-pair and pooled GROSS (cost=0) day-clustered
    significance — a real signal generalizes gross to pairs that didn't inform the choice."""
    per_pair, gross_nets, gross_bks = {}, [], []
    for sym in OOS_PAIRS:
        g = _long_trades_with_buckets(sym, freq, q, 0.0, n_folds)
        nt = _long_trades_with_buckets(sym, freq, q, COST_BPS[sym], n_folds)
        per_pair[sym] = {
            "gross": day_clustered_tstat(g["net"], g["bucket"]),
            "net": day_clustered_tstat(nt["net"], nt["bucket"]),
            "n": len(g["net"]),
        }
        if len(g["net"]):
            gross_nets.append(g["net"])
            gross_bks.append(g["bucket"])
    pooled = (day_clustered_tstat(np.concatenate(gross_nets), np.concatenate(gross_bks))
              if gross_nets else {"n_days": 0, "daily_mean": float("nan"),
                                  "t_stat": float("nan"), "p_value": float("nan")})
    return {"per_pair": per_pair, "pooled_gross": pooled}


def era_split_test(pairs: list[str], freq: str = "2h", q: float = 0.95,
                   n_folds: int = 5) -> dict:
    """Stability test: split the pooled long-top-decile NET trades at the median trade date
    and report day-clustered significance in each half. A robust edge holds in both halves;
    a decayed/forking-paths edge concentrates in one era."""
    nets, bks = [], []
    for sym in pairs:
        tr = _long_trades_with_buckets(sym, freq, q, COST_BPS[sym], n_folds)
        if len(tr["net"]):
            nets.append(tr["net"])
            bks.append(tr["bucket"])
    if not nets:
        return {"split_date": None, "first": None, "second": None}
    net = np.concatenate(nets)
    bk = pd.to_datetime(pd.Series(np.concatenate(bks)))
    split = bk.sort_values().iloc[len(bk) // 2]
    first = bk < split
    return {
        "split_date": str(split.date()),
        "first": day_clustered_tstat(net[first.to_numpy()], bk[first.to_numpy()].to_numpy()),
        "second": day_clustered_tstat(net[~first.to_numpy()], bk[~first.to_numpy()].to_numpy()),
    }


def diagnose_edge_death(
    sym: str,
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> list[dict]:
    """Decompose WHY the edge died after 2023Q1.

    Pools ALL WFO test observations (not just gated trades) and slices by calendar quarter.
    Reports per-quarter:
        - Spearman IC (pred vs target_z) — did the model stop ranking?
        - Realized vol (std of ret_next_bps) — did returns compress?
        - Gross mean (all obs + top-q only) — did the tail reward shrink?
        - Net top-q — did it die because of vol, IC, or tail-adversity?

    This distinguishes three failure modes:
        1. IC collapse → model mapping broke → retraining MIGHT help.
        2. IC stable + vol collapse → z-space prediction works but bps reward too small →
           NO retraining fix; need lower cost or leverage.
        3. IC stable + vol stable + topq gross negative → adverse selection in the tail →
           NO retraining fix; the tail itself became toxic."""
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return []
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return []

    folds = walk_forward(panel, n_folds=n_folds)
    preds, tzs, acts, buckets, thrs = [], [], [], [], []
    for f in folds:
        thr = np.quantile(f["train_pred"], q)
        preds.append(f["test_pred"])
        tzs.append(f["test_target_z"])
        acts.append(f["test_actual_bps"])
        buckets.append(f["test_bucket"])
        thrs.append(np.full(len(f["test_pred"]), thr))

    df = pd.DataFrame({
        "pred": np.concatenate(preds),
        "tz": np.concatenate(tzs),
        "act": np.concatenate(acts),
        "bucket": pd.to_datetime(np.concatenate(buckets)),
        "thr": np.concatenate(thrs),
    })
    df["qtr"] = df["bucket"].dt.to_period("Q")
    cost = COST_BPS[sym]
    rows: list[dict] = []
    for qtr, grp in df.groupby("qtr"):
        if len(grp) < 10:
            continue
        ic = (float(spearmanr(grp["pred"], grp["tz"]).correlation)
              if len(grp) > 2 else float("nan"))
        vol = float(grp["act"].std())
        gross_all = float(grp["act"].mean())
        sel = grp["pred"] >= grp["thr"]
        gross_topq = float(grp.loc[sel, "act"].mean()) if sel.sum() > 0 else float("nan")
        net_topq = gross_topq - cost if np.isfinite(gross_topq) else float("nan")
        rows.append({
            "qtr": str(qtr),
            "n": len(grp),
            "n_topq": int(sel.sum()),
            "ic": ic,
            "vol": vol,
            "gross_all": gross_all,
            "gross_topq": gross_topq,
            "net_topq": net_topq,
            "cost": cost,
        })
    return rows


def diagnose_edge_death_pooled(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> list[dict]:
    """Pooled version of `diagnose_edge_death`: aggregates across `pairs` for higher
    statistical power per quarter. This gives clean IC, vol, and top-q gross at the
    multi-pair level — the level the strategy actually trades."""
    all_frames = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=n_folds)
        preds, tzs, acts, buckets, thrs = [], [], [], [], []
        for f in folds:
            thr = np.quantile(f["train_pred"], q)
            preds.append(f["test_pred"])
            tzs.append(f["test_target_z"])
            acts.append(f["test_actual_bps"])
            buckets.append(f["test_bucket"])
            thrs.append(np.full(len(f["test_pred"]), thr))
        all_frames.append(pd.DataFrame({
            "pred": np.concatenate(preds),
            "tz": np.concatenate(tzs),
            "act": np.concatenate(acts),
            "bucket": pd.to_datetime(np.concatenate(buckets)),
            "thr": np.concatenate(thrs),
        }))
    if not all_frames:
        return []
    df = pd.concat(all_frames, ignore_index=True)
    df["qtr"] = df["bucket"].dt.to_period("Q")
    rows: list[dict] = []
    for qtr, grp in df.groupby("qtr"):
        if len(grp) < 20:
            continue
        ic = (float(spearmanr(grp["pred"], grp["tz"]).correlation)
              if len(grp) > 2 else float("nan"))
        vol = float(grp["act"].std())
        gross_all = float(grp["act"].mean())
        sel = grp["pred"] >= grp["thr"]
        gross_topq = float(grp.loc[sel, "act"].mean()) if sel.sum() > 0 else float("nan")
        # Weighted average cost of selected trades
        costs = [COST_BPS[sym] for sym in pairs]
        avg_cost = float(np.mean(costs))
        net_topq = gross_topq - avg_cost if np.isfinite(gross_topq) else float("nan")
        rows.append({
            "qtr": str(qtr),
            "n": len(grp),
            "n_topq": int(sel.sum()),
            "ic": ic,
            "vol": vol,
            "gross_all": gross_all,
            "gross_topq": gross_topq,
            "net_topq": net_topq,
            "avg_cost": avg_cost,
        })
    return rows


def diagnose_why_tail_died(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> list[dict]:
    """Deep diagnostic: decompose the "tail stopped paying" failure into four mechanisms.

    1. Hit-rate vs magnitude: did wins get smaller or did hit-rate collapse?
    2. Distribution shape: did skew / kurtosis of top-q returns change (fatter left tail)?
    3. Conditional IC by vol quintile: does ranking work in low-vol but die in high-vol?
    4. Hour-of-day shift: did the profitable entry hours change?

    These answer *why* the tail is toxic, not just *that* it is."""
    all_frames = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=n_folds)
        preds, tzs, acts, hours, buckets, thrs = [], [], [], [], [], []
        for f in folds:
            thr = np.quantile(f["train_pred"], q)
            preds.append(f["test_pred"])
            tzs.append(f["test_target_z"])
            acts.append(f["test_actual_bps"])
            hours.append(f["test_hour"])
            buckets.append(f["test_bucket"])
            thrs.append(np.full(len(f["test_pred"]), thr))
        all_frames.append(pd.DataFrame({
            "pred": np.concatenate(preds),
            "tz": np.concatenate(tzs),
            "act": np.concatenate(acts),
            "hour": np.concatenate(hours),
            "bucket": pd.to_datetime(np.concatenate(buckets)),
            "thr": np.concatenate(thrs),
        }))
    if not all_frames:
        return []
    df = pd.concat(all_frames, ignore_index=True)
    df["qtr"] = df["bucket"].dt.to_period("Q")
    costs = [COST_BPS[sym] for sym in pairs]
    avg_cost = float(np.mean(costs))
    rows: list[dict] = []
    for qtr, grp in df.groupby("qtr"):
        if len(grp) < 20:
            continue
        sel = grp["pred"] >= grp["thr"]
        top = grp.loc[sel, "act"]
        if sel.sum() < 5:
            continue
        wins = top[top > 0]
        losses = top[top <= 0]
        hr = float((top > 0).mean())
        win_avg = float(wins.mean()) if len(wins) else float("nan")
        loss_avg = float(losses.mean()) if len(losses) else float("nan")
        skew = float(top.skew())
        kurt = float(top.kurtosis())
        # Conditional IC: rank correlation in each VOL QUINTILE of the quarter
        grp = grp.copy()
        grp["vol_q"] = pd.qcut(grp["act"].abs(), q=5, labels=["q1", "q2", "q3", "q4", "q5"],
                               duplicates="drop")
        ic_by_vol: dict[str, float] = {}
        for vq, vg in grp.groupby("vol_q"):
            if len(vg) > 5:
                ic_by_vol[str(vq)] = float(spearmanr(vg["pred"], vg["tz"]).correlation)
        # Top-3 hours by count in this quarter
        top_hours = grp.loc[sel, "hour"].mode().head(3).tolist()
        rows.append({
            "qtr": str(qtr),
            "n": len(grp),
            "n_topq": int(sel.sum()),
            "hit_rate": hr,
            "win_avg": win_avg,
            "loss_avg": loss_avg,
            "expectancy": hr * win_avg + (1 - hr) * loss_avg if np.isfinite(win_avg) and np.isfinite(loss_avg) else float("nan"),
            "skew": skew,
            "kurt": kurt,
            "ic_by_vol": ic_by_vol,
            "top_hours": top_hours,
            "gross_topq": float(top.mean()),
            "net_topq": float(top.mean()) - avg_cost,
        })
    return rows


def temporal_slice_report(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
    bins: str = "Y",
) -> list[dict]:
    """Slice pooled long-top-decile NET trades into calendar bins (Y=year, Q=quarter, M=month)
    and report day-clustered stats per bin. Exposes whether decay is smooth, a cliff, or
    episodic — and whether recent weakness is a sample-size artefact."""
    nets, bks = [], []
    for sym in pairs:
        tr = _long_trades_with_buckets(sym, freq, q, COST_BPS[sym], n_folds)
        if len(tr["net"]):
            nets.append(tr["net"])
            bks.append(tr["bucket"])
    if not nets:
        return []
    net = np.concatenate(nets)
    bk = pd.to_datetime(pd.Series(np.concatenate(bks)))
    df = pd.DataFrame({"net": net, "bucket": bk})
    df["period"] = bk.dt.to_period(bins)
    rows: list[dict] = []
    for period, grp in df.groupby("period"):
        if len(grp) < 3:
            continue
        dc = day_clustered_tstat(grp["net"].to_numpy(), grp["bucket"].to_numpy())
        rows.append({
            "period": str(period),
            "n_trades": len(grp),
            "n_days": dc["n_days"],
            "mean_net": dc["daily_mean"],
            "t_stat": dc["t_stat"],
            "p_value": dc["p_value"],
            "hit_rate": float((grp["net"] > 0).mean()),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="all", choices=UNIVERSE + ["all"])
    ap.add_argument("--freq", default="all", choices=FREQS + ["all"])
    ap.add_argument("--q", type=float, default=0.9)
    args = ap.parse_args()
    syms = UNIVERSE if args.symbol == "all" else [args.symbol]
    freqs = FREQS if args.freq == "all" else [args.freq]

    rows = [r for s in syms for f in freqs
            if (r := run_cell_wfo(s, f, side="long", q=args.q)) is not None]
    if not rows:
        print("No cells produced (missing data?).")
        return
    rej = bh_reject([r["p_value"] for r in rows], q=0.10)
    hdr = (f"{'pair':>7} {'freq':>4} {'q':>4} {'n':>5} {'meanNet':>8} {'t':>6} "
           f"{'posFold':>7} {'hit':>5} {'totNet':>8} {'BH':>3} {'GO':>3}")
    print(hdr)
    print("-" * len(hdr))
    for r, sig in zip(rows, rej):
        go = bool(r["mean_net_bps"] > 0 and sig and r["pos_fold_pct"] >= 0.6)
        print(f"{r['symbol']:>7} {r['freq']:>4} {r['q']:>4.2f} {r['n']:>5} "
              f"{r['mean_net_bps']:>+8.3f} {r['t_stat']:>+6.2f} {r['pos_fold_pct']:>7.2f} "
              f"{r['hit_rate']*100:>4.0f}% {r['total_net_bps']:>+8.1f} "
              f"{str(sig):>3} {str(go):>3}")

    print("\nq-sensitivity (mean net bps, long-only):")
    print(f"{'pair':>7} {'freq':>4} {'q0.80':>7} {'q0.90':>7} {'q0.95':>7}")
    for s in syms:
        for f in freqs:
            vals = []
            for qq in (0.80, 0.90, 0.95):
                rr = run_cell_wfo(s, f, side="long", q=qq)
                vals.append(rr["mean_net_bps"] if rr else float("nan"))
            print(f"{s:>7} {f:>4} {vals[0]:>+7.3f} {vals[1]:>+7.3f} {vals[2]:>+7.3f}")

    jpy = run_cell_wfo("USDJPY", "3h", side="short", q=0.9)
    if jpy:
        print(f"\nUSDJPY 3h SHORT-side: n={jpy['n']} meanNet={jpy['mean_net_bps']:+.3f} "
              f"t={jpy['t_stat']:+.2f} posFold={jpy['pos_fold_pct']:.2f} hit={jpy['hit_rate']*100:.0f}%")

    # POOLED tight majors at 2h long: breadth for power, day-clustered t for honesty.
    print(f"\nPOOLED tight majors {TIGHT_MAJORS} @ 2h long — q-sweep:")
    print(f"{'q':>5} {'n':>6} {'meanNet':>8} {'naiveT':>7} {'naiveP':>7} "
          f"{'days':>5} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    for qq in TIGHT_2H_Q_SWEEP:
        p = pooled_long_test(TIGHT_MAJORS, "2h", q=qq)
        if p:
            print(f"{qq:>5.2f} {p['n']:>6} {p['mean_net_bps']:>+8.3f} {p['naive_t']:>+7.2f} "
                  f"{p['naive_p']:>7.3f} {p['day_n']:>5} {p['day_t']:>+6.2f} {p['day_p']:>7.3f} "
                  f"{p['hit_rate']*100:>4.0f}%")

    # Forking-paths attacks: does the selected edge generalize OOS and hold across eras?
    oos = oos_pairs_test("2h", q=0.95)
    print("\nOOS-PAIRS test (identical 2h long q0.95 rule on EXCLUDED majors), day-clustered:")
    print(f"{'pair':>7} {'n':>5} {'grossMean':>9} {'grossP':>7} {'netP':>7}")
    for sym in OOS_PAIRS:
        pp = oos["per_pair"][sym]
        print(f"{sym:>7} {pp['n']:>5} {pp['gross']['daily_mean']:>+9.3f} "
              f"{pp['gross']['p_value']:>7.3f} {pp['net']['p_value']:>7.3f}")
    pg = oos["pooled_gross"]
    print(f"  pooled GROSS: dailyMean={pg['daily_mean']:+.3f} t={pg['t_stat']:+.2f} p={pg['p_value']:.3f}")

    era = era_split_test(TIGHT_MAJORS, "2h", q=0.95)
    print(f"\nERA split-half (EUR/GBP/JPY 2h long q0.95 net) at {era['split_date']}, day-clustered:")
    for label in ("first", "second"):
        e = era[label]
        print(f"  {label:>6}: n_days={e['n_days']} dailyMean={e['daily_mean']:+.3f} "
              f"t={e['t_stat']:+.2f} p={e['p_value']:.3f}")

    # Target distribution analysis: did the target itself change shape?
    print("\n=== TARGET DISTRIBUTION ===")
    tdist = target_distribution_report(TIGHT_MAJORS, freq="2h", q=0.95, n_folds=5)
    if tdist:
        df_t = pd.DataFrame(tdist)
        df_t.sort_values("qtr", inplace=True)
        print(df_t.to_string(index=False))
    else:
        print("No data for target distribution.")

    # Granular temporal slices — is the decay smooth, a cliff, or episodic?
    for bins, label in (("Y", "YEARLY"), ("Q", "QUARTERLY")):
        slices = temporal_slice_report(TIGHT_MAJORS, "2h", q=0.95, bins=bins)
        if slices:
            print(f"\nTEMPORAL SLICE — {label} (EUR/GBP/JPY 2h long q0.95 net), day-clustered:")
            print(f"{'period':>8} {'n':>5} {'days':>5} {'meanNet':>8} {'t':>6} {'p':>7} {'hit':>5}")
            for s in slices:
                t_str = f"{s['t_stat']:>+6.2f}" if np.isfinite(s['t_stat']) else "   nan"
                p_str = f"{s['p_value']:>7.3f}" if np.isfinite(s['p_value']) else "    nan"
                print(f"{s['period']:>8} {s['n_trades']:>5} {s['n_days']:>5} "
                      f"{s['mean_net']:>+8.3f} {t_str} {p_str} "
                      f"{s['hit_rate']*100:>4.0f}%")

    # Death diagnostics: WHY did the edge die? IC collapse, vol compression, or tail toxicity?
    print("\nDIAGNOSTIC — POOLED tight majors: WHY did the edge die? (IC / vol / gross)")
    print(f"{'qtr':>7} {'n':>6} {'nTop':>5} {'IC':>6} {'vol':>6} "
          f"{'gAll':>7} {'gTopQ':>7} {'netTQ':>7}")
    for d in diagnose_edge_death_pooled(TIGHT_MAJORS, "2h", q=0.95):
        print(f"{d['qtr']:>7} {d['n']:>6} {d['n_topq']:>5} "
              f"{d['ic']:>+6.3f} {d['vol']:>6.3f} "
              f"{d['gross_all']:>+7.3f} {d['gross_topq']:>+7.3f} {d['net_topq']:>+7.3f}")

    # Deeper diagnostic: hit-vs-magnitude, distribution shape, vol-conditional IC, hour shift.
    print("\nDEEP DIAGNOSTIC — WHY did the tail stop paying? (hit / mag / skew / vol-cond IC)")
    print(f"{'qtr':>7} {'nTop':>5} {'hit%':>5} {'winAvg':>8} {'lossAvg':>8} "
          f"{'skew':>7} {'kurt':>7} {'netTQ':>7}")
    for d in diagnose_why_tail_died(TIGHT_MAJORS, "2h", q=0.95):
        print(f"{d['qtr']:>7} {d['n_topq']:>5} {d['hit_rate']*100:>4.0f}% "
              f"{d['win_avg']:>+8.3f} {d['loss_avg']:>+8.3f} "
              f"{d['skew']:>+7.3f} {d['kurt']:>+7.3f} {d['net_topq']:>+7.3f}")
        if d["ic_by_vol"]:
            vol_ic = " ".join(f"{k}={v:+.3f}" for k, v in sorted(d["ic_by_vol"].items()))
            print(f"  → vol-cond IC: {vol_ic}  topHours={d['top_hours']}")

    # ENHANCED MODEL EXPERIMENT — regime features baked INTO the model
    print("\nENHANCED MODEL — regime features IN the Ridge model (interactions)")
    print(f"{'variant':>22} {'n':>5} {'meanNet':>8} {'t':>6} {'hit':>5} {'posFold':>7}")
    for sym in TIGHT_MAJORS:
        base = run_cell_wfo(sym, "2h", side="long", q=0.95)
        enh = run_cell_wfo_enhanced(sym, "2h", side="long", q=0.95)
        if base:
            print(f"{sym:>7} baseline      {base['n']:>5} {base['mean_net_bps']:>+8.3f} "
                  f"{base['t_stat']:>+6.2f} {base['hit_rate']*100:>4.0f}% {base['pos_fold_pct']:>7.2f}")
        if enh:
            print(f"{sym:>7} enhanced      {enh['n']:>5} {enh['mean_net_bps']:>+8.3f} "
                  f"{enh['t_stat']:>+6.2f} {enh['hit_rate']*100:>4.0f}% {enh['pos_fold_pct']:>7.2f}")

    # Pooled enhanced vs baseline
    print("\nPOOLED ENHANCED vs BASELINE (EUR/GBP/JPY 2h long q0.95)")
    print(f"{'variant':>22} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    for label, use_enhanced in [("baseline", False), ("enhanced", True)]:
        nets, buckets = [], []
        for sym in TIGHT_MAJORS:
            if use_enhanced:
                panel = build_enhanced_panel(sym, "2h")
                if panel is None or len(panel) < 200:
                    continue
                folds = walk_forward_enhanced(panel, n_folds=5)
            else:
                src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
                if not src.exists():
                    continue
                panel = build_panel(build_freq_bars(pl.read_parquet(src), "2h"))
                if len(panel) < 200:
                    continue
                folds = walk_forward(panel, n_folds=5)
            tr = gate_trades(folds, q=0.95, cost_bps=COST_BPS[sym])
            if tr["n"] > 0:
                nets.append(tr["net"])
                buckets.append(tr["bucket"])
        if not nets:
            continue
        net = np.concatenate(nets)
        bk = np.concatenate(buckets)
        dc = day_clustered_tstat(net, bk)
        print(f"{label:>22} {len(net):>5} {net.mean():>+8.3f} "
              f"{dc['t_stat']:>+6.2f} {dc['p_value']:>7.3f} {(net>0).mean()*100:>4.0f}%")

    # REGIME + META-RULE EXPERIMENT — can we rescue the edge?
    print("\nREGIME + META-RULE EXPERIMENT (EUR/GBP/JPY 2h long q0.95)")
    print(f"{'variant':>22} {'n':>5} {'meanNet':>8} {'t':>6} {'hit':>5} {'posFold':>7}")
    variants = [
        ("baseline (no filters)", 0.0, 0.0),
        ("regime skew≥0.0", 0.0, 0.0),  # placebo — should match baseline
        ("regime skew≥0.3", 0.3, 0.0),
        ("regime skew≥0.5", 0.5, 0.0),
        ("regime skew≥0.7", 0.7, 0.0),
        ("meta payoff≥1.0", 0.0, 1.0),
        ("meta payoff≥1.2", 0.0, 1.2),
        ("meta payoff≥1.5", 0.0, 1.5),
        ("regime≥0.3 + meta≥1.2", 0.3, 1.2),
        ("regime≥0.5 + meta≥1.2", 0.5, 1.2),
        ("regime≥0.3 + meta≥1.5", 0.3, 1.5),
        ("regime≥0.5 + meta≥1.5", 0.5, 1.5),
    ]
    for sym in TIGHT_MAJORS:
        for label, min_skew, min_payoff in variants:
            rr = run_cell_wfo_regime(
                sym, "2h", side="long", q=0.95,
                min_regime=min_skew, min_payoff=min_payoff,
            )
            if rr:
                print(f"{sym:>7} {label:>14} {rr['n']:>5} {rr['mean_net_bps']:>+8.3f} "
                      f"{rr['t_stat']:>+6.2f} {rr['hit_rate']*100:>4.0f}% {rr['pos_fold_pct']:>7.2f}")

    # POOLED version of the same experiment
    print("\nPOOLED REGIME + META EXPERIMENT (EUR/GBP/JPY 2h long q0.95)")
    print(f"{'variant':>25} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    for label, min_skew, min_payoff in variants:
        nets, buckets = [], []
        for sym in TIGHT_MAJORS:
            src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
            if not src.exists():
                continue
            panel = add_trailing_regime_features(
                build_panel(build_freq_bars(pl.read_parquet(src), "2h")), window=30
            )
            if len(panel) < 200:
                continue
            folds = walk_forward_regime_aware(panel, n_folds=5)
            if min_skew > 0 and min_payoff > 0:
                tr = _gate_both(folds, q=0.95, cost_bps=COST_BPS[sym],
                                min_skew=min_skew, min_payoff=min_payoff)
            elif min_skew > 0:
                tr = gate_trades_regime(folds, q=0.95, cost_bps=COST_BPS[sym],
                                        min_regime=min_skew)
            elif min_payoff > 0:
                tr = gate_trades_meta(folds, q=0.95, cost_bps=COST_BPS[sym],
                                      min_payoff=min_payoff)
            else:
                tr = gate_trades(folds, q=0.95, cost_bps=COST_BPS[sym])
            if tr["n"] > 0:
                nets.append(tr["net"])
                buckets.append(tr["bucket"])
        if not nets:
            continue
        net = np.concatenate(nets)
        bk = np.concatenate(buckets)
        dc = day_clustered_tstat(net, bk)
        print(f"{label:>25} {len(net):>5} {net.mean():>+8.3f} "
              f"{dc['t_stat']:>+6.2f} {dc['p_value']:>7.3f} {(net>0).mean()*100:>4.0f}%")

    # FEATURE ABLATION EXPERIMENT — does reducing the input space help?
    print("\nFEATURE ABLATION (EUR/GBP/JPY 2h long q0.95) — single features + best pairs")
    print(f"{'features':>25} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    ablations: list[tuple[str, list[str]]] = [
        ("baseline (all 5)", None),
        ("r_1 only", ["r_1"]),
        ("mom_short only", ["mom_short"]),
        ("mom_long only", ["mom_long"]),
        ("rvol_24 only", ["rvol_24"]),
        ("hour only", ["hour"]),
        ("r_1 + mom_short", ["r_1", "mom_short"]),
        ("r_1 + mom_long", ["r_1", "mom_long"]),
        ("mom_short + mom_long", ["mom_short", "mom_long"]),
        ("r_1 + hour", ["r_1", "hour"]),
        ("mom_short + hour", ["mom_short", "hour"]),
        ("r_1 + mom_short + hour", ["r_1", "mom_short", "hour"]),
        ("r_1 + mom_long + hour", ["r_1", "mom_long", "hour"]),
        ("r_1 + mom_short + mom_long", ["r_1", "mom_short", "mom_long"]),
        ("mom_short + mom_long + rvol", ["mom_short", "mom_long", "rvol_24"]),
        ("r_1 + mom_short + mom_long + hour", ["r_1", "mom_short", "mom_long", "hour"]),
    ]
    for label, cols in ablations:
        nets, buckets = [], []
        for sym in TIGHT_MAJORS:
            src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
            if not src.exists():
                continue
            panel = build_panel(build_freq_bars(pl.read_parquet(src), "2h"))
            if len(panel) < 200:
                continue
            # Validate columns exist
            use_cols = cols if cols is not None else FEATURE_COLS
            if not all(c in panel.columns for c in use_cols):
                continue
            folds = walk_forward(panel, n_folds=5, feature_cols=use_cols)
            tr = gate_trades(folds, q=0.95, cost_bps=COST_BPS[sym])
            if tr["n"] > 0:
                nets.append(tr["net"])
                buckets.append(tr["bucket"])
        if not nets:
            continue
        net = np.concatenate(nets)
        bk = np.concatenate(buckets)
        dc = day_clustered_tstat(net, bk)
        print(f"{label:>25} {len(net):>5} {net.mean():>+8.3f} "
              f"{dc['t_stat']:>+6.2f} {dc['p_value']:>7.3f} {(net>0).mean()*100:>4.0f}%")

    # GAMLSS PROOF — distributional regression cannot rescue a dead tail
    print("\nGAMLSS PROOF — Quantile Regression transfer + oracle test")
    print(f"{'tau':>5} {'nPre':>6} {'nPost':>6} {'predPre':>9} {'predPost':>9} "
          f"{'selPreMean':>10} {'selPreP95':>9} {'selPostMean':>11} {'selPostP95':>10} "
          f"{'covPre':>7} {'covPost':>7}")
    for row in gamlss_quantile_proof(TIGHT_MAJORS, freq="2h"):
        print(f"{row['tau']:>5.2f} {row['n_pre']:>6} {row['n_post']:>6} "
              f"{row['pred_pre_mean']:>+9.3f} {row['pred_post_mean']:>+9.3f} "
              f"{row['sel_pre_mean']:>+10.3f} {row['sel_pre_p95']:>+9.3f} "
              f"{row['sel_post_mean']:>+11.3f} {row['sel_post_p95']:>+10.3f} "
              f"{row['coverage_pre']*100:>6.1f}% {row['coverage_post']*100:>6.1f}%")

    print("\nGAMLSS ORACLE — Ridge vs QR(0.95) head-to-head on SAME folds, top-5% gate:")
    print("  [Normal t = standard; Boot CI = percentile bootstrap 5k samples; "
          "Student-T = MLE on daily means, LR test for mu=0]")
    oracle = gamlss_oracle_wfo(TIGHT_MAJORS, freq="2h", q=0.95, n_folds=5)
    if oracle:
        for label, key in [("FULL SAMPLE", "full"), ("POST-2023Q1 ONLY", "post")]:
            r = oracle[f"ridge_{key}"]
            q = oracle[f"qr_{key}"]
            print(f"  {label}:")
            print(f"    Ridge: n={r['n']} meanNet={r['mean']:+.3f} "
                  f"normalT={r['day_t']:+.2f} normalP={r['day_p']:.3f} "
                  f"bootCI=[{r['boot_lo']:+.3f}, {r['boot_hi']:+.3f}] "
                  f"tDF={r['t_df']:.1f} tLoc={r['t_loc']:+.3f} tScale={r['t_scale']:.3f} "
                  f"tP={r['t_pvalue']:.3f} hit={r['hit']*100:.0f}%")
            print(f"    QR-95: n={q['n']} meanNet={q['mean']:+.3f} "
                  f"normalT={q['day_t']:+.2f} normalP={q['day_p']:.3f} "
                  f"bootCI=[{q['boot_lo']:+.3f}, {q['boot_hi']:+.3f}] "
                  f"tDF={q['t_df']:.1f} tLoc={q['t_loc']:+.3f} tScale={q['t_scale']:.3f} "
                  f"tP={q['t_pvalue']:.3f} hit={q['hit']*100:.0f}%")
    else:
        print("  Oracle produced no trades.")

    # Deep dive: buffer sweep + per-pair + calibration
    print("\nGAMLSS DEEP DIVE — buffer sweep, per-pair, calibration:")
    gamlss_deep_dive(TIGHT_MAJORS, freq="2h", q=0.95, n_folds=5)

    # Ultra-high-frequency experiment: 5m bars, top-1% + top-0.1%
    print("\n5-MINUTE TAIL EXPERIMENT — 5m bars, q-sweep:")
    print(f"{'pair':>7} {'freq':>4} {'q':>5} {'n':>5} {'meanNet':>8} {'t':>6} "
          f"{'posFold':>7} {'hit':>5} {'totNet':>8}")
    for qq in (0.99, 0.999):
        for r in run_5m_top1_experiment(TIGHT_MAJORS, q=qq, n_folds=5):
            print(f"{r['symbol']:>7} {r['freq']:>4} {r['q']:>5.3f} {r['n']:>5} "
                  f"{r['mean_net_bps']:>+8.3f} {r['t_stat']:>+6.2f} {r['pos_fold_pct']:>7.2f} "
                  f"{r['hit_rate']*100:>4.0f}% {r['total_net_bps']:>+8.1f}")

    # Longer-horizon experiment: 6h and daily (full-session, 0-24h) — q-sweep
    print("\nLONGER-HORIZON EXPERIMENT — 6h + 1d, q-sweep (broader gates for more trades):")
    print(f"{'pair':>7} {'freq':>4} {'q':>5} {'n':>5} {'meanNet':>8} {'t':>6} "
          f"{'posFold':>7} {'hit':>5} {'totNet':>8}")
    for freq in ("6h", "1d"):
        sess = (0, 24)
        for qq in (0.80, 0.85, 0.90, 0.95, 0.99):
            for sym in TIGHT_MAJORS:
                src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
                if not src.exists():
                    continue
                panel = build_panel(
                    build_freq_bars(pl.read_parquet(src), freq, session=sess),
                    vol_lookback=24 if freq == "6h" else 5,
                )
                if len(panel) < 200:
                    continue
                cost = COST_BPS[sym]
                folds = walk_forward(panel, n_folds=5)
                tr = gate_trades(folds, q=qq, cost_bps=cost, side="long")
                s = cell_stats(tr["net"], tr["fold_id"])
                print(f"{sym:>7} {freq:>4} {qq:>5.2f} {s['n']:>5} "
                      f"{s['mean_net_bps']:>+8.3f} {s['t_stat']:>+6.2f} {s['pos_fold_pct']:>7.2f} "
                      f"{s['hit_rate']*100:>4.0f}% {s['total_net_bps']:>+8.1f}")

    # Pooled daily EURUSD + GBPUSD (excluding USDJPY) at q=0.80, 0.85, 0.90
    print("\nPOOLED DAILY — EURUSD + GBPUSD (ex-USDJPY), q-sweep, day-clustered:")
    print(f"{'q':>5} {'n':>6} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5} {'days':>5}")
    for qq in (0.80, 0.85, 0.90):
        nets, buckets = [], []
        for sym in ("EURUSD", "GBPUSD"):
            src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
            if not src.exists():
                continue
            panel = build_panel(
                build_freq_bars(pl.read_parquet(src), "1d", session=(0, 24)),
                vol_lookback=5,
            )
            if len(panel) < 200:
                continue
            folds = walk_forward(panel, n_folds=5)
            tr = gate_trades(folds, q=qq, cost_bps=COST_BPS[sym], side="long")
            if tr["n"] > 0:
                nets.append(tr["net"])
                buckets.append(tr["bucket"])
        if not nets:
            continue
        net_all = np.concatenate(nets)
        bk_all = np.concatenate(buckets)
        dc = day_clustered_tstat(net_all, bk_all)
        print(f"{qq:>5.2f} {len(net_all):>6} {net_all.mean():>+8.3f} "
              f"{dc['t_stat']:>+6.2f} {dc['p_value']:>7.3f} "
              f"{(net_all > 0).mean() * 100:>4.0f}% {dc['n_days']:>5}")

    # Daily ERA split-half (EURUSD + GBPUSD pooled, 1d long q=0.85)
    print("\nDAILY ERA SPLIT-HALF — EURUSD + GBPUSD pooled 1d long q0.85, day-clustered:")
    print(f"{'half':>8} {'n':>6} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5} {'days':>5}")
    SPLIT_DATE = np.datetime64("2023-04-03")
    daily_nets, daily_buckets = [], []
    for sym in ("EURUSD", "GBPUSD"):
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(
            build_freq_bars(pl.read_parquet(src), "1d", session=(0, 24)),
            vol_lookback=5,
        )
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=5)
        tr = gate_trades(folds, q=0.85, cost_bps=COST_BPS[sym], side="long")
        if tr["n"] > 0:
            daily_nets.append(tr["net"])
            daily_buckets.append(tr["bucket"])
    if daily_nets:
        net_all = np.concatenate(daily_nets)
        bk_all = np.concatenate(daily_buckets)
        # split
        first_mask = bk_all < SPLIT_DATE
        second_mask = bk_all >= SPLIT_DATE
        for label, mask in [("first", first_mask), ("second", second_mask), ("full", np.ones_like(first_mask, dtype=bool))]:
            if mask.sum() < 2:
                continue
            dc = day_clustered_tstat(net_all[mask], bk_all[mask])
            print(f"{label:>8} {mask.sum():>6} {net_all[mask].mean():>+8.3f} "
                  f"{dc['t_stat']:>+6.2f} {dc['p_value']:>7.3f} "
                  f"{(net_all[mask] > 0).mean() * 100:>4.0f}% {dc['n_days']:>5}")

    # PATH ANALYSIS — cumulative P&L, drawdown, worst streaks
    print("\nPATH ANALYSIS — daily pooled EURUSD+GBPUSD q0.85 (sorted by trade date):")
    # Already have net_all and bk_all from above; sort chronologically
    order = np.argsort(bk_all)
    cum = np.cumsum(net_all[order])
    running_max = np.maximum.accumulate(cum)
    drawdown = cum - running_max
    max_dd_idx = np.argmin(drawdown)
    max_dd = drawdown[max_dd_idx]
    # longest underwater streak
    underwater = drawdown < 0
    streaks = []
    current_start = None
    for i, u in enumerate(underwater):
        if u and current_start is None:
            current_start = i
        elif not u and current_start is not None:
            streaks.append((current_start, i - current_start))
            current_start = None
    if current_start is not None:
        streaks.append((current_start, len(underwater) - current_start))
    longest_streak = max(streaks, key=lambda x: x[1]) if streaks else (0, 0)
    # best / worst 3-month rolling window (approx: ~65 trades ≈ 3 months)
    if len(cum) >= 65:
        rolling_3m = cum[65:] - cum[:-65]
        best_3m = rolling_3m.max()
        worst_3m = rolling_3m.min()
    else:
        best_3m = cum[-1] if len(cum) else 0.0
        worst_3m = best_3m
    # print key stats
    print(f"  trades: {len(cum):>4}  final_cum: {cum[-1]:>+8.2f}  "
          f"maxDD: {max_dd:>+8.2f}  longest_underwater: {longest_streak[1]:>4} trades")
    print(f"  best 3m: {best_3m:>+8.2f}  worst 3m: {worst_3m:>+8.2f}")
    # print cumulative curve (sampled every ~20 trades for brevity)
    step = max(1, len(cum) // 20)
    print("  CUMULATIVE P&L (sampled):")
    print(f"    {'trade#':>8} {'cumNet':>8} {'drawdown':>10}")
    for i in range(0, len(cum), step):
        print(f"    {i:>8} {cum[i]:>+8.2f} {drawdown[i]:>+10.2f}")

    # GAP RISK — unconditional daily return distribution (all days, not just signal)
    print("\nGAP RISK — unconditional daily next-close return distribution:")
    print(f"{'pair':>7} {'n':>6} {'mean':>8} {'std':>7} {'min':>8} {'1pct':>8} {'99pct':>8} {'max':>8}")
    raw_nets = []
    for sym in ("EURUSD", "GBPUSD"):
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(
            build_freq_bars(pl.read_parquet(src), "1d", session=(0, 24)),
            vol_lookback=5,
        )
        r = panel["ret_next_bps"].to_numpy() - COST_BPS[sym]
        raw_nets.append(r)
        print(f"{sym:>7} {len(r):>6} {r.mean():>+8.3f} {r.std():>7.3f} "
              f"{r.min():>+8.2f} {np.percentile(r, 1):>+8.2f} "
              f"{np.percentile(r, 99):>+8.2f} {r.max():>+8.2f}")
    if len(raw_nets) == 2:
        r_all = np.concatenate(raw_nets)
        print(f"{'pooled':>7} {len(r_all):>6} {r_all.mean():>+8.3f} {r_all.std():>7.3f} "
              f"{r_all.min():>+8.2f} {np.percentile(r_all, 1):>+8.2f} "
              f"{np.percentile(r_all, 99):>+8.2f} {r_all.max():>+8.2f}")
        # How many signal days coincided with worst 1% of all days?
        cutoff_1pct = np.percentile(r_all, 1)
        worst_signal_days = (net_all <= cutoff_1pct).sum()
        print(f"\n  Signal trades in worst 1% of all days: {worst_signal_days}/{len(net_all)} "
              f"({worst_signal_days/len(net_all)*100:.1f}%)")
        print(f"  Signal 1pctile net: {np.percentile(net_all, 1):+.2f} bps  "
              f"vs unconditional 1pctile: {cutoff_1pct:+.2f} bps")
        print(f"  Signal max loss: {net_all.min():+.2f} bps  "
              f"vs unconditional min: {r_all.min():+.2f} bps")


def target_distribution_report(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> list[dict]:
    """Analyze the distribution of the target (ret_next_bps) across WFO test sets.

    Answers: Is the mean positive? What is the skew? How heavy are the tails?
    Did the distribution SHAPE change (regime shift) or did the model's ability
    to discriminate change?

    Also reports the joint distribution: P(target in top-10% | pred in top-10%).
    If this conditional probability exceeds random chance (10%), the model is
    genuinely discriminating the right tail."""
    all_frames = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=n_folds)
        preds, acts, buckets = [], [], []
        for f in folds:
            preds.append(f["test_pred"])
            acts.append(f["test_actual_bps"])
            buckets.append(f["test_bucket"])
        all_frames.append(pd.DataFrame({
            "pred": np.concatenate(preds),
            "act": np.concatenate(acts),
            "bucket": pd.to_datetime(np.concatenate(buckets)),
        }))
    if not all_frames:
        return []
    df = pd.concat(all_frames, ignore_index=True)
    df["qtr"] = df["bucket"].dt.to_period("Q")

    rows: list[dict] = []
    for qtr, grp in df.groupby("qtr"):
        if len(grp) < 20:
            continue
        act = grp["act"]
        pred = grp["pred"]
        # Target distribution moments
        mean = float(act.mean())
        std = float(act.std())
        sk = float(act.skew())
        kurt = float(act.kurtosis())
        pct_pos = float((act > 0).mean())
        pct_gt_cost = float((act > 0.7).mean())  # approx cost
        pct_lt_neg_cost = float((act < -0.7).mean())
        # Joint tail: how often does top-10% pred hit top-10% target?
        pred_thr = np.quantile(pred, q)
        act_thr = np.quantile(act, q)
        pred_top = pred >= pred_thr
        act_top = act >= act_thr
        joint = float((pred_top & act_top).mean())
        cond = float(act_top[pred_top].mean()) if pred_top.sum() > 0 else float("nan")
        rows.append({
            "qtr": str(qtr),
            "n": len(grp),
            "mean": mean,
            "std": std,
            "skew": sk,
            "kurt": kurt,
            "pct_pos": pct_pos,
            "pct_gt_cost": pct_gt_cost,
            "pct_lt_neg_cost": pct_lt_neg_cost,
            "joint_tail": joint,
            "cond_hit": cond,
            "random_chance": 1.0 - q,
        })
    return rows


def gamlss_quantile_proof(
    pairs: list[str],
    freq: str = "2h",
    taus: tuple[float, ...] = (0.50, 0.75, 0.90, 0.95),
) -> list[dict]:
    """Empirical proof that GAMLSS-style distributional regression does NOT rescue
    the dead tail edge.

    We fit linear quantile regression (the building block of GAMLSS) for each tau
    on the pre-2023Q2 "good" era, then evaluate on the post-2023Q1 "bad" era.

    Two killer facts we will demonstrate:
    1.  **Transfer decay**: A QR(0.95) trained on the good era predicts a 95th
        percentile that is way too optimistic for the bad era (miscalibration).
    2.  **Oracle impossibility**: Even when we fit QR(0.95) *directly inside*
        each WFO fold of the bad era, the trades selected by that predicted
        95th percentile still lose money net of cost.

    If the oracle (perfect knowledge of the bad-era conditional distribution)
    cannot produce a profitable tail, no GAMLSS model can."""
    import statsmodels.api as sm  # noqa: F811
    from statsmodels.regression.quantile_regression import QuantReg  # noqa: F811

    all_frames = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        all_frames.append(panel)
    if not all_frames:
        return []
    df = pd.concat(all_frames, ignore_index=True)
    df["bucket"] = pd.to_datetime(df["bucket"])
    df["era"] = np.where(df["bucket"] < "2023-04-01", "pre", "post")

    cols = FEATURE_COLS
    X_pre = df.loc[df["era"] == "pre", cols].to_numpy()
    y_pre = df.loc[df["era"] == "pre", "ret_next_bps"].to_numpy()
    X_post = df.loc[df["era"] == "post", cols].to_numpy()
    y_post = df.loc[df["era"] == "post", "ret_next_bps"].to_numpy()
    X_pre_c = sm.add_constant(X_pre, has_constant="add")
    X_post_c = sm.add_constant(X_post, has_constant="add")

    rows: list[dict] = []
    for tau in taus:
        # 1. Transfer: train on pre, predict on post
        qr = QuantReg(y_pre, X_pre_c).fit(q=tau, max_iter=2000, p_tol=1e-6)
        pred_pre = qr.predict(X_pre_c)
        pred_post = qr.predict(X_post_c)

        # Select top 5% by predicted conditional quantile
        thr_pre = np.quantile(pred_pre, 0.95)
        sel_pre = pred_pre >= thr_pre
        actual_pre = y_pre[sel_pre]

        thr_post = np.quantile(pred_post, 0.95)
        sel_post = pred_post >= thr_post
        actual_post = y_post[sel_post]

        rows.append({
            "tau": tau,
            "n_pre": len(y_pre),
            "n_post": len(y_post),
            "pred_pre_mean": float(pred_pre.mean()),
            "pred_post_mean": float(pred_post.mean()),
            "sel_pre_n": int(sel_pre.sum()),
            "sel_pre_mean": float(actual_pre.mean()),
            "sel_pre_hit": float((actual_pre > 0).mean()),
            "sel_pre_p95": float(np.quantile(actual_pre, 0.95)) if len(actual_pre) else float("nan"),
            "sel_post_n": int(sel_post.sum()),
            "sel_post_mean": float(actual_post.mean()),
            "sel_post_hit": float((actual_post > 0).mean()),
            "sel_post_p95": float(np.quantile(actual_post, 0.95)) if len(actual_post) else float("nan"),
            "coverage_pre": float((actual_pre <= pred_pre[sel_pre]).mean()),
            "coverage_post": float((actual_post <= pred_post[sel_post]).mean()),
        })
    return rows


def gamlss_oracle_wfo(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> dict | None:
    """Head-to-head: Ridge (mean) vs QuantReg(0.95) on the SAME expanding-window folds.
    Both models fit in-sample; gate the top-(1-q) test observations by their prediction.
    If the QR tail-selection is not materially better than Ridge mean-selection,
    distributional regression adds no value."""
    import statsmodels.api as sm  # noqa: F811
    from statsmodels.regression.quantile_regression import QuantReg  # noqa: F811

    qr_nets, qr_buckets = [], []
    ridge_nets, ridge_buckets = [], []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        cost = COST_BPS[sym]
        n = len(panel)
        start = int(n * 0.5)
        edges = np.linspace(start, n, n_folds + 1).astype(int)
        X = panel[FEATURE_COLS].to_numpy()
        y = panel["ret_next_bps"].to_numpy()
        bucket = panel["bucket"].to_numpy()

        for k in range(n_folds):
            split = edges[k]
            test_lo, test_hi = edges[k] + 1, edges[k + 1]
            if test_hi - test_lo < 1 or split < 10:
                continue
            # Ridge on target_z (baseline)
            scaler = StandardScaler().fit(X[:split])
            ridge = Ridge(alpha=1.0).fit(
                scaler.transform(X[:split]),
                panel["target_z"].to_numpy()[:split],
            )
            ridge_pred_tr = ridge.predict(scaler.transform(X[:split]))
            ridge_pred_te = ridge.predict(scaler.transform(X[test_lo:test_hi]))
            ridge_thr = np.quantile(ridge_pred_tr, q)
            ridge_sel = ridge_pred_te >= ridge_thr
            if ridge_sel.any():
                ridge_nets.append(y[test_lo:test_hi][ridge_sel] - cost)
                ridge_buckets.append(bucket[test_lo:test_hi][ridge_sel])

            # QuantReg on raw bps (oracle)
            X_tr_c = sm.add_constant(X[:split], has_constant="add")
            X_te_c = sm.add_constant(X[test_lo:test_hi], has_constant="add")
            try:
                qr = QuantReg(y[:split], X_tr_c).fit(q=q, max_iter=2000, p_tol=1e-6)
            except Exception:
                continue
            qr_pred_tr = qr.predict(X_tr_c)
            qr_pred_te = qr.predict(X_te_c)
            qr_thr = np.quantile(qr_pred_tr, q)
            qr_sel = qr_pred_te >= qr_thr
            if qr_sel.any():
                qr_nets.append(y[test_lo:test_hi][qr_sel] - cost)
                qr_buckets.append(bucket[test_lo:test_hi][qr_sel])

    def _sub_stats(nets: list[np.ndarray], bks: list[np.ndarray], after: str | None = None) -> dict:
        if not nets:
            return {"n": 0, "mean": float("nan"), "hit": float("nan"),
                    "day_t": float("nan"), "day_p": float("nan"),
                    "boot_lo": float("nan"), "boot_hi": float("nan"),
                    "t_df": float("nan"), "t_loc": float("nan"), "t_scale": float("nan"),
                    "t_pvalue": float("nan"), "t_ll_ratio": float("nan")}
        net_all = np.concatenate(nets)
        bk_all = pd.to_datetime(np.concatenate(bks))
        if after:
            mask = np.asarray(bk_all >= pd.Timestamp(after), bool)
            net_all = net_all[mask]
            bk_all = bk_all[mask]
        if len(net_all) == 0:
            return {"n": 0, "mean": float("nan"), "hit": float("nan"),
                    "day_t": float("nan"), "day_p": float("nan"),
                    "boot_lo": float("nan"), "boot_hi": float("nan"),
                    "t_df": float("nan"), "t_loc": float("nan"), "t_scale": float("nan"),
                    "t_pvalue": float("nan"), "t_ll_ratio": float("nan")}
        dc = day_clustered_tstat(net_all, bk_all.to_numpy())
        daily = pd.Series(net_all).groupby(bk_all.date).mean().to_numpy()

        # Percentile bootstrap (B=5000) on daily means — robust to heavy tails
        rng = np.random.default_rng(42)
        boot_means = np.array([
            rng.choice(daily, size=len(daily), replace=True).mean()
            for _ in range(5000)
        ])
        boot_lo, boot_hi = float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))

        # Student-T MLE on daily means — directly models heavy tails
        from scipy.optimize import minimize  # noqa: F811

        def _student_t_nll(params: np.ndarray, data: np.ndarray) -> float:
            loc, log_scale, log_df = params
            scale = np.exp(log_scale)
            df = np.exp(log_df) + 2.0  # enforce df > 2 for finite variance
            z = (data - loc) / scale
            # stable log-likelihood for Student-T
            ll = (
                -np.log(scale)
                + sp.gammaln((df + 1) / 2)
                - sp.gammaln(df / 2)
                - 0.5 * np.log(df * np.pi)
                - ((df + 1) / 2) * np.log1p(z ** 2 / df)
            )
            return float(-np.sum(ll))

        def _fit_student_t(data: np.ndarray) -> dict:
            # Initial guesses
            loc0 = float(np.median(data))
            scale0 = float(np.clip(np.std(data, ddof=1), 1e-6, None))
            df0 = 5.0
            res = minimize(
                _student_t_nll,
                np.array([loc0, np.log(scale0), np.log(df0 - 2.0)]),
                args=(data,),
                method="L-BFGS-B",
                options={"maxiter": 1000},
            )
            loc, log_scale, log_df = res.x
            scale = float(np.exp(log_scale))
            df = float(np.exp(log_df) + 2.0)

            # Profile log-likelihood at mu=0 for LR test
            nll0 = minimize(
                lambda p: _student_t_nll(np.array([0.0, p[0], p[1]]), data),
                np.array([np.log(scale0), np.log(df0 - 2.0)]),
                method="L-BFGS-B",
                options={"maxiter": 1000},
            ).fun
            nll1 = res.fun
            lr_stat = float(2 * (nll0 - nll1))
            # p-value from chi-square with 1 df (testing loc=0)
            from scipy.stats import chi2  # noqa: F811
            p_val = float(chi2.sf(lr_stat, 1))

            return {
                "df": df,
                "loc": loc,
                "scale": scale,
                "p_value": p_val,
                "lr_stat": lr_stat,
            }

        t_fit = _fit_student_t(daily)

        return {
            "n": len(net_all),
            "mean": float(net_all.mean()),
            "hit": float((net_all > 0).mean()),
            "day_t": dc["t_stat"],
            "day_p": dc["p_value"],
            "boot_lo": boot_lo,
            "boot_hi": boot_hi,
            "t_df": t_fit["df"],
            "t_loc": t_fit["loc"],
            "t_scale": t_fit["scale"],
            "t_pvalue": t_fit["p_value"],
            "t_ll_ratio": t_fit["lr_stat"],
        }

    return {
        "ridge_full": _sub_stats(ridge_nets, ridge_buckets),
        "ridge_post": _sub_stats(ridge_nets, ridge_buckets, after="2023-04-01"),
        "qr_full": _sub_stats(qr_nets, qr_buckets),
        "qr_post": _sub_stats(qr_nets, qr_buckets, after="2023-04-01"),
    }


def gamlss_deep_dive(
    pairs: list[str],
    freq: str = "2h",
    q: float = 0.95,
    n_folds: int = 5,
) -> None:
    """Deep dive into QR(0.95) predictions vs realized returns.

    Tests three things that matter for practical deployment:
    1. Buffer sweep: does requiring pred > cost + X improve mean?
    2. Calibration: do higher QR predictions map to higher realized returns?
    3. Per-pair breakdown: which pairs carry the QR premium?
    """
    import statsmodels.api as sm  # noqa: F811
    from statsmodels.regression.quantile_regression import QuantReg  # noqa: F811

    per_pair_rows: list[dict] = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        cost = COST_BPS[sym]
        n = len(panel)
        start = int(n * 0.5)
        edges = np.linspace(start, n, n_folds + 1).astype(int)
        X = panel[FEATURE_COLS].to_numpy()
        y = panel["ret_next_bps"].to_numpy()
        bucket = panel["bucket"].to_numpy()

        all_preds, all_actuals, all_buckets, all_is_post = [], [], [], []
        for k in range(n_folds):
            split = edges[k]
            test_lo, test_hi = edges[k] + 1, edges[k + 1]
            if test_hi - test_lo < 1 or split < 10:
                continue
            X_tr_c = sm.add_constant(X[:split], has_constant="add")
            X_te_c = sm.add_constant(X[test_lo:test_hi], has_constant="add")
            try:
                qr = QuantReg(y[:split], X_tr_c).fit(q=q, max_iter=2000, p_tol=1e-6)
            except Exception:
                continue
            pred = qr.predict(X_te_c)
            thr = np.quantile(qr.predict(X_tr_c), q)
            sel = pred >= thr
            if sel.any():
                all_preds.append(pred[sel])
                all_actuals.append(y[test_lo:test_hi][sel])
                all_buckets.append(bucket[test_lo:test_hi][sel])
                all_is_post.append(
                    pd.to_datetime(bucket[test_lo:test_hi][sel]) >= pd.Timestamp("2023-04-01")
                )
        if not all_preds:
            continue
        preds = np.concatenate(all_preds)
        actuals = np.concatenate(all_actuals)
        _buckets = pd.to_datetime(np.concatenate(all_buckets))  # noqa: F841
        is_post = np.concatenate(all_is_post)

        # Buffer sweep on post-era only
        print(f"\n  {sym} QR-95 buffer sweep (post-2023Q1 only):")
        print(f"    {'buffer':>8} {'n':>5} {'meanNet':>8} {'hit':>5} {'std':>7}")
        for buf in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
            sel = (preds >= cost + buf) & is_post
            if sel.sum() == 0:
                continue
            net = actuals[sel] - cost
            print(f"    {buf:>8.1f} {sel.sum():>5} {net.mean():>+8.3f} "
                  f"{(net > 0).mean() * 100:>4.0f}% {net.std():>7.3f}")

        # Calibration: pred rank vs actual rank in post-era
        post_preds = preds[is_post]
        post_actuals = actuals[is_post]
        if len(post_preds) > 5:
            cal = float(spearmanr(post_preds, post_actuals).correlation)
            print(f"    Post-era pred-actual Spearman: {cal:+.3f}")

        # Record summary for pooled table
        net_all = actuals - cost
        net_post = actuals[is_post] - cost
        per_pair_rows.append({
            "symbol": sym,
            "n_total": len(net_all),
            "mean_total": float(net_all.mean()),
            "hit_total": float((net_all > 0).mean()),
            "n_post": len(net_post),
            "mean_post": float(net_post.mean()),
            "hit_post": float((net_post > 0).mean()),
        })

    # Pooled per-pair table
    if per_pair_rows:
        print("\n  QR-95 PER-PAIR SUMMARY:")
        print(f"    {'pair':>7} {'nTotal':>7} {'meanTot':>8} {'hitTot':>5} "
              f"{'nPost':>6} {'meanPost':>9} {'hitPost':>6}")
        for r in per_pair_rows:
            print(f"    {r['symbol']:>7} {r['n_total']:>7} {r['mean_total']:>+8.3f} "
                  f"{r['hit_total'] * 100:>4.0f}% {r['n_post']:>6} {r['mean_post']:>+9.3f} "
                  f"{r['hit_post'] * 100:>5.0f}%")


def run_5m_top1_experiment(
    pairs: list[str],
    q: float = 0.99,
    n_folds: int = 5,
) -> list[dict]:
    """Ultra-high-frequency experiment: 5-minute bars, top-1% gate.

    Motivation: more bars = more observations, tighter conditional distributions,
    and the extreme tail (top-1%) may isolate a cleaner sub-population than 2h top-5%.
    vol_lookback is scaled proportionally (288 bars ≈ 24h of 5m data).
    """
    rows: list[dict] = []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), "5m"), vol_lookback=288)
        if len(panel) < 2000:
            continue
        cost = COST_BPS[sym]
        folds = walk_forward(panel, n_folds=n_folds)
        tr = gate_trades(folds, q=q, cost_bps=cost, side="long")
        s = cell_stats(tr["net"], tr["fold_id"])
        rows.append({"symbol": sym, "freq": "5m", "q": q, **s})
    return rows


def _gate_both(
    folds: list[dict], q: float, cost_bps: float,
    min_skew: float = 0.3, min_payoff: float = 1.2,
) -> dict:
    """Combined gate: both regime skew AND payoff ratio must pass."""
    nets, fids, hours, buckets = [], [], [], []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        thr = np.quantile(f["train_pred"], q)
        sel = tp >= thr
        if "test_skew_ret" in f:
            sel = sel & (f["test_skew_ret"] >= min_skew)
        if "test_payoff_ret" in f:
            sel = sel & (f["test_payoff_ret"] >= min_payoff)
        net = f["test_actual_bps"][sel] - cost_bps
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
            buckets.append(f["test_bucket"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int),
                "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
    return {
        "net": np.concatenate(nets),
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "bucket": np.concatenate(buckets),
        "n": len(np.concatenate(nets)),
    }


if __name__ == "__main__":
    main()
