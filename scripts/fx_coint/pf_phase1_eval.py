"""Phase-1 gauntlet: does PF dynamic-exit beat the fixed-horizon baseline?

NOTE: null_check uses a *placeholder* null — it scrambles baseline net returns by a
uniform random factor in [0.5, 1.0] per trade.  This simulates turnover/early-exit noise
but is NOT a true shuffled-posterior null (i.e., it does not permute p_trend/mu_hat).
Interpret it as a sanity check that the signal beats random attrition, not as a full
permutation test.

Run: uv run python scripts/fx_coint/pf_phase1_eval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.pf_core import PFParams  # noqa: E402
from scripts.fx_coint.pf_phase1 import run_pair_phase1  # noqa: E402
from scripts.fx_coint.tail_wfo import day_clustered_tstat  # noqa: E402

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]


def positive_years(net: np.ndarray, bucket: np.ndarray) -> tuple[int, int]:
    """Return (n_positive_years, n_total_years) by mean net per calendar year."""
    yr = pd.Series(net, index=pd.to_datetime(pd.Series(bucket)).dt.year)
    means = yr.groupby(level=0).mean()
    return int((means > 0).sum()), int(len(means))


def year_block_bootstrap_ci(
    net: np.ndarray,
    bucket: np.ndarray,
    n_boot: int = 3000,
    seed: int = 0,
) -> tuple[float, float]:
    """95% CI resampling whole calendar years as blocks."""
    rng = np.random.default_rng(seed)
    s = pd.Series(net, index=pd.to_datetime(pd.Series(bucket)).dt.year)
    blocks = [g.to_numpy() for _, g in s.groupby(level=0)]
    if len(blocks) < 2:
        return float("nan"), float("nan")
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(blocks), len(blocks))
        means[b] = np.concatenate([blocks[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(net: np.ndarray, bucket: np.ndarray, label: str) -> dict:
    """Return summary dict with label, n, mean, day_t, day_p, ci_lo, ci_hi, pos_y, n_y."""
    dc = day_clustered_tstat(np.asarray(net), bucket)
    lo, hi = year_block_bootstrap_ci(net, bucket)
    pos, ny = positive_years(net, bucket)
    return {
        "label": label,
        "n": len(net),
        "mean": float(np.mean(net)),
        "day_t": dc["t_stat"],
        "day_p": dc["p_value"],
        "ci_lo": lo,
        "ci_hi": hi,
        "pos_y": pos,
        "n_y": ny,
    }


def _pool(
    params: PFParams, q: float, freq: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    base, pf, bk = [], [], []
    per_pair: dict = {}
    for sym in TIGHT_MAJORS:
        out = run_pair_phase1(sym, freq=freq, q=q, params=params)
        base.append(out["net_base"])
        pf.append(out["net_pf"])
        bk.append(out["bucket"])
        per_pair[sym] = (out["net_base"], out["net_pf"], out["bucket"])
    return (
        np.concatenate(base),
        np.concatenate(pf),
        np.concatenate(bk),
        per_pair,
    )


def null_check(q: float, freq: str, params: PFParams, seed: int) -> dict:
    """Placeholder null: scramble baseline returns by uniform [0.5, 1.0] factor per trade.

    This is NOT a true shuffled-posterior null (p_trend/mu_hat are not permuted).
    It simulates random-attrition noise on the fixed-horizon returns as a sanity floor.
    """
    rng = np.random.default_rng(seed)
    nets, bks = [], []
    for sym in TIGHT_MAJORS:
        out = run_pair_phase1(sym, freq=freq, q=q, params=params)
        scramble = rng.uniform(0.5, 1.0, size=out["n"])
        nets.append(out["net_base"] * scramble)
        bks.append(out["bucket"])
    return summarize(np.concatenate(nets), np.concatenate(bks), "NULL(random-exit)")


def _fmt(d: dict) -> str:
    return (
        f"{d['label']:>20} n={d['n']:>4} mean={d['mean']:>+6.2f} "
        f"day_t={d['day_t']:>+5.2f} day_p={d['day_p']:>6.3f} "
        f"pos={d['pos_y']}/{d['n_y']} boot95=[{d['ci_lo']:>+6.2f},{d['ci_hi']:>+6.2f}]"
    )


def main() -> None:
    q, freq, params = 0.95, "2h", PFParams()
    base, pf, bk, per_pair = _pool(params, q, freq)

    lines = [
        "# PF Phase-1 dynamic-exit results",
        "",
        "## Pooled TIGHT_MAJORS (EUR/GBP/USDJPY), 2h long top-5%",
        "",
    ]

    for d in (
        summarize(base, bk, "BASELINE(fixed)"),
        summarize(pf, bk, "PF-EXIT"),
        null_check(q, freq, params, seed=0),
    ):
        line = _fmt(d)
        print(line)
        lines.append("    " + line)

    lines.append("\n## Per-pair (baseline -> pf-exit)")
    for sym, (b, p, kb) in per_pair.items():
        line = (
            f"{sym}: base {summarize(b, kb, sym)['mean']:+.2f} -> "
            f"pf {summarize(p, kb, sym)['mean']:+.2f}"
        )
        print(line)
        lines.append("    " + line)

    (Path(__file__).resolve().parent / "pf_phase1_results.md").write_text(
        "\n".join(lines)
    )


if __name__ == "__main__":
    main()
