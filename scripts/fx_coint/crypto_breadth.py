"""Multi-coin breadth test: are the crypto candidates laws or single-asset luck?

Tests two signals across ~18 liquid coins, NON-OVERLAPPING trades, realistic cost:
  A) 12h momentum CONTINUATION on top-decile |6h momentum| (the marginal ETH needle)
  B) extreme-spike REVERSAL on top-1% |6h momentum|, 3h fade (the robust tail finding)

Per coin: mean net bps, t, N. Breadth: fraction of coins net-positive + sign agreement.
A real edge holds across most coins (caveat: coins co-move, so breadth is partly shared).

Usage:  uv run python scripts/fx_coint/crypto_breadth.py
"""
# ruff: noqa: E402
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT",
           "DOGEUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "ATOMUSDT",
           "TRXUSDT", "ETCUSDT", "XLMUSDT", "BCHUSDT", "EOSUSDT", "UNIUSDT"]
START_MS = int(pd.Timestamp("2018-01-01").timestamp() * 1000)
L, H_CONT, H_REV, COST = 6, 12, 3, 10.0


def fetch_1h(sym):
    cache = Path(f"/tmp/{sym}_1h_klines.parquet")
    if cache.exists():
        return pd.read_parquet(cache)["close"].to_numpy(dtype=np.float64)
    rows, start = [], START_MS
    url = "https://api.binance.com/api/v3/klines"
    try:
        while True:
            q = f"{url}?symbol={sym}&interval=1h&startTime={start}&limit=1000"
            data = json.loads(urllib.request.urlopen(q, timeout=30).read())
            if not data:
                break
            rows += data
            start = data[-1][0] + 3_600_000
            if len(data) < 1000:
                break
            time.sleep(0.12)
    except Exception as e:
        print(f"  {sym}: fetch failed {e}")
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows).iloc[:, [0, 4]]
    df.columns = ["open_ms", "close"]
    df["close"] = df["close"].astype(float)
    df.to_parquet(cache)
    print(f"  {sym}: {len(df)} bars", flush=True)
    return df["close"].to_numpy(dtype=np.float64)


def nonoverlap(idx, gap):
    picked, last = [], -10**9
    for i in idx:
        if i - last >= gap:
            picked.append(i)
            last = i
    return np.array(picked)


def signal_trades(close, pct, hold, fade):
    r = np.empty(len(close)); r[0] = np.nan
    r[1:] = np.diff(np.log(close)) * 1e4
    mom = pd.Series(r).rolling(L).sum().to_numpy()
    sgn = np.sign(mom); strength = np.abs(mom)
    fwd = pd.Series(r).rolling(hold).sum().shift(-(hold + 1)).to_numpy()
    pos = (-sgn if fade else sgn)
    pnl = pos * fwd
    valid = np.isfinite(strength) & np.isfinite(pnl) & (sgn != 0)
    thr = np.nanquantile(strength[valid], 1 - pct / 100)
    idx = np.where(valid & (strength >= thr))[0]
    idx = nonoverlap(idx, hold)
    v = pnl[idx]
    return v[np.isfinite(v)]


def run(name, pct, hold, fade):
    print(f"\n### {name}  (top {pct}% |mom|, hold {hold}h, "
          f"{'FADE' if fade else 'FOLLOW'}, non-overlap, cost {COST}bps) ###")
    print(f"  {'coin':>8} {'netMean':>8} {'t':>5} {'N':>5}")
    means = []
    for s in SYMBOLS:
        c = CLOSES.get(s)
        if c is None or len(c) < 3000:
            continue
        v = signal_trades(c, pct, hold, fade) - COST
        if len(v) < 30:
            continue
        t = v.mean() / (v.std() + 1e-12) * np.sqrt(len(v))
        means.append(v.mean())
        print(f"  {s:>8} {v.mean():+8.2f} {t:+5.1f} {len(v):>5}")
    means = np.array(means)
    pos = (means > 0).mean() * 100
    bt = means.mean() / (means.std(ddof=1) + 1e-12) * np.sqrt(len(means))
    print(f"  BREADTH: {len(means)} coins, {pos:.0f}% net-positive, "
          f"mean={means.mean():+.2f}bps, cross-coin t={bt:+.1f}")
    print(f"  VERDICT: {'LAW (broad + positive)' if pos >= 70 and bt > 2 else 'NOT broad — single-asset/regime'}")


CLOSES = {}


def main():
    print("=== CRYPTO BREADTH TEST ===")
    for s in SYMBOLS:
        CLOSES[s] = fetch_1h(s)
    run("A: 12h MOMENTUM CONTINUATION", 10, H_CONT, fade=False)
    run("A2: top-5% continuation", 5, H_CONT, fade=False)
    run("B: EXTREME-SPIKE REVERSAL", 1, H_REV, fade=True)
    run("B2: top-0.5% reversal", 0.5, H_REV, fade=True)


if __name__ == "__main__":
    main()
