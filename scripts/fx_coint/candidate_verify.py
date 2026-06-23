"""Verify the top engineered lag features properly (effN~1300 at 30-bar TB makes
stride-30 non-overlap too noisy; use split-half stability + OOS incremental test).

For each candidate: full partial IC vs ffd (5/5), first-half & second-half partial
IC (temporal stability), corr to ffd. Then the DECISIVE test: pooled-train Ridge
on [ffd] vs [ffd, candidate], per-symbol chronological-OOS test IC — does adding
the candidate beat ffd-alone?

Usage: uv run python scripts/fx_coint/candidate_verify.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engineered_lag_features import build  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_TB = 30
N_EVENTS = 40000
CANDIDATES = ["dev_age", "ffd_vel20", "ffd_demean50", "runlen", "already_rev20"]
TRAIN_FRAC = 0.70


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, z)[0]
    ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den


def zc(a):
    m, s = np.nanmean(a, 0), np.nanstd(a, 0)
    s = np.where(s == 0, 1, s)
    return (a - m) / s


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
        data[s] = (f, ev, y)

    print("=" * 92)
    print(f"SPLIT-HALF stability (partial IC vs ffd, target={N_TB}-bar TB)")
    print("=" * 92)
    print(f"{'feature':14s} {'full':>9s} {'sign':>5s} {'half1':>9s} {'half2':>9s} {'corr_ffd':>9s} {'stable':>7s}")
    for fn in CANDIDATES:
        full, h1, h2, cc = [], [], [], []
        for s in POOL:
            f, ev, y = data[s]
            x, z = f[fn][ev], f["ffd_0.1"][ev]
            ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            x, y2, z = x[ok], y[ok], z[ok]
            full.append(partial_ic(x, y2, z))
            m = len(x) // 2
            h1.append(partial_ic(x[:m], y2[:m], z[:m]))
            h2.append(partial_ic(x[m:], y2[m:], z[m:]))
            cc.append(stats.spearmanr(x, z)[0])
        full = np.array(full)
        sgn = int((np.sign(full) == np.sign(full.mean())).sum())
        stable = np.sign(np.mean(h1)) == np.sign(np.mean(h2)) == np.sign(full.mean())
        print(f"{fn:14s} {full.mean():9.4f} {sgn:>3d}/5 {np.mean(h1):9.4f} {np.mean(h2):9.4f} "
              f"{np.mean(cc):9.4f} {'YES' if stable else 'no':>7s}")

    print("\n" + "=" * 92)
    print(f"OOS INCREMENTAL: Ridge[ffd] vs Ridge[ffd, cand] — per-symbol test IC (chrono {int(TRAIN_FRAC*100)}/30)")
    print("=" * 92)
    # base: ffd alone
    base_cols = ["ffd_0.1"]

    def oos_ic(cols):
        Xtr, ytr, te = [], [], {}
        for s in POOL:
            f, ev, y = data[s]
            X = np.column_stack([f[c][ev] for c in cols])
            yv = y / (np.nanstd(y) + 1e-9)
            ok = np.isfinite(X).all(1) & np.isfinite(yv)
            X, yv = zc(X[ok]), yv[ok]
            cut = int(len(yv) * TRAIN_FRAC)
            Xtr.append(X[:cut])
            ytr.append(yv[:cut])
            te[s] = (X[cut:], yv[cut:])
        model = Ridge(alpha=10.0).fit(np.vstack(Xtr), np.concatenate(ytr))
        ics = [stats.spearmanr(model.predict(te[s][0]), te[s][1])[0] for s in POOL]
        return np.array(ics)

    base = oos_ic(base_cols)
    bsgn = int((np.sign(base) == np.sign(base.mean())).sum())
    print(f"  {'ffd only':22s} OOS IC {base.mean():+.4f}  {bsgn}/5")
    for fn in CANDIDATES:
        ic = oos_ic(base_cols + [fn])
        sgn = int((np.sign(ic) == np.sign(ic.mean())).sum())
        verdict = "BEATS ffd" if abs(ic.mean()) > abs(base.mean()) + 1e-4 else "no lift"
        print(f"  ffd + {fn:16s} OOS IC {ic.mean():+.4f}  {sgn}/5   {verdict}")


if __name__ == "__main__":
    main()
