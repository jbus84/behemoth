"""Stage-2 crypto perp cross-sectional flow + positioning + funding (research probe).

Verified result behind docs/analysis/2026-06-07_crypto_futures_flow_stage2_findings.md.
Combines (a) spot order-flow imbalance, (b) FREE futures positioning signals (top-trader &
global long/short, open-interest change) from Binance `metrics`, and (c) funding carry, in a
CONCENTRATED top-k/bottom-k dollar-neutral book. Holdout-2025 maker net is positive and
~significant, but regime-dependent (weak 2024) and adverse-selection-sensitive — a lead, not
a confirmed edge.

Network/data dependent; not unit-tested. Builds three cached parquets under /tmp if absent:
  /tmp/crypto_panel_ext.parquet  (spot OHLCV+OFI, 32 pairs; from the Stage-1 ext ingest)
  /tmp/fut_metrics_hourly.parquet (futures metrics, hourly)
  /tmp/funding.parquet            (funding rates, 8h)
Gotcha: Binance kline ts went microseconds in 2025 (unit-detect). Run:
  uv run python -m scripts.research.crypto_futures_flow
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

PERPS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "DOTUSDT",
         "LTCUSDT", "LINKUSDT", "AVAXUSDT", "ATOMUSDT", "ETCUSDT", "BCHUSDT", "TRXUSDT",
         "NEARUSDT", "FILUSDT", "AAVEUSDT", "ICPUSDT", "XLMUSDT"]
DAYS = pd.date_range("2024-01-01", "2025-05-31", freq="D").strftime("%Y-%m-%d").tolist()
MONTHS = ([f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 6)])
H, K = 6, 5


def _dl_zip_csv(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        zf = zipfile.ZipFile(io.BytesIO(r.read()))
    return pd.read_csv(io.BytesIO(zf.read(zf.namelist()[0])))


def ingest_metrics(path="/tmp/fut_metrics_hourly.parquet") -> None:
    base = "https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"

    def f(a):
        s, d = a
        try:
            df = _dl_zip_csv(base.format(s=s, d=d))
            df["symbol"] = s
            return df
        except Exception:
            return None
    tasks = [(s, d) for s in PERPS for d in DAYS]
    out = [r for r in cf.ThreadPoolExecutor(max_workers=24).map(f, tasks) if r is not None and len(r)]
    m = pd.concat(out, ignore_index=True)
    m["dt"] = pd.to_datetime(m["create_time"], utc=True)
    m["hour"] = m["dt"].dt.floor("h")
    m.sort_values(["symbol", "dt"]).groupby(["symbol", "hour"]).last().reset_index().to_parquet(path)


def ingest_funding(path="/tmp/funding.parquet") -> None:
    base = "https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{mo}.zip"

    def f(a):
        s, mo = a
        try:
            df = _dl_zip_csv(base.format(s=s, mo=mo))
            df["symbol"] = s
            return df
        except Exception:
            return None
    tasks = [(s, mo) for s in PERPS for mo in MONTHS]
    out = [r for r in cf.ThreadPoolExecutor(max_workers=16).map(f, tasks) if r is not None and len(r)]
    pd.concat(out, ignore_index=True).to_parquet(path)


def load() -> pd.DataFrame:
    if not os.path.exists("/tmp/fut_metrics_hourly.parquet"):
        ingest_metrics()
    if not os.path.exists("/tmp/funding.parquet"):
        ingest_funding()
    h = pd.read_parquet("/tmp/fut_metrics_hourly.parquet").sort_values(["symbol", "hour"])
    sp = pd.read_parquet("/tmp/crypto_panel_ext.parquet")  # built by crypto_flow_xs ext ingest
    ts = sp["ts"].astype("int64")
    sp["dt"] = pd.to_datetime(np.where(ts < 100_000_000_000_000, ts * 1_000_000, ts * 1000), utc=True)
    sp = sp[(sp["dt"] >= "2024-01-01") & (sp["dt"] < "2025-06-01")].sort_values(["symbol", "dt"])
    g = sp.groupby("symbol", group_keys=False)
    sp["ofi_ma6"] = g["ofi"].transform(lambda x: x.rolling(6, min_periods=3).mean())
    spx = sp[["dt", "symbol", "close", "ofi_ma6"]].rename(columns={"dt": "hour"})
    h["oi_chg6"] = h.groupby("symbol")["sum_open_interest"].transform(
        lambda x: pd.to_numeric(x, errors="coerce") / pd.to_numeric(x, errors="coerce").shift(6) - 1)
    h["tt_ls"] = np.log(pd.to_numeric(h["sum_toptrader_long_short_ratio"], errors="coerce").clip(1e-3))
    h["gl_ls"] = np.log(pd.to_numeric(h["count_long_short_ratio"], errors="coerce").clip(1e-3))
    df = h.merge(spx, on=["symbol", "hour"], how="inner").sort_values(["symbol", "hour"])
    df["fwd"] = df.groupby("symbol", group_keys=False)["close"].transform(lambda x: x.shift(-H) / x - 1)
    df["year"] = df["hour"].dt.year
    # funding ffilled to hourly
    fd = pd.read_parquet("/tmp/funding.parquet")
    fd["hour"] = pd.to_datetime(fd["calc_time"], unit="ms", utc=True).dt.floor("h")
    fd = fd[["symbol", "hour", "last_funding_rate"]].rename(columns={"last_funding_rate": "fund8h"})
    grid = pd.date_range(df["hour"].min(), df["hour"].max(), freq="h", tz="UTC")
    parts = []
    for s, gg in fd.groupby("symbol"):
        m = pd.DataFrame({"hour": grid}).merge(gg.sort_values("hour"), on="hour", how="left")
        m["symbol"] = s
        m["fund8h"] = m["fund8h"].ffill()
        parts.append(m)
    return df.merge(pd.concat(parts, ignore_index=True)[["symbol", "hour", "fund8h"]],
                    on=["symbol", "hour"], how="left")


def _xsz(w):
    return (w.sub(w.mean(axis=1), axis=0)).div(w.std(axis=1) + 1e-12, axis=0)


def backtest(df: pd.DataFrame, use_fund_signal: bool):
    cols = [("ofi_ma6", 1), ("tt_ls", -1), ("gl_ls", -1), ("oi_chg6", 1)]
    if use_fund_signal:
        cols.append(("fund8h", -1))
    z = None
    for c, s in cols:
        zc = _xsz(df.pivot(index="hour", columns="symbol", values=c)) * s
        z = zc if z is None else z.add(zc, fill_value=0)
    f = df.pivot(index="hour", columns="symbol", values="fwd")
    fu = df.pivot(index="hour", columns="symbol", values="fund8h")
    z = z.reindex(index=f.index, columns=f.columns)
    fu = fu.reindex(index=f.index, columns=f.columns)
    za, fa, fua = z.to_numpy(), f.to_numpy(), fu.to_numpy()
    n = len(f.index)
    prev = np.zeros(z.shape[1])
    gross, fpnl, turn, dates = [], [], [], []
    for ti in range(0, n - H, H):
        s = za[ti]
        fin = np.isfinite(s) & np.isfinite(fa[ti])
        valid = np.where(fin)[0]
        if len(valid) < 2 * K:
            continue
        order = valid[np.argsort(s[valid])]
        w = np.zeros(len(s))
        w[order[-K:]] = 1.0 / K
        w[order[:K]] = -1.0 / K
        gross.append(float((w * np.nan_to_num(fa[ti])).sum()))
        fpnl.append(float((-w * np.nan_to_num(fua[ti]) / 8.0 * H).sum()))  # carry over H hours
        turn.append(float(np.abs(w - prev).sum()))
        dates.append(f.index[ti])
        prev = w
    return np.array(gross), np.array(fpnl), np.array(turn), pd.DatetimeIndex(dates)


def _metrics(net, dates):
    t = net.mean() / (net.std(ddof=1) / np.sqrt(len(net)) + 1e-12)
    mo = pd.Series(net, index=dates).groupby(dates.to_period("M")).sum()
    return net.mean() * 1e4, float(t), float((mo > 0).mean())


def main() -> None:
    df = load()
    splits = {"V1_2024a": (df["year"] == 2024) & (df["hour"] < "2024-07-01"),
              "HOLDOUT_2025": df["year"] == 2025}
    for lbl, mask in splits.items():
        for variant, sig, addfp in [("base", False, False), ("+fundPnL", False, True),
                                     ("+fundSig+PnL", True, True)]:
            g, fp, tu, d = backtest(df[mask], sig)
            for fee, adv, nm in [(5, 0, "taker"), (2, 0, "maker0"), (2, 0.5, "maker.5")]:
                net = g * (1 - adv) + (fp if addfp else 0) - tu * fee / 1e4
                mean, t, posm = _metrics(net, d)
                print(f"{lbl:13s} {variant:13s} {nm:7s} gross={g.mean()*1e4:+.2f} "
                      f"fundPnL={fp.mean()*1e4:+.2f} net={mean:+.2f} t={t:+.2f} posM={posm:.0%}")


if __name__ == "__main__":
    main()
