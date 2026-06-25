"""Multi-temporal-resolution momentum: does adding 15-min (sub-bar) and 6-hour
(supra-bar) momentum improve the 2h Ridge tail model?  NO TEMPORAL LEAKAGE.

The baseline model decides at the CLOSE of 2h bar t (== open of bar t+1 ==
bucket_t + 2h) and predicts bar t+1's return.  Any finer/coarser momentum feature
must therefore use only bars that have fully CLOSED by bucket_t + 2h.

Leakage control: we compute momentum natively on 15m and 6h bar grids, stamp each
fine/coarse bar with its CLOSE time (bucket + bar_width), and attach to the 2h panel
with a BACKWARD merge_asof keyed on decision_time = bucket_t + 2h.  By construction the
attached bar's close <= decision_time, so no future information can enter.  An explicit
assert verifies it.

Each candidate (and grouped sets) is tested as an incremental add to the baseline on
the deployable top-5% 2h basket, net realistic Razor cost, identical WFO, day-clustered
significance, BH-FDR across candidates.

Usage:
    uv run python scripts/fx_coint/tail_multires_mom.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr, ttest_1samp, ttest_rel
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30, "6h": 360})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
BASE = FEATURE_COLS  # r_1, mom_short, mom_long, rvol_24, hour
warnings.filterwarnings("ignore")

COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def razor_cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def _bar_returns(df_1m: pl.DataFrame, freq: str, width_min: int,
                 session=(7, 21), apply_session=True) -> pd.DataFrame:
    """Build freq bars and their log-returns (bps), breaking returns across gaps.
    Returns DataFrame with bucket, close_time (=bucket+width), r (bps), contig."""
    t = df_1m.sort("bucket").with_columns(pl.col("bucket").dt.truncate(freq).alias("bf"))
    bars = (t.group_by("bf").agg(pl.col("mid").last()).rename({"bf": "bucket"})
            .sort("bucket").to_pandas())
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    if apply_session:
        h = bars["bucket"].dt.hour
        keep = (h >= session[0]) & (h < session[1]) & (bars["bucket"].dt.dayofweek < 5)
        bars = bars[keep].reset_index(drop=True)
    else:
        bars = bars[bars["bucket"].dt.dayofweek < 5].reset_index(drop=True)
    step = np.timedelta64(width_min, "m")
    prev = bars["bucket"].shift(1).to_numpy()
    contig = (bars["bucket"].to_numpy() - prev) == step
    contig[0] = False
    mid = bars["mid"].to_numpy()
    r = np.empty(len(bars))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~contig] = np.nan
    bars["r"] = r
    bars["contig"] = contig
    bars["close_time"] = bars["bucket"] + pd.Timedelta(minutes=width_min)
    return bars


def fine_momentum(df_1m: pl.DataFrame, freq: str, width_min: int, horizons: dict,
                  apply_session=True) -> pd.DataFrame:
    """Momentum (rolling sum of bar returns) at given resolution; keyed by close_time."""
    bars = _bar_returns(df_1m, freq, width_min, apply_session=apply_session)
    rs = pd.Series(bars["r"].to_numpy())
    out = pd.DataFrame({"close_time": bars["close_time"]})
    for name, k in horizons.items():
        out[name] = rs.rolling(k, min_periods=min(k, max(1, k // 2))).sum().to_numpy()
    return out.dropna().sort_values("close_time").reset_index(drop=True)


# candidate horizons
H15 = {"m15_30m": 2, "m15_1h": 4, "m15_2h": 8, "m15_4h": 16}   # 15-min grid
H6H = {"m6h_6h": 1, "m6h_12h": 2, "m6h_24h": 4}                # 6-hour grid
CAND = list(H15) + list(H6H)


def build_multires_panel(sym: str):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    raw = pl.read_parquet(src)
    panel = build_panel(rsh.build_freq_bars(raw, "2h")).copy()
    panel["decision_time"] = panel["bucket"] + pd.Timedelta(hours=2)
    panel = panel.sort_values("decision_time").reset_index(drop=True)

    m15 = fine_momentum(raw, "15m", 15, H15, apply_session=True)
    m6h = fine_momentum(raw, "6h", 360, H6H, apply_session=False)

    for fine in (m15, m6h):
        cols = [c for c in fine.columns if c != "close_time"]
        merged = pd.merge_asof(panel[["decision_time"]], fine,
                               left_on="decision_time", right_on="close_time",
                               direction="backward")
        # LEAKAGE ASSERT: every attached bar closed at or before the decision instant
        used = merged["close_time"].dropna()
        assert (used <= panel.loc[used.index, "decision_time"]).all(), "TEMPORAL LEAK"
        for c in cols:
            panel[c] = merged[c].to_numpy()
    return panel


def wfo(panel, cols, q=0.95, n_folds=5):
    p = panel[np.isfinite(panel[cols].to_numpy()).all(axis=1)].reset_index(drop=True)
    n = len(p)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = p[cols].to_numpy()
    yz = p["target_z"].to_numpy()
    act = p["ret_next_bps"].to_numpy()
    bk = p["bucket"].to_numpy()
    rows = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        pred = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        rows.append(df[df["pred"] >= df["pred"].quantile(q)])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def bh_reject(pvals, alpha=0.1):
    p = np.asarray(pvals)
    m = len(p)
    order = np.argsort(p)
    passed = p[order] <= alpha * np.arange(1, m + 1) / m
    rej = np.zeros(m, bool)
    if passed.any():
        rej[order[:np.where(passed)[0].max() + 1]] = True
    return rej


def daily(d):
    return d.groupby(d["bucket"].dt.date)["net"].mean()


def basket(panels, cols):
    sels = []
    for sym, p in panels.items():
        sel = wfo(p, cols)
        sel["net"] = sel["act"] - razor_cost(sym)
        sels.append(sel)
    return pd.concat(sels, ignore_index=True)


def main():
    panels = {s: build_multires_panel(s) for s in TIGHT}
    print("Leakage asserts passed (every fine/coarse bar closed <= decision instant).\n")

    # (a) standalone OOS IC of each multires candidate
    print("=== (a) standalone OOS Spearman IC vs target_z (pooled, holdout 40%) ===")
    for c in CAND:
        ics = []
        for p in panels.values():
            q = p[np.isfinite(p[c].to_numpy())]
            s = int(len(q) * 0.6)
            ics.append(spearmanr(q[c].to_numpy()[s:], q["target_z"].to_numpy()[s:]).statistic)
        print(f"  {c:>10} ic={np.mean(ics):+.4f}")

    # (b) incremental basket lift
    bsel = basket(panels, BASE)
    bday = daily(bsel)
    _, bp = ttest_1samp(bday, 0)
    print(f"\n=== (b) deployable top-5% basket: baseline net={bsel['net'].mean():+.3f} "
          f"dayP={bp:.3f} n={len(bsel)} ===")
    groups = {**{c: [c] for c in CAND},
              "ALL_15m": list(H15), "ALL_6h": list(H6H), "ALL_multires": CAND}
    rows = []
    for name, add in groups.items():
        csel = basket(panels, BASE + add)
        cday = daily(csel)
        _, pv = ttest_1samp(cday, 0)
        j = pd.concat([bday.rename("b"), cday.rename("c")], axis=1).dropna()
        dt, dp = ttest_rel(j["c"], j["b"]) if len(j) > 5 else (np.nan, np.nan)
        rows.append({"add": name, "net": csel["net"].mean(),
                     "dnet": csel["net"].mean() - bsel["net"].mean(),
                     "dayP": pv, "imp_t": float(dt), "imp_p": float(dp)})
    rdf = pd.DataFrame(rows)
    bh = bh_reject(rdf["imp_p"].to_numpy(), alpha=0.1)
    # directional: only an IMPROVEMENT if BH-significant AND imp_t > 0
    rdf["verdict"] = ["IMPROVE" if b and t > 0 else "DEGRADE" if b and t < 0 else ""
                      for b, t in zip(bh, rdf["imp_t"], strict=False)]
    rdf = rdf.sort_values("dnet", ascending=False)
    print(f"  {'add':>13} {'net':>7} {'dnet':>7} {'dayP':>6} {'imp_t':>6} {'imp_p':>6} {'verdict':>8}")
    for _, r in rdf.iterrows():
        print(f"  {r['add']:>13} {r['net']:>+7.3f} {r['dnet']:>+7.3f} {r['dayP']:>6.3f} "
              f"{r['imp_t']:>+6.2f} {r['imp_p']:>6.3f} {r['verdict']:>8}")
    print("\n  IMPROVE = BH-FDR significant AND positive; DEGRADE = BH-FDR significant AND negative.")


if __name__ == "__main__":
    main()
