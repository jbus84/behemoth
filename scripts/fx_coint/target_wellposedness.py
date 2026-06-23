"""Stage C — target well-posedness metrics (feature-agnostic, own-history only).

Cheap label-quality diagnostics that run first in the predictability funnel. Each
metric maps to a past mirage: overlap inflation, day-clustered significance,
degenerate balance, regime shift, tick-exact illusions. Pure functions, unit-tested.

Self-test: `uv run python scripts/fx_coint/target_wellposedness.py`
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    var = np.dot(x, x)
    if var == 0:
        return np.zeros(max_lag + 1)
    out = np.empty(max_lag + 1)
    for k in range(max_lag + 1):
        out[k] = np.dot(x[: len(x) - k], x[k:]) / var
    return out


def effective_n(labels: np.ndarray) -> dict:
    """Integrated-autocorrelation-time estimate of independent sample count.

    tau = 1 + 2 * sum_{k>=1} rho_k, truncated at the first non-positive rho
    (initial-positive-sequence rule). n_eff = n / tau.
    """
    x = np.asarray(labels, dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n < 3:
        return {"n": n, "tau": 1.0, "n_eff": float(n), "overlap_ratio": 1.0}
    max_lag = min(n - 1, 500)
    rho = _autocorr(x, max_lag)
    tau = 1.0
    for k in range(1, max_lag + 1):
        if rho[k] <= 0:
            break
        tau += 2.0 * rho[k]
    tau = max(tau, 1.0)
    n_eff = n / tau
    return {"n": n, "tau": float(tau), "n_eff": float(n_eff),
            "overlap_ratio": float(n_eff / n)}


def _gini(v: np.ndarray) -> float:
    v = np.sort(np.abs(v))
    n = v.size
    if n == 0 or v.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2.0 * np.dot(idx, v) / (n * v.sum())) - (n + 1.0) / n)


def temporal_concentration(signal: np.ndarray, day_index: np.ndarray) -> dict:
    """Gini of total |signal| aggregated per day + share in the top 1% of days."""
    s = np.abs(np.asarray(signal, dtype=float))
    d = np.asarray(day_index)
    ok = np.isfinite(s)
    s, d = s[ok], d[ok]
    uniq = np.unique(d)
    per_day = np.array([s[d == u].sum() for u in uniq])
    total = per_day.sum()
    if total == 0 or per_day.size == 0:
        return {"gini": 0.0, "top1pct_share": 0.0}
    k = max(1, int(np.ceil(0.01 * per_day.size)))
    top = np.sort(per_day)[::-1][:k].sum()
    return {"gini": _gini(per_day), "top1pct_share": float(top / total)}


def class_balance(labels: np.ndarray, kind: str) -> dict:
    """Label class distribution and entropy for barrier or continuous targets.

    For kind="barrier": returns frac_up, frac_dn, frac_vert (fractions of +1, -1, 0)
    and entropy (base-3 normalized, in [0,1]).

    For kind="continuous": returns skew, tail_share (fraction of total |x| in top 5%)
    and entropy=np.nan.
    """
    x = np.asarray(labels)
    x = x[np.isfinite(x.astype(float))]
    if kind == "barrier":
        n = x.size
        up = float(np.mean(x == 1)) if n else 0.0
        dn = float(np.mean(x == -1)) if n else 0.0
        vt = float(np.mean(x == 0)) if n else 0.0
        p = np.array([up, dn, vt])
        nz = p[p > 0]
        ent = float(-np.sum(nz * np.log(nz)) / np.log(3)) if nz.size else 0.0
        return {"frac_up": up, "frac_dn": dn, "frac_vert": vt, "entropy": ent}
    a = np.abs(x.astype(float))
    total = a.sum()
    k = max(1, int(np.ceil(0.05 * a.size)))
    tail = np.sort(a)[::-1][:k].sum()
    return {"skew": float(stats.skew(x.astype(float))),
            "tail_share": float(tail / total) if total else 0.0,
            "entropy": float("nan")}


def regime_stability(labels: np.ndarray, split_idx: int, kind: str) -> dict:
    """Detect regime shifts between train ([:split_idx]) and OOS ([split_idx:]).

    Returns: vol_ratio, skew_diff, acf1_diff, max_shift.
    max_shift is the maximum of the standardized absolute differences.
    """
    x = np.asarray(labels, dtype=float)
    tr, oos = x[:split_idx], x[split_idx:]
    tr = tr[np.isfinite(tr)]
    oos = oos[np.isfinite(oos)]
    s_tr = tr.std() if tr.size else 0.0
    s_oos = oos.std() if oos.size else 0.0
    vol_ratio = float(max(s_oos, 1e-12) / max(s_tr, 1e-12))
    skew_diff = abs(float(stats.skew(oos)) - float(stats.skew(tr))) if min(tr.size, oos.size) > 2 else 0.0
    acf1_diff = abs(_autocorr(oos, 1)[1] - _autocorr(tr, 1)[1]) if min(tr.size, oos.size) > 2 else 0.0
    # standardized shifts: log vol ratio, raw skew diff, raw acf diff
    shifts = [abs(np.log(vol_ratio)) if vol_ratio > 0 else 0.0, skew_diff, acf1_diff]
    return {"vol_ratio": vol_ratio, "skew_diff": float(skew_diff),
            "acf1_diff": float(acf1_diff), "max_shift": float(max(shifts))}


def _self_test() -> None:
    rng = np.random.default_rng(0)
    print("iid:", effective_n(rng.standard_normal(2000)))
    print("conc:", temporal_concentration(np.ones(100), np.arange(100)))


if __name__ == "__main__":
    _self_test()
