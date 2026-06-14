#!/usr/bin/env python3
"""Kalman-filter duet for EURUSD~GBPUSD on hourly and daily bars.

Loads tick data, aggregates to time bars, then runs a 2-state Kalman filter
(dynamic alpha + beta) on log prices.  The residual is analysed for mean
reversion and a simple z-score strategy is back-tested in-sample and out-of-sample.

Usage:
    uv run python scripts/fx_coint/kalman_duet.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.canonical_tick_feed import (  # noqa: E402
    DEFAULT_CANONICAL_ROOT,
    month_tags_between,
    quote_sql_path,
)

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
SYMBOLS = ["EURUSD", "GBPUSD"]
PIP_SIZE: dict[str, float] = {"EURUSD": 0.0001, "GBPUSD": 0.0001}
OOS_START = pd.Timestamp("2024-01-01", tz="UTC")

# Retail spread assumption (pips) — IG typical for majors during London/NY overlap.
SPREAD_PIPS: dict[str, float] = {"EURUSD": 1.2, "GBPUSD": 1.5}

# Kalman defaults — small process noise so beta drifts slowly.
KALMAN_Q = np.diag([1.0e-8, 1.0e-6])   # [alpha_var, beta_var]
KALMAN_R = 1.0e-6                        # observation noise (log-price units)

# Trading thresholds (z-score entry levels to sweep)
Z_THRESHOLDS = [0.5, 1.0, 1.5, 2.0]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ticks_to_bars(
    symbol: str,
    freq: str,  # "1h" or "1d"
    root: Path = DEFAULT_CANONICAL_ROOT,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Load tick parquet for *symbol* and aggregate to *freq* bars.

    Returns DataFrame with columns:
        timestamp (bar open), open_bid, high_bid, low_bid, close_bid,
        high_ask, close_ask, spread_mean, tick_volume
    """
    sym = str(symbol).upper()
    files_all = sorted((root / sym).glob(f"{sym}_*_ticks.parquet"))
    if not files_all:
        raise FileNotFoundError(f"No tick parquet for {sym} under {root}")

    # Filter by date range if provided.
    files: list[Path]
    if start is not None or end is not None:
        s = start if start is not None else pd.Timestamp.min.tz_localize("UTC")
        e = end if end is not None else pd.Timestamp.max.tz_localize("UTC")
        tags = set(month_tags_between(s, e))
        files = [p for p in files_all if any(tag in p.name for tag in tags)]
        if not files:
            files = files_all  # fallback
    else:
        files = files_all

    files_sql = "[" + ",".join(quote_sql_path(p) for p in files) + "]"

    # Use DuckDB's TIME_BUCKET for aggregation.
    con = duckdb.connect()
    try:
        bucket = "TIME_BUCKET(INTERVAL '1 hour', ts)" if freq == "1h" else "TIME_BUCKET(INTERVAL '1 day', ts)"
        sql = f"""
        SELECT
            {bucket} AS timestamp,
            first(bid) AS open_bid,
            max(bid)  AS high_bid,
            min(bid)  AS low_bid,
            last(bid) AS close_bid,
            max(ask)  AS high_ask,
            last(ask) AS close_ask,
            avg(ask - bid) AS spread_mean,
            count(*) AS tick_volume
        FROM (
            SELECT
                try_cast(timestamp AS TIMESTAMP WITH TIME ZONE) AS ts,
                try_cast(bid AS DOUBLE) AS bid,
                try_cast(ask AS DOUBLE) AS ask
            FROM read_parquet({files_sql})
        )
        WHERE ts IS NOT NULL AND bid IS NOT NULL AND ask IS NOT NULL
        GROUP BY timestamp
        ORDER BY timestamp
        """
        df = con.execute(sql).fetchdf()
    finally:
        con.close()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Kalman filter: dynamic regression y_t = alpha_t + beta_t * x_t + v_t
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DuetState:
    alpha: float
    beta: float
    residual: float          # y - (alpha + beta*x)
    innovation_var: float    # posterior variance of residual
    alpha_var: float
    beta_var: float


class KalmanDuet:
    """2-state random-walk Kalman for the linear relationship between two series.

    State: [alpha_t, beta_t]
    Observation at time t: y_t = [1, x_t] @ [alpha_t, beta_t] + v_t
    """

    def __init__(
        self,
        q: np.ndarray = KALMAN_Q,
        r: float = KALMAN_R,
    ) -> None:
        self._q = np.asarray(q, dtype=float)
        self._r = float(r)
        self._x = np.zeros(2, dtype=float)   # [alpha, beta]
        self._p = np.diag([1.0, 1.0])          # initial uncertainty
        self._warm = False

    def update(self, y: float, x: float) -> DuetState:
        """Observe pair (y, x) and return filtered state."""
        h = np.array([1.0, x], dtype=float)   # observation matrix (row vector)

        if not self._warm:
            # Initialise with OLS-like guess using just this point.
            self._x[:] = (y, 1.0)             # assume beta ~ 1 initially
            self._p = np.diag([1.0, 1.0])
            self._warm = True
            pred = float(self._x[0] + self._x[1] * x)
            return DuetState(
                alpha=float(self._x[0]),
                beta=float(self._x[1]),
                residual=y - pred,
                innovation_var=1.0,
                alpha_var=float(self._p[0, 0]),
                beta_var=float(self._p[1, 1]),
            )

        # Prediction step (random walk: F = I)
        x_pred = self._x.copy()
        p_pred = self._p + self._q

        # Update step
        pred = float(h @ x_pred)
        residual = y - pred
        s = float(h @ p_pred @ h.T) + self._r   # innovation variance
        k = (p_pred @ h) / s if s > 0 else np.zeros(2)   # Kalman gain

        self._x = x_pred + k * residual
        self._p = p_pred - np.outer(k, h @ p_pred)

        return DuetState(
            alpha=float(self._x[0]),
            beta=float(self._x[1]),
            residual=float(residual),
            innovation_var=float(s),
            alpha_var=float(self._p[0, 0]),
            beta_var=float(self._p[1, 1]),
        )


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def half_life_ou(series: np.ndarray) -> float:
    """Estimate Ornstein-Uhlenbeck half-life via AR(1) on the series."""
    s = np.asarray(series, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < 10:
        return np.nan
    y = s[1:]
    x = s[:-1]
    # y = a + b*x  =>  b = 1 - k*dt  =>  half-life = -ln(2)/ln(b)
    b = np.cov(y, x)[0, 1] / np.var(x) if np.var(x) > 0 else np.nan
    if np.isnan(b) or b >= 1.0 or b <= 0.0:
        return np.nan
    return -np.log(2) / np.log(b)


def adf_pvalue(series: np.ndarray) -> float:
    s = np.asarray(series, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < 30:
        return np.nan
    try:
        return float(adfuller(s, maxlag=1, regression="ct")[1])
    except Exception:
        return np.nan


def zscore(series: np.ndarray, window: int) -> np.ndarray:
    """Rolling z-score using *trailing* window (look-ahead-free)."""
    s = pd.Series(series, dtype=float)
    roll_mean = s.rolling(window, min_periods=window // 2).mean().shift(1)
    roll_std = s.rolling(window, min_periods=window // 2).std(ddof=0).shift(1)
    return ((s - roll_mean) / roll_std.replace(0, np.nan)).to_numpy()


# ---------------------------------------------------------------------------
# Back-test: simple residual z-score strategy
# ---------------------------------------------------------------------------

def backtest_residual(
    df: pd.DataFrame,
    z_thresh: float,
    half_life: float,
    spread_pips: float,
    pip: float,
) -> pd.DataFrame:
    """Back-test a simple fade-the-residual strategy.

    Position:
        residual = y - (alpha + beta*x)
        If residual z-score >  +thresh  → short residual (short y, long beta*x)
        If residual z-score <  -thresh  → long  residual (long  y, short beta*x)
    Costs:
        Round-trip ≈ 2 * spread_pips * pip  (both legs)
    """
    df = df.copy()
    df["pos"] = 0.0
    # Entry when |z| exceeds threshold
    long_mask = df["resid_z"] < -z_thresh
    short_mask = df["resid_z"] > z_thresh
    df.loc[long_mask, "pos"] = 1.0
    df.loc[short_mask, "pos"] = -1.0

    # Hold until sign flip or max hold based on half-life
    max_hold = max(1, int(np.ceil(half_life)))
    pos = df["pos"].to_numpy().copy()
    # Forward-fill positions up to max_hold bars, but close on zero-crossing
    current = 0.0
    hold_count = 0
    for i in range(len(pos)):
        if pos[i] != 0.0:
            current = pos[i]
            hold_count = 0
        else:
            hold_count += 1
            if current != 0.0:
                # Close if zero-crossed or max hold exceeded
                crossed = (
                    (current > 0 and df["resid_z"].iloc[i] > 0)
                    or (current < 0 and df["resid_z"].iloc[i] < 0)
                )
                if crossed or hold_count >= max_hold:
                    current = 0.0
                    hold_count = 0
        pos[i] = current
    df["pos"] = pos

    # Gross return in log-price units (approx pips / price)
    # return_y = log(close_y[t]) - log(close_y[t-1])
    # return_x = log(close_x[t]) - log(close_x[t-1])
    # residual return = return_y - beta[t-1] * return_x
    df["ret_y"] = df["log_y"].diff()
    df["ret_x"] = df["log_x"].diff()
    df["resid_ret"] = df["ret_y"] - df["beta"].shift(1) * df["ret_x"]

    # Cost per trade: both legs pay half-spread on entry + exit.
    # In log units: spread_pips * pip / mid ≈ spread_pips * pip / close_price
    # We approximate with average close prices.
    avg_price = df["close_y"].mean()
    cost_per_roundtrip = 2.0 * spread_pips * pip / avg_price
    df["trade"] = (df["pos"].diff().abs() > 0).astype(int)
    df["cum_cost"] = df["trade"].cumsum() * cost_per_roundtrip / 2.0  # amortise

    df["gross_pnl"] = df["pos"].shift(1) * df["resid_ret"]
    df["net_pnl"] = df["gross_pnl"] - df["trade"] * (cost_per_roundtrip / 2.0)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_duet(
    freq: str,
    root: Path = DEFAULT_CANONICAL_ROOT,
    oos_start: pd.Timestamp = OOS_START,
    start: pd.Timestamp | None = None,
) -> pd.DataFrame:
    if start is None:
        start = pd.Timestamp("2020-01-01", tz="UTC")
    print(f"\n{'='*60}", flush=True)
    print(f"Kalman Duet — EURUSD~GBPUSD — {freq} bars", flush=True)
    print(f"{'='*60}", flush=True)

    # ------------------------------------------------------------------
    # 1. Load bars
    # ------------------------------------------------------------------
    print(f"\n[1] Loading {freq} bars from tick data (from {start.date()})…", flush=True)
    eur = load_ticks_to_bars("EURUSD", freq=freq, root=root, start=start)
    gbp = load_ticks_to_bars("GBPUSD", freq=freq, root=root, start=start)
    print(f"    EURUSD: {len(eur):,} bars  ({eur['timestamp'].iloc[0]} → {eur['timestamp'].iloc[-1]})", flush=True)
    print(f"    GBPUSD: {len(gbp):,} bars  ({gbp['timestamp'].iloc[0]} → {gbp['timestamp'].iloc[-1]})", flush=True)

    # ------------------------------------------------------------------
    # 2. Align on common timestamps
    # ------------------------------------------------------------------
    merged = pd.merge(
        eur[["timestamp", "close_bid", "close_ask", "spread_mean"]].rename(
            columns={
                "close_bid": "close_y",
                "close_ask": "close_y_ask",
                "spread_mean": "spread_y",
            }
        ),
        gbp[["timestamp", "close_bid", "close_ask", "spread_mean"]].rename(
            columns={
                "close_bid": "close_x",
                "close_ask": "close_x_ask",
                "spread_mean": "spread_x",
            }
        ),
        on="timestamp",
        how="inner",
    )
    merged = merged.dropna().reset_index(drop=True)
    print(f"\n[2] Aligned common bars: {len(merged):,}", flush=True)

    # ------------------------------------------------------------------
    # 3. Log prices + Kalman filter
    # ------------------------------------------------------------------
    merged["log_y"] = np.log(merged["close_y"])
    merged["log_x"] = np.log(merged["close_x"])

    kf = KalmanDuet()
    states: list[DuetState] = []
    for _, row in merged.iterrows():
        states.append(kf.update(y=row["log_y"], x=row["log_x"]))

    merged["alpha"] = [s.alpha for s in states]
    merged["beta"] = [s.beta for s in states]
    merged["residual"] = [s.residual for s in states]
    merged["beta_var"] = [s.beta_var for s in states]

    # Warm-up drop: first 100 observations while filter stabilises.
    merged = merged.iloc[100:].reset_index(drop=True)
    print(f"\n[3] Kalman filter warm-up dropped; beta range: {merged['beta'].min():.3f} → {merged['beta'].max():.3f}", flush=True)
    print(f"    Final beta = {merged['beta'].iloc[-1]:.3f}  (std={merged['beta'].std():.3f})", flush=True)

    # ------------------------------------------------------------------
    # 4. Residual analysis
    # ------------------------------------------------------------------
    resid = merged["residual"].to_numpy()
    hl = half_life_ou(resid)
    adf_p = adf_pvalue(resid)
    print(f"\n[4] Residual diagnostics", flush=True)
    print(f"    Mean reversion half-life : {hl:.1f} bars", flush=True)
    print(f"    ADF p-value (constant+trend) : {adf_p:.4f}", flush=True)

    # Rolling z-score of residual (look-ahead-free)
    z_window = max(24, int(np.ceil(hl * 2)) if np.isfinite(hl) else 48)
    if freq == "1d":
        z_window = max(20, int(np.ceil(hl * 2)) if np.isfinite(hl) else 60)
    merged["resid_z"] = zscore(merged["residual"].to_numpy(), window=z_window)

    # ------------------------------------------------------------------
    # 5. Train / test split
    # ------------------------------------------------------------------
    merged["is_oos"] = merged["timestamp"] >= oos_start
    train = merged[~merged["is_oos"]]
    test = merged[merged["is_oos"]]
    print(f"\n[5] Split: train={len(train):,}  test={len(test):,}  (OOS from {oos_start.date()})", flush=True)

    # ------------------------------------------------------------------
    # 6. Back-test z-score thresholds
    # ------------------------------------------------------------------
    print(f"\n[6] Back-testing z-score entry thresholds…", flush=True)
    print(f"    {'z-thresh':>8} {'IS Sharpe':>10} {'IS mean':>10} {'IS WR%':>8} {'OOS Sharpe':>10} {'OOS mean':>10} {'OOS WR%':>8}", flush=True)
    best = None
    best_sharpe = -np.inf
    for zt in Z_THRESHOLDS:
        bt_is = backtest_residual(
            train, zt, hl,
            SPREAD_PIPS["EURUSD"] + SPREAD_PIPS["GBPUSD"],
            PIP_SIZE["EURUSD"],
        )
        bt_oos = backtest_residual(
            test, zt, hl,
            SPREAD_PIPS["EURUSD"] + SPREAD_PIPS["GBPUSD"],
            PIP_SIZE["EURUSD"],
        )

        def _metrics(bt: pd.DataFrame) -> tuple[float, float, float]:
            gross = bt["gross_pnl"].dropna()
            net = bt["net_pnl"].dropna()
            if len(net) < 2 or net.std() == 0:
                return (0.0, 0.0, 0.0)
            sharpe = net.mean() / net.std() * np.sqrt(252 if freq == "1d" else 24 * 252)
            wr = (net > 0).sum() / len(net)
            return (sharpe, net.mean(), wr)

        is_sh, is_mean, is_wr = _metrics(bt_is)
        oos_sh, oos_mean, oos_wr = _metrics(bt_oos)
        print(f"    {zt:8.1f} {is_sh:10.3f} {is_mean:10.6f} {is_wr*100:7.1f}% {oos_sh:10.3f} {oos_mean:10.6f} {oos_wr*100:7.1f}%", flush=True)
        if oos_sh > best_sharpe:
            best_sharpe = oos_sh
            best = (zt, bt_is, bt_oos)

    # ------------------------------------------------------------------
    # 7. Detail best threshold
    # ------------------------------------------------------------------
    if best:
        zt, bt_is, bt_oos = best
        print(f"\n[7] Best OOS threshold = ±{zt:.1f}", flush=True)
        for label, bt in [("In-sample", bt_is), ("Out-of-sample", bt_oos)]:
            net = bt["net_pnl"].dropna()
            gross = bt["gross_pnl"].dropna()
            trades = int(bt["trade"].sum())
            if len(net) == 0:
                continue
            ann_factor = np.sqrt(252) if freq == "1d" else np.sqrt(24 * 252)
            print(f"    {label}:", flush=True)
            print(f"        Gross Sharpe : {gross.mean()/gross.std()*ann_factor:.3f}", flush=True)
            print(f"        Net  Sharpe  : {net.mean()/net.std()*ann_factor:.3f}", flush=True)
            print(f"        Net mean/bar : {net.mean():.6f}  (annualised ≈ {net.mean()*ann_factor**2:.4f})", flush=True)
            print(f"        Win rate     : {(net>0).sum()/len(net)*100:.1f}%", flush=True)
            print(f"        Trades       : {trades}", flush=True)
            print(f"        Cum gross    : {gross.sum():.4f}", flush=True)
            print(f"        Cum net      : {net.sum():.4f}", flush=True)

    return merged


def main() -> None:
    p = argparse.ArgumentParser(description="Kalman duet EURUSD~GBPUSD")
    p.add_argument("--tick-root", default=str(DEFAULT_CANONICAL_ROOT))
    p.add_argument("--oos-start", default="2024-01-01")
    p.add_argument("--start", default="2020-01-01", help="Earliest tick data to load (YYYY-MM-DD)")
    args = p.parse_args()

    root = Path(args.tick_root)
    oos_start = pd.Timestamp(args.oos_start, tz="UTC")
    start = pd.Timestamp(args.start, tz="UTC")

    for freq in ("1h", "1d"):
        try:
            run_duet(freq=freq, root=root, oos_start=oos_start, start=start)
        except Exception as e:
            print(f"FAIL {freq}: {e}", flush=True)
            raise


if __name__ == "__main__":
    main()
