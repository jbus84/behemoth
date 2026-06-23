"""Demonstrate AFML ch.4 sample weights on the FX 48h reversion label.

Quantifies label overlap (the reason our earlier non-overlap discipline mattered)
and shows weighting in action across TIME bars (15m, 1h) and TICK bars (1000tick):

  1. per-dataset uniqueness / effective-N (how many INDEPENDENT samples we really
     have at a 48h horizon)
  2. sequential vs standard bootstrap (uniqueness gain)
  3. weighted vs unweighted IC for ffd_0.1 (does down-weighting redundant,
     overlapping labels change the estimate?)

Usage: uv run python scripts/fx_coint/sample_weights_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_weights import (  # noqa: E402
    average_uniqueness,
    concurrency,
    label_end_idx,
    return_attribution_weights,
    seq_bootstrap,
    time_decay,
)

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
DATASETS = {"15m_time": "15m_flow", "1h_time": "1h_flow", "1000tick": "1000tick"}
H_NS = 48 * 3600 * 1_000_000_000  # 48h


def load(sym: str, suffix: str) -> tuple[np.ndarray, np.ndarray, float]:
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    if "mid" in df.columns:
        mid = df["mid"].to_numpy()
        t = pd.to_datetime(df["bucket"])
    else:
        mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
        t = pd.to_datetime(df["timestamp"])
    t = pd.DatetimeIndex(t).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    t = t[o]
    mid = mid[o]
    ts = t.view("int64").astype("int64")
    span_h = (ts[-1] - ts[0]) / 3.6e12
    return ts, np.log(mid), len(ts) / span_h


def ffd01(logp: np.ndarray, bph: float) -> np.ndarray:
    width = max(int(480 * bph), 50)
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (0.1 - k + 1) / k)
    w = np.array(w[::-1])
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = fftconvolve(logp, w[::-1], "valid")
    return (out - np.nanmean(out)) / np.nanstd(out)


def w_spearman(x, y, w):
    rx = stats.rankdata(x)
    ry = stats.rankdata(y)
    sw = w.sum()
    mx = (w * rx).sum() / sw
    my = (w * ry).sum() / sw
    cov = (w * (rx - mx) * (ry - my)).sum() / sw
    vx = (w * (rx - mx) ** 2).sum() / sw
    vy = (w * (ry - my) ** 2).sum() / sw
    return cov / np.sqrt(vx * vy)


def main() -> None:
    print("=" * 92)
    print("1. LABEL OVERLAP at 48h — uniqueness & EFFECTIVE sample size (5 majors)")
    print("=" * 92)
    print(f"{'dataset':10s} {'sym':7s} {'raw N':>9s} {'mean conc':>10s} {'mean uniq':>10s} {'eff N':>9s} {'eff/raw':>8s}")
    cache = {}
    for label, suffix in DATASETS.items():
        for s in POOL:
            ts, logp, bph = load(s, suffix)
            n = len(ts)
            e = label_end_idx(ts, H_NS)
            start = np.arange(n)
            valid = e > start
            co = concurrency(n, e)
            u = average_uniqueness(start, e, co)
            effN = u[valid].sum()
            cache[(label, s)] = (ts, logp, bph, e, start, co, u, valid)
            print(f"{label:10s} {s:7s} {valid.sum():9,d} {co.mean():10.1f} "
                  f"{u[valid].mean():10.4f} {effN:9.1f} {effN/valid.sum():8.4f}")
        print()

    print("=" * 92)
    print("2. SEQUENTIAL vs STANDARD bootstrap — avg uniqueness of the drawn sample")
    print("   (EURUSD 1000tick, 800-label random subsample)")
    print("=" * 92)
    ts, logp, bph, e, start, co, u, valid = cache[("1000tick", "EURUSD")]
    rng = np.random.default_rng(0)
    vidx = np.where(valid)[0]
    sub = np.sort(rng.choice(vidx, 800, replace=False))
    s_sub, e_sub = sub, e[sub]
    lo = int(s_sub.min())
    spans = [(int(a) - lo, int(b) - lo) for a, b in zip(s_sub, e_sub)]

    def drawn_avg_uniqueness(draws: np.ndarray) -> float:
        cover = np.zeros(int(e_sub.max()) - lo + 2)
        for d in draws:
            a, b = spans[d]
            cover[a:b + 1] += 1.0
        vals = [np.mean(1.0 / cover[a:b + 1]) for a, b in (spans[d] for d in draws)]
        return float(np.mean(vals))

    std_draw = rng.choice(len(sub), len(sub), replace=True)
    seq_draw = seq_bootstrap(s_sub, e_sub, n_draws=len(sub), rng=rng)
    print(f"  standard bootstrap  : mean avg-uniqueness of draws = {drawn_avg_uniqueness(std_draw):.4f}")
    print(f"  sequential bootstrap: mean avg-uniqueness of draws = {drawn_avg_uniqueness(seq_draw):.4f}  (higher = less overlap)")

    print("\n" + "=" * 92)
    print("3. WEIGHTED vs UNWEIGHTED IC — ffd_0.1 -> 48h return (per symbol, 1000tick)")
    print("   weights = return-attribution x time-decay(last_w=0.5)")
    print("=" * 92)
    print(f"{'sym':7s} {'unweighted IC':>14s} {'weighted IC':>13s} {'sign(flip?)':>12s}")
    for s in POOL:
        ts, logp, bph, e, start, co, u, valid = cache[("1000tick", s)]
        feat = ffd01(logp, bph)
        fwd = np.full(len(logp), np.nan)
        fwd[valid] = (logp[e[valid]] - logp[valid]) * 1e4
        ok = valid & np.isfinite(feat) & np.isfinite(fwd)
        ret = np.diff(logp, prepend=logp[0]) * 1e4
        w_attr = return_attribution_weights(ret, start, e, co)
        w_td = time_decay(u, last_w=0.5)
        w = (w_attr * w_td)
        x, y, ww = feat[ok], fwd[ok], w[ok]
        ic_u = stats.spearmanr(x, y)[0]
        ic_w = w_spearman(x, y, ww)
        flip = "same" if np.sign(ic_u) == np.sign(ic_w) else "FLIP"
        print(f"{s:7s} {ic_u:14.4f} {ic_w:13.4f} {flip:>12s}")

    print("\nInterpretation: eff/raw ~ how few INDEPENDENT 48h labels exist; weighting")
    print("down-weights redundant overlapping labels and emphasises high-|return|, recent ones.")


if __name__ == "__main__":
    main()
