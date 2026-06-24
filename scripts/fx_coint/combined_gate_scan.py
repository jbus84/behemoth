"""Do the two OOS-robust reversion gates COMPOUND?

reversion_gate_scan found two conceptually-orthogonal gates on the ffd reversion
signal: dev_age HIGH (stale deviation) and adf_sup LOW (non-explosive structure).
This tests their interaction: ffd reversion IC within the 3x3 grid of
dev_age-tercile x adf_sup-tercile, OOS (thresholds fit on train), N=30/50, pooled
5 ex-JPY majors. If the gates compound, the (stale, non-explosive) corner cell
beats both single-gate terciles.

This is the empirical case for (or against) feeding a dev_age x adf_sup interaction
to the model (cf. interaction_test's ffd x dev_age term).

Usage: uv run python scripts/fx_coint/combined_gate_scan.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [1, 5, 10, 20, 30, 50]
N_EVENTS = 40000
TRAIN_FRAC = 0.70
BASE = "ffd_0.1"
GA, GB = "dev_age", "adf_sup"          # row gate, col gate
QS = [0.0, 0.34, 0.67, 1.0]            # tercile edges
ROW_LAB = ["dev_age T1", "dev_age T2", "dev_age T3(stale)"]
COL_LAB = ["adf T1(stable)", "adf T2", "adf T3(explosive)"]
OUT = Path("reports/combined_gate_scan")


def _cell_ic(base, ga, gb, y, ra, rb, ta, tb):
    """ffd->y IC for events in dev_age tercile `ra` and adf_sup tercile `rb`."""
    ma = (ga >= ta[ra]) & (ga <= ta[ra + 1])
    mb = (gb >= tb[rb]) & (gb <= tb[rb + 1])
    m = ma & mb & np.isfinite(base) & np.isfinite(y)
    return stats.spearmanr(base[m], y[m])[0] if m.sum() > 150 else np.nan


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(N_GRID) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    for n_tb in N_GRID:
        cells = np.full((5, 3, 3), np.nan)   # [sym, row, col]
        unc = []
        for si, s in enumerate(POOL):
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            entry = ev + 1
            vert = np.minimum(entry + n_tb, len(logp) - 1)
            _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
            base, ga, gb = f[BASE][ev], f[GA][ev], f[GB][ev]
            cut = int(len(ev) * TRAIN_FRAC)
            ta = np.nanquantile(ga[:cut], QS)            # thresholds on train only
            tb = np.nanquantile(gb[:cut], QS)
            bt, gat, gbt, yt = base[cut:], ga[cut:], gb[cut:], y[cut:]   # OOS slice
            oku = np.isfinite(bt) & np.isfinite(yt)
            unc.append(stats.spearmanr(bt[oku], yt[oku])[0])
            for ra in range(3):
                for rb in range(3):
                    cells[si, ra, rb] = _cell_ic(bt, gat, gbt, yt, ra, rb, ta, tb)
        grid = np.nanmean(cells, axis=0)                 # pooled OOS IC per cell
        sign = (np.sign(cells) == np.sign(grid)[None]).sum(axis=0)
        unc_m = float(np.nanmean(unc))

        print("=" * 88)
        print(f"COMBINED GATE (dev_age x adf_sup) — OOS ffd reversion IC per cell | N={n_tb}")
        print(f"  pooled 5 ex-JPY majors | unconditional OOS IC = {unc_m:+.4f} | reversion is NEGATIVE")
        print("=" * 88)
        hdr = "  " + " " * 20 + "".join(f"{c:>20s}" for c in COL_LAB)
        print(hdr)
        for ra in range(3):
            row = f"  {ROW_LAB[ra]:20s}"
            for rb in range(3):
                row += f"{grid[ra, rb]:+.4f}({int(sign[ra, rb])}/5)".rjust(20)
            print(row)
        corner = grid[2, 0]
        print(f"\n  corner (stale & stable) = {corner:+.4f}  ({corner / unc_m:.2f}x unconditional, "
              f"{int(sign[2, 0])}/5)")
        print(f"  vs single gates: dev_age T3 any-adf = {np.nanmean(grid[2, :]):+.4f}  "
              f"| adf T1 any-dev = {np.nanmean(grid[:, 0]):+.4f}")

        fig, ax = plt.subplots(figsize=(6.5, 5))
        vmax = np.nanmax(np.abs(grid))
        im = ax.imshow(grid, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        ax.set_xticks(range(3))
        ax.set_xticklabels(COL_LAB, rotation=20, fontsize=8)
        ax.set_yticks(range(3))
        ax.set_yticklabels(ROW_LAB, fontsize=8)
        for ra in range(3):
            for rb in range(3):
                ax.text(rb, ra, f"{grid[ra, rb]:+.4f}\n{int(sign[ra, rb])}/5",
                        ha="center", va="center", fontsize=9)
        ax.set_title(f"OOS ffd reversion IC by dev_age x adf_sup tercile (N={n_tb})\n"
                     f"unconditional = {unc_m:+.4f}")
        fig.colorbar(im, ax=ax, fraction=0.046)
        fig.tight_layout()
        fig.savefig(OUT / f"combined_gate_N{n_tb}.png", dpi=110)
        plt.close(fig)
        print()
    print(f"plots -> {OUT}")


if __name__ == "__main__":
    main()
