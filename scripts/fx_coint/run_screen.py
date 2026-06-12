from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.amplitude import close_to_close_amplitude, intrabar_excursion
from scripts.fx_coint.cointegration import (
    fit_hedge,
    instrument_series,
    residual,
    residual_weight,
)
from scripts.fx_coint.cost import MARKUP_SWEEP_PIPS, spread_cost_frac
from scripts.fx_coint.gate import classify
from scripts.fx_coint.instruments import MAJORS, all_pairs
from scripts.fx_coint.panels import coarsen, load_aligned
from scripts.fx_coint.report import write_report
from scripts.fx_coint.reversion import oos_reversion, ou_fit, reversion_exists
from scripts.fx_coint.stability import bh_fdr, structure_exists, walk_forward_eg

REVERSION_HORIZON = 10


def _mean_legs(coarse: pd.DataFrame):
    spreads = np.array([coarse[(m, "spread")].mean() for m in MAJORS])
    mids = np.array([np.exp(coarse[(m, "logmid")].mean()) for m in MAJORS])
    return spreads, mids


def screen_pair(fine: pd.DataFrame, coarse_freq: str, base: str, hedge: str,
                universe: str, fdr_pass: bool) -> dict:
    coarse = coarsen(fine, coarse_freq)
    wf = walk_forward_eg(coarse, base, hedge)
    beta = wf["beta_mean"] if np.isfinite(wf["beta_mean"]) else fit_hedge(coarse, base, hedge)

    res_coarse = residual(coarse, base, hedge, beta)
    fit = ou_fit(res_coarse)
    rev = oos_reversion(res_coarse, horizon=REVERSION_HORIZON)

    # Amplitude floor (coarse close-to-close) and ceiling (fine intrabar excursion).
    floor = close_to_close_amplitude(res_coarse, horizon=REVERSION_HORIZON)
    fine_res = (instrument_series(fine, base) - beta * instrument_series(fine, hedge))
    fine_res = fine_res - fine_res.mean()
    ceiling = float(intrabar_excursion(fine_res, coarse_freq).mean())

    # Cost across markup sweep using mean legs of the residual's weight vector.
    w = residual_weight(base, hedge, beta)
    spreads, mids = _mean_legs(coarse)
    cost_by_markup = {f"{mk}": spread_cost_frac(w, spreads, mids, mk)
                      for mk in MARKUP_SWEEP_PIPS}

    structure = structure_exists(wf)
    reverts = reversion_exists(fit, rev)
    verdict_by_markup = {
        mk: classify(structure, reverts, fdr_pass, floor, ceiling, c).value
        for mk, c in cost_by_markup.items()
    }
    return {
        "timeframe": coarse_freq, "universe": universe,
        "base": base, "hedge": hedge, "beta": beta,
        "fraction_stationary": wf["fraction_stationary"],
        "n_windows": wf["n_windows"], "fdr_pass": fdr_pass,
        "half_life": fit["half_life"], "reversion_frac": rev["mean_reversion_frac"],
        "n_events": rev["n_events"], "floor": floor, "ceiling": ceiling,
        "cost_by_markup": cost_by_markup, "verdict_by_markup": verdict_by_markup,
    }


def run(coarse_freqs=("1D", "1h", "1W"), fine_freq="5min",
        out_dir=Path("docs/analysis/fx_coint")) -> None:
    fine = load_aligned(freq=fine_freq)
    out_dir.mkdir(parents=True, exist_ok=True)
    instruments = all_pairs()
    for cf in coarse_freqs:
        coarse = coarsen(fine, cf)
        # Two-pass for FDR: first collect EG OOS p-values, then classify.
        candidates = list(combinations(instruments, 2))
        pvals, partial = [], []
        for base, hedge in candidates:
            wf = walk_forward_eg(coarse, base, hedge)
            p = float(np.median(wf["oos_pvals"])) if wf["oos_pvals"] else 1.0
            pvals.append(p)
            partial.append((base, hedge))
        keep = bh_fdr(pvals, alpha=0.10)
        rows = [screen_pair(fine, cf, b, h, "pairwise", fdr_pass=k)
                for (b, h), k in zip(partial, keep)]
        write_report(rows, out_dir / f"screen_{cf}.json",
                     out_dir / f"screen_{cf}.md")
        print(f"{cf}: wrote {len(rows)} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="+", default=["1D", "1h", "1W"])
    ap.add_argument("--fine", default="5min")
    args = ap.parse_args()
    run(coarse_freqs=tuple(args.timeframes), fine_freq=args.fine)


if __name__ == "__main__":
    main()
