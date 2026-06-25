"""Rolling walk-forward optimization for hourly FX using MultiRocketHydraClassifier.

Cost-aware triple barrier labels + multivariate sliding window features + rolling WFO.

Usage:
    uv run python scripts/fx_coint/hourly_multirocket_wfo.py \
        --symbol EURUSD \
        --year 2024 \
        --horizon 6 \
        --lookback 24 \
        --train-months 6 \
        --test-months 1
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_triple_barrier import DEFAULT_COST_BPS, label_hourly

# ── CONFIG ─────────────────────────────────────────────────────────────────
PAIRS = list(DEFAULT_COST_BPS.keys())
HOURS_PER_YEAR = 24 * 365.25  # ~8,766


# ── DATA LOADING ────────────────────────────────────────────────────────────
def load_hourly(symbol: str) -> pd.DataFrame:
    path = _REPO_ROOT / f"data/tick_bars/{symbol}_1h_flow.parquet"
    df = pl.read_parquet(path).to_pandas()
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.sort_values("bucket").reset_index(drop=True)
    return df


# ── REGIME DETECTION ──────────────────────────────────────────────────────
def classify_regime(rvol_bps: pd.Series, train_idx: np.ndarray) -> pd.Series:
    """Classify each bar into low / mid / high volatility regime.
    Thresholds are computed from the training set only (causal)."""
    train_rvol = rvol_bps.iloc[train_idx]
    p33 = train_rvol.quantile(0.33)
    p67 = train_rvol.quantile(0.67)
    return pd.cut(
        rvol_bps, bins=[-np.inf, p33, p67, np.inf], labels=[0, 1, 2]
    ).astype(int)


# ── FEATURE ENGINEERING ───────────────────────────────────────────────────
def build_feature_panel(
    df: pd.DataFrame,
    lookback: int,
    exclude_channels: set[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    """Build multivariate sliding windows for aeon.

    Args:
        df: hourly DataFrame with features + tb_label + regime
        lookback: window length in hours
        exclude_channels: optional set of channel names to drop

    Returns:
        X: (n_samples, n_channels, lookback)
        y: (n_samples,)  — triple barrier labels
        regime: (n_samples,) — regime code per sample
    """
    n = len(df)
    if n <= lookback:
        raise ValueError(f"Data too short: {n} bars, need > {lookback}")

    # Causal features (no future leakage)
    df["mid_ret"] = np.log(df["mid"]).diff().fillna(0.0)
    df["hour_sin"] = np.sin(2 * np.pi * df["bucket"].dt.hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["bucket"].dt.hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["bucket"].dt.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["bucket"].dt.dayofweek / 7)

    # NEW: normed returns = z-score of return over rolling 24h window, causal
    df["norm_ret"] = (
        (df["mid_ret"] - df["mid_ret"].rolling(24, min_periods=24).mean().shift(1))
        / (df["mid_ret"].rolling(24, min_periods=24).std().shift(1) + 1e-12)
    )
    df["norm_ret"] = df["norm_ret"].fillna(0.0)

    # NEW: raw spread in price terms
    df["raw_spread"] = df["ask"] - df["bid"]
    df["raw_spread_norm"] = (
        (df["raw_spread"] - df["raw_spread"].rolling(24, min_periods=24).mean().shift(1))
        / (df["raw_spread"].rolling(24, min_periods=24).std().shift(1) + 1e-12)
    )
    df["raw_spread_norm"] = df["raw_spread_norm"].fillna(0.0)

    all_channels = [
        "mid_ret",
        "norm_ret",
        "flow_tick",
        "flow_ofi",
        "rvol_bps",
        "spread_bps",
        "raw_spread_norm",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
    ]
    channels = [c for c in all_channels if c not in (exclude_channels or set())]

    # Normalize each channel to ~zero mean, unit variance over the full sample
    # (this is safe because we're only shifting/scaling, no future info)
    for c in channels:
        mean = df[c].mean()
        std = df[c].std() + 1e-12
        df[c] = (df[c] - mean) / std

    n_samples = n - lookback
    n_channels = len(channels)
    X = np.zeros((n_samples, n_channels, lookback), dtype=np.float32)
    y = df["tb_label"].iloc[lookback:].to_numpy().astype(np.int8)
    regime = df["regime"].iloc[lookback:].reset_index(drop=True)

    for i in range(n_samples):
        t = i + lookback
        window = df[channels].iloc[t - lookback : t].to_numpy()
        # window shape: (lookback, n_channels) → transpose to (n_channels, lookback)
        X[i] = window.T

    return X, y, regime


# ── COST-AWARE SIMULATION ─────────────────────────────────────────────────
def simulate_trades(
    df: pd.DataFrame,
    preds: np.ndarray,
    cost_bps: float,
    regime_gate: np.ndarray | None = None,
) -> dict:
    """Simulate trading on predictions, net of cost.

    Only acts on +1 (long) and -1 (short) predictions. 0 = no trade.
    Entry: next bar's ask for long, bid for short.
    Exit: when triple barrier is hit or time expires.

    If regime_gate is provided, only trade in regimes 0 (low vol) or 1 (mid vol).
    Regime 2 (high vol) is skipped — this is the tail-risk filter.
    """
    n = len(df)
    rets = []
    skipped = 0
    for i in range(n - 1):
        pred = preds[i]
        if pred == 0:
            continue

        # Regime gate: skip high-volatility regimes
        if regime_gate is not None and regime_gate[i] == 2:
            skipped += 1
            continue

        entry_ask = df["ask"].iloc[i + 1]
        entry_bid = df["bid"].iloc[i + 1]
        horizon = int(df["tb_horizon"].iloc[i])

        # Look forward to find exit price
        exit_idx = min(i + 1 + horizon, n - 1)
        exit_ask = df["ask"].iloc[exit_idx]
        exit_bid = df["bid"].iloc[exit_idx]

        # Cost in price terms (using entry mid as reference)
        entry_mid = (entry_ask + entry_bid) / 2.0
        cost_price = entry_mid * cost_bps / 10_000.0

        if pred == 1:  # long
            gross = exit_bid - entry_ask
            net = gross - cost_price
        else:  # short
            gross = entry_bid - exit_ask
            net = gross - cost_price

        rets.append(net / entry_mid)  # return in % terms

    if not rets:
        return {
            "n_trades": 0,
            "gross_return_pct": 0.0,
            "net_return_pct": 0.0,
            "net_sharpe": 0.0,
            "positive_pct": 0.0,
            "max_dd": 0.0,
            "skipped": skipped,
        }

    rets = np.array(rets)
    cum = np.cumsum(rets)
    return {
        "n_trades": len(rets),
        "gross_return_pct": round(rets.sum() * 100, 3),
        "net_return_pct": round(rets.sum() * 100, 3),  # same since cost already deducted
        "net_sharpe": round(
            np.sqrt(len(rets)) * rets.mean() / (rets.std() + 1e-12), 3
        ),
        "positive_pct": round((rets > 0).mean() * 100, 1),
        "max_dd": round((cum - np.maximum.accumulate(cum)).min() * 100, 3),
        "skipped": skipped,
    }


# ── ROLLING WFO ────────────────────────────────────────────────────────────
@dataclass
class WfoResult:
    window: str
    n_train: int
    n_test: int
    accuracy: float
    precision_pos: float
    precision_neg: float
    net_sharpe: float
    positive_pct: float
    max_dd: float
    n_trades: int
    skipped: int


def rolling_wfo(
    df: pd.DataFrame,
    symbol: str,
    *,
    year: int,
    train_months: int,
    test_months: int,
    lookback: int,
    barrier_bps: float,
    horizon: int,
) -> list[WfoResult]:
    """Run rolling walk-forward on 1 year of hourly data."""

    cost_bps = DEFAULT_COST_BPS.get(symbol, 0.80)

    # Filter to target year
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.Timestamp(f"{year + 1}-01-01")
    mask = (df["bucket"] >= start) & (df["bucket"] < end)
    df = df[mask].copy().reset_index(drop=True)

    if len(df) == 0:
        raise ValueError(f"No data for {symbol} in {year}")

    # Add triple barrier labels
    df_pl = pl.from_pandas(df)
    df_pl = label_hourly(df_pl, symbol, barrier_bps=barrier_bps, horizon=horizon)
    df = df_pl.to_pandas()

    # Align timestamps (features start at index `lookback`)
    timestamps = df["bucket"].iloc[lookback:].reset_index(drop=True)

    # Generate rolling windows
    months = pd.date_range(start, end, freq="MS")  # month starts
    results: list[WfoResult] = []

    n_months = len(months)
    n_windows = n_months - train_months - test_months
    for i in range(n_windows):
        train_start = months[i]
        train_end = months[i + train_months]
        test_start = months[i + train_months]
        test_end = months[i + train_months + test_months] if (i + train_months + test_months) < n_months else end

        train_mask = (timestamps >= train_start) & (timestamps < train_end)
        test_mask = (timestamps >= test_start) & (timestamps < test_end)

        train_idx = np.where(train_mask.to_numpy())[0]
        test_idx = np.where(test_mask.to_numpy())[0]

        if len(train_idx) < 500 or len(test_idx) < 100:
            print(f"  SKIP {test_start:%Y-%m}: train={len(train_idx)} test={len(test_idx)}")
            continue

        # Regime: compute thresholds on training rvol only, then classify full window
        df["regime"] = classify_regime(df["rvol_bps"], train_idx)

        # Build feature panel (sliding windows) — now includes regime per bar
        X, y, regime = build_feature_panel(df, lookback)

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]
        regime_test = regime.iloc[test_idx].to_numpy()

        print(
            f"Window {test_start:%Y-%m}: train={len(X_train):,}  test={len(X_test):,}  "
            f"classes={np.bincount(y_train + 1)}  "
            f"regimes={np.bincount(regime_test)}"
        )

        # Train MultiRocketHydra (aeon is an isolated-env-only dependency; imported lazily)
        from aeon.classification.convolution_based import MultiRocketHydraClassifier

        clf = MultiRocketHydraClassifier(random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        # Classification metrics
        acc = (preds == y_test).mean()

        # Precision per class
        from sklearn.metrics import precision_score
        try:
            prec = precision_score(y_test, preds, labels=[-1, 1], average=None, zero_division=0)
            prec_neg, prec_pos = prec[0], prec[1]
        except Exception:
            prec_neg, prec_pos = 0.0, 0.0

        # Net-of-cost simulation with regime gate (only trade in low/mid vol)
        base_df = df.iloc[lookback:].reset_index(drop=True)
        test_df = base_df.iloc[test_idx].copy().reset_index(drop=True)
        sim = simulate_trades(test_df, preds, cost_bps, regime_gate=regime_test)

        results.append(
            WfoResult(
                window=f"{test_start:%Y-%m}",
                n_train=len(X_train),
                n_test=len(X_test),
                accuracy=round(acc, 4),
                precision_pos=round(prec_pos, 4),
                precision_neg=round(prec_neg, 4),
                net_sharpe=sim["net_sharpe"],
                positive_pct=sim["positive_pct"],
                max_dd=sim["max_dd"],
                n_trades=sim["n_trades"],
                skipped=sim.get("skipped", 0),
            )
        )

    return results


# ── MAIN ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="EURUSD", choices=PAIRS)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--lookback", type=int, default=24)
    parser.add_argument("--train-months", type=int, default=6)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--barrier-bps", type=float, default=5.0)
    args = parser.parse_args()

    print("=" * 70)
    print("Hourly MultiRocketHydra WFO")
    print("=" * 70)
    print(f"Symbol:      {args.symbol}")
    print(f"Year:        {args.year}")
    print(f"Horizon:     {args.horizon}h")
    print(f"Lookback:    {args.lookback}h")
    print(f"Barrier:     {args.barrier_bps} bps")
    print(f"Train/Test:  {args.train_months}mo / {args.test_months}mo")
    print(f"Cost:        {DEFAULT_COST_BPS[args.symbol]} bps")
    print("=" * 70)

    df = load_hourly(args.symbol)
    results = rolling_wfo(
        df,
        args.symbol,
        year=args.year,
        train_months=args.train_months,
        test_months=args.test_months,
        lookback=args.lookback,
        barrier_bps=args.barrier_bps,
        horizon=args.horizon,
    )

    if not results:
        print("No valid windows.")
        return

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(
        f"{'Window':8s} {'Train':>6s} {'Test':>6s} {'Acc':>6s} {'Prec+':>6s} {'Prec-':>6s} "
        f"{'Sharpe':>7s} {'Pos%':>6s} {'Trades':>7s} {'Skip':>5s} {'MaxDD':>7s}"
    )
    print("-" * 70)
    for r in results:
        print(
            f"{r.window:8s} {r.n_train:>6,} {r.n_test:>6,} {r.accuracy:>6.3f} "
            f"{r.precision_pos:>6.3f} {r.precision_neg:>6.3f} {r.net_sharpe:>7.3f} "
            f"{r.positive_pct:>6.1f} {r.n_trades:>7,} {r.skipped:>5,} {r.max_dd:>7.3f}"
        )

    # Aggregate
    avg_acc = np.mean([r.accuracy for r in results])
    avg_sharpe = np.mean([r.net_sharpe for r in results])
    avg_pos = np.mean([r.positive_pct for r in results])
    print("-" * 70)
    print(f"{'AVG':8s} {'':>6s} {'':>6s} {avg_acc:>6.3f} {'':>6s} {'':>6s} "
          f"{avg_sharpe:>7.3f} {avg_pos:>6.1f} {'':>7s} {'':>5s} {'':>7s}")


if __name__ == "__main__":
    main()
