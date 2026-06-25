"""
pf_15m_reversal.py
Bootstrap Particle Filter for selective mean-reversion entry at 15m.

Hypothesis: the unconditional 15m mom_3 fade is faint but real (IC ~ -0.05).
A particle filter tracking the time-varying predictive coefficient can identify
periods when the reversal probability is temporarily strong, and selective entry
above a cost threshold lifts the signal net-positive.

Method:
- Build true 15m time bars from enriched 1m bars (close = last mid, no stale ticks).
- Signal z_t = -(mid_t - mid_{t-3})  (fade 3-bar momentum, in fractional / bps).
- Particle filter: latent beta_t drifts as a random walk.  Each particle proposes
  a slope and predicts next return.  Weights updated by the likelihood of the
  realised return under a heavy-tailed observation model (Student-t, nu=5).
- Entry rule: only trade when the posterior probability that predicted return
  exceeds half-spread cost is above a threshold theta.
- Theta is tuned on the first 50 % of the sample; evaluation is strictly on the
  second 50 % (temporal holdout).

Output: causal net metrics for unconditional vs PF-filtered, printed + JSON.

Usage:
    uv run python scripts/fx_coint/pf_15m_reversal.py --symbol EURUSD --years 2018 2019 2020 2021 2022 2023 2024 2025

The script expects enriched 1m bars at data/tick_bars/{SYM}_1m_enriched.parquet.
If absent it will build them from ~/Desktop/dukascopy_ticks (slow first run).
"""
from __future__ import annotations

import argparse
import json
import sys as _sys
from pathlib import Path as _Path

import numpy as np
import pandas as pd

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    DEFAULT_COST_BPS,
    build_enriched_1m_bars,
    evaluate_family,
    load_raw_ticks,
)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
BAR_FREQ = "15min"
HORIZON_BARS = 1  # one 15m bar forward
MOM_WINDOW = 3  # mom_3
NPARTICLES = 2_000
STUDENT_NU = 5.0  # heavy-tailed observation likelihood (robust to outliers)
BETA_RW_STD = 0.05  # random-walk sigma for beta_t
THETA_GRID = np.linspace(0.50, 0.95, 10)  # calibration grid for P(ret > cost)
TRAIN_FRAC = 0.50  # first half for theta calibration


def _cached_1m(symbol: str, year: int) -> pd.DataFrame:
    """Load or build enriched 1m bars for symbol+year (cache is per-year)."""
    path = _ROOT / "data" / "tick_bars" / f"{symbol.upper()}_{year}_1m_enriched.parquet"
    if path.exists():
        return pd.read_parquet(path)
    ticks = load_raw_ticks(symbol, year)
    df = build_enriched_1m_bars(ticks, symbol)
    # save under the year-qualified name so multi-year loops don't collide
    out_dir = _ROOT / "data" / "tick_bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol.upper()}_{year}_1m_enriched.parquet"
    df.to_parquet(path)
    return df


def aggregate_to_15m(df1m: pd.DataFrame) -> pd.DataFrame:
    """True 15m OHLCV-style bars from 1m enriched bars."""
    df = df1m.copy()
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    # Resample on 15-min boundaries
    agg = {
        "mid": "last",
        "bid": "last",
        "ask": "last",
        "flow_tick": "mean",
        "flow_ofi": "mean",
        "tick_volume": "sum",
        "quote_revisions": "sum",
        "bar_return_sign": "sum",  # directional persistence proxy
    }
    # Preserve columns that exist
    cols = [c for c in agg if c in df.columns]
    bars = df[cols].resample(BAR_FREQ).agg({c: agg[c] for c in cols})
    bars = bars.dropna()
    bars["spread_bps"] = (
        (bars["ask"] - bars["bid"]) / bars["mid"] * 10_000
    )
    return bars.reset_index()


def compute_15m_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Causal 15m features (all .shift(1))."""
    df = df.copy()
    close = df["mid"].astype(float)
    0.01 if str(symbol).upper().endswith("JPY") else 0.0001

    # 15m bar return in fractional terms
    df["ret_15m"] = close.pct_change().replace(0, np.nan)
    # Momentum over 3 bars (45m lookback)
    df["mom_3"] = (close - close.shift(MOM_WINDOW)) / close.shift(MOM_WINDOW)
    # Signal: fade mom_3 -> predict negative continuation of move
    df["signal"] = -df["mom_3"]

    # Microstructure features (z-scored with expanding moments, .shift(1))
    for col in ["flow_tick", "flow_ofi", "tick_volume", "spread_bps"]:
        if col not in df.columns:
            continue
        s = df[col].astype(float)
        ema = s.ewm(halflife=24, min_periods=12).mean().shift(1)
        evar = s.ewm(halflife=24, min_periods=12).var().shift(1)
        df[f"{col}_z"] = (s - ema) / (evar**0.5 + 1e-12)

    # Session indicator (UTC hour of the 15m bucket)
    df["hour"] = pd.to_datetime(df["bucket"]).dt.hour

    return df


def _student_loglik(resid: np.ndarray, nu: float) -> np.ndarray:
    """Log-likelihood of residuals under a Student-t scaled to unit variance."""
    # scale-free: we assume residual is already divided by observation noise std
    # log p(x) propto -(nu+1)/2 * log(1 + x^2/nu)
    return -0.5 * (nu + 1.0) * np.log1p((resid**2) / nu)


class BetaPF:
    """Bootstrap particle filter for a drifting linear predictor.

    Latent state: beta_t = scalar slope linking signal z_t to forward return r_{t+1}.
    Dynamics:   beta_t = beta_{t-1} + N(0, sigma_beta^2)
    Likelihood: r_t ~ Student_t( nu , mean = beta_{t-1} * z_{t-1} , scale = sigma_obs )
    """

    def __init__(self, n_particles: int = NPARTICLES, nu: float = STUDENT_NU,
                 rw_std: float = BETA_RW_STD):
        self.n = n_particles
        self.nu = nu
        self.rw_std = rw_std
        # initialise particles broadly around zero (weak prior)
        self.beta = np.random.normal(0.0, 0.5, size=n_particles)
        self.w = np.ones(n_particles) / n_particles
        self.sigma_obs = 1.0  # will adapt online via median absolute deviation

    def predict(self) -> None:
        """Propagate particles one step (random walk)."""
        self.beta += np.random.normal(0.0, self.rw_std, size=self.n)
        # light regularisation: soft-bound particles
        self.beta = np.clip(self.beta, -3.0, 3.0)

    def update(self, z_prev: float, r_obs: float) -> None:
        """Observe return r_obs that was predicted from signal z_prev."""
        if not (np.isfinite(z_prev) and np.isfinite(r_obs)):
            return
        pred = self.beta * z_prev
        # Robust scale estimate: online MAD of residuals
        resid = r_obs - pred
        mad = float(np.median(np.abs(resid))) + 1e-12
        self.sigma_obs = 1.4826 * mad  # consistent estimator for Gaussian core
        std_resid = resid / (self.sigma_obs + 1e-12)
        logw = _student_loglik(std_resid, self.nu)
        # stabilise numerically
        logw -= np.max(logw)
        self.w = np.exp(logw)
        self.w /= (self.w.sum() + 1e-12)
        self._resample()
        # forget slowly: inflate sigma_obs slightly to avoid overconfidence
        self.sigma_obs = max(self.sigma_obs, 1e-4)

    def _resample(self) -> None:
        """Systematic resampling if effective sample size drops."""
        ess = 1.0 / (np.sum(self.w**2) + 1e-12)
        if ess < 0.5 * self.n:
            idx = self._systematic_resample(self.w)
            self.beta = self.beta[idx]
            self.w = np.ones(self.n) / self.n

    @staticmethod
    def _systematic_resample(w: np.ndarray) -> np.ndarray:
        n = len(w)
        cumsum = np.cumsum(w)
        u0 = np.random.rand() / n
        j = 0
        idx = np.empty(n, dtype=int)
        for i in range(n):
            u = u0 + i / n
            while cumsum[j] < u:
                j += 1
            idx[i] = j
        return idx

    def prob_above(self, z_now: float, threshold: float) -> float:
        """Posterior probability that predicted return beta*z_now > threshold."""
        if not np.isfinite(z_now):
            return 0.0
        pred = self.beta * z_now
        # account for observation noise
        above = pred > threshold
        return float(np.average(above, weights=self.w))


def calibrate_theta(prob_scores: np.ndarray, returns: np.ndarray,
                    cost_frac: float) -> tuple[float, float]:
    """Pick theta on the training half that maximises net mean return per trade."""
    m = np.isfinite(prob_scores) & np.isfinite(returns)
    ps, ret = prob_scores[m], returns[m]
    if len(ps) == 0:
        return 0.90, 0.0

    best_theta, best_net = 0.90, -1e9
    for theta in THETA_GRID:
        sel = ps >= theta
        n = int(sel.sum())
        if n < 20:
            continue
        net = ret[sel] - cost_frac
        mean_net = float(net.mean())
        if mean_net > best_net:
            best_net = mean_net
            best_theta = float(theta)
    return best_theta, best_net


def run_single_year(symbol: str, year: int) -> dict:
    cost_bps = DEFAULT_COST_BPS.get(symbol, 0.80)
    cost_frac = cost_bps / 10_000

    df1m = _cached_1m(symbol, year)
    df = aggregate_to_15m(df1m)
    df = compute_15m_features(df, symbol)

    # Forward return: next 15m log-return
    df["fwd_ret"] = np.log(df["mid"].astype(float).shift(-1) /
                           df["mid"].astype(float))

    # Drop rows without needed fields
    needed = ["signal", "fwd_ret", "hour"]
    df = df.dropna(subset=needed).reset_index(drop=True)
    if len(df) < 200:
        return {"year": year, "error": "too few bars"}

    # -----------------------------------------------------------------------
    # Unconditional fade evaluation (baseline)
    # -----------------------------------------------------------------------
    base_res = evaluate_family(df["signal"], df["fwd_ret"],
                               cost_frac=cost_frac, entry_quantile=0.90)

    # -----------------------------------------------------------------------
    # Particle filter run
    # -----------------------------------------------------------------------
    pf = BetaPF()
    prob_scores = np.full(len(df), np.nan)
    # Burn-in: run PF on first 100 bars without trading
    burn = 100
    for i in range(1, min(burn, len(df))):
        z_prev = float(df.loc[i - 1, "signal"])
        r_obs = float(df.loc[i - 1, "fwd_ret"])
        if np.isfinite(z_prev) and np.isfinite(r_obs):
            pf.predict()
            pf.update(z_prev, r_obs)
        prob_scores[i] = 0.0  # no trade during burn

    # Main loop: produce live scores
    for i in range(burn, len(df)):
        # Step the filter forward to time i and update with the observation
        # that just became available: fwd_ret[i-1] realised from signal[i-1]
        pf.predict()
        z_prev = float(df.loc[i - 1, "signal"])
        r_obs = float(df.loc[i - 1, "fwd_ret"])
        if np.isfinite(z_prev) and np.isfinite(r_obs):
            pf.update(z_prev, r_obs)
        # Score entry at time i (before observing fwd_ret[i])
        z_now = float(df.loc[i, "signal"])
        prob_scores[i] = pf.prob_above(z_now, threshold=cost_frac / 2)

    # -----------------------------------------------------------------------
    # Temporal split: first 50 % calibrate theta, second 50 % evaluate
    # -----------------------------------------------------------------------
    split = int(len(df) * TRAIN_FRAC)
    train_ps, train_ret = prob_scores[:split], df["fwd_ret"].iloc[:split].to_numpy()
    theta, _ = calibrate_theta(train_ps, train_ret, cost_frac)

    test_mask = np.arange(split, len(df))
    test_ps = prob_scores[test_mask]
    test_ret = df["fwd_ret"].iloc[test_mask].to_numpy()
    test_signal = df["signal"].iloc[test_mask].reset_index(drop=True)

    # Evaluate PF-filtered signal: override signal with NaN where prob < theta
    filtered_signal = test_signal.where(test_ps >= theta, np.nan)
    pf_res = evaluate_family(filtered_signal, pd.Series(test_ret),
                             cost_frac=cost_frac, entry_quantile=0.90)

    # Also record the *unconditional* on the same test slice for fair comparison
    test_base_res = evaluate_family(test_signal, pd.Series(test_ret),
                                    cost_frac=cost_frac, entry_quantile=0.90)

    return {
        "year": year,
        "symbol": symbol,
        "cost_bps": cost_bps,
        "theta": round(theta, 4),
        "base_full_sample": base_res,
        "base_test_split": test_base_res,
        "pf_test_split": pf_res,
        "n_bars": len(df),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--years", nargs="+", type=int,
                   default=list(range(2018, 2026)))
    args = p.parse_args()

    sym = args.symbol.upper()
    all_results = []
    print(f"\n=== PF 15m Reversal  {sym}  years={args.years} ===\n")
    for yr in args.years:
        try:
            res = run_single_year(sym, yr)
        except FileNotFoundError as exc:
            print(f"  {yr}: SKIP (missing tick data: {exc})")
            continue
        all_results.append(res)

        base = res["base_test_split"]
        pf = res["pf_test_split"]
        print(
            f"{yr}: base net={base['net_mean_bps']:+.3f} lb95={base['net_lb95_bps']:+.3f}  "
            f"n={base['n_entries']} | "
            f"PF  net={pf['net_mean_bps']:+.3f} lb95={pf['net_lb95_bps']:+.3f} "
            f"n={pf['n_entries']} theta={res['theta']:.2f}"
        )

    # Aggregate across years (concatenate test-split entries)
    for _r in all_results:
        # Reconstruct individual trade net returns from evaluate_family is not stored;
        # For a lightweight aggregate we rely on per-year means weighted by n_entries.
        pass

    # Simple pooled-mean metric across years
    total_base_n = sum(r["base_test_split"]["n_entries"] for r in all_results)
    sum(r["pf_test_split"]["n_entries"] for r in all_results)
    if total_base_n > 0:
        pooled_base = np.average(
            [r["base_test_split"]["net_mean_bps"] for r in all_results],
            weights=[max(r["base_test_split"]["n_entries"], 1) for r in all_results]
        )
        pooled_pf = np.average(
            [r["pf_test_split"]["net_mean_bps"] for r in all_results],
            weights=[max(r["pf_test_split"]["n_entries"], 1) for r in all_results]
        )
        print(f"\nPooled test-split: base net={pooled_base:+.3f}  PF net={pooled_pf:+.3f}")

    out = _ROOT / "data" / "analysis" / f"pf_15m_{sym}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(all_results, fh, indent=2, default=str)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
