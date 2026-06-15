#!/usr/bin/env python3
"""Simulate CME-style FX analysis on Binance crypto tick data.

Uses real Binance trade tick data (price, qty, isBuyerMaker) to:
1. Classify ticks as buy-initiated (aggressive buyer) or sell-initiated (aggressive seller)
2. Build N-tick bars with real OFI = (buy_qty - sell_qty) / total_qty
3. Fit bivariate Hawkes on buy/sell event counts with structural stationarity enforcement
4. Generate a per-bar feature matrix for downstream modeling
5. Backtest with CME-style costs (~0.4 pips round-trip)
"""

from __future__ import annotations

import argparse
import io
import urllib.request
import warnings
import zipfile

import numpy as np
import pandas as pd
from scipy.optimize import minimize

warnings.filterwarnings("ignore")

# CME micro FX futures cost reference:
#   - M6E contract: 12,500 EUR notional, tick = $1.25 (0.0001 price)
#   - Retail round-trip ≈ $2–3 (exchange + clearing + broker)
#   - Pro round-trip   ≈ $1–1.50
# We simulate on BTCUSDT but report in $ terms; a realistic CME-like
# round-trip cost on BTC at ~$100k is ~$4–$10 per side.
# For clarity we express cost as a relative fee and convert to $.
CME_REL_COST_PER_SIDE = 0.00004  # 0.4 pips = 0.004 % relative


def fetch_binance_trades(symbol: str = "BTCUSDT", date: str = "2025-06-10") -> pd.DataFrame:
    """Fetch a full day's trades from Binance data.binance.vision (free historical)."""
    url = f"https://data.binance.vision/data/spot/daily/trades/{symbol}/{symbol}-trades-{date}.zip"
    print(f"Downloading {url} ...")
    with urllib.request.urlopen(url, timeout=60) as r:
        zf = zipfile.ZipFile(io.BytesIO(r.read()))
    csv_name = zf.namelist()[0]
    df = pd.read_csv(
        io.BytesIO(zf.read(csv_name)),
        header=None,
        names=["id", "price", "qty", "quote_qty", "time", "isBuyerMaker", "isBestMatch"],
    )
    df["price"] = pd.to_numeric(df["price"])
    df["qty"] = pd.to_numeric(df["qty"])
    df["time"] = pd.to_datetime(df["time"].astype("int64"), unit="us", utc=True)
    df["is_buy"] = (~df["isBuyerMaker"]).astype(int)
    df["is_sell"] = df["isBuyerMaker"].astype(int)
    print(f"Loaded {len(df):,} trades")
    return df.sort_values("time").reset_index(drop=True)


def build_tick_bars(df: pd.DataFrame, n_ticks: int = 100) -> pd.DataFrame:
    """Group ticks into N-tick bars with real OFI and microstructure stats."""
    n = len(df) // n_ticks
    chunk = df.iloc[: n * n_ticks].copy()
    chunk["bar_id"] = np.repeat(np.arange(n), n_ticks)

    # Pre-aggregate for speed
    grouped = chunk.groupby("bar_id")
    bars = pd.DataFrame({
        "open_ts": grouped["time"].first(),
        "close_ts": grouped["time"].last(),
        "open_price": grouped["price"].first(),
        "close_price": grouped["price"].last(),
        "high_price": grouped["price"].max(),
        "low_price": grouped["price"].min(),
        "buy_qty": grouped.apply(lambda g: g.loc[g["is_buy"] == 1, "qty"].sum()),
        "sell_qty": grouped.apply(lambda g: g.loc[g["is_sell"] == 1, "qty"].sum()),
        "total_qty": grouped["qty"].sum(),
        "buy_events": grouped["is_buy"].sum(),
        "sell_events": grouped["is_sell"].sum(),
        "n_ticks": grouped.size(),
    }).reset_index()

    bars["mid_price"] = (bars["open_price"] + bars["close_price"]) / 2
    bars["return"] = bars["close_price"] - bars["open_price"]
    bars["return_pct"] = bars["return"] / bars["open_price"]

    # Real OFI with volume weighting
    bars["ofi"] = np.where(
        bars["total_qty"] > 0,
        (bars["buy_qty"] - bars["sell_qty"]) / bars["total_qty"],
        0.0,
    )

    # Event-based OFI (unweighted by size)
    bars["ofi_events"] = np.where(
        bars["n_ticks"] > 0,
        (bars["buy_events"] - bars["sell_events"]) / bars["n_ticks"],
        0.0,
    )

    # VWAP and VWAP return
    vwap = grouped.apply(lambda g: np.average(g["price"], weights=g["qty"])).values
    bars["vwap"] = vwap
    bars["vwap_return"] = bars["vwap"] - bars["open_price"]

    return bars


def build_time_bars(df: pd.DataFrame, minutes: int = 5) -> pd.DataFrame:
    """Group ticks into time-based bars with real OFI and microstructure stats."""
    df = df.copy()
    df["bar_id"] = df["time"].dt.floor(f"{minutes}min")

    grouped = df.groupby("bar_id")
    bars = pd.DataFrame({
        "open_ts": grouped["time"].first(),
        "close_ts": grouped["time"].last(),
        "open_price": grouped["price"].first(),
        "close_price": grouped["price"].last(),
        "high_price": grouped["price"].max(),
        "low_price": grouped["price"].min(),
        "buy_qty": grouped.apply(lambda g: g.loc[g["is_buy"] == 1, "qty"].sum()),
        "sell_qty": grouped.apply(lambda g: g.loc[g["is_sell"] == 1, "qty"].sum()),
        "total_qty": grouped["qty"].sum(),
        "buy_events": grouped["is_buy"].sum(),
        "sell_events": grouped["is_sell"].sum(),
        "n_ticks": grouped.size(),
    }).reset_index()

    bars["mid_price"] = (bars["open_price"] + bars["close_price"]) / 2
    bars["return"] = bars["close_price"] - bars["open_price"]
    bars["return_pct"] = bars["return"] / bars["open_price"]

    bars["ofi"] = np.where(
        bars["total_qty"] > 0,
        (bars["buy_qty"] - bars["sell_qty"]) / bars["total_qty"],
        0.0,
    )

    bars["ofi_events"] = np.where(
        bars["n_ticks"] > 0,
        (bars["buy_events"] - bars["sell_events"]) / bars["n_ticks"],
        0.0,
    )

    vwap = grouped.apply(lambda g: np.average(g["price"], weights=g["qty"])).values
    bars["vwap"] = vwap
    bars["vwap_return"] = bars["vwap"] - bars["open_price"]

    return bars


def hawkes_loglik(params, buy_counts, sell_counts, penalty_weight=1e6):
    """Bivariate Hawkes with differentiable stationarity penalty."""
    mu_b, mu_s, alpha_bb, alpha_bs, alpha_sb, alpha_ss, beta = params
    if any(p <= 0 for p in params) or beta <= 0:
        return 1e10

    A = np.array([[alpha_bb, alpha_bs], [alpha_sb, alpha_ss]]) / beta
    eigvals = np.linalg.eigvals(A)
    sr = max(abs(eigvals))
    # Differentiable soft penalty — smooth gradient keeps optimizer away from boundary
    penalty = penalty_weight * max(0.0, sr - 0.95) ** 2

    decay = np.exp(-beta)
    n = len(buy_counts)
    R_bb, R_bs, R_sb, R_ss = 0.0, 0.0, 0.0, 0.0
    ll = 0.0
    for i in range(n):
        lb = max(mu_b + alpha_bb * R_bb + alpha_bs * R_bs, 1e-10)
        ls = max(mu_s + alpha_sb * R_sb + alpha_ss * R_ss, 1e-10)
        ll += buy_counts[i] * np.log(lb) - lb + sell_counts[i] * np.log(ls) - ls
        R_bb = decay * R_bb + buy_counts[i]
        R_bs = decay * R_bs + sell_counts[i]
        R_sb = decay * R_sb + buy_counts[i]
        R_ss = decay * R_ss + sell_counts[i]
    return -ll + penalty


def fit_hawkes(buy_counts, sell_counts, n_restarts: int = 15, seed: int = 42):
    """Fit bivariate Hawkes with multiple random starts."""
    best = None
    best_ll = np.inf
    rng = np.random.default_rng(seed)
    for _ in range(n_restarts):
        x0 = [
            rng.uniform(15, 45),
            rng.uniform(15, 45),
            rng.uniform(0.1, 5.0),
            rng.uniform(0.0, 2.0),
            rng.uniform(0.0, 2.0),
            rng.uniform(0.1, 5.0),
            rng.uniform(0.1, 1.0),
        ]
        bounds = [
            (0.1, 200), (0.1, 200),
            (0.01, 50), (0, 20), (0, 20), (0.01, 50),
            (0.01, 2.0),
        ]
        try:
            res = minimize(
                hawkes_loglik,
                x0,
                args=(buy_counts, sell_counts),
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 2000, "disp": False},
            )
            if res.fun < best_ll and res.fun > -1e9:
                best_ll = res.fun
                best = res
        except Exception:
            continue
    return best, best_ll


def apply_hawkes(params, buy_counts, sell_counts):
    """Apply fitted Hawkes to get predicted intensities."""
    mu_b, mu_s, alpha_bb, alpha_bs, alpha_sb, alpha_ss, beta = params
    decay = np.exp(-beta)
    n = len(buy_counts)
    pred_buy = np.empty(n)
    pred_sell = np.empty(n)
    R_bb, R_bs, R_sb, R_ss = 0.0, 0.0, 0.0, 0.0
    for i in range(n):
        pred_buy[i] = mu_b + alpha_bb * R_bb + alpha_bs * R_bs
        pred_sell[i] = mu_s + alpha_sb * R_sb + alpha_ss * R_ss
        R_bb = decay * R_bb + buy_counts[i]
        R_bs = decay * R_bs + sell_counts[i]
        R_sb = decay * R_sb + buy_counts[i]
        R_ss = decay * R_ss + sell_counts[i]
    return pred_buy, pred_sell


def evaluate_signal(signal, returns, label: str, cost_per_trade: float = 0.0, *, is_oos: bool = False):
    """Evaluate a signal's predictive power and backtest viability.

    Parameters
    ----------
    cost_per_trade : float
        Round-trip cost in the **same units as returns** (e.g. dollars).
    is_oos : bool
        If True, prints an "[OOS]" marker so we can distinguish in-sample
        Hawkes from out-of-sample Hawkes.
    """
    prefix = "[OOS] " if is_oos else ""
    print(f"\n=== {prefix}{label} ===")

    # Correlation with future returns at various lags
    for lag in [1, 2, 3, 5]:
        if len(signal) <= lag:
            continue
        corr = np.corrcoef(signal[:-lag], returns[lag:])[0, 1]
        print(f"  Lag {lag}: corr = {corr:+.4f}")

    # Decile-based backtest
    deciles = pd.qcut(signal, 10, labels=False, duplicates="drop")
    n_deciles = int(deciles.max()) + 1
    if n_deciles < 2:
        print("  Too few unique deciles to evaluate.")
        return

    top = deciles == deciles.max()
    bot = deciles == deciles.min()

    future_ret = returns[1:]
    top_mask = top[:-1]
    bot_mask = bot[:-1]

    top_ret_gross = future_ret[top_mask].mean() if top_mask.any() else np.nan
    bot_ret_gross = future_ret[bot_mask].mean() if bot_mask.any() else np.nan

    # Net after realistic round-trip cost
    top_ret_net = top_ret_gross - cost_per_trade if top_mask.any() else np.nan
    bot_ret_net = bot_ret_gross - cost_per_trade if bot_mask.any() else np.nan

    n_top = top_mask.sum()
    n_bot = bot_mask.sum()

    print(f"  Top decile gross: {top_ret_gross:+.6f}  net: {top_ret_net:+.6f}  (n={n_top})")
    print(f"  Bot decile gross: {bot_ret_gross:+.6f}  net: {bot_ret_net:+.6f}  (n={n_bot})")
    print(f"  Top accuracy (+ret): {(future_ret[top_mask] > 0).mean():.1%}")
    print(f"  Bot accuracy (−ret): {(future_ret[bot_mask] < 0).mean():.1%}")

    # Long/short: only trade top & bot deciles, cost on every round-trip
    traded_ret = np.where(top_mask, future_ret, np.where(bot_mask, -future_ret, np.nan))
    traded = traded_ret[~np.isnan(traded_ret)]
    if len(traded) > 0:
        long_short_gross = traded.mean()
        long_short_net = long_short_gross - cost_per_trade
        print(f"  Long/short per trade gross: {long_short_gross:+.6f}  net: {long_short_net:+.6f}  (trades={len(traded)})")
        print(f"  Long/short total gross: {traded.sum():+.6f}  net: {traded.sum() - len(traded)*cost_per_trade:+.6f}")
    else:
        print("  No trades in top/bot deciles.")


def generate_feature_matrix(bars, params, buy_counts, sell_counts, output_path: str | None = None):
    """Generate the full per-bar feature matrix for downstream modeling."""
    pred_buy, pred_sell = apply_hawkes(params, buy_counts, sell_counts)
    net_intensity = pred_buy - pred_sell
    total_intensity = pred_buy + pred_sell

    # Recursive computation of excitation for each bar
    decay = np.exp(-params[6])
    R_bb, R_bs, R_sb, R_ss = 0.0, 0.0, 0.0, 0.0
    exc_buy = np.empty(len(buy_counts))
    exc_sell = np.empty(len(sell_counts))
    for i in range(len(buy_counts)):
        exc_buy[i] = params[2] * R_bb + params[3] * R_bs
        exc_sell[i] = params[4] * R_sb + params[5] * R_ss
        R_bb = decay * R_bb + buy_counts[i]
        R_bs = decay * R_bs + sell_counts[i]
        R_sb = decay * R_sb + buy_counts[i]
        R_ss = decay * R_ss + sell_counts[i]

    features = pd.DataFrame({
        # Core identifiers
        "bar_id": bars["bar_id"],
        "open_ts": bars["open_ts"],
        "close_ts": bars["close_ts"],
        # Price / return targets
        "open_price": bars["open_price"],
        "close_price": bars["close_price"],
        "high_price": bars["high_price"],
        "low_price": bars["low_price"],
        "return": bars["return"],
        "return_pct": bars["return_pct"],
        "vwap": bars["vwap"],
        "vwap_return": bars["vwap_return"],
        # OFI signals
        "ofi": bars["ofi"],
        "ofi_events": bars["ofi_events"],
        # Hawkes intensities
        "hawkes_buy_intensity": pred_buy,
        "hawkes_sell_intensity": pred_sell,
        "hawkes_net_intensity": net_intensity,
        "hawkes_total_intensity": total_intensity,
        "hawkes_buy_excitation": exc_buy,
        "hawkes_sell_excitation": exc_sell,
        # Microstructure counts
        "buy_events": bars["buy_events"],
        "sell_events": bars["sell_events"],
        "buy_qty": bars["buy_qty"],
        "sell_qty": bars["sell_qty"],
        "total_qty": bars["total_qty"],
        "n_ticks": bars["n_ticks"],
        # Time features
        "hour": bars["open_ts"].dt.hour,
        "minute": bars["open_ts"].dt.minute,
        "dayofweek": bars["open_ts"].dt.dayofweek,
        # Rolling imbalance (3-bar, 10-bar)
        "imbalance_3": bars["ofi"].rolling(3, min_periods=1).mean(),
        "imbalance_10": bars["ofi"].rolling(10, min_periods=1).mean(),
        "event_imbalance_3": bars["ofi_events"].rolling(3, min_periods=1).mean(),
        "event_imbalance_10": bars["ofi_events"].rolling(10, min_periods=1).mean(),
    })

    # Future return targets (shifted for supervised learning)
    features["target_return_1"] = features["return"].shift(-1)
    features["target_return_pct_1"] = features["return_pct"].shift(-1)
    features["target_sign_1"] = np.sign(features["target_return_1"])

    if output_path:
        features.to_parquet(output_path, index=False)
        print(f"\nFeature matrix saved to {output_path} ({len(features)} rows x {len(features.columns)} cols)")

    return features


def walk_forward_hawkes(buy_counts, sell_counts, returns, train_size: int, test_size: int,
                        n_restarts: int = 15, seed: int = 42, cost_per_trade: float = 0.0):
    """Rolling walk-forward: fit on train_size bars, predict/test on next test_size bars, roll forward.

    Returns
    -------
    dict with aggregated OOS signal, returns, and evaluation metrics.
    """
    n = len(buy_counts)
    oos_signals = []
    oos_returns = []
    window_stats = []

    step = 0
    while True:
        train_start = step * test_size
        train_end = train_start + train_size
        test_end = train_end + test_size

        if test_end > n:
            break

        bc_train = buy_counts[train_start:train_end]
        sc_train = sell_counts[train_start:train_end]
        bc_test = buy_counts[train_end:test_end]
        sc_test = sell_counts[train_end:test_end]
        ret_test = returns[train_end:test_end]

        result, ll = fit_hawkes(bc_train, sc_train, n_restarts=n_restarts, seed=seed + step)
        if result is None:
            print(f"  Window {step+1}: fit failed, skipping")
            step += 1
            continue

        params = result.x
        pred_buy_test, pred_sell_test = apply_hawkes(params, bc_test, sc_test)
        net_test = pred_buy_test - pred_sell_test

        oos_signals.extend(net_test.tolist())
        oos_returns.extend(ret_test.tolist())

        corr = np.corrcoef(net_test[:-1], ret_test[1:])[0, 1] if len(net_test) > 1 else np.nan
        window_stats.append({
            "train_start": train_start,
            "train_end": train_end,
            "test_start": train_end,
            "test_end": test_end,
            "corr_lag1": corr,
            "spectral_radius": max(abs(np.linalg.eigvals(
                np.array([[params[2], params[3]], [params[4], params[5]]]) / params[6]
            ))),
        })
        step += 1

    if len(oos_signals) == 0:
        return {"success": False, "reason": "No windows completed"}

    oos_signals = np.array(oos_signals)
    oos_returns = np.array(oos_returns)

    # Aggregate correlation across all OOS predictions
    corr_lag1 = np.corrcoef(oos_signals[:-1], oos_returns[1:])[0, 1] if len(oos_signals) > 1 else np.nan

    # Decile-based backtest on aggregated OOS
    deciles = pd.qcut(oos_signals, 10, labels=False, duplicates="drop")
    n_deciles = int(deciles.max()) + 1
    if n_deciles < 2:
        return {"success": True, "corr_lag1": corr_lag1, "n_windows": len(window_stats),
                "n_oos": len(oos_signals), "message": "Too few unique deciles"}

    top = deciles == deciles.max()
    bot = deciles == deciles.min()
    future_ret = oos_returns[1:]
    top_mask = top[:-1]
    bot_mask = bot[:-1]

    top_ret_gross = future_ret[top_mask].mean() if top_mask.any() else np.nan
    bot_ret_gross = future_ret[bot_mask].mean() if bot_mask.any() else np.nan
    top_ret_net = top_ret_gross - cost_per_trade if top_mask.any() else np.nan
    bot_ret_net = bot_ret_gross - cost_per_trade if bot_mask.any() else np.nan

    traded_ret = np.where(top_mask, future_ret, np.where(bot_mask, -future_ret, np.nan))
    traded = traded_ret[~np.isnan(traded_ret)]
    ls_gross = traded.mean() if len(traded) > 0 else np.nan
    ls_net = ls_gross - cost_per_trade if len(traded) > 0 else np.nan

    return {
        "success": True,
        "corr_lag1": corr_lag1,
        "n_windows": len(window_stats),
        "n_oos": len(oos_signals),
        "top_decile_gross": top_ret_gross,
        "top_decile_net": top_ret_net,
        "bot_decile_gross": bot_ret_gross,
        "bot_decile_net": bot_ret_net,
        "long_short_gross": ls_gross,
        "long_short_net": ls_net,
        "n_trades": len(traded),
        "total_gross": traded.sum() if len(traded) > 0 else np.nan,
        "total_net": traded.sum() - len(traded) * cost_per_trade if len(traded) > 0 else np.nan,
        "window_stats": window_stats,
        "oos_signals": oos_signals,
        "oos_returns": oos_returns,
    }


def main(symbol: str = "BTCUSDT", n_ticks: int = 100, time_bar_minutes: int | None = None,
         dates: list[str] | None = None, walk_forward: bool = False):
    dates = dates or ["2025-06-10"]
    mode = "time" if time_bar_minutes else "tick"
    bar_param = time_bar_minutes or n_ticks

    all_dfs = []
    for date in dates:
        print(f"\nFetching {symbol} trades for {date}...")
        df = fetch_binance_trades(symbol, date)
        all_dfs.append(df)

    df = pd.concat(all_dfs, ignore_index=True).sort_values("time").reset_index(drop=True)
    print(f"\nTotal ticks: {len(df):,}")
    print(f"Buy events: {df['is_buy'].sum():,} ({100*df['is_buy'].mean():.1f}%)")
    print(f"Sell events: {df['is_sell'].sum():,} ({100*df['is_sell'].mean():.1f}%)")
    print(f"Mean trade size: {df['qty'].mean():.4f} BTC")

    if mode == "time":
        print(f"\nBuilding {bar_param}-minute time bars...")
        bars = build_time_bars(df, minutes=bar_param)
    else:
        print(f"\nBuilding {bar_param}-tick bars...")
        bars = build_tick_bars(df, n_ticks=bar_param)

    print(f"Bars: {len(bars):,}")
    duration = bars["close_ts"].iloc[-1] - bars["open_ts"].iloc[0]
    print(f"Total duration: {duration}")
    bar_dur = (bars["close_ts"] - bars["open_ts"]).median()
    print(f"Median bar duration: {bar_dur}")

    returns = bars["return"].values
    ofi = bars["ofi"].values
    ofi_events = bars["ofi_events"].values
    buy_counts = bars["buy_events"].values.astype(float)
    sell_counts = bars["sell_events"].values.astype(float)

    # Compute realistic cost in the same units as returns (dollars).
    mean_price = bars["open_price"].mean()
    cost_per_trade = mean_price * CME_REL_COST_PER_SIDE
    round_trip_cost = 2 * cost_per_trade
    print(f"\nMean bar open price: ${mean_price:,.2f}")
    print(f"Simulated CME cost per side: ${cost_per_trade:.4f}")
    print(f"Simulated CME round-trip cost: ${round_trip_cost:.4f}")

    # OFI has no fitted parameters → evaluate on full data (no overfitting risk)
    evaluate_signal(ofi, returns, "OFI (volume-weighted)", cost_per_trade=round_trip_cost)
    evaluate_signal(ofi_events, returns, "OFI (event-only, FX-style)", cost_per_trade=round_trip_cost)

    # ---- Hawkes evaluation ----
    if walk_forward:
        print("\n=== HAWKES WALK-FORWARD ===")
        # Use reasonable window sizes based on data length
        n = len(buy_counts)
        if mode == "time":
            train_size = 288   # 1 day of 5-min bars
            test_size = 96     # 8 hours
        else:
            train_size = 50000  # ~14 hours of 100-tick bars
            test_size = 10000   # ~3 hours
        print(f"Train window: {train_size} bars | Test window: {test_size} bars | Total bars: {n}")
        wf = walk_forward_hawkes(buy_counts, sell_counts, returns, train_size, test_size,
                                  n_restarts=10, seed=42, cost_per_trade=round_trip_cost)
        if not wf["success"]:
            print(f"Walk-forward failed: {wf.get('reason', 'unknown')}")
            return
        print("\n=== [WALK-FORWARD OOS] Hawkes net intensity ===")
        print(f"  OOS bars: {wf['n_oos']} across {wf['n_windows']} windows")
        print(f"  Lag 1: corr = {wf['corr_lag1']:+.4f}")
        print(f"  Top decile gross: {wf['top_decile_gross']:+.6f}  net: {wf['top_decile_net']:+.6f}")
        print(f"  Bot decile gross: {wf['bot_decile_gross']:+.6f}  net: {wf['bot_decile_net']:+.6f}")
        print(f"  Long/short per trade gross: {wf['long_short_gross']:+.6f}  net: {wf['long_short_net']:+.6f}  (trades={wf['n_trades']})")
        print(f"  Long/short total gross: {wf['total_gross']:+.6f}  net: {wf['total_net']:+.6f}")

        # Show per-window stability
        ws = pd.DataFrame(wf["window_stats"])
        print(f"\n  Window corr_lag1 stats: mean={ws['corr_lag1'].mean():+.4f}, std={ws['corr_lag1'].std():.4f}, min={ws['corr_lag1'].min():+.4f}, max={ws['corr_lag1'].max():+.4f}")
        print(f"  Window spectral radius: mean={ws['spectral_radius'].mean():.3f}, std={ws['spectral_radius'].std():.3f}")

        # Use the aggregated OOS signal for feature matrix
        oos_signals = wf["oos_signals"]
        # Pad to full length with NaN for non-OOS bars
        full_signal = np.full(len(bars), np.nan)
        full_signal[-len(oos_signals):] = oos_signals
        # We'll use a placeholder params for feature matrix (OOS signal already computed)
        params = (0, 0, 0, 0, 0, 0, 1)  # dummy
    else:
        # Single train/test split (original behaviour)
        split_idx = int(len(buy_counts) * 0.70)
        print("\n=== HAWKES FIT / EVAL ===")
        print(f"Train bars: {split_idx} | Test bars: {len(buy_counts) - split_idx}")

        result, ll = fit_hawkes(buy_counts[:split_idx], sell_counts[:split_idx], n_restarts=15, seed=42)
        if result is None:
            print("Fit failed")
            return

        params = result.x
        mu_b, mu_s, alpha_bb, alpha_bs, alpha_sb, alpha_ss, beta = params
        print(f"Parameters: mu_b={mu_b:.2f} mu_s={mu_s:.2f} alpha_bb={alpha_bb:.3f} alpha_ss={alpha_ss:.3f} alpha_bs={alpha_bs:.3f} alpha_sb={alpha_sb:.3f} beta={beta:.3f}")
        A = np.array([[alpha_bb, alpha_bs], [alpha_sb, alpha_ss]]) / beta
        sr = max(abs(np.linalg.eigvals(A)))
        print(f"Spectral radius: {sr:.3f}")
        print(f"Branching: buy→buy={alpha_bb/beta:.3f} sell→sell={alpha_ss/beta:.3f} sell→buy={alpha_bs/beta:.3f} buy→sell={alpha_sb/beta:.3f}")

        pred_buy_train, pred_sell_train = apply_hawkes(params, buy_counts[:split_idx], sell_counts[:split_idx])
        net_intensity_train = pred_buy_train - pred_sell_train
        evaluate_signal(net_intensity_train, returns[:split_idx], "Hawkes net intensity (train)", cost_per_trade=round_trip_cost)

        pred_buy_test, pred_sell_test = apply_hawkes(params, buy_counts[split_idx:], sell_counts[split_idx:])
        net_intensity_test = pred_buy_test - pred_sell_test
        evaluate_signal(net_intensity_test, returns[split_idx:], "Hawkes net intensity (test)", cost_per_trade=round_trip_cost, is_oos=True)

        full_signal = None

    # Feature matrix
    suffix = f"{bar_param}min" if mode == "time" else f"{bar_param}tick"
    out_path = f"scripts/tick_ofi/features_{symbol}_{suffix}_{dates[0]}_to_{dates[-1]}.parquet"
    features = generate_feature_matrix(bars, params, buy_counts, sell_counts, output_path=out_path)

    if full_signal is not None:
        features["hawkes_net_intensity_wf"] = full_signal
        features.to_parquet(out_path, index=False)
        print(f"Updated feature matrix with walk-forward Hawkes saved to {out_path}")

    print("\n=== SUMMARY ===")
    print(f"Symbol: {symbol}")
    print(f"Dates: {dates[0]} to {dates[-1]} ({len(dates)} day(s))")
    print(f"Ticks: {len(df):,} | Bars: {len(bars):,} ({mode}={bar_param})")
    print(f"Mean bar open price: ${mean_price:,.2f}")
    print(f"Simulated CME round-trip cost per trade: ${round_trip_cost:.4f}")
    print(f"Mean bar return: {returns.mean():+.6f} (std={returns.std():.6f})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="CME-style analysis on Binance tick data")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--n-ticks", type=int, default=100)
    p.add_argument("--time-bar-minutes", type=int, default=None, help="Build time bars (e.g. 5 for 5min); overrides --n-ticks")
    p.add_argument("--dates", nargs="+", default=["2025-06-10"])
    p.add_argument("--walk-forward", action="store_true", help="Use rolling walk-forward for Hawkes instead of single train/test split")
    args = p.parse_args()
    main(args.symbol, args.n_ticks, args.time_bar_minutes, args.dates, args.walk_forward)
