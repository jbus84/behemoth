"""FX breadth revalidation: 21-pair reversion (6 majors + 15 crosses).

Faithful port of the validated reversion engine:
- causal_fade with non-overlapping H-day holds
- expanding-window decile thresholds
- vol-normalized signal
- t-stat over trades (not Sharpe)

Data source: ~/Desktop/tick/ (HistData, proven distributionally identical to Dukascopy)
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

# ─── Config ─────────────────────────────────────────────────────────────────
MAJORS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF"]
CROSSES = [
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF",
    "AUDCAD", "GBPAUD", "EURAUD", "GBPCHF", "CADJPY",
    "CHFJPY", "NZDUSD", "EURNZD", "GBPNZD", "AUDNZD",
]
ALL_PAIRS = MAJORS + CROSSES

TICK_ROOT = Path("/Users/danielfisher/Desktop/tick")

PARAMS = {
    "lookback": 10,   # past 10d extended move
    "hold": 2,        # hold 2 days
    "decile": 0.90,   # top decile = extreme move
}

COST_BPS = 0.7  # Pepperstone Razor equivalent in bps


# ─── Data loaders ─────────────────────────────────────────────────────────────
def _load_1m_from_ticks(tick_dir: Path, symbol: str) -> pd.DataFrame:
    """Build 1m close mid from tick parquets."""
    sym_dir = tick_dir / symbol
    files = sorted(sym_dir.glob(f"{symbol}_*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"No tick files for {symbol} in {tick_dir}")

    chunks = []
    for f in files:
        df = pd.read_parquet(f, columns=["timestamp", "mid"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df = df.set_index("timestamp").resample("1min").last().dropna()
        chunks.append(df)

    prices = pd.concat(chunks).sort_index()
    prices = prices[~prices.index.duplicated(keep="first")]
    return prices


def load_pair(symbol: str) -> pd.DataFrame:
    """Load 1m mid prices for a pair from TICK_ROOT."""
    return _load_1m_from_ticks(TICK_ROOT, symbol)


# ─── Signal engine ────────────────────────────────────────────────────────────
def build_signal(prices: pd.DataFrame, lookback: int = 10) -> pd.Series:
    """Cumulative log-return over lookback days (vol-normalized)."""
    daily = prices["mid"].resample("1D").last().dropna()
    log_ret = np.log(daily / daily.shift(1))

    # Expanding-window vol (causal)
    vol = log_ret.expanding(min_periods=30).std() * np.sqrt(252)
    vol = vol.replace(0, np.nan).ffill()

    # Cumulative move over lookback
    cum_move = log_ret.rolling(lookback).sum()
    signal = cum_move / vol
    return signal.reindex(daily.index)


def simulate_fade(
    daily: pd.Series,
    signal: pd.Series,
    *,
    decile: float = 0.90,
    hold: int = 2,
    cost_bps: float = 0.7,
) -> dict:
    """Non-overlapping decile-triggered fade."""
    # Causal expanding decile threshold
    threshold = signal.expanding(min_periods=60).quantile(decile)
    threshold = threshold.ffill()

    # Trigger: extreme positive move → fade (short)
    trigger = signal > threshold

    # Build non-overlapping trade schedule
    trades = []
    i = 0
    idx = daily.index
    rets = np.log(daily / daily.shift(1))

    while i < len(idx):
        if trigger.iloc[i]:
            entry_idx = idx[i]
            exit_idx = idx[min(i + hold, len(idx) - 1)]
            if exit_idx in daily.index and entry_idx in daily.index:
                gross = -rets.loc[exit_idx]  # fade = opposite direction
                # Cost: 2-way spread (entry + exit)
                net = gross - (cost_bps / 10_000)
                trades.append({
                    "entry": entry_idx,
                    "exit": exit_idx,
                    "gross": gross,
                    "net": net,
                    "signal": signal.iloc[i],
                    "threshold": threshold.iloc[i],
                })
            i += hold  # non-overlap
        else:
            i += 1

    if not trades:
        return {"trades": 0, "net_mean": np.nan, "t": np.nan, "p": np.nan, "pos_years": "0/0"}

    df_trades = pd.DataFrame(trades)
    nets = df_trades["net"].dropna()
    if len(nets) < 2:
        return {"trades": len(nets), "net_mean": np.nan, "t": np.nan, "p": np.nan, "pos_years": "0/0"}

    # Annual breakdown
    df_trades["year"] = df_trades["entry"].dt.year
    yr_means = df_trades.groupby("year")["net"].sum()
    pos_years = (yr_means > 0).sum()
    total_years = len(yr_means)

    # Bootstrap CI (simple percentile bootstrap)
    boot_means = []
    rng = np.random.default_rng(42)
    for _ in range(10_000):
        sample = rng.choice(nets, size=len(nets), replace=True)
        boot_means.append(sample.mean())
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])

    tstat, pval = ttest_1samp(nets, popmean=0, alternative="two-sided")

    return {
        "trades": len(nets),
        "net_mean": nets.mean(),
        "gross_mean": df_trades["gross"].mean(),
        "t": tstat,
        "p": pval,
        "pos_years": f"{pos_years}/{total_years}",
        "boot95": f"[{ci_low:+.2f}, {ci_high:+.2f}]",
        "df_trades": df_trades,
    }


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    results = []
    all_trades = {}

    for symbol in ALL_PAIRS:
        print(f"Processing {symbol}...", file=sys.stderr)
        try:
            prices = load_pair(symbol)
            signal = build_signal(prices, lookback=PARAMS["lookback"])
            daily = prices["mid"].resample("1D").last().dropna()
            res = simulate_fade(
                daily,
                signal,
                decile=PARAMS["decile"],
                hold=PARAMS["hold"],
                cost_bps=COST_BPS,
            )
            res["symbol"] = symbol
            all_trades[symbol] = res.pop("df_trades", None)
            results.append(res)
            print(f"  {symbol}: {res['trades']} trades, net={res['net_mean']:+.2f}bps t={res['t']:.2f}", file=sys.stderr)
        except Exception as e:
            print(f"  {symbol}: FAILED - {e}", file=sys.stderr)
            results.append({
                "symbol": symbol,
                "trades": 0,
                "net_mean": np.nan,
                "gross_mean": np.nan,
                "t": np.nan,
                "p": np.nan,
                "pos_years": "-",
                "boot95": "-",
            })

    df = pd.DataFrame(results)
    df = df[["symbol", "trades", "gross_mean", "net_mean", "t", "p", "pos_years", "boot95"]]
    print(df.to_string(index=False))

    # ─── Pooled summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    for subset_name, subset_syms in [
        ("Majors (6)", MAJORS),
        ("Crosses (15)", CROSSES),
        ("All 21", ALL_PAIRS),
    ]:
        subset_trades = []
        for sym in subset_syms:
            if sym in all_trades and all_trades[sym] is not None:
                subset_trades.extend(all_trades[sym]["net"].dropna().tolist())
        if len(subset_trades) < 2:
            print(f"{subset_name}: insufficient trades")
            continue
        nets = pd.Series(subset_trades)
        tstat, pval = ttest_1samp(nets, popmean=0, alternative="two-sided")
        rng = np.random.default_rng(42)
        boot_means = [rng.choice(nets, size=len(nets), replace=True).mean() for _ in range(10_000)]
        ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
        print(f"{subset_name}: trades={len(nets)} net={nets.mean():+.2f}bps t={tstat:.2f} p={pval:.3f} boot95=[{ci_low:+.2f},{ci_high:+.2f}]")


if __name__ == "__main__":
    main()
