"""GAMLSS in the TAIL we actually trade — not whole-sample IC.

The strategy only takes the top percentiles, so average ranking IC is the wrong
lens.  GAMLSS gives a full conditional distribution; the faithful use is to rank
/ gate on a conditional UPPER QUANTILE (mu + z*sigma with conditional skew),
not the conditional mean.  We compare selection rules on the SAME walk-forward
OOS top-q long basket, net of real cost:

  baseline  : rank by ridge conditional MEAN (mu)
  q-upper   : rank by linear conditional 0.90 QUANTILE  (GAMLSS upper-tail object)
  mu|hi-sig : mu selection, then keep only predicted-high-sigma bars (scale gate)
  mu|rskew  : mu selection, then keep only right-skew trailing regime (shape gate)

If any GAMLSS channel helps, its top-q basket beats baseline net OOS.

Usage:
    uv run python scripts/fx_coint/tail_gamlss_quantile.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import QuantileRegressor, Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import COST_BPS, FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
warnings.filterwarnings("ignore")


def load_panel(sym: str, freq: str) -> pd.DataFrame | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return None
    # trailing right-skew regime flag (past returns only, no look-ahead)
    rs = panel["ret_next_bps"].shift(1)
    panel["trail_skew"] = rs.rolling(30, min_periods=15).skew()
    return panel


def wfo_select(panel: pd.DataFrame, q: float, n_folds: int = 5) -> pd.DataFrame:
    """Expanding WFO; return one row per test bar with each rule's selection mask."""
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    sig = panel["rvol_24"].to_numpy()
    tskew = panel["trail_skew"].to_numpy()
    out = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        Xtr, Xte = sc.transform(X[:split]), sc.transform(X[lo:hi])
        mu = Ridge(alpha=1.0).fit(Xtr, yz[:split]).predict(Xte)
        qr = QuantileRegressor(quantile=0.90, alpha=0.0, solver="highs")
        qup = qr.fit(Xtr, yz[:split]).predict(Xte)
        df = pd.DataFrame({
            "mu": mu, "qup": qup, "act": act[lo:hi],
            "sig": sig[lo:hi], "tskew": tskew[lo:hi],
        })
        # within-fold top-q thresholds (decision uses only train-period info? -
        # thresholds are cross-sectional within the OOS fold, standard for ranking)
        df["sel_mu"] = df["mu"] >= df["mu"].quantile(q)
        df["sel_qup"] = df["qup"] >= df["qup"].quantile(q)
        out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def run(freq: str, q: float = 0.95) -> None:
    print(f"\n{'='*70}\nFREQ {freq}  |  top-{(1-q)*100:.0f}% long basket, net of real cost\n{'='*70}")
    frames = []
    for sym in TIGHT:
        panel = load_panel(sym, freq)
        if panel is None:
            continue
        df = wfo_select(panel, q)
        if df.empty:
            continue
        df["cost"] = COST_BPS[sym]
        df["sym"] = sym
        frames.append(df)
    if not frames:
        print("  no data")
        return
    d = pd.concat(frames, ignore_index=True)

    def econ(mask: pd.Series, label: str) -> None:
        s = d[mask]
        if len(s) < 10:
            print(f"  {label:<14} n={len(s):<5} (too few)")
            return
        net = (s["act"] - s["cost"]).to_numpy()
        t, p = ttest_1samp(net, 0.0)
        print(f"  {label:<14} n={len(s):<5} gross={s['act'].mean():+.3f} "
              f"net={net.mean():+.3f}  t={t:+.2f} p={p:.3f}  hit={(s['act']>0).mean()*100:.0f}%")

    # selection-rule comparison
    econ(d["sel_mu"], "mu (baseline)")
    econ(d["sel_qup"], "q-upper 0.90")
    # gates applied ON TOP of mu selection, using OOS-fold median of the gate var
    hi_sig = d["sig"] >= d.groupby("sym")["sig"].transform("median")
    r_skew = d["tskew"] > 0
    econ(d["sel_mu"] & hi_sig, "mu | hi-sigma")
    econ(d["sel_mu"] & ~hi_sig, "mu | lo-sigma")
    econ(d["sel_mu"] & r_skew, "mu | rskew>0")
    econ(d["sel_mu"] & ~r_skew, "mu | rskew<=0")
    # tighter tail: top-1%
    thr99 = d.groupby("sym")["mu"].transform(lambda s: s.quantile(0.99))
    econ(d["mu"] >= thr99, "mu top-1%")


def main() -> None:
    for freq in ["2h", "3h", "1h", "15m"]:
        run(freq, q=0.95)


if __name__ == "__main__":
    main()
