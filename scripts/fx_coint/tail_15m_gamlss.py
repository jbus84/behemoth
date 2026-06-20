"""Two questions:

1. Would GAMLSS (modelling sigma/skew/kurtosis conditionally, not just the mean)
   rescue the 2h tail edge?  Empirical decomposition of which conditional
   moment is actually predictable from the features at decision time.

2. Do shorter timeframes (15m, 30m) show the same right-tail-collapse and the
   same sub-cost economics?

Usage:
    uv run python scripts/fx_coint/tail_15m_gamlss.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    build_panel,
)
from scripts.fx_coint.tail_wfo import walk_forward  # noqa: E402

# Register sub-hourly frequencies the panel builder doesn't ship with.
rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]


def load_panel(sym: str, freq: str) -> pd.DataFrame | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return None
    panel["sym"] = sym
    return panel


def pooled_folds(freq: str, q: float = 0.95) -> pd.DataFrame:
    """Run WFO per pair, collect test-set (pred, actual, bucket, cost)."""
    frames = []
    for sym in TIGHT:
        panel = load_panel(sym, freq)
        if panel is None:
            continue
        folds = walk_forward(panel)
        for f in folds:
            frames.append(pd.DataFrame({
                "pred": f["test_pred"],
                "act": f["test_actual_bps"],
                "bucket": pd.to_datetime(f["test_bucket"]),
                "cost": COST_BPS[sym],
                "sym": sym,
            }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def tail_economics(df: pd.DataFrame, q: float = 0.95) -> dict:
    """Top-(1-q) long-only net-of-cost economics, pooled across pairs."""
    thr = df.groupby("sym")["pred"].transform(lambda s: s.quantile(q))
    sel = df[df["pred"] >= thr]
    net = sel["act"] - sel["cost"]            # long: pay cost, capture next-bar return
    return {
        "n": len(sel),
        "gross": float(sel["act"].mean()),
        "net": float(net.mean()),
        "hit": float((sel["act"] > 0).mean()),
        "cost": float(sel["cost"].mean()),
    }


def quarterly_distribution(df: pd.DataFrame, q: float = 0.95) -> pd.DataFrame:
    df = df.copy()
    df["qtr"] = df["bucket"].dt.to_period("Q")
    rows = []
    for qtr, g in df.groupby("qtr"):
        if len(g) < 40:
            continue
        act, pred = g["act"], g["pred"]
        pt = pred >= np.quantile(pred, q)
        at = act >= np.quantile(act, q)
        cond = float(at[pt].mean()) if pt.sum() else np.nan
        rows.append({
            "qtr": str(qtr), "n": len(g),
            "skew": float(act.skew()), "kurt": float(act.kurtosis()),
            "cond_hit": cond, "rand": round(1 - q, 3),
        })
    return pd.DataFrame(rows)


def gamlss_decomposition(freq: str = "2h") -> None:
    """Which conditional MOMENT is predictable from the features?

    GAMLSS would model mu, sigma, nu (skew), tau (kurt) each as a function of
    the covariates.  It only helps if some moment beyond mu carries usable,
    OUT-OF-SAMPLE signal that the plain ridge-on-mean throws away.  We test
    each moment's conditional predictability with the SAME walk-forward split.
    """
    print(f"\n=== GAMLSS DECOMPOSITION ({freq}) — is any conditional moment predictable OOS? ===")
    print("moment            target               OOS spearman IC   interpretation")
    rows = []
    for sym in TIGHT:
        panel = load_panel(sym, freq)
        if panel is None:
            continue
        n = len(panel)
        split = int(n * 0.6)
        Xtr, Xte = panel[FEATURE_COLS].iloc[:split], panel[FEATURE_COLS].iloc[split + 1:]
        sc = StandardScaler().fit(Xtr)
        Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)
        r = panel["ret_next_bps"].to_numpy()
        tr, te = slice(0, split), slice(split + 1, n)

        targets = {
            # mu: directional mean (the alpha we actually need)
            "mu (direction)": r,
            # sigma: magnitude — GAMLSS scale submodel
            "sigma (|ret|)": np.abs(r),
            # nu: signed tail / skew proxy — does X predict which side tails?
            "nu (ret^3 sign)": np.sign(r) * r ** 2,
        }
        for name, y in targets.items():
            ytr = y[tr]
            m = Ridge(alpha=1.0).fit(Xtr_s, (ytr - ytr.mean()) / (ytr.std() + 1e-9))
            pred = m.predict(Xte_s)
            ic = spearmanr(pred, y[te]).statistic
            rows.append({"sym": sym, "moment": name, "ic": float(ic)})
        # rvol_24 -> |ret| is the canonical GAMLSS sigma channel; report directly
        ic_vol = spearmanr(panel["rvol_24"].to_numpy()[te], np.abs(r)[te]).statistic
        rows.append({"sym": sym, "moment": "sigma (rvol_24->|ret|)", "ic": float(ic_vol)})

    agg = pd.DataFrame(rows).groupby("moment")["ic"].agg(["mean", "min", "max"])
    order = ["mu (direction)", "nu (ret^3 sign)", "sigma (|ret|)", "sigma (rvol_24->|ret|)"]
    notes = {
        "mu (direction)": "the alpha we NEED — must rank the right tail",
        "nu (ret^3 sign)": "can we predict WHICH side tails?",
        "sigma (|ret|)": "magnitude only — sizing/risk, not direction",
        "sigma (rvol_24->|ret|)": "vol clustering — well known, not tradable alone",
    }
    for m in order:
        if m in agg.index:
            row = agg.loc[m]
            print(f"  {m:<24} ic={row['mean']:+.3f} [{row['min']:+.3f},{row['max']:+.3f}]  {notes[m]}")


def main() -> None:
    print("=" * 78)
    print("TIMEFRAME SWEEP — top-5% long-only, pooled EUR/GBP/JPY, net of real cost")
    print("=" * 78)
    print(f"{'freq':>5} {'n':>6} {'gross':>8} {'cost':>6} {'net':>8} {'hit':>6}   median per-quarter skew")
    for freq in ["15m", "30m", "1h", "2h"]:
        df = pooled_folds(freq)
        if df.empty:
            print(f"{freq:>5}  (no data)")
            continue
        e = tail_economics(df)
        qd = quarterly_distribution(df)
        med_skew = float(qd["skew"].median()) if not qd.empty else float("nan")
        print(f"{freq:>5} {e['n']:>6} {e['gross']:>+8.3f} {e['cost']:>6.2f} "
              f"{e['net']:>+8.3f} {e['hit']*100:>5.0f}%   {med_skew:>+.2f}")

    # Detailed quarterly distribution at 15m vs 2h to compare tail behaviour
    for freq in ["15m", "2h"]:
        df = pooled_folds(freq)
        if df.empty:
            continue
        print(f"\n=== QUARTERLY TARGET DISTRIBUTION ({freq}) ===")
        qd = quarterly_distribution(df)
        print(qd.to_string(index=False))
        print(f"  mean cond_hit={qd['cond_hit'].mean():.3f}  (random={qd['rand'].iloc[0]})  "
              f"frac quarters skew>0: {(qd['skew']>0).mean():.0%}")

    gamlss_decomposition("2h")
    gamlss_decomposition("15m")


if __name__ == "__main__":
    main()
