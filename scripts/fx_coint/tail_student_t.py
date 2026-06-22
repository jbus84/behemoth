"""Student-t location (and location-scale GAMLSS-t) as the ranking signal.

Huber is a FIXED robustness.  A Student-t likelihood ESTIMATES the tail weight
via the degrees-of-freedom nu: low nu => heavily down-weight tails, high nu =>
Gaussian.  This is the genuine heavy-tailed GAMLSS LOCATION submodel.  We fit by
MLE and also report the fitted nu — if the data drives nu low, it 'wants' to
discount the tails, and we see whether that helps or hurts the tradable basket.

  t-loc       : y ~ t(nu),  loc = X beta,           scale = sigma (const)
  t-locscale  : y ~ t(nu),  loc = X beta,  log scale = X gamma   (real GAMLSS-t,
                location + scale both conditional)
  ridge       : Gaussian/L2 baseline for reference

Ranking is by the conditional location (= conditional median) X beta in every case.

Usage:
    uv run python scripts/fx_coint/tail_student_t.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
warnings.filterwarnings("ignore")

COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def razor_cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def load_panel(sym, freq):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    return panel if len(panel) >= 200 else None


def _t_logpdf(z, nu):
    # standard Student-t logpdf of z with df nu (z already standardized by scale)
    return (gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log(nu * np.pi)
            - (nu + 1) / 2 * np.log1p(z * z / nu))


def fit_t(Xtr, ytr, scale_model: bool):
    """MLE of Student-t (location-scale) linear model.  Returns beta, fitted nu."""
    n, k = Xtr.shape
    Xi = np.column_stack([np.ones(n), Xtr])  # intercept
    beta0 = np.r_[ytr.mean(), Ridge(alpha=1.0).fit(Xtr, ytr).coef_]
    log_sig0 = np.log(ytr.std() + 1e-6)

    def unpack(p):
        beta = p[:k + 1]
        if scale_model:
            gamma = p[k + 1:2 * k + 2]      # log-scale coefs (incl intercept)
            log_nu = p[-1]
            log_sig = Xi @ gamma
        else:
            log_sig = p[k + 1]
            log_nu = p[-1]
        nu = 2.0 + np.exp(log_nu)            # keep finite variance, nu>2
        return beta, log_sig, nu

    def nll(p):
        beta, log_sig, nu = unpack(p)
        sig = np.exp(log_sig)
        z = (ytr - Xi @ beta) / sig
        return -np.sum(_t_logpdf(z, nu) - log_sig)

    if scale_model:
        p0 = np.r_[beta0, log_sig0, np.zeros(k), np.log(5.0)]
    else:
        p0 = np.r_[beta0, log_sig0, np.log(5.0)]
    res = minimize(nll, p0, method="L-BFGS-B", options={"maxiter": 400})
    beta, _, nu = unpack(res.x)
    return beta, float(nu)


def wfo_rank(panel, kind, q=0.95, n_folds=5):
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    rows, nus = [], []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        Xtr, Xte = sc.transform(X[:split]), sc.transform(X[lo:hi])
        if kind == "ridge":
            pred = Ridge(alpha=1.0).fit(Xtr, yz[:split]).predict(Xte)
        else:
            beta, nu = fit_t(Xtr, yz[:split], scale_model=(kind == "t-locscale"))
            nus.append(nu)
            pred = np.column_stack([np.ones(len(Xte)), Xte]) @ beta
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        rows.append(df[df["pred"] >= df["pred"].quantile(q)])
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return out, (np.mean(nus) if nus else np.nan)


def day_clustered(d):
    daily = d.groupby(d["bucket"].dt.date)["net"].mean().to_numpy()
    if len(daily) < 3:
        return np.nan, np.nan
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p)


def main():
    print("Student-t location ranking vs Ridge — identical top-5% 2h basket "
          "(EUR/GBP/JPY, net Razor cost)\n")
    print(f"{'model':>11} {'fitNu':>6} {'n':>5} {'net':>8} {'naive_p':>8} "
          f"{'dayT':>6} {'dayP':>7} {'hit':>5} {'posYrs':>7}")
    for kind in ["ridge", "t-loc", "t-locscale"]:
        frames, nuvals = [], []
        for sym in TIGHT:
            p = load_panel(sym, "2h")
            if p is None:
                continue
            d, nu = wfo_rank(p, kind)
            d["net"] = d["act"] - razor_cost(sym)
            frames.append(d)
            nuvals.append(nu)
        d = pd.concat(frames, ignore_index=True)
        d["year"] = d["bucket"].dt.year
        _, pp = ttest_1samp(d["net"], 0)
        dt, dp = day_clustered(d)
        yr = d.groupby("year")["net"].mean()
        fitnu = np.nanmean(nuvals)
        print(f"{kind:>11} {fitnu:>6.1f} {len(d):>5} {d['net'].mean():>+8.3f} {pp:>8.3f} "
              f"{dt:>+6.2f} {dp:>7.3f} {(d['act']>0).mean()*100:>4.0f}% {(yr>0).sum()}/{len(yr)}")


if __name__ == "__main__":
    main()
