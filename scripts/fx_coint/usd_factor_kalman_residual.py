"""Kalman state-space decomposition of the USD-factor residual.

Question: does separating the residual into a mean-reverting (transitory) state
vs a random-walk (permanent) state -- and fading the transitory STRETCH --
select better trades than thresholding the raw |residual move|?

Model (per pair), on the residual PRICE level p_t = cumsum(residual return):
    p_t   = trend_t + c_t
    trend_t = trend_{t-1} + eta_t        (permanent / random walk)
    c_t     = phi * c_{t-1} + eps_t       (transitory / mean-reverting, AR(1))
Fit by MLE (statsmodels UnobservedComponents) on a TRAIN window; then run the
CAUSAL Kalman FILTER (filtered_state, uses only data <= t -- NOT the smoother)
over the full series with the train params. c_{t|t} is the stretch signal.

Trade: fade the stretch, position = -sign(c_{t|t}); pnl over next h hours =
-sign(c_t) * (p_{t+h} - p_t). Cost = flat Pepperstone commission (one RT).

Look-ahead guards: EW factor (no beta), filtered (not smoothed) states, params
from train only, OOS evaluation on the held-out tail. Distinct from the era_tick
Kalman tape-reader (that faded raw PRICE and failed); here we fade the FACTOR
RESIDUAL, which is established to mean-revert (t -30).
"""

from __future__ import annotations

import warnings

import numpy as np
from statsmodels.tsa.statespace.structural import UnobservedComponents
from usd_factor_residual_probe import PAIRS, hourly_mid

COMMISSION_RT_BPS = 0.7
TRAIN_FRAC = 0.6
BAND = (6.0, 12.0)  # baseline |residual move| band, bps


def kalman_stretch(p: np.ndarray, train_n: int) -> tuple[np.ndarray, float]:
    """Causal filtered AR(1) transitory component of residual price p.

    Returns (c_filtered over full series, phi). Params fit on p[:train_n] only.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod_tr = UnobservedComponents(p[:train_n], level="random walk", autoregressive=1, irregular=False)
        res_tr = mod_tr.fit(disp=False, maxiter=200)
        mod_full = UnobservedComponents(p, level="random walk", autoregressive=1, irregular=False)
        res_full = mod_full.filter(res_tr.params)
    names = list(mod_full.state_names)
    ar_idx = next(i for i, nm in enumerate(names) if nm.startswith("ar."))
    c = np.asarray(res_full.filtered_state[ar_idx])
    phi = float(res_tr.params[mod_tr.param_names.index("ar.L1")])
    return c, phi


def stats(cap: np.ndarray) -> tuple[float, float, float]:
    g = cap.mean()
    return g, g - COMMISSION_RT_BPS, (cap > 0).mean() * 100


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
    E = R - R.mean(axis=1, keepdims=True)  # 1-factor residual returns (T-1, 6)
    T = E.shape[0]
    train_n = int(T * TRAIN_FRAC)
    print(f"hours={T}  train_n={train_n}  OOS={T - train_n}  cost={COMMISSION_RT_BPS}bps RT")

    for h in (1, 3):
        print(f"\n================  hold horizon = {h}h  ================")
        print("  pair    phi   | baseline |move|6-12bps        | Kalman stretch (matched active)")
        print("                | n     gross   net   win        | n     gross   net   win")
        for j, sy in enumerate(syms):
            e = E[:, j]
            p = np.cumsum(e)
            c, phi = kalman_stretch(p, train_n)

            # forward h-hour residual return = p_{t+h} - p_t = sum(e[t+1 .. t+h])
            fwd = np.full(T, np.nan)
            fwd[: T - h] = p[h : T] - p[: T - h]

            oos = np.zeros(T, dtype=bool)
            oos[train_n : T - h] = True

            # baseline: |last-hour residual move| in band, fade -sign(e_t)
            absb = np.abs(e) * 1e4
            base_sel = oos & (absb >= BAND[0]) & (absb < BAND[1])
            cap_b = (-np.sign(e[base_sel]) * fwd[base_sel]) * 1e4
            active = base_sel.sum() / max(1, oos.sum())

            # kalman: |stretch c_t| top fraction matched to baseline active %, fade -sign(c_t)
            c_oos_abs = np.abs(c[oos])
            thr = np.quantile(c_oos_abs, 1 - active) if 0 < active < 1 else np.inf
            kal_sel = oos & (np.abs(c) >= thr)
            cap_k = (-np.sign(c[kal_sel]) * fwd[kal_sel]) * 1e4

            if cap_b.size < 30 or cap_k.size < 30:
                continue
            gb, nb, wb = stats(cap_b)
            gk, nk, wk = stats(cap_k)
            print(f"  {sy} {phi:5.2f} | {cap_b.size:5d} {gb:+.3f} {nb:+.3f} {wb:4.0f}  | {cap_k.size:5d} {gk:+.3f} {nk:+.3f} {wk:4.0f}")


if __name__ == "__main__":
    main()
