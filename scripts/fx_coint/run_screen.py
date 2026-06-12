from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.fx_coint.amplitude import close_to_close_amplitude, intrabar_excursion
from scripts.fx_coint.cointegration import (
    eg_test,
    fit_hedge,
    instrument_series,
    residual_weight,
)
from scripts.fx_coint.cost import MARKUP_SWEEP_PIPS, spread_cost_frac
from scripts.fx_coint.gate import classify
from scripts.fx_coint.instruments import MAJORS, all_pairs
from scripts.fx_coint.panels import coarsen, load_aligned, walk_forward_windows
from scripts.fx_coint.report import write_report
from scripts.fx_coint.reversion import oos_reversion, ou_fit, reversion_exists
from scripts.fx_coint.stability import (
    bh_fdr,
    fraction_stationary,
    structure_exists,
)

REVERSION_HORIZON = 10
TRAIN_YEARS = 2
MIN_OOS_BARS = 30


def _mean_legs(coarse: pd.DataFrame):
    spreads = np.array([coarse[(m, "spread")].mean() for m in MAJORS])
    mids = np.array([np.exp(coarse[(m, "logmid")].mean()) for m in MAJORS])
    return spreads, mids


def _raw_spread(panel: pd.DataFrame, base: str, hedge: str, beta: float) -> pd.Series:
    """base - beta*hedge in log space, WITHOUT de-meaning (caller subtracts a
    train-only mean to keep the OOS residual look-ahead safe)."""
    return instrument_series(panel, base) - beta * instrument_series(panel, hedge)


def _measure(coarse: pd.DataFrame, fine: pd.DataFrame, coarse_freq: str,
             base: str, hedge: str) -> dict:
    """Walk-forward, look-ahead-safe measurement of one spread.

    Every window: beta AND the de-meaning constant come from the TRAIN slice
    only and are applied forward to the OOS slice. All of conditions A, B, and C
    are then measured on the concatenated OOS residuals — never the full sample —
    so an optimistic in-sample amplitude/reversion can't leak in.
    """
    wins = walk_forward_windows(coarse, train_years=TRAIN_YEARS)
    oos_pvals: list[float] = []
    betas: list[float] = []
    coarse_parts: list[pd.Series] = []
    fine_exc_parts: list[pd.Series] = []
    for train, oos in wins:
        beta = fit_hedge(train, base, hedge)
        mu = float(_raw_spread(train, base, hedge, beta).mean())
        oos_res = _raw_spread(oos, base, hedge, beta) - mu
        if len(oos_res) < MIN_OOS_BARS:
            continue
        betas.append(beta)
        oos_pvals.append(eg_test(oos_res))
        coarse_parts.append(oos_res)
        lo, hi = oos.index.min(), oos.index.max()
        fseg = fine[(fine.index >= lo) & (fine.index <= hi)]
        if len(fseg) > 0:
            fine_res = _raw_spread(fseg, base, hedge, beta) - mu
            fine_exc_parts.append(intrabar_excursion(fine_res, coarse_freq))

    wf = {
        "oos_pvals": oos_pvals,
        "fraction_stationary": fraction_stationary(oos_pvals),
        "n_windows": len(oos_pvals),
    }
    beta_mean = float(np.mean(betas)) if betas else float("nan")
    coarse_res = pd.concat(coarse_parts) if coarse_parts else pd.Series(dtype=float)
    fine_exc = pd.concat(fine_exc_parts) if fine_exc_parts else pd.Series(dtype=float)

    if len(coarse_res):
        fit = ou_fit(coarse_res)
        rev = oos_reversion(coarse_res, horizon=REVERSION_HORIZON)
        floor = close_to_close_amplitude(coarse_res, horizon=REVERSION_HORIZON)
    else:
        fit = {"theta": 0.0, "half_life": float("inf"), "phi": float("nan")}
        rev = {"mean_reversion_frac": 0.0, "mean_reversion": 0.0, "n_events": 0}
        floor = 0.0
    ceiling = float(fine_exc.mean()) if len(fine_exc) else 0.0

    w = residual_weight(base, hedge, beta_mean if np.isfinite(beta_mean) else 0.0)
    spreads, mids = _mean_legs(coarse)
    cost_by_markup = {f"{mk}": spread_cost_frac(w, spreads, mids, mk)
                      for mk in MARKUP_SWEEP_PIPS}

    return {
        "timeframe": coarse_freq, "base": base, "hedge": hedge, "beta": beta_mean,
        "fraction_stationary": wf["fraction_stationary"], "n_windows": wf["n_windows"],
        "half_life": fit["half_life"], "reversion_frac": rev["mean_reversion_frac"],
        "n_events": rev["n_events"], "floor": floor, "ceiling": ceiling,
        "cost_by_markup": cost_by_markup,
        "structure": structure_exists(wf), "reverts": reversion_exists(fit, rev),
        "p_value": float(np.median(oos_pvals)) if oos_pvals else 1.0,
    }


def _finalize(m: dict, universe: str, fdr_pass: bool) -> dict:
    """Turn a measurement into a report row by applying the gate at each markup."""
    verdict_by_markup = {
        mk: classify(m["structure"], m["reverts"], fdr_pass,
                     m["floor"], m["ceiling"], c).value
        for mk, c in m["cost_by_markup"].items()
    }
    row = {k: v for k, v in m.items() if k not in ("structure", "reverts", "p_value")}
    row["universe"] = universe
    row["fdr_pass"] = fdr_pass
    row["verdict_by_markup"] = verdict_by_markup
    return row


def screen_pair(fine: pd.DataFrame, coarse_freq: str, base: str, hedge: str,
                universe: str, fdr_pass: bool) -> dict:
    """Convenience single-pair screen (coarsens internally)."""
    coarse = coarsen(fine, coarse_freq)
    return _finalize(_measure(coarse, fine, coarse_freq, base, hedge),
                     universe, fdr_pass)


def run(coarse_freqs=("1D", "1h", "1W"), fine_freq="5min",
        out_dir=Path("docs/analysis/fx_coint")) -> None:
    fine = load_aligned(freq=fine_freq)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = list(combinations(all_pairs(), 2))
    for cf in coarse_freqs:
        coarse = coarsen(fine, cf)  # coarsen ONCE per timeframe, reuse for all pairs
        measures = [_measure(coarse, fine, cf, b, h) for b, h in candidates]
        keep = bh_fdr([m["p_value"] for m in measures], alpha=0.10)
        rows = [_finalize(m, "pairwise", k) for m, k in zip(measures, keep)]
        write_report(rows, out_dir / f"screen_{cf}.json", out_dir / f"screen_{cf}.md")
        print(f"{cf}: wrote {len(rows)} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="+", default=["1D", "1h", "1W"])
    ap.add_argument("--fine", default="5min")
    args = ap.parse_args()
    run(coarse_freqs=tuple(args.timeframes), fine_freq=args.fine)


if __name__ == "__main__":
    main()
