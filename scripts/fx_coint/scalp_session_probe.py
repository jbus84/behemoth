"""Session-conditioned CLASSIFICATION scalp @ 15m H1 — can time-of-day lift the
large-move-tail hit toward the ~56% breakeven?

Family-D RidgeClassifier (sign target) was more favourable than regression at 15m H1.
Here we take its confident-prediction tail (top |decision_function| at P90/95/99) and break
hit-rate + net down BY SESSION (UTC hour buckets), pooled across tight majors. Breakeven
hit on the P90 tail is ~56% (mean tail move ~5.5 bps vs ~0.7 cost); we look for any session
that clears it.

Usage:
    uv run python scripts/fx_coint/scalp_session_probe.py --year 2024 --freq 15m
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

from scripts.fx_coint.phase0_family_d import build_microstructure_classifier  # noqa: E402
from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    add_rolling_features,
    compute_forward_returns,
    load_raw_ticks,
)
from scripts.fx_coint.scalp_tf_probe import build_enriched  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
# UTC sessions
SESSIONS = {"Asia(0-7)": (0, 7), "London(7-13)": (7, 13),
            "Overlap(13-16)": (13, 16), "NY(16-21)": (16, 21), "Late(21-24)": (21, 24)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--freq", default="15m")
    ap.add_argument("--quantiles", nargs="+", type=float, default=[0.90, 0.95, 0.99])
    args = ap.parse_args()

    # collect tail trades across pairs: dict q -> DataFrame(net, gross, hour, hit)
    rows = {q: [] for q in args.quantiles}
    for sym in TIGHT:
        cf = DEFAULT_COST_BPS[sym] / 10_000
        df = add_rolling_features(build_enriched(load_raw_ticks(sym, args.year), sym, args.freq), sym)
        df = compute_forward_returns(df, [1])
        sig = build_microstructure_classifier(df, np.sign(df["fwd_ret_1"].to_numpy()))
        fwd = df["fwd_ret_1"].to_numpy()
        hour = df["hour_utc"].to_numpy()
        v = np.isfinite(sig) & np.isfinite(fwd)
        s, f, h = sig[v], fwd[v], hour[v]
        for q in args.quantiles:
            sel = np.abs(s) >= np.quantile(np.abs(s), q)
            gross = np.sign(s[sel]) * f[sel]
            rows[q].append(pd.DataFrame({"gross": gross, "net": gross - cf, "hour": h[sel]}))

    print(f"SESSION-conditioned classifier tail @ {args.freq} H1, pooled tight majors, {args.year}")
    print("  breakeven hit on P90 tail ~56%; net in bps\n")
    for q in args.quantiles:
        d = pd.concat(rows[q], ignore_index=True)
        print(f"--- P{int(q*100)} tail (n={len(d)}, overall hit {(d['gross']>0).mean()*100:.0f}%, "
              f"net {d['net'].mean()*1e4:+.3f}) ---")
        print(f"  {'session':>16} {'n':>5} {'hit':>5} {'grossBps':>9} {'netBps':>8} {'netFadeBps':>10}")
        for name, (lo, hi) in SESSIONS.items():
            g = d[(d["hour"] >= lo) & (d["hour"] < hi)]
            if len(g) < 20:
                continue
            hit = (g["gross"] > 0).mean() * 100
            gb = g["gross"].mean() * 1e4
            flag = "  <<<" if g["net"].mean() > 0 else ("  <fade" if (-g["gross"].mean()*1e4 - 0.7) > 0 else "")
            print(f"  {name:>16} {len(g):>5} {hit:>4.0f}% {gb:>9.3f} {g['net'].mean()*1e4:>8.3f} "
                  f"{(-g['gross']).mean()*1e4 - 0.7:>10.3f}{flag}")
        print()


if __name__ == "__main__":
    main()
