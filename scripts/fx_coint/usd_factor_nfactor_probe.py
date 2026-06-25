"""Does a BETTER USD factor improve the residual reversion edge?

Compares 1-factor (equal-weighted dollar) vs 2-/3-factor (PCA) residuals on the
6-12 bps band, per pair, under a Pepperstone-style FLAT commission cost
(~0.7 bps round-trip, roughly uniform across majors) -- NOT Dukascopy quoted
spreads, which overstate the wide-spread pairs' real execution cost.

Rationale: a "better factor" = one that absorbs MORE common/unpredictable
variance, leaving a cleaner idiosyncratic residual. The weak pairs (safe-haven
JPY/CHF, commodity CAD) may carry an un-removed common component (risk/carry)
in their 1-factor residual. Removing a 2nd PC tests whether that helps.

Caveat: EW factor is look-ahead-free (unit weights). PCA removal uses
full-sample SVD -> in-sample factor (optimistic UPPER BOUND on what factor
improvement can buy). If the in-sample 2-factor does not help, a causal one
will not either.
"""

from __future__ import annotations

import numpy as np
from usd_factor_residual_probe import PAIRS, hourly_mid

COMMISSION_RT_BPS = 0.7  # Pepperstone Razor: ~0.3 pip/side x2 + near-zero raw spread
BAND = (6.0, 12.0)


def residual_remove_k(R: np.ndarray, k: int) -> np.ndarray:
    """Residual of oriented returns after removing the top-k principal components.

    k=1 ~ remove dollar factor (≈ EW). k=2 also removes the 2nd (risk/carry) axis.
    """
    if k == 0:
        return R
    mu = R.mean(axis=0)
    Rc = R - mu
    # SVD on centered returns (not standardized -> keeps bps scale interpretable)
    U, S, Vt = np.linalg.svd(Rc, full_matrices=False)
    recon = U[:, :k] @ np.diag(S[:k]) @ Vt[:k]
    return Rc - recon


def per_pair(R_res: np.ndarray, syms: list[str], label: str) -> None:
    lo, hi = BAND
    s = R_res[:-1]
    fwd = R_res[1:]
    cap = -np.sign(s) * fwd
    absb = np.abs(s) * 1e4
    print(f"\n[{label}]  band {lo:.0f}-{hi:.0f}bps, cost = {COMMISSION_RT_BPS}bps RT flat commission")
    print("  pair      n     gross    net    win%")
    nets = []
    for j, sy in enumerate(syms):
        m = (absb[:, j] >= lo) & (absb[:, j] < hi)
        if m.sum() < 50:
            continue
        g = cap[m, j].mean() * 1e4
        net = g - COMMISSION_RT_BPS
        nets.append(net)
        flag = "  +" if net > 0 else ""
        print(f"  {sy}  {m.sum():>6}  {g:+.3f}  {net:+.3f}   {(cap[m, j] > 0).mean() * 100:.0f}{flag}")
    print(f"  -- mean net across pairs: {np.mean(nets):+.3f}  (pairs net>0: {sum(n > 0 for n in nets)}/{len(nets)})")


def main() -> None:
    syms = list(PAIRS)
    frames = [hourly_mid(s) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="hour", how="inner")
    df = df.drop_nulls().sort("hour")

    rets = []
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        rets.append(PAIRS[s] * np.diff(np.log(mid)))
    R = np.column_stack(rets)

    # variance explained by each PC (how much a 2nd/3rd factor could remove)
    Rc = R - R.mean(axis=0)
    _, S, _ = np.linalg.svd(Rc, full_matrices=False)
    var = S**2 / (S**2).sum()
    print("PC variance explained:", np.round(var * 100, 1))

    for k in (1, 2, 3):
        per_pair(residual_remove_k(R, k), syms, f"{k}-factor residual (remove top-{k} PC)")


if __name__ == "__main__":
    main()
