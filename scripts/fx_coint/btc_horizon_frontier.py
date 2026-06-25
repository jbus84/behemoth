"""Reversion frontier for crypto (BTC/ETH), same method as FX, fees as the cost wall.

Binance klines have no bid/ask, so cost = a parametrised round-trip fee (bps). Crypto
fees (taker ~10bps/side, maker ~1-2bps) dwarf FX spreads, but crypto moves are far
bigger — so the signal/cost frontier may differ. 24/7, no weekend gaps.

Fetches 1h klines (cached), resamples to a horizon ladder, fades the prior period,
reports net per (symbol, horizon) at several cost levels with a t-stat.

Usage:  uv run python scripts/fx_coint/btc_horizon_frontier.py
"""
# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
START_MS = int(pd.Timestamp("2018-01-01").timestamp() * 1000)
HORIZONS = {"1h": 1, "2h": 2, "4h": 4, "8h": 8, "12h": 12, "1d": 24, "2d": 48, "1w": 168}
COSTS_BPS = [2, 5, 10, 20]  # round-trip; maker-tight .. taker


def fetch_1h(sym: str) -> np.ndarray:
    cache = Path(f"/tmp/{sym}_1h_klines.parquet")
    if cache.exists():
        return pd.read_parquet(cache)["close"].to_numpy(dtype=np.float64)
    rows = []
    start = START_MS
    url = "https://api.binance.com/api/v3/klines"
    while True:
        q = f"{url}?symbol={sym}&interval=1h&startTime={start}&limit=1000"
        data = json.loads(urllib.request.urlopen(q, timeout=30).read())
        if not data:
            break
        rows += data
        start = data[-1][0] + 3_600_000
        if len(data) < 1000:
            break
        time.sleep(0.15)
    df = pd.DataFrame(rows).iloc[:, [0, 4]]
    df.columns = ["open_ms", "close"]
    df["close"] = df["close"].astype(float)
    df.to_parquet(cache)
    print(f"  {sym}: fetched {len(df)} 1h bars -> {cache}", flush=True)
    return df["close"].to_numpy(dtype=np.float64)


def cell(close_1h: np.ndarray, h_bars: int, cost_bps: float, follow: bool = False):
    bars = close_1h[::h_bars] if h_bars > 1 else close_1h
    r = np.diff(np.log(bars)) * 1e4
    prev, nxt = r[:-1], r[1:]
    m = np.isfinite(prev) & np.isfinite(nxt)
    if m.sum() < 50:
        return None
    prev, nxt = prev[m], nxt[m]
    ic = np.corrcoef(prev, nxt)[0, 1]
    direction = np.sign(prev) if follow else -np.sign(prev)  # follow=momentum
    net = direction * nxt - cost_bps
    t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
    return ic, net.mean(), t, len(net)


def main():
    print("=== CRYPTO reversion frontier (fade prior period), fees as cost ===")
    closes = {s: fetch_1h(s) for s in SYMBOLS}
    for s in SYMBOLS:
        n = len(closes[s])
        ann = np.std(np.diff(np.log(closes[s])) * 1e4)
        print(f"  {s}: {n} 1h bars, 1h ret std={ann:.1f} bps")
    for follow, name in [(False, "REVERSION (fade prior)"), (True, "MOMENTUM (follow prior)")]:
        for s in SYMBOLS:
            print(f"\n### {s} — {name} ###  revIC=corr(prev,next); net bps (t) per cost")
            print(f"  {'horizon':>8} {'revIC':>7} " + " ".join(f"c={c}bps".rjust(13) for c in COSTS_BPS))
            for label, hb in HORIZONS.items():
                base = cell(closes[s], hb, 0.0, follow)
                if base is None:
                    continue
                ic = base[0]
                cells = []
                for c in COSTS_BPS:
                    r = cell(closes[s], hb, c, follow)
                    star = "*" if (r[1] > 0 and r[2] > 2) else " "
                    cells.append(f"{r[1]:+7.2f}({r[2]:+4.1f}){star}")
                print(f"  {label:>8} {ic:+7.3f} " + " ".join(cells))
    print("\n  * = net>0 & t>2 (a needle).  revIC<0 = mean-reversion, >0 = momentum.")


if __name__ == "__main__":
    main()
