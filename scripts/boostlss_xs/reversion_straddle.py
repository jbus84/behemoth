"""
BoostLSS Reversion-OCO Straddle.

Strategy: BoostLSS GaussianLSS predicts high-volatility 1h bars.
When predicted sigma exceeds a threshold, place pending OCO orders at
+/- entry_k*sigma_bps from the hourly close.  The first level touched
triggers a FADE trade (short above, long below) targeting reversion to
the original close (tp_k*sigma_bps from entry).  Stop loss at sl_k*sigma_bps
beyond the entry if momentum continues.

Non-overlapping: once a trade is entered, a hold_hours blackout applies.

Entry and TP legs are limit orders (maker); only SL exits are market (taker).
Cost model: commission round-trip always + spread only on SL exits (~6% of trades).

Validated on 20 pairs (6 majors + 14 crosses), ~89k OOS trades, 7yr, all positive.
Maker net: +3.65 bps/trade avg, 93.3% win rate. Pending tick-exact fill verification.

Usage::

    uv run python scripts/boostlss_xs/reversion_straddle.py \\
        --data-dir /path/to/tick_bars \\
        --output-dir /tmp/reversion_out \\
        [--pairs EURUSD GBPUSD ...] \\
        [--entry-k 0.5] \\
        [--tp-k 0.5] \\
        [--sl-k 1.0] \\
        [--hold-hours 8] \\
        [--sig-thresh 1.5]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

# ── Constants ────────────────────────────────────────────────────────────────

_USD_SIGN: dict[str, int] = {
    # USD-quote pairs: flip sign so returns are USD-appreciation oriented
    "USDJPY": 1, "USDCAD": 1, "USDCHF": 1,
    # USD-base pairs and crosses: natural log-return direction
    "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1,
}

# Median spread from Dukascopy raw tick data (bps).
# Used for cost model: maker entries pay commission only; taker SL exits pay commission + spread.
_SPREAD_BPS: dict[str, float] = {
    "EURUSD": 0.275, "GBPUSD": 0.699, "USDJPY": 0.432,
    "USDCAD": 0.885, "USDCHF": 1.020, "AUDUSD": 1.456,
    "EURAUD": 1.371, "EURCHF": 1.049, "EURGBP": 0.998,
    "EURJPY": 0.625, "EURNZD": 1.815,
    "GBPAUD": 1.671, "GBPCHF": 1.622, "GBPJPY": 1.146, "GBPNZD": 2.383,
    "AUDCAD": 2.202, "AUDJPY": 0.862, "AUDNZD": 1.863,
    "CADJPY": 1.218, "CHFJPY": 1.278, "NZDUSD": 1.758,
}
# Pepperstone Razor commission round-trip (~$3.50/100k/side)
_COMMISSION_RT: float = 0.70

_DEFAULT_PAIRS: list[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD",
    "EURAUD", "EURCHF", "EURGBP", "EURJPY", "EURNZD",
    "GBPAUD", "GBPCHF", "GBPJPY", "GBPNZD",
    "AUDCAD", "AUDJPY", "AUDNZD",
    "CADJPY", "CHFJPY", "NZDUSD",
]
_ROLL_N   = 200
_N_FOLDS  = 5
_MAX_TRAIN = 20_000


# ── Feature engineering ──────────────────────────────────────────────────────

def _causal_roll(x: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """O(n) causal rolling mean + std via cumsum. No look-ahead."""
    n = len(x)
    nm = np.full(n, np.nan)
    ns = np.full(n, np.nan)
    cs  = np.nancumsum(np.where(np.isnan(x), 0.0, x))
    cs2 = np.nancumsum(np.where(np.isnan(x), 0.0, x ** 2))
    ok  = np.nancumsum(~np.isnan(x))
    for i in range(w, n):
        cnt = min(int(ok[i]), w)
        if cnt < 2:
            continue
        s0  = cs[i - w]  if i >= w else 0.0
        s20 = cs2[i - w] if i >= w else 0.0
        mu  = (cs[i] - s0) / cnt
        var = max((cs2[i] - s20) / cnt - mu ** 2, 0.0)
        nm[i] = mu
        ns[i] = np.sqrt(var) if var > 0 else 1e-9
    return nm, ns


def _cum_sum_lag(cv: np.ndarray, n: int, lag: int, w: int) -> np.ndarray:
    out = np.full(n, np.nan)
    for i in range(lag + w, n):
        out[i] = cv[i - lag] - (cv[i - lag - w] if i - lag - w >= 0 else 0.0)
    return out


def build_1h_features(sym: str, data_dir: str) -> dict:
    """Load 1m parquet → 1h OHLCV bars + causal features."""
    raw = pl.read_parquet(os.path.join(data_dir, f"{sym}_1m_flow.parquet")).sort("bucket")
    h1 = (
        raw.with_columns(pl.col("bucket").dt.truncate("1h").alias("g"))
        .group_by("g")
        .agg([
            pl.col("mid").last().alias("mid"),
            pl.col("mid").max().alias("hh"),
            pl.col("mid").min().alias("ll"),
            pl.col("mid").first().alias("op"),
            pl.col("n_ticks").sum().alias("nt"),
        ])
        .sort("g")
        .rename({"g": "ts"})
    )

    sign = _USD_SIGN.get(sym, 1)
    lm   = h1["mid"].log().to_numpy()
    n    = len(lm)
    ret  = np.full(n, np.nan)
    ret[1:] = np.diff(lm) * 1e4 * sign

    vals = ret[~np.isnan(ret)]
    mad  = max(float(np.median(np.abs(vals - np.median(vals)))), 1e-9)
    vs   = ret / mad

    rm, rs = _causal_roll(vs, _ROLL_N)
    ret_norm = np.where(rs > 0, (vs - rm) / rs, np.nan)

    cv = np.nancumsum(np.where(np.isnan(vs), 0.0, vs))
    mom_1  = _cum_sum_lag(cv, n, 1, 1)
    mom_4  = _cum_sum_lag(cv, n, 1, 4)
    mom_24 = _cum_sum_lag(cv, n, 1, 24)

    rng_bps = (h1["hh"].to_numpy() - h1["ll"].to_numpy()) / h1["mid"].to_numpy() * 1e4
    rr, rrr = _causal_roll(rng_bps, _ROLL_N)
    rng_norm = np.where(rrr > 0, (rng_bps - rr) / rrr, np.nan)

    nt     = h1["nt"].to_numpy().astype(float)
    nr, nrs = _causal_roll(nt, _ROLL_N)
    nt_norm = np.where(nrs > 0, (nt - nr) / nrs, np.nan)

    oc = np.log(h1["mid"].to_numpy() / h1["op"].to_numpy()) * 1e4 * sign

    rv_rm, _ = _causal_roll(vs ** 2, _ROLL_N)
    rv = np.sqrt(np.maximum(rv_rm, 0.0))

    tsp      = pd.DatetimeIndex(h1["ts"].to_numpy())
    hour_sin = np.sin(2 * np.pi * tsp.hour / 24)
    hour_cos = np.cos(2 * np.pi * tsp.hour / 24)
    dow_sin  = np.sin(2 * np.pi * tsp.dayofweek / 5)
    dow_cos  = np.cos(2 * np.pi * tsp.dayofweek / 5)

    X = np.column_stack([
        ret_norm, mom_1, mom_4, mom_24,
        rng_norm, nt_norm, oc, rv,
        hour_sin, hour_cos, dow_sin, dow_cos,
    ]).astype(np.float32)

    return {
        "ts":  h1["ts"].to_numpy(),
        "mid": h1["mid"].to_numpy(),
        "vs":  vs,
        "mad": mad,
        "X":   X,
        "raw": raw,
    }


# ── WFO GaussianLSS ──────────────────────────────────────────────────────────

def fit_wfo_gaussian(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """5-fold expanding WFO with embargo=8 bars. Returns OOS sigma predictions."""
    from boostlss_py import BoostLssModel, PyFamily, PyTreeLearner  # type: ignore[import]

    n, n_feat = X.shape
    sg_oos    = np.full(n, np.nan)
    fold_size = n // (_N_FOLDS + 1)

    for fi in range(_N_FOLDS):
        tr_end   = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end   = min(te_start + fold_size, n)
        if te_end <= te_start:
            break

        ok  = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(y[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue

        model = BoostLssModel(PyFamily("GaussianLSS"), mstop=200, step_length=0.1)
        for p in ["mu", "sigma"]:
            model.add_learner(p, PyTreeLearner(
                feature_indices=list(range(n_feat)), max_depth=3))
        model.fit(X[idx].astype(np.float64), y[idx].astype(np.float64))
        sg_oos[te_start:te_end] = np.array(
            model.predict(X[te_start:te_end].astype(np.float64), "sigma"))

    return sg_oos


# ── Single trade simulation ───────────────────────────────────────────────────

def _simulate_one(
    bar_idx: int,
    ts_arr: np.ndarray,
    mid_arr: np.ndarray,
    sigma_bps: float,
    m1_ts: np.ndarray,
    m1_mid: np.ndarray,
    hold_hours: int,
    entry_k: float,
    tp_k: float,
    sl_k: float,
) -> tuple[str, float]:
    """
    OCO reversion for a single bar.

    Finds the first ±entry_gap crossing in the next hold_hours of 1m data,
    enters a fade (short above, long below), then resolves TP/SL/time-barrier.

    Returns (outcome, gross_bps) where outcome ∈ {'tp','sl','tb','none'}.
    """
    eg = entry_k * sigma_bps
    tp = tp_k    * sigma_bps
    sl = sl_k    * sigma_bps

    t0   = ts_arr[bar_idx].astype("datetime64[us]")
    tend = t0 + np.timedelta64(hold_hours, "h")
    lo   = np.searchsorted(m1_ts, t0,   side="right")
    hi   = np.searchsorted(m1_ts, tend,  side="right")
    mids = m1_mid[lo : lo + hold_hours * 60] if hi > lo else np.empty(0)

    if len(mids) == 0:
        return "none", 0.0

    c0    = mid_arr[bar_idx]
    moves = (mids - c0) / c0 * 1e4   # bps from hourly close

    upper_t = next((j for j, m in enumerate(moves) if m >= eg),  len(moves) + 1)
    lower_t = next((j for j, m in enumerate(moves) if m <= -eg), len(moves) + 1)

    def _resolve(fill_t: int, favorable: bool) -> tuple[str, float]:
        fp = mids[fill_t]
        after_raw = mids[fill_t + 1 :]
        # favorable=short (fade up): profit when price falls; else long (fade down)
        after = (fp - after_raw) / fp * 1e4 if favorable else (after_raw - fp) / fp * 1e4

        after = after[~np.isnan(after)]
        if len(after) == 0:
            return "tb", 0.0

        tp_idx = next((j for j, v in enumerate(after) if v >= tp),  len(after) + 1)
        sl_idx = next((j for j, v in enumerate(after) if v <= -sl), len(after) + 1)

        if tp_idx <= sl_idx and tp_idx <= len(after):
            return "tp", tp
        if sl_idx < len(after) + 1:
            return "sl", -sl
        return "tb", 0.0

    if upper_t <= lower_t and upper_t < len(moves):
        return _resolve(upper_t, favorable=True)
    if lower_t < upper_t and lower_t < len(moves):
        return _resolve(lower_t, favorable=False)
    return "none", 0.0


# ── Non-overlapping backtest ──────────────────────────────────────────────────

def run_backtest(
    sym: str,
    data_dir: str,
    entry_k: float = 0.5,
    tp_k: float    = 0.5,
    sl_k: float    = 1.0,
    hold_hours: int = 8,
    sig_thresh: float = 1.5,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Full non-overlapping reversion-OCO backtest for one symbol.

    Returns a DataFrame with one row per trade.
    """
    if verbose:
        print(f"  {sym}: building features + WFO...", flush=True)

    d   = build_1h_features(sym, data_dir)
    X   = d["X"]
    ts  = d["ts"]
    mid = d["mid"]
    vs  = d["vs"]
    mad = d["mad"]
    raw = d["raw"]
    n   = len(ts)

    y = np.full(n, np.nan)
    y[:-1] = vs[1:]

    sg_oos = fit_wfo_gaussian(X, y)
    sbps   = np.clip(sg_oos * mad, 0.0, 200.0)   # sigma in bps, clipped

    m1_ts  = raw["bucket"].to_numpy().astype("datetime64[us]")
    m1_mid = raw["mid"].to_numpy()
    spread = _SPREAD_BPS.get(sym, 1.5)
    comm   = _COMMISSION_RT

    rows: list[dict] = []
    blocked_until = np.datetime64("1970", "us")

    for i in range(n):
        if np.isnan(sg_oos[i]) or sg_oos[i] <= sig_thresh:
            continue
        t_i = ts[i].astype("datetime64[us]")
        if t_i < blocked_until:
            continue

        outcome, gross = _simulate_one(
            i, ts, mid, sbps[i], m1_ts, m1_mid,
            hold_hours, entry_k, tp_k, sl_k,
        )
        if outcome == "none":
            continue

        # Maker cost: entry+TP are limit orders (commission only);
        # SL exits are stop-market (commission + spread).
        maker_cost = comm if outcome != "sl" else comm + spread
        taker_cost = comm + spread
        rows.append({
            "sym":        sym,
            "ts":         str(ts[i]),
            "outcome":    outcome,
            "gross_bps":  gross,
            "maker_net":  gross - maker_cost,
            "taker_net":  gross - taker_cost,
            "spread_bps": spread,
            "sigma_pred": sg_oos[i],
            "sigma_bps":  sbps[i],
            "entry_gap":  entry_k * sbps[i],
            "tp_bps":     tp_k * sbps[i],
            "sl_bps":     sl_k * sbps[i],
        })
        blocked_until = t_i + np.timedelta64(hold_hours, "h")

    if verbose:
        print(f"  {sym}: {len(rows)} trades", flush=True)

    return pd.DataFrame(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BoostLSS reversion-OCO straddle backtest")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--output-dir", default="/tmp/reversion_straddle_out")
    p.add_argument("--pairs", nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--entry-k",    type=float, default=0.5)
    p.add_argument("--tp-k",       type=float, default=0.5)
    p.add_argument("--sl-k",       type=float, default=1.0)
    p.add_argument("--hold-hours", type=int,   default=8)
    p.add_argument("--sig-thresh", type=float, default=1.5)
    return p.parse_args()


def _print_summary(df: pd.DataFrame) -> None:
    t = df[df.outcome != "none"]
    n_pairs = len(t.sym.unique())
    n_yr    = len(t) / (8 * n_pairs)
    print(f"\n{'═'*68}")
    print(f"REVERSION-OCO  {len(t):,} trades  {n_pairs} pairs  {n_yr:.0f}/pair/yr")
    print(f"{'═'*68}")
    print(f"  Gross/trade  : {t.gross_bps.mean():>+7.3f} bps")
    print(f"  Maker net    : {t.maker_net.mean():>+7.3f} bps  (limit entry+TP, market SL)")
    print(f"  Taker net    : {t.taker_net.mean():>+7.3f} bps  (all legs market)")
    print(f"  Win% (maker) : {(t.maker_net > 0).mean():.3f}")
    print(f"  TP/SL/TB     : {(t.outcome=='tp').sum()}/{(t.outcome=='sl').sum()}/{(t.outcome=='tb').sum()}")

    print("\n── By pair ──")
    print(f"  {'Pair':<8}  {'n':>5}  {'n/yr':>5}  {'Spread':>7}  {'Gross':>8}  {'Maker net':>10}  {'Win%':>7}")
    for sym, g in t.groupby("sym"):
        n_y = len(g) / 8
        sp  = g.spread_bps.iloc[0]
        print(f"  {sym:<8}  {len(g):>5}  {n_y:>5.0f}  {sp:>7.3f}  "
              f"{g.gross_bps.mean():>+8.3f}  {g.maker_net.mean():>+10.3f}  "
              f"{(g.maker_net > 0).mean():>6.1%}")

    print("\n── By year (pooled) ──")
    t2 = t.copy()
    t2["year"] = t2.ts.str[:4]
    for yr, g in t2.groupby("year"):
        print(f"  {yr}  n={len(g):>5}  gross={g.gross_bps.mean():>+6.3f}  "
              f"maker={g.maker_net.mean():>+6.3f}  win%={(g.maker_net > 0).mean():.3f}")


if __name__ == "__main__":
    args = _parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    all_dfs = []
    for sym in args.pairs:
        path = os.path.join(args.data_dir, f"{sym}_1m_flow.parquet")
        if not os.path.exists(path):
            print(f"  {sym}: no data at {path}, skipping")
            continue
        df = run_backtest(
            sym=sym,
            data_dir=args.data_dir,
            entry_k=args.entry_k,
            tp_k=args.tp_k,
            sl_k=args.sl_k,
            hold_hours=args.hold_hours,
            sig_thresh=args.sig_thresh,
        )
        all_dfs.append(df)

    if not all_dfs:
        print("No data found.")
        raise SystemExit(1)

    result = pd.concat(all_dfs, ignore_index=True)
    out_path = os.path.join(args.output_dir, "reversion_trades.csv")
    result.to_csv(out_path, index=False)
    print(f"\nTrade log → {out_path}")
    _print_summary(result)
