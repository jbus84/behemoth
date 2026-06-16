"""Reversion conditioner null-test runner.

Loads 30m flow bars, computes USD-factor residual targets (signed_fade, abs_move),
and evaluates gross predictability (rank+linear IC, tail return, ridge OOS) vs
execution cost (spread).  Outputs JSON + console summary.

Usage:
    PYTHONPATH=<repo-root> uv run python scripts/fx_coint/reversion_conditioner_nulltest.py \
        --data-dir data/tick_bars [--out results/reversion_null.json]
"""

from __future__ import annotations

import argparse
import json
import os
from math import erfc, sqrt

import numpy as np
import polars as pl

from scripts.fx_coint.flow_metrics import (
    bh_fdr,
    deviation_tail_return,
    information_coefficient,
    ridge_oos,
    spearman_ic,
)
from scripts.fx_coint.usd_flow_factor import usd_factor_residual

PAIRS = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,
    "USDCAD": +1.0,
}
HORIZONS = [1, 2, 4, 8]
IS_END = np.datetime64("2022-12-31")


def load(data_dir: str) -> pl.DataFrame:
    """Load 30m bars for all pairs and join on bucket."""
    syms = list(PAIRS)
    df = None
    for s in syms:
        d = pl.read_parquet(f"{data_dir}/{s}_30m_flow.parquet").select(
            "bucket",
            pl.col("mid").alias(f"mid_{s}"),
            pl.col("flow_tick").alias(f"ft_{s}"),
            pl.col("flow_ofi").alias(f"fo_{s}"),
            pl.col("rvol_bps").alias(f"rvol_{s}"),
            pl.col("spread_bps").alias(f"spr_{s}"),
            pl.col("n_ticks").alias(f"nt_{s}"),
        )
        df = d if df is None else df.join(d, on="bucket", how="inner")
    return df.drop_nulls().sort("bucket")


def _p_from_t(t: float) -> float:
    return erfc(abs(t) / sqrt(2)) if np.isfinite(t) else 1.0


def _stride_nonoverlap(arr: np.ndarray, mask: np.ndarray, h: int) -> np.ndarray:
    """Select mask then stride by h for non-overlapping samples."""
    return arr[mask][::h]


def _collect_pooled(
    sig2d: np.ndarray, fwd2d: np.ndarray, mask: np.ndarray, h: int
) -> tuple[np.ndarray, np.ndarray]:
    s_parts, f_parts = [], []
    for p in range(sig2d.shape[1]):
        s_parts.append(sig2d[mask, p][::h])
        f_parts.append(fwd2d[mask, p][::h])
    return np.concatenate(s_parts), np.concatenate(f_parts)


def run(data_dir: str) -> list[dict]:
    syms = list(PAIRS)
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    df = load(data_dir)
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    is_mask = times <= IS_END
    oos_mask = ~is_mask

    # Price levels and oriented returns
    logmid = np.column_stack([np.log(df[f"mid_{s}"].to_numpy()) for s in syms])
    oriented_lr = np.vstack(
        [np.full((1, len(syms)), np.nan), (logmid[1:] - logmid[:-1]) * signs[None, :]]
    )
    factor, residual = usd_factor_residual(oriented_lr[1:])
    residual = np.vstack([np.full((1, len(syms)), np.nan), residual])

    # Signals aligned to bar index
    signals: dict[str, np.ndarray] = {
        "residual": residual,
        "flow_tick": np.column_stack([df[f"ft_{s}"].to_numpy() for s in syms]),
        "flow_ofi": np.column_stack([df[f"fo_{s}"].to_numpy() for s in syms]),
        "rvol": np.column_stack([df[f"rvol_{s}"].to_numpy() for s in syms]),
        "spread": np.column_stack([df[f"spr_{s}"].to_numpy() for s in syms]),
        "n_ticks": np.column_stack([df[f"nt_{s}"].to_numpy() for s in syms]),
    }

    # Spread cost matrix (bps) aligned to bar index
    spread_bps = signals["spread"]

    results: list[dict] = []
    pvals: list[float] = []
    p_labels: list[str] = []

    print(f"bars={len(df)}  IS<= {IS_END}  IS_bars={int(is_mask.sum())} OOS_bars={int(oos_mask.sum())}\n")
    header = (
        f"  {'pair':8s} {'signal':12s} {'target':10s} {'horizon':>7s} {'regime':>6s} "
        f"{'n':>7s} {'pearson':>8s} {'t':>6s} {'spear':>8s} {'t':>6s} "
        f"{'tail_gross':>10s} {'tail_cost':>10s} {'tail_net':>10s}"
    )
    print(header)

    def emit(
        pair: str,
        signal_name: str,
        target_name: str,
        sig: np.ndarray,
        tgt: np.ndarray,
        cost: np.ndarray,
        h: int,
        tag: str,
        mask: np.ndarray,
    ) -> None:
        s = _stride_nonoverlap(sig, mask, h)
        t = _stride_nonoverlap(tgt, mask, h)
        c = _stride_nonoverlap(cost, mask, h)
        if len(s) < 10:
            return
        pearson_ic, pearson_t, n = information_coefficient(s, t, horizon=1)
        spear_ic, spear_t, _ = spearman_ic(s, t)
        tail_gross, tail_fade = deviation_tail_return(s, t, q=0.90)
        # cost in the same tail selection
        a = np.abs(s)
        sel = a >= np.nanquantile(a, 0.90)
        tail_cost = float(c[sel].mean()) if sel.sum() else float("nan")
        tail_net = tail_fade - tail_cost

        pvals.append(_p_from_t(pearson_t))
        p_labels.append(f"{pair}|{signal_name}|{target_name}|h{h}|{tag}|pearson")
        pvals.append(_p_from_t(spear_t))
        p_labels.append(f"{pair}|{signal_name}|{target_name}|h{h}|{tag}|spear")

        results.append(
            {
                "pair": pair,
                "signal": signal_name,
                "target": target_name,
                "horizon": h,
                "regime": tag,
                "n": n,
                "pearson_ic": float(pearson_ic),
                "pearson_t": float(pearson_t),
                "spear_ic": float(spear_ic),
                "spear_t": float(spear_t),
                "tail_gross": float(tail_gross),
                "tail_fade": float(tail_fade),
                "tail_cost": float(tail_cost),
                "tail_net": float(tail_net),
            }
        )
        print(
            f"  {pair:8s} {signal_name:12s} {target_name:10s} {('h'+str(h)):>7s} {tag:>6s} "
            f"{n:>7d} {pearson_ic:>+8.4f} {pearson_t:>+6.1f} {spear_ic:>+8.4f} {spear_t:>+6.1f} "
            f"{tail_gross:>+10.2f} {tail_cost:>+10.2f} {tail_net:>+10.2f}"
        )

    for h in HORIZONS:
        # Forward returns (bps) aligned to bar index
        fwd_h = np.full_like(logmid, np.nan)
        fwd_h[:-h] = (logmid[h:] - logmid[:-h]) * signs[None, :]
        signed_fade = -np.sign(residual) * fwd_h * 1e4
        abs_move = np.abs(fwd_h) * 1e4

        # Pair-level univariate
        for p_idx, pair in enumerate(syms):
            for sig_name, sig_mat in signals.items():
                for tgt_name, tgt_mat in (("signed_fade", signed_fade), ("abs_move", abs_move)):
                    for tag, mask in (("IS", is_mask), ("OOS", oos_mask)):
                        emit(
                            pair,
                            sig_name,
                            tgt_name,
                            sig_mat[:, p_idx],
                            tgt_mat[:, p_idx],
                            spread_bps[:, p_idx],
                            h,
                            tag,
                            mask,
                        )

        # Pooled non-overlapping (per-pair stride then concatenate)
        for sig_name, sig_mat in signals.items():
            for tgt_name, tgt_mat in (("signed_fade", signed_fade), ("abs_move", abs_move)):
                for tag, mask in (("IS", is_mask), ("OOS", oos_mask)):
                    s_pool, t_pool = _collect_pooled(sig_mat, tgt_mat, mask, h)
                    c_pool, _ = _collect_pooled(spread_bps, spread_bps, mask, h)
                    if len(s_pool) < 10:
                        continue
                    pearson_ic, pearson_t, n = information_coefficient(s_pool, t_pool, horizon=1)
                    spear_ic, spear_t, _ = spearman_ic(s_pool, t_pool)
                    tail_gross, tail_fade = deviation_tail_return(s_pool, t_pool, q=0.90)
                    a = np.abs(s_pool)
                    sel = a >= np.nanquantile(a, 0.90)
                    tail_cost = float(c_pool[sel].mean()) if sel.sum() else float("nan")
                    tail_net = tail_fade - tail_cost

                    pvals.append(_p_from_t(pearson_t))
                    p_labels.append(f"pooled|{sig_name}|{tgt_name}|h{h}|{tag}|pearson")
                    pvals.append(_p_from_t(spear_t))
                    p_labels.append(f"pooled|{sig_name}|{tgt_name}|h{h}|{tag}|spear")

                    results.append(
                        {
                            "pair": "pooled",
                            "signal": sig_name,
                            "target": tgt_name,
                            "horizon": h,
                            "regime": tag,
                            "n": n,
                            "pearson_ic": float(pearson_ic),
                            "pearson_t": float(pearson_t),
                            "spear_ic": float(spear_ic),
                            "spear_t": float(spear_t),
                            "tail_gross": float(tail_gross),
                            "tail_fade": float(tail_fade),
                            "tail_cost": float(tail_cost),
                            "tail_net": float(tail_net),
                        }
                    )
                    print(
                        f"  {'pooled':8s} {sig_name:12s} {tgt_name:10s} {('h'+str(h)):>7s} {tag:>6s} "
                        f"{n:>7d} {pearson_ic:>+8.4f} {pearson_t:>+6.1f} {spear_ic:>+8.4f} {spear_t:>+6.1f} "
                        f"{tail_gross:>+10.2f} {tail_cost:>+10.2f} {tail_net:>+10.2f}"
                    )

        # ---- joint ridge OOS per horizon (pooled across pairs, non-overlapping) ----
        for tgt_name, tgt_mat in (("signed_fade", signed_fade), ("abs_move", abs_move)):
            # Build feature matrix X (bars × features) and expand to (bars*pairs × features)
            # We stack all pairs vertically so the model learns a single cross-pair mapping.
            feat_names = ["flow_tick", "flow_ofi", "rvol", "spread", "n_ticks"]
            T, P = signed_fade.shape
            X_list = []
            for fn in feat_names:
                X_list.append(signals[fn].ravel())
            # Add residual as a feature too
            X_list.append(residual.ravel())
            all_feats = feat_names + ["residual"]
            X_full = np.column_stack(X_list)
            y_full = tgt_mat.ravel()
            m = np.isfinite(X_full).all(1) & np.isfinite(y_full)
            X_full, y_full = X_full[m], y_full[m]
            t_full = np.repeat(times, P)[m]
            is_m = t_full <= IS_END
            X_is, y_is = X_full[is_m], y_full[is_m]
            X_oos, y_oos = X_full[~is_m], y_full[~is_m]
            # Non-overlapping by h
            X_is_s = X_is[::h]
            y_is_s = y_is[::h]
            X_oos_s = X_oos[::h]
            y_oos_s = y_oos[::h]
            if len(y_is_s) < 20 or len(y_oos_s) < 20:
                continue
            oos_ic, oos_r2, _ = ridge_oos(X_is_s, y_is_s, X_oos_s, y_oos_s, lam=10.0)
            results.append(
                {
                    "pair": "pooled",
                    "signal": "ridge_" + "_".join(all_feats),
                    "target": tgt_name,
                    "horizon": h,
                    "regime": "OOS",
                    "n": len(y_oos_s),
                    "pearson_ic": float(oos_ic),
                    "pearson_t": float("nan"),
                    "spear_ic": float("nan"),
                    "spear_t": float("nan"),
                    "tail_gross": float("nan"),
                    "tail_fade": float("nan"),
                    "tail_cost": float("nan"),
                    "tail_net": float("nan"),
                    "oos_r2": float(oos_r2),
                }
            )
            print(
                f"  {'pooled':8s} {'ridge_joint':12s} {tgt_name:10s} {('h'+str(h)):>7s} {'OOS':>6s} "
                f"{len(y_oos_s):>7d} {oos_ic:>+8.4f} {'--':>6s} {'--':>8s} {'--':>6s} "
                f"{'--':>10s} {'--':>10s} {'--':>10s}  R²={oos_r2:+.4f}"
            )

    # BH-FDR across all univariate tests
    pvals_arr = np.array(pvals)
    rej = bh_fdr(pvals_arr, alpha=0.05)
    print(f"\nBH-FDR @0.05 across {len(rej)} univariate tests: {int(rej.sum())} significant\n")
    for lbl, p, r in sorted(zip(p_labels, pvals, rej, strict=True), key=lambda x: x[1])[:15]:
        print(f"  {'REJECT' if r else '  ----'}  {lbl:50s}  p={p:.2e}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Reversion conditioner null-test runner.")
    parser.add_argument("--data-dir", default="data/tick_bars", help="Directory containing 30m flow parquet files.")
    parser.add_argument("--out", default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    rows = run(args.data_dir)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(rows, fh, indent=2, default=str)
        print(f"\nWrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
