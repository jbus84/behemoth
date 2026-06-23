"""dev_age as a REVERSION GATE (the engineered lag feature that works).

dev_age = bars since the ffd-deviation last changed sign (staleness of the current
deviation). It adds no LINEAR OOS lift over ffd, but it strongly CONDITIONS the
reversion: fitting ffd IC within dev_age terciles shows the 30-bar reversion edge
is ~5x stronger for OLD (stale) deviations than YOUNG (fresh) ones, 5/5.

Mechanism: a long-standing overextension is mature/exhausted -> ripe to revert; a
fresh deviation may still be developing (momentum) -> weak reversion.

Usage: uv run python scripts/fx_coint/dev_age_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engineered_lag_features import build  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_TB = 30
N_EVENTS = 40000
TERCILES = [("YOUNG (fresh dev)", 0.0, 0.33), ("MID", 0.33, 0.66), ("OLD (stale dev)", 0.66, 1.0)]


def main():
    rng = np.random.default_rng(0)
    data = {}
    for s in POOL:
        logp, f, vol, bph = build(s)
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - N_TB - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        vert = np.minimum(entry + N_TB, n - 1)
        _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(N_TB))
        data[s] = (f["ffd_0.1"][ev], f["dev_age"][ev], y)

    print(f"ffd reversion IC vs {N_TB}-bar TB, within dev_age terciles (pooled 5 ex-JPY majors)\n")
    print(f"  {'dev_age tercile':22s} {'ffd IC':>9s} {'sign':>6s}   per-symbol")
    base_all = []
    for lab, lo, hi in TERCILES:
        ics = []
        for s in POOL:
            ffd, age, y = data[s]
            ok = np.isfinite(ffd) & np.isfinite(age) & np.isfinite(y)
            ffd, age, y = ffd[ok], age[ok], y[ok]
            ql, qh = np.quantile(age, lo), np.quantile(age, hi)
            m = (age >= ql) & (age <= qh)
            if m.sum() > 500:
                ics.append(stats.spearmanr(ffd[m], y[m])[0])
        ics = np.array(ics)
        sgn = int((np.sign(ics) == np.sign(ics.mean())).sum())
        print(f"  {lab:22s} {ics.mean():9.4f} {sgn:>4d}/5   {np.round(ics, 3)}")
        if lab.startswith("OLD"):
            base_all = ics
    # unconditional reference
    unc = []
    for s in POOL:
        ffd, age, y = data[s]
        ok = np.isfinite(ffd) & np.isfinite(y)
        unc.append(stats.spearmanr(ffd[ok], y[ok])[0])
    print(f"\n  unconditional ffd IC = {np.mean(unc):+.4f}   ->  OLD-deviation gate = {np.mean(base_all):+.4f} "
          f"({np.mean(base_all)/np.mean(unc):.1f}x)")
    print("  => gate the reversion bet on STALE deviations; fresh deviations ~noise.")


if __name__ == "__main__":
    main()
