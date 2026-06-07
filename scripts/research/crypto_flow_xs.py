"""Stage-1 crypto cross-sectional order-flow validation (research probe).

Tests whether public crypto order-flow imbalance (from free Binance kline taker_buy_volume)
predicts cross-sectional forward returns, net of fees. Findings:
docs/analysis/2026-06-07_crypto_flow_xs_findings.md.

NOTE: network/exchange-data dependent; not part of the app and not unit-tested. Run with
`uv run python -m scripts.research.crypto_flow_xs`.

Key gotcha: Binance switched kline timestamps to MICROSECONDS in 2025; unit-detect or 2025
data silently drops (parses to year ~57385).
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import urllib.request
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "DOTUSDT",
        "LTCUSDT", "LINKUSDT", "AVAXUSDT", "ATOMUSDT", "ETCUSDT", "BCHUSDT", "TRXUSDT", "MATICUSDT"]
MONTHS = ([f"{y}-{m:02d}" for y in (2022, 2023, 2024) for m in range(1, 13)]
          + [f"2025-{m:02d}" for m in range(1, 6)])
BASE = "https://data.binance.vision/data/spot/monthly/klines/{s}/1h/{s}-1h-{mo}.zip"
CACHE = "/tmp/crypto_panel.parquet"


def _fetch(args: tuple[str, str]) -> pd.DataFrame | None:
    s, mo = args
    try:
        with urllib.request.urlopen(BASE.format(s=s, mo=mo), timeout=30) as r:
            zf = zipfile.ZipFile(io.BytesIO(r.read()))
        df = pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])), header=None,
                         usecols=[0, 4, 5, 9], names=["ts", "close", "vol", "tbv"])
        df = df[pd.to_numeric(df["ts"], errors="coerce").notna()].copy()
        for c in ["ts", "close", "vol", "tbv"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["symbol"] = s
        return df
    except Exception:
        return None


def ingest() -> pd.DataFrame:
    """Download + parse all klines into a tidy panel with order-flow imbalance."""
    tasks = [(s, mo) for s in SYMS for mo in MONTHS]
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        out = [r for r in ex.map(_fetch, tasks) if r is not None and len(r)]
    p = pd.concat(out, ignore_index=True)
    ts = p["ts"].astype("int64")
    # ms (<=2024, ~1.7e12) vs microseconds (2025+, ~1.7e15) -> nanoseconds
    p["dt"] = pd.to_datetime(np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True)
    p["ofi"] = (2 * p["tbv"] - p["vol"]) / p["vol"].replace(0, np.nan)
    p = p.sort_values(["symbol", "dt"]).reset_index(drop=True)
    p.to_parquet(CACHE)
    return p


def _features(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby("symbol", group_keys=False)
    p["flow"] = g["ofi"].transform(lambda x: x.rolling(6, min_periods=3).mean())
    p["flow24"] = g["ofi"].transform(lambda x: x.rolling(24, min_periods=8).mean())
    p["rev3"] = -(g["close"].transform(lambda x: x / x.shift(3) - 1))
    return p


def _xsz(w: pd.DataFrame) -> pd.DataFrame:
    return (w.sub(w.mean(axis=1), axis=0)).div(w.std(axis=1) + 1e-12, axis=0)


def ic(p: pd.DataFrame, sig: str, h: int, years: tuple[int, ...]) -> tuple[float, float, int]:
    """Mean cross-sectional Spearman IC of signal vs forward h-return + t-stat."""
    close = p.pivot(index="dt", columns="symbol", values="close")
    fwd = close.shift(-h) / close - 1
    sig_w = _xsz(p.pivot(index="dt", columns="symbol", values=sig))
    idx = sig_w.index[sig_w.index.year.isin(years)]
    vals = []
    for t in idx:
        s, f = sig_w.loc[t], fwd.loc[t]
        ok = s.notna() & f.notna()
        if ok.sum() >= 6:
            c = spearmanr(s[ok], f[ok]).correlation
            if np.isfinite(c):
                vals.append(c)
    v = np.array(vals)
    if len(v) < 3:
        return float("nan"), float("nan"), len(v)
    return float(v.mean()), float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)) + 1e-12)), len(v)


def longshort(p: pd.DataFrame, sig: str, h: int, k: int, fee_bps: float,
              years: tuple[int, ...]) -> dict | None:
    """Dollar-neutral long-top-k/short-bottom-k net P&L (bps/rebalance) after taker fee."""
    close = p.pivot(index="dt", columns="symbol", values="close")
    fwd = close.shift(-h) / close - 1
    sig_w = p.pivot(index="dt", columns="symbol", values=sig)
    idx = sig_w.index[sig_w.index.year.isin(years)][::h]
    fee = fee_bps / 1e4
    prevw = pd.Series(0.0, index=sig_w.columns)
    gross, cost = [], []
    for t in idx:
        s = sig_w.loc[t].dropna()
        f = fwd.loc[t]
        s = s.reindex(s.index[f.reindex(s.index).notna()])
        if len(s) < 2 * k:
            continue
        o = s.sort_values()
        w = pd.Series(0.0, index=sig_w.columns)
        w[o.index[:k]] = -1.0 / k
        w[o.index[-k:]] = 1.0 / k
        gross.append(float((w * fwd.loc[t].reindex(w.index).fillna(0)).sum()))
        cost.append((w - prevw).abs().sum() * fee)
        prevw = w
    g_arr, c_arr = np.array(gross), np.array(cost)
    net = g_arr - c_arr
    if len(net) < 5:
        return None
    t = net.mean() / (net.std(ddof=1) / np.sqrt(len(net)) + 1e-12)
    return {"n": len(net), "gross": g_arr.mean() * 1e4, "cost": c_arr.mean() * 1e4,
            "net": net.mean() * 1e4, "t": float(t)}


def main() -> None:
    import os
    p = pd.read_parquet(CACHE) if os.path.exists(CACHE) else ingest()
    # re-derive dt from raw ts (unit-detect) so a stale cache can't drop 2025
    ts = p["ts"].astype("int64")
    p["dt"] = pd.to_datetime(np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True)
    p = p[(p["dt"] >= "2022-01-01") & (p["dt"] < "2025-06-01")]
    p = _features(p.sort_values(["symbol", "dt"]))
    trainval = (2022, 2023, 2024)
    print("IC (train+val) | IC (holdout 2025):")
    for sig in ("flow", "flow24", "rev3"):
        for h in (1, 6, 24):
            a = ic(p, sig, h, trainval)
            b = ic(p, sig, h, (2025,))
            print(f"  {sig:7s} h{h:<2d}  tv={a[0]:+.4f}(t{a[1]:+.1f})  ho={b[0]:+.4f}(t{b[1]:+.1f})")
    print("\nLong/short net bps (train+val):")
    for sig in ("flow", "flow24", "rev3"):
        for h in (6, 24):
            for fee in (7.5, 1.0):
                r = longshort(p, sig, h, 3, fee, trainval)
                if r:
                    print(f"  {sig:7s} h{h:<2d} fee{fee}: net={r['net']:+.2f} t={r['t']:+.2f}")


if __name__ == "__main__":
    main()
