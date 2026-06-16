"""Misspecification probe for the reversion null-test.

Three targeted checks:
  1. Beta-adjusted residual + asymmetric tail split
  2. Manual threshold interaction splits (depth-2 tree, numpy-only)
  3. Extended horizon sweep (h=12,24,48,96)

Usage:
    PYTHONPATH=<repo-root> uv run python scripts/fx_coint/reversion_misspecification_probe.py --data-dir data/tick_bars
"""

from __future__ import annotations

import argparse

import numpy as np
import polars as pl

from scripts.fx_coint.usd_flow_factor import usd_factor_residual

PAIRS: dict[str, float] = {
    "EURUSD": -1.0,
    "GBPUSD": -1.0,
    "AUDUSD": -1.0,
    "USDJPY": +1.0,
    "USDCHF": +1.0,
    "USDCAD": +1.0,
}
IS_END = np.datetime64("2022-12-31")
DATA_DIR = "data/tick_bars"


def load(data_dir: str = DATA_DIR) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    syms = list(PAIRS)
    df = None
    for s in syms:
        d = pl.read_parquet(f"{data_dir}/{s}_30m_flow.parquet").select(
            "bucket",
            pl.col("mid").alias(f"mid_{s}"),
            pl.col("rvol_bps").alias(f"rvol_{s}"),
            pl.col("spread_bps").alias(f"spr_{s}"),
            pl.col("flow_tick").alias(f"ft_{s}"),
            pl.col("flow_ofi").alias(f"fo_{s}"),
            pl.col("n_ticks").alias(f"nt_{s}"),
        )
        df = d if df is None else df.join(d, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")

    logmid = np.column_stack([np.log(df[f"mid_{s}"].to_numpy()) for s in syms])
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    # oriented[0] is NaN (no prior), oriented[t] = logmid[t] - logmid[t-1] for t>=1
    oriented_lr = np.vstack(
        [np.full((1, len(syms)), np.nan), (logmid[1:] - logmid[:-1]) * signs[None, :]]
    )
    return df, logmid, oriented_lr


def _rolling_beta(
    factor: np.ndarray, oriented: np.ndarray, window: int
) -> np.ndarray:
    """Rolling beta of each pair on the factor.  Expanding up to `window`,
    then rolling.  Pure numpy, no look-ahead."""
    T, P = oriented.shape
    betas = np.full_like(oriented, np.nan)
    for p in range(P):
        for t in range(min(window, T)):
            x = factor[:t]
            y = oriented[:t, p]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() > 10 and np.var(x[m]) > 0:
                betas[t, p] = np.cov(x[m], y[m])[0, 1] / np.var(x[m])
        for t in range(window, T):
            x = factor[t - window : t]
            y = oriented[t - window : t, p]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() > 10 and np.var(x[m]) > 0:
                betas[t, p] = np.cov(x[m], y[m])[0, 1] / np.var(x[m])
    return betas


def _tail_stats(sig: np.ndarray, fwd: np.ndarray, cost: np.ndarray, q: float = 0.95) -> dict:
    m = np.isfinite(sig) & np.isfinite(fwd) & np.isfinite(cost)
    sig, fwd, cost = sig[m], fwd[m], cost[m]
    if len(sig) < 50:
        return {}
    a = np.abs(sig)
    thresh = np.nanquantile(a, q)
    sel = a >= thresh
    if sel.sum() < 10:
        return {}
    return {
        "n_total": len(sig),
        "n_tail": int(sel.sum()),
        "gross": float(fwd[sel].mean()),
        "cost": float(cost[sel].mean()),
        "net": float((fwd[sel] - cost[sel]).mean()),
        "pos_pct": float((fwd[sel] > 0).mean() * 100),
    }


def _fwd(logmid: np.ndarray, signs: np.ndarray, h: int) -> np.ndarray:
    """Forward log-return from each bar t to t+h, in fractional units."""
    T, P = logmid.shape
    fwd = np.full_like(logmid, np.nan)
    fwd[:-h] = (logmid[h:] - logmid[:-h]) * signs[None, :]
    return fwd


def test_1_beta_adjusted(df: pl.DataFrame, logmid: np.ndarray, oriented: np.ndarray) -> None:
    syms = list(PAIRS)
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    T, P = oriented.shape
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    oos = times > IS_END

    # Equal-weight factor and residual (both have NaN at index 0)
    factor_ew = oriented.mean(axis=1)
    _, res_ew = usd_factor_residual(oriented)

    # Beta-adjusted residual
    betas = _rolling_beta(factor_ew, oriented, window=60 * 48)
    factor_adj = factor_ew[:, None] * betas
    res_beta = oriented - factor_adj

    h = 1
    fwd = _fwd(logmid, signs, h)
    sf = -np.sign(res_ew) * fwd * 1e4
    sf_beta = -np.sign(res_beta) * fwd * 1e4
    sf_beta_long = -np.where(res_beta > 0, 1, -1) * fwd * 1e4
    sf_beta_short = np.where(res_beta < 0, 1, -1) * fwd * 1e4

    spread = np.column_stack([df[f"spr_{s}"].to_numpy() for s in syms])

    print("\n=== TEST 1: BETA-ADJUSTED RESIDUAL + ASYMMETRIC TAIL SPLIT (OOS, h=1) ===")
    print(f"{'pair':8s} | {'model':12s} | {'side':8s} |   n   | gross | cost |  net  | pos%")
    for p, pair in enumerate(syms):
        oos_m = oos & np.isfinite(res_ew[:, p]) & np.isfinite(sf[:, p]) & np.isfinite(spread[:, p])
        for label, sig, target in [
            ("raw", res_ew[:, p][oos_m], sf[:, p][oos_m]),
            ("beta-adj", res_beta[:, p][oos_m], sf_beta[:, p][oos_m]),
        ]:
            st = _tail_stats(sig, target, spread[:, p][oos_m], q=0.95)
            if st:
                print(
                    f"{pair:8s} | {label:12s} | {'both':8s} | {st['n_tail']:>5d} | "
                    f"{st['gross']:>+5.2f} | {st['cost']:>+4.2f} | {st['net']:>+5.2f} | {st['pos_pct']:>4.1f}"
                )

        # Asymmetric split for beta-adj only
        for side_label, side_sig, side_target in [
            ("long", res_beta[:, p][oos_m], sf_beta_long[:, p][oos_m]),
            ("short", -res_beta[:, p][oos_m], sf_beta_short[:, p][oos_m]),
        ]:
            st = _tail_stats(side_sig, side_target, spread[:, p][oos_m], q=0.95)
            if st:
                print(
                    f"{pair:8s} | {'beta-adj':12s} | {side_label:8s} | {st['n_tail']:>5d} | "
                    f"{st['gross']:>+5.2f} | {st['cost']:>+4.2f} | {st['net']:>+5.2f} | {st['pos_pct']:>4.1f}"
                )


def test_2_interactions(df: pl.DataFrame, logmid: np.ndarray, oriented: np.ndarray) -> None:
    syms = list(PAIRS)
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    T, P = oriented.shape
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    oos = times > IS_END

    factor_ew = oriented.mean(axis=1)
    _, res_ew = usd_factor_residual(oriented)

    h = 1
    fwd = _fwd(logmid, signs, h)
    sf = -np.sign(res_ew) * fwd * 1e4

    rvol = np.column_stack([df[f"rvol_{s}"].to_numpy() for s in syms])
    spr = np.column_stack([df[f"spr_{s}"].to_numpy() for s in syms])

    print("\n=== TEST 2: THRESHOLD INTERACTION SPLITS (OOS, h=1) ===")
    print("Testing 4 rules per pair: residual>0×rvol_high, residual<0×rvol_high, residual>0×spr_low, residual<0×spr_low")
    print(f"{'pair':8s} | {'rule':30s} |    n   | gross | cost |  net  | pos%")

    for p, pair in enumerate(syms):
        res = res_ew[:, p]
        target = sf[:, p]
        cost = spr[:, p]
        rv = rvol[:, p]

        m = np.isfinite(res) & np.isfinite(target) & np.isfinite(cost) & np.isfinite(rv) & oos
        res, target, cost, rv = res[m], target[m], cost[m], rv[m]

        # Define thresholds
        rv_med = np.median(rv)
        spr_med = np.median(cost)
        res_q90 = np.quantile(np.abs(res), 0.90)
        res_q95 = np.quantile(np.abs(res), 0.95)

        rules = [
            ("res>0 & rv_high & |res|>95", (res > 0) & (rv > rv_med) & (np.abs(res) >= res_q95)),
            ("res<0 & rv_high & |res|>95", (res < 0) & (rv > rv_med) & (np.abs(res) >= res_q95)),
            ("res>0 & spr_low & |res|>95", (res > 0) & (cost < spr_med) & (np.abs(res) >= res_q95)),
            ("res<0 & spr_low & |res|>95", (res < 0) & (cost < spr_med) & (np.abs(res) >= res_q95)),
            ("res>0 & rv_high & |res|>90", (res > 0) & (rv > rv_med) & (np.abs(res) >= res_q90)),
            ("res<0 & rv_high & |res|>90", (res < 0) & (rv > rv_med) & (np.abs(res) >= res_q90)),
            ("res>0 & spr_low & |res|>90", (res > 0) & (cost < spr_med) & (np.abs(res) >= res_q90)),
            ("res<0 & spr_low & |res|>90", (res < 0) & (cost < spr_med) & (np.abs(res) >= res_q90)),
            ("|res|>95 (baseline)", np.abs(res) >= res_q95),
            ("|res|>90 (baseline)", np.abs(res) >= res_q90),
        ]

        for rule_name, sel in rules:
            if sel.sum() < 10:
                continue
            gross = target[sel].mean()
            cst = cost[sel].mean()
            net = gross - cst
            pos = (target[sel] > 0).mean() * 100
            print(
                f"{pair:8s} | {rule_name:30s} | {sel.sum():>6d} | {gross:>+5.2f} | {cst:>+4.2f} | {net:>+5.2f} | {pos:>4.1f}"
            )


def test_3_extended_horizons(df: pl.DataFrame, logmid: np.ndarray, oriented: np.ndarray) -> None:
    syms = list(PAIRS)
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    oos = times > IS_END

    factor_ew = oriented.mean(axis=1)
    _, res_ew = usd_factor_residual(oriented)
    spread = np.column_stack([df[f"spr_{s}"].to_numpy() for s in syms])

    horizons = [1, 2, 4, 8, 12, 24, 48, 96]

    print("\n=== TEST 3: EXTENDED HORIZON SWEEP (OOS, pooled + pair-level) ===")
    print(f"{'pair':8s} | {'horizon':>7s} |    n   | gross | cost |  net  | pos% | spear_ic | t")

    for pair in syms + ["pooled"]:
        if pair == "pooled":
            # pooled non-overlap
            for h in horizons:
                fwd = _fwd(logmid, signs, h)
                sf = -np.sign(res_ew) * fwd * 1e4

                s_parts, f_parts, c_parts = [], [], []
                for p in range(len(syms)):
                    m = (
                        np.isfinite(res_ew[:, p])
                        & np.isfinite(sf[:, p])
                        & np.isfinite(spread[:, p])
                        & oos
                    )
                    s_parts.append(res_ew[:, p][m][::h])
                    f_parts.append(sf[:, p][m][::h])
                    c_parts.append(spread[:, p][m][::h])
                s_pool = np.concatenate(s_parts)
                f_pool = np.concatenate(f_parts)
                c_pool = np.concatenate(c_parts)
                if len(s_pool) < 100:
                    continue
                sel = np.abs(s_pool) >= np.nanquantile(np.abs(s_pool), 0.95)
                if sel.sum() < 10:
                    continue
                gross = f_pool[sel].mean()
                cst = c_pool[sel].mean()
                net = gross - cst
                pos = (f_pool[sel] > 0).mean() * 100
                # rank IC
                if sel.sum() > 20:
                    ra = np.argsort(np.argsort(np.abs(s_pool[sel]))).astype(float)
                    rb = np.argsort(np.argsort(f_pool[sel])).astype(float)
                    ic = float(np.corrcoef(ra, rb)[0, 1])
                    t = ic * np.sqrt(sel.sum() - 2) / np.sqrt(max(1e-12, 1.0 - ic ** 2))
                else:
                    ic, t = float("nan"), float("nan")
                print(
                    f"{'pooled':8s} | {'h'+str(h):>7s} | {sel.sum():>6d} | {gross:>+5.2f} | {cst:>+4.2f} | {net:>+5.2f} | {pos:>4.1f} | {ic:>+8.4f} | {t:>+5.1f}"
                )
        else:
            p = syms.index(pair)
            for h in horizons:
                fwd = _fwd(logmid, signs, h)
                sf = -np.sign(res_ew[:, p]) * fwd[:, p] * 1e4

                m = (
                    np.isfinite(res_ew[:, p])
                    & np.isfinite(sf)
                    & np.isfinite(spread[:, p])
                    & oos
                )
                sig, tgt, cost = res_ew[:, p][m][::h], sf[m][::h], spread[:, p][m][::h]
                if len(sig) < 100:
                    continue
                sel = np.abs(sig) >= np.nanquantile(np.abs(sig), 0.95)
                if sel.sum() < 10:
                    continue
                gross = tgt[sel].mean()
                cst = cost[sel].mean()
                net = gross - cst
                pos = (tgt[sel] > 0).mean() * 100
                if sel.sum() > 20:
                    ra = np.argsort(np.argsort(np.abs(sig[sel]))).astype(float)
                    rb = np.argsort(np.argsort(tgt[sel])).astype(float)
                    ic = float(np.corrcoef(ra, rb)[0, 1])
                    t = ic * np.sqrt(sel.sum() - 2) / np.sqrt(max(1e-12, 1.0 - ic ** 2))
                else:
                    ic, t = float("nan"), float("nan")
                print(
                    f"{pair:8s} | {'h'+str(h):>7s} | {sel.sum():>6d} | {gross:>+5.2f} | {cst:>+4.2f} | {net:>+5.2f} | {pos:>4.1f} | {ic:>+8.4f} | {t:>+5.1f}"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args()
    df, logmid, oriented = load(args.data_dir)
    test_1_beta_adjusted(df, logmid, oriented)
    test_2_interactions(df, logmid, oriented)
    test_3_extended_horizons(df, logmid, oriented)


if __name__ == "__main__":
    main()
