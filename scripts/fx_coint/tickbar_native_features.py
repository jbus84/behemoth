"""Tick-bar NATIVE microstructure features — clean replication-based scan.

Columns with no time-bar analogue (100tick bars, ~1min): intra_bar_momentum,
quote_revisions, hl_pos_frac, tick_burst, bar_return_sign, hl_pos_delta_tick,
high/low_pos_tick, spread, tick_volume.

Discipline (re-applied after prior scan used overlap-inflated t-stats): judge by
RAW pooled IC + PARTIAL IC (controlling short price-momentum) + >=4/5 sign +
non-overlap IC. Short wall-clock horizons (15/30/60/120 min) where microstructure
lives. No t-stat gate.

Usage: uv run python scripts/fx_coint/tickbar_native_features.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
FWD_MIN = [15, 30, 60, 120]
NATIVE = ["intra_bar_momentum", "quote_revisions", "hl_pos_frac", "tick_burst",
          "bar_return_sign", "hl_pos_delta_tick", "high_pos_tick", "low_pos_tick",
          "spread", "tick_volume"]


def build(sym: str) -> tuple[pd.DataFrame, float]:
    df = pd.read_parquet(f"{DATA}/{sym}_100tick.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    df = df.set_index(t).sort_index()
    df = df[~df.index.duplicated()]
    mid = (df["close_bid"] + df["close_ask"]) / 2
    logp = np.log(mid)
    span_h = (df.index[-1] - df.index[0]).total_seconds() / 3600
    bph = len(df) / span_h
    d = pd.DataFrame(index=df.index)
    for c in NATIVE:
        d[c] = df[c].shift(1)
    # extra engineered: |ibm| (vol proxy), signed ibm
    d["abs_ibm"] = df["intra_bar_momentum"].abs().shift(1)
    # price-momentum control (trailing 2h sum of bar returns)
    d["ctrl_mom2h"] = (logp.diff() * 1e4).rolling("2h").sum().shift(1)
    tnum = df.index.view("int64")
    v = logp.to_numpy()
    n = len(v)
    ar = np.arange(n)
    for m in FWD_MIN:
        j = np.searchsorted(tnum, tnum + int(m * 60 * 1e9), side="left")
        valid = j < n
        fwd = np.full(n, np.nan)
        fwd[valid] = (v[j[valid]] - v[ar[valid]]) * 1e4
        d[f"y{m}"] = fwd
    return d, bph


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, z)[0]
    ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den, rxz


def main() -> None:
    print("Loading 100tick bars + features ...")
    data, bph = {}, {}
    for s in POOL:
        d, b = build(s)
        data[s] = d
        bph[s] = b
    print(f"  ~{np.mean(list(bph.values())):.0f} bars/h\n")

    feats = NATIVE + ["abs_ibm"]
    rows = []
    for f in feats:
        for m in FWD_MIN:
            raws, parts, novs, ccs = [], [], [], []
            for s in POOL:
                dd = data[s][[f, "ctrl_mom2h", f"y{m}"]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(dd) < 1000 or dd[f].nunique() < 5:
                    continue
                raws.append(stats.spearmanr(dd[f], dd[f"y{m}"])[0])
                pic, cc = partial_ic(dd[f].to_numpy(), dd[f"y{m}"].to_numpy(), dd["ctrl_mom2h"].to_numpy())
                parts.append(pic)
                ccs.append(cc)
                step = max(int((m / 60) * bph[s]), 1)
                no = dd.iloc[::step]
                if len(no) > 200:
                    novs.append(stats.spearmanr(no[f], no[f"y{m}"])[0])
            if len(parts) < 5:
                continue
            parts = np.array(parts)
            pic = parts.mean()
            raw = np.mean(raws)
            sgn = int((np.sign(parts) == np.sign(pic)).sum())
            nov = np.mean(novs) if novs else np.nan
            nov_ok = np.isfinite(nov) and np.sign(nov) == np.sign(pic)
            rows.append(dict(feature=f, fwd_min=m, raw_ic=raw, partial_ic=pic,
                             corr_ctrl=np.mean(ccs), sign=f"{sgn}/5", nov_ic=nov,
                             robust=(sgn >= 4 and nov_ok and abs(pic) > 0.003)))
    res = pd.DataFrame(rows)
    res = res.reindex(res.partial_ic.abs().sort_values(ascending=False).index)
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:9.4f}")
    print("=" * 104)
    print("TICK-BAR NATIVE FEATURES (100tick) — raw + partial IC (ctrl: mom_2h) | 5/5 | non-overlap")
    print("  judged by sign-consistency + non-overlap, NOT t-stats")
    print("=" * 104)
    print(res[["feature", "fwd_min", "raw_ic", "partial_ic", "corr_ctrl", "sign", "nov_ic", "robust"]]
          .head(20).to_string(index=False))
    rob = res[res.robust]
    print(f"\nROBUST (>=4/5 sign, non-overlap same sign, |partial IC|>0.003): {len(rob)}")
    if len(rob):
        print(rob[["feature", "fwd_min", "partial_ic", "corr_ctrl", "sign", "nov_ic"]].to_string(index=False))
    print("\nContext: ffd_0.1 reversion @48h ~ -0.065. Microstructure IC ~0.005-0.008 = real but")
    print("orders of magnitude smaller; only usable as ENSEMBLE inputs, never standalone (sub-cost).")


if __name__ == "__main__":
    main()
