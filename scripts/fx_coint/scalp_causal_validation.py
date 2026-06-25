"""Causal multi-year validation of the extreme-extension fade @ 15m liquid sessions.

The magnitude-band map (1yr, full-sample q95 threshold) showed the top-5% |mom_3| band fades
positive. This validates it honestly:
  - MULTI-YEAR 2018-2025 (out-of-sample across regimes),
  - CAUSAL band threshold: the q95 |mom_3| cut comes from a TRAILING window of PAST liquid
    bars only (rolling quantile, shifted) — never full-sample,
  - per-pair + pooled + ex-USDJPY, per-year, taker AND maker cost, day-block bootstrap.

Signal: in London+Overlap (07-16 UTC), when |mom_3| >= causal-q95, FADE it (pnl = -sign(mom3)*fwd).

Usage:
    uv run python scripts/fx_coint/scalp_causal_validation.py --start 2018 --end 2025
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import ttest_1samp  # noqa: E402

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    add_rolling_features,
    compute_forward_returns,
    load_raw_ticks,
)
from scripts.fx_coint.scalp_tf_probe import build_enriched  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
LIQUID = (7, 16)
MAKER_BPS = 0.20
WIN = 4000        # trailing liquid-bar window for the causal q95 threshold (~4 months)
RNG = np.random.default_rng(0)


def build_signal(sym: str, years: list[int]) -> pd.DataFrame:
    """Concat 15m bars across years; causal extreme-extension fade in liquid hours."""
    frames = []
    for y in years:
        try:
            b = build_enriched(load_raw_ticks(sym, y), sym, "15m")
        except FileNotFoundError:
            continue
        frames.append(b)
    if not frames:
        return pd.DataFrame()
    df = add_rolling_features(pd.concat(frames, ignore_index=True).sort_values("bucket"), sym)
    df = compute_forward_returns(df, [1])
    mid = df["mid"].astype(float)
    r = np.log(mid / mid.shift(1)) * 1e4
    rv = r.rolling(48, min_periods=20).std().shift(1)
    mom3 = (r.rolling(3, min_periods=2).sum() / (rv * np.sqrt(3))).shift(1)
    fwd = np.log(mid.shift(-1) / mid) * 1e4
    hr = df["bucket"].dt.hour
    d = pd.DataFrame({"absmom": mom3.abs(), "fade": -np.sign(mom3) * fwd,
                      "bucket": df["bucket"]})[(hr >= LIQUID[0]) & (hr < LIQUID[1])]
    d = d[np.isfinite(d["absmom"]) & np.isfinite(d["fade"])].reset_index(drop=True)
    # CAUSAL q95 threshold from trailing window of PAST liquid bars (shifted)
    d["thr"] = d["absmom"].rolling(WIN, min_periods=WIN // 4).quantile(0.95).shift(1)
    sel = d[(d["absmom"] >= d["thr"]) & np.isfinite(d["thr"])].copy()
    sel["year"] = sel["bucket"].dt.year
    sel["taker"] = DEFAULT_COST_BPS[sym]
    return sel


def boot_p_pos(net, bucket, n_boot=5000):
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for i in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(label, d):
    fade = d["fade"].to_numpy()
    nt = fade - d["taker"].to_numpy()
    nm = fade - MAKER_BPS
    t, _ = ttest_1samp(nt, 0)
    clo_m, chi_m = boot_p_pos(nm, d["bucket"].to_numpy())
    clo_t, chi_t = boot_p_pos(nt, d["bucket"].to_numpy())
    yr = d.groupby("year")["fade"].mean()
    yrs_pos_taker = int(((d.groupby("year").apply(lambda g: (g["fade"] - g["taker"]).mean(),
                                                  include_groups=False)) > 0).sum())
    print(f"  {label:>16} n={len(d):>5} gross={fade.mean():>+6.3f} hit={(fade>0).mean()*100:>3.0f}% "
          f"netT={nt.mean():>+6.3f} netM={nm.mean():>+6.3f} "
          f"takerCI=[{clo_t:>+5.2f},{chi_t:>+5.2f}] makerCI=[{clo_m:>+5.2f},{chi_m:>+5.2f}] "
          f"posYrT={yrs_pos_taker}/{len(yr)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2025)
    args = ap.parse_args()
    years = list(range(args.start, args.end + 1))

    print(f"CAUSAL VALIDATION — extreme-extension fade @ 15m liquid, {args.start}-{args.end}")
    print(f"  causal trailing-q95 threshold (win={WIN}); taker per-pair; maker={MAKER_BPS}\n")
    per = {}
    for sym in TIGHT:
        d = build_signal(sym, years)
        if len(d):
            per[sym] = d
            summarize(sym, d)
    if not per:
        return
    alld = pd.concat(per.values(), ignore_index=True)
    print()
    summarize("POOLED", alld)
    summarize("POOLED ex-JPY", pd.concat([per[s] for s in per if s != "USDJPY"], ignore_index=True))
    # per-year pooled net (taker)
    print("\n  per-year pooled netTaker:")
    yt = alld.groupby("year").apply(lambda g: (g["fade"] - g["taker"]).mean(), include_groups=False)
    print("   " + "  ".join(f"{int(y)}:{v:+.2f}" for y, v in yt.items()))


if __name__ == "__main__":
    main()
