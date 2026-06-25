"""Does COMBINING features beat the best single feature, at the two candidate
settings — (A) 1-bar target, (B) 30-bar triple-barrier — out-of-sample?

Bounce-free (1-bar entry embargo). Per-symbol z-scored features, vol-normalized
target, pooled across the 5 ex-JPY majors. Chronological 70/30 split: fit a small
Ridge on the pooled TRAIN, evaluate IC per symbol on its TEST -> ensemble OOS IC
+ 5/5 sign, vs the best single-feature OOS IC. No look-ahead (features causal,
weights fit on train only).

Usage: uv run python scripts/fx_coint/ensemble_two_settings.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triple_barrier import triple_barrier_core  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
SUFFIX = "1000tick"
N_TB = 30
N_EVENTS = 40000
TRAIN_FRAC = 0.70
FEATS = ["ffd_0.1", "pxdev_96h", "mom_1bar", "mom_10bar", "intra_bar_mom", "hl_pos_frac"]


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


def build(sym):
    df = pd.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    logp = np.log(((df["close_bid"] + df["close_ask"]) / 2).to_numpy()[o])
    ibm = df["intra_bar_momentum"].to_numpy()[o]
    hlf = df["hl_pos_frac"].to_numpy()[o]
    n = len(logp)
    bph = n / ((t.view("int64")[o][-1] - t.view("int64")[o][0]) / 3.6e12)
    s = pd.Series(logp)
    r = s.diff().fillna(0.0)
    feats = {
        "ffd_0.1": ffd01(logp, bph),
        "pxdev_96h": ((logp - s.rolling(int(96 * bph)).mean()) / s.rolling(int(96 * bph)).std()).to_numpy(),
        "mom_1bar": (r * 1e4).to_numpy(),
        "mom_10bar": (r.rolling(10).sum() * 1e4).to_numpy(),
        "intra_bar_mom": ibm,
        "hl_pos_frac": hlf,
    }
    vol = r.ewm(span=100).std().to_numpy()
    return logp, feats, vol, bph


def zscore_cols(X):
    mu = np.nanmean(X, 0)
    sd = np.nanstd(X, 0)
    sd[sd == 0] = 1
    return (X - mu) / sd


def assemble(setting):
    """Return per-symbol (X, y, split_idx) for the chosen target setting."""
    rng = np.random.default_rng(0)
    out = {}
    for sym in POOL:
        logp, feats, vol, bph = build(sym)
        n = len(logp)
        warm = int(96 * bph) + 20
        idx = np.arange(warm, n - N_TB - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        if setting == "1bar":
            y = (logp[entry + 1] - logp[entry]) * 1e4
        else:  # tb30
            vert = np.minimum(entry + N_TB, n - 1)
            width = 1.0 * vol[entry] * np.sqrt(N_TB)
            _, y, _, _ = triple_barrier_core(logp, entry, vert, width)
        y = y / (np.nanstd(y) + 1e-9)  # vol-normalize per symbol
        X = np.column_stack([feats[f][ev] for f in FEATS])
        ok = np.isfinite(X).all(1) & np.isfinite(y)
        X, y = zscore_cols(X[ok]), y[ok]
        cut = int(len(y) * TRAIN_FRAC)
        out[sym] = (X, y, cut)
    return out


def evaluate(setting):
    data = assemble(setting)
    Xtr = np.vstack([data[s][0][:data[s][2]] for s in POOL])
    ytr = np.concatenate([data[s][1][:data[s][2]] for s in POOL])
    model = Ridge(alpha=10.0).fit(Xtr, ytr)
    # ensemble OOS IC per symbol
    ens, singles = [], {f: [] for f in FEATS}
    for s in POOL:
        X, y, cut = data[s]
        Xte, yte = X[cut:], y[cut:]
        pred = model.predict(Xte)
        ens.append(stats.spearmanr(pred, yte)[0])
        for j, f in enumerate(FEATS):
            singles[f].append(stats.spearmanr(Xte[:, j], yte)[0])
    return np.array(ens), singles, model.coef_


def main():
    print(f"Two settings on {SUFFIX}, bounce-free, OOS (chronological {int(TRAIN_FRAC*100)}/"
          f"{int((1-TRAIN_FRAC)*100)}), pooled-train Ridge -> per-symbol test IC\n")
    for setting, name in [("1bar", "A: 1-BAR target"), ("tb30", f"B: {N_TB}-BAR TRIPLE-BARRIER")]:
        ens, singles, coef = evaluate(setting)
        best_f = max(singles, key=lambda f: abs(np.mean(singles[f])))
        bs = np.array(singles[best_f])
        es = int((np.sign(ens) == np.sign(np.mean(ens))).sum())
        bss = int((np.sign(bs) == np.sign(np.mean(bs))).sum())
        print("=" * 80)
        print(name)
        print("=" * 80)
        print(f"  best single feature : {best_f:14s} OOS IC {np.mean(bs):+.4f}  {bss}/5")
        print(f"  ENSEMBLE (Ridge)    : {'':14s} OOS IC {np.mean(ens):+.4f}  {es}/5  "
              f"({'BEATS' if abs(np.mean(ens))>abs(np.mean(bs)) else 'below'} best single)")
        print("  ridge weights:", {f: round(c, 2) for f, c in zip(FEATS, coef)})
        print()


if __name__ == "__main__":
    main()
