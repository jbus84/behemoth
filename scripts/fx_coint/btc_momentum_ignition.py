"""Selective short-term momentum: do STRONG recent moves continue, net of cost?

Every-bar crypto momentum loses at short horizons (cost squeeze). Test the selective
version: condition on an ex-ante signal (recent-momentum strength |sum last L returns|,
or vol expansion), stratify bars into deciles, and within each decile follow the move
(enter t+1 in the momentum direction, hold H) net of cost. A needle = a top decile whose
continuation clears cost with t>2.

Uses cached BTC/ETH 1h closes (btc_horizon_frontier fetch). Causal: signal at t uses
only past returns; trade t+1..t+1+H.

Usage:  uv run python scripts/fx_coint/btc_momentum_ignition.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
L = 6          # momentum lookback (hours)
HOLDS = [1, 3, 6]
COSTS = [2, 10]


def load_close(sym):
    p = Path(f"/tmp/{sym}_1h_klines.parquet")
    return pd.read_parquet(p)["close"].to_numpy(dtype=np.float64)


def deciles(x):
    q = pd.qcut(pd.Series(x).rank(method="first"), 10, labels=False)
    return q.to_numpy()


def main():
    print("=== SELECTIVE SHORT-TERM MOMENTUM (crypto 1h): do strong moves continue? ===")
    print(f"    signal = |sum last {L}h returns| (momentum strength); follow direction.\n")
    for sym in SYMBOLS:
        c = load_close(sym)
        r = np.empty(len(c)); r[0] = np.nan
        r[1:] = np.diff(np.log(c)) * 1e4
        n = len(r)
        # causal momentum signal at t: sum of returns over [t-L+1, t]
        mom = pd.Series(r).rolling(L).sum().to_numpy()
        sgn = np.sign(mom)
        strength = np.abs(mom)
        for H in HOLDS:
            # forward H-bar continuation from t+1: sum r[t+2 .. t+1+H]
            fwd = pd.Series(r).rolling(H).sum().shift(-(H + 1)).to_numpy()  # sum r[t+2..t+1+H]
            cont = sgn * fwd  # sign-aligned to recent momentum
            valid = np.isfinite(strength) & np.isfinite(cont) & (sgn != 0)
            s, contv = strength[valid], cont[valid]
            dq = deciles(s)
            print(f"  {sym}  H={H}h   decile of momentum strength -> mean continuation (bps), t, net@cost")
            for d in [0, 4, 8, 9]:  # low, mid, high, top
                m = dq == d
                v = contv[m]
                if len(v) < 50:
                    continue
                t = v.mean() / (v.std() + 1e-12) * np.sqrt(len(v))
                nets = "  ".join(f"net@{c}={v.mean()-c:+.2f}" for c in COSTS)
                tag = ""
                for cc in COSTS:
                    tt = (v - cc).mean() / (v.std() + 1e-12) * np.sqrt(len(v))
                    if (v.mean() - cc) > 0 and tt > 2:
                        tag = " *NEEDLE*"
                print(f"     d{d:<2} contMean={v.mean():+7.2f} t={t:+5.1f} n={len(v):>6}  {nets}{tag}")
            print()


if __name__ == "__main__":
    main()
