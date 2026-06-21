"""Gate 1: does an edge's conditional path distribution differ from unconditional?

Run: uv run python scripts/fx_coint/path_shift_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.path_ensemble import (  # noqa: E402
    _panel_and_closes,
    build_ensemble,
    jittered_entries,
    offset_placebo_entries,
    tail_long_entries,
)

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]


def shift_tests(
    cond: np.ndarray, uncond: np.ndarray, seed: int = 0, n_boot: int = 2000
) -> dict:
    cond = np.asarray(cond, float)
    cond = cond[np.isfinite(cond)]
    uncond = np.asarray(uncond, float)
    uncond = uncond[np.isfinite(uncond)]
    ks = ks_2samp(cond, uncond)
    rng = np.random.default_rng(seed)
    obs = cond.mean() - uncond.mean()
    pool = np.concatenate([cond, uncond])
    nc = len(cond)
    null = np.empty(n_boot)
    for b in range(n_boot):
        p = rng.permutation(pool)
        null[b] = p[:nc].mean() - p[nc:].mean()
    boot_p = float((np.abs(null) >= abs(obs)).mean())
    return {
        "ks_stat": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "mean_cond": float(cond.mean()),
        "mean_uncond": float(uncond.mean()),
        "diff": float(obs),
        "boot_p": boot_p,
        "n_cond": nc,
        "n_uncond": len(uncond),
    }


def gate_one_edge(
    sym_list, entries_fn, freq, n_bars, label, min_off_days=3, seed=0
) -> dict:
    metrics = ["terminal_sigma", "mfe_sigma", "mae_sigma"]
    cond_frames, uncond_frames = [], []
    robust: dict[int, list[np.ndarray]] = {k: [] for k in (-2, -1, 0, 1, 2)}
    for sym in sym_list:
        ents = entries_fn(sym, freq)
        cond_frames.append(build_ensemble(sym, ents, freq, n_bars=n_bars))
        plc = offset_placebo_entries(sym, freq, ents, min_off_days=min_off_days, seed=seed)
        uncond_frames.append(build_ensemble(sym, plc, freq, n_bars=n_bars))
        # small-offset robustness: mean terminal_sigma at jitter k
        panel, _c, sig = _panel_and_closes(sym, freq)
        bars = panel["bucket"].to_numpy()
        for k in robust:
            je = jittered_entries(ents, bars, freq, k, sig)
            df = build_ensemble(sym, je, freq, n_bars=n_bars)
            if len(df):
                robust[k].append(df["terminal_sigma"].to_numpy())
    cond = pd.concat(cond_frames, ignore_index=True)
    uncond = pd.concat(uncond_frames, ignore_index=True)
    res = {
        m: shift_tests(cond[m].to_numpy(), uncond[m].to_numpy(), seed=seed)
        for m in metrics
    }
    shifted = any(
        res[m]["ks_p"] < 0.05 / len(metrics) and res[m]["boot_p"] < 0.05 / len(metrics)
        for m in metrics
    )
    robustness = {
        k: float(np.concatenate(v).mean()) if v else float("nan")
        for k, v in robust.items()
    }
    return {
        "label": label,
        "n_cond": len(cond),
        "n_uncond": len(uncond),
        "metrics": res,
        "shifted": shifted,
        "robustness": robustness,
    }


def _fmt(g: dict) -> str:
    lines = [
        f"## {g['label']}  (n_cond={g['n_cond']} n_uncond={g['n_uncond']})  SHIFTED={g['shifted']}"
    ]
    for m, r in g["metrics"].items():
        lines.append(
            f"  {m:>15}: cond={r['mean_cond']:+.3f} unc(placebo)={r['mean_uncond']:+.3f} "
            f"diff={r['diff']:+.3f} ks_p={r['ks_p']:.4f} boot_p={r['boot_p']:.4f}"
        )
    rob = g["robustness"]
    lines.append(
        "  robustness terminal_sigma by jitter (bars): "
        + " ".join(f"{k:+d}={rob[k]:+.3f}" for k in sorted(rob))
    )
    return "\n".join(lines)


def main() -> None:
    g = gate_one_edge(
        TIGHT_MAJORS,
        lambda s, f: tail_long_entries(s, f, q=0.95),
        freq="2h",
        n_bars=1,
        label="2h tail-long",
        min_off_days=3,
    )
    block = _fmt(g)
    print(block)
    (Path(__file__).resolve().parent / "path_shift_results.md").write_text(
        "# Path-shift gate (gate 1) results\n\n" + block + "\n"
    )


if __name__ == "__main__":
    main()
