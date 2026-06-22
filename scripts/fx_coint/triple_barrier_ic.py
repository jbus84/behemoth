"""How does triple-barrier labeling change feature->label correlation, by timeframe?

For each dataset (15m time, 1000tick, 100tick), pooled over 5 ex-JPY majors:
  - features: ffd_0.1 (reversion), pxdev_96h (reversion), intra_bar_momentum
    (tick-native continuation; tick datasets only)
  - vertical barrier = 24h; symmetric horizontals = 1.0 * expected-24h-move
    (EWM bar-vol * sqrt(bars/24h))
  - compares pooled Spearman IC of each feature vs:
      FIXED  : return to the 24h vertical barrier (fixed-horizon label)
      TRIPLE : return at first barrier touch (path-dependent label)
  - reports avg holding (bars / hours), %% vertical-touched, label balance, and the
    effective-N implication (shorter holds => less overlap => more independent labels)

Usage: uv run python scripts/fx_coint/triple_barrier_ic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triple_barrier import triple_barrier, vertical_idx  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
DATASETS = {"15m_time": "15m_flow", "1000tick": "1000tick", "100tick": "100tick"}
VERT_NS = 24 * 3600 * 1_000_000_000
N_EVENTS = 15000
PTSL = 1.0


def ffd01(logp, bph):
    width = max(int(480 * bph), 50)
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (0.1 - k + 1) / k)
    w = np.array(w[::-1])
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = fftconvolve(logp, w[::-1], "valid")
    return (out - np.nanmean(out)) / np.nanstd(out)


def load(sym, suffix):
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    if "mid" in df.columns:
        mid = df["mid"].to_numpy()
        t = pd.to_datetime(df["bucket"])
        ibm = None
    else:
        mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
        t = pd.to_datetime(df["timestamp"])
        ibm = df["intra_bar_momentum"].to_numpy()
    t = pd.DatetimeIndex(t).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    return t.view("int64").astype("int64")[o], np.log(mid[o]), (ibm[o] if ibm is not None else None)


def build(sym, suffix):
    ts, logp, ibm = load(sym, suffix)
    n = len(ts)
    span_h = (ts[-1] - ts[0]) / 3.6e12
    bph = n / span_h
    s = pd.Series(logp, index=pd.DatetimeIndex(ts))
    pxdev = ((s - s.rolling("96h").mean()) / s.rolling("96h").std()).to_numpy()
    feats = {"ffd_0.1": ffd01(logp, bph), "pxdev_96h": pxdev}
    if ibm is not None:
        feats["intra_bar_mom"] = ibm
    # target vol: EWM std of bar log-returns, scaled to the 24h horizon
    r = pd.Series(np.diff(logp, prepend=logp[0]))
    vol = r.ewm(span=100).std().to_numpy()
    bars_24h = bph * 24
    width = PTSL * vol * np.sqrt(bars_24h)
    return ts, logp, feats, width, bph


def main():
    for label, suffix in DATASETS.items():
        rng = np.random.default_rng(0)
        per_feat_fixed, per_feat_triple = {}, {}
        holds, vtouch, labels = [], [], []
        feat_names = None
        for sym in POOL:
            ts, logp, feats, width, bph = build(sym, suffix)
            n = len(ts)
            warm = int(96 * bph) + 5
            ev_all = np.arange(warm, n - 1)
            ev_all = ev_all[np.isfinite(width[ev_all]) & (width[ev_all] > 0)]
            ev = np.sort(rng.choice(ev_all, min(N_EVENTS, len(ev_all)), replace=False))
            vert = vertical_idx(ts, ev, VERT_NS)
            fixed_ret = (logp[vert] - logp[ev]) * 1e4
            t1, trip_ret, hold, tc = triple_barrier(logp, ts, ev, VERT_NS, width[ev])
            holds.append(hold.mean())
            vtouch.append((tc == 0).mean())
            labels.append((np.mean(tc == 1), np.mean(tc == -1), np.mean(tc == 0)))
            feat_names = list(feats)
            for f in feats:
                fv = feats[f][ev]
                ok = np.isfinite(fv)
                per_feat_fixed.setdefault(f, []).append(stats.spearmanr(fv[ok], fixed_ret[ok])[0])
                per_feat_triple.setdefault(f, []).append(stats.spearmanr(fv[ok], trip_ret[ok])[0])
        avg_hold = np.mean(holds)
        avg_hold_h = avg_hold / np.mean([b for b in [bph]])  # bph last sym ~ representative
        print("=" * 92)
        print(f"{label}  —  vertical=24h, symmetric barriers=1.0*24h-move, {N_EVENTS} events/sym")
        print(f"  avg hold {avg_hold:.0f} bars (~{avg_hold/ bph:.1f}h)  | vertical-touched {np.mean(vtouch)*100:.0f}%  "
              f"| labels up/dn/vert = {np.mean([x[0] for x in labels]):.2f}/"
              f"{np.mean([x[1] for x in labels]):.2f}/{np.mean([x[2] for x in labels]):.2f}")
        print("=" * 92)
        print(f"  {'feature':16s} {'FIXED IC':>12s} {'sign':>6s}   {'TRIPLE IC':>12s} {'sign':>6s}   {'delta':>9s}")
        for f in feat_names:
            a = np.array(per_feat_fixed[f])
            b = np.array(per_feat_triple[f])
            sa = int((np.sign(a) == np.sign(a.mean())).sum())
            sb = int((np.sign(b) == np.sign(b.mean())).sum())
            print(f"  {f:16s} {a.mean():12.4f} {sa:>4d}/5   {b.mean():12.4f} {sb:>4d}/5   {b.mean()-a.mean():+9.4f}")
        print()


if __name__ == "__main__":
    main()
