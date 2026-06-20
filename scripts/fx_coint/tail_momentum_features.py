"""Hunt for NEW momentum features that lift the EUR/GBP/JPY 2h tail edge.

Model search is exhausted (OLS-linear is optimal); the only live lever is genuinely
ORTHOGONAL momentum signal.  We pre-specify a candidate set, then for each:
  (a) standalone OOS Spearman IC vs the vol-normalized target,
  (b) incremental lift: baseline(5 feat) vs baseline+candidate on the deployable
      top-5% 2h basket, net realistic Razor cost, day-clustered significance,
  (c) BH-FDR across candidates on the per-day improvement, to avoid forking paths.

All features are computed from PAST data only (decision-time observable).

Usage:
    uv run python scripts/fx_coint/tail_momentum_features.py
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

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
BASE = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]
warnings.filterwarnings("ignore")

COMMISSION_BPS = 0.60
_SPREAD_PIP = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
_PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def razor_cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMMISSION_BPS + (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4


def freq_bars_ext(df_1m: pl.DataFrame, freq: str, session=(7, 21)) -> pd.DataFrame:
    """Like reg_signal_hunt.build_freq_bars but also carries summed tick-rule flow."""
    t = df_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        pl.col("bucket").dt.truncate(freq).alias("bf"),
    )
    bars = (
        t.group_by("bf").agg(
            pl.col("mid").last(),
            pl.col("n_ticks").sum(),
            pl.col("flow_tick").sum().alias("flow_sum"),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
        ).rename({"bf": "bucket"}).sort("bucket").to_pandas()
    )
    bars["bucket"] = pd.to_datetime(bars["bucket"])
    hour = bars["bucket"].dt.hour
    keep = (hour >= session[0]) & (hour < session[1]) & (bars["bucket"].dt.dayofweek < 5)
    bars = bars[keep].reset_index(drop=True)
    step = np.timedelta64(rsh.FREQ_MINUTES[freq], "m")
    prev = bars["bucket"].shift(1).to_numpy()
    bars["contig"] = (bars["bucket"].to_numpy() - prev) == step
    bars.loc[0, "contig"] = False
    return bars


def build_panel_ext(bars: pd.DataFrame, vol_lookback=24) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    mid = b["mid"].to_numpy()
    r = np.empty(len(b))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~b["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    f = pd.DataFrame({"bucket": b["bucket"]})
    # --- baseline features ---
    f["r_1"] = rs.to_numpy()
    f["mom_short"] = rs.rolling(5, min_periods=3).sum().to_numpy()
    f["mom_long"] = rs.rolling(18, min_periods=9).sum().shift(5).to_numpy()
    f["rvol_24"] = rs.rolling(vol_lookback, min_periods=vol_lookback // 2).std().shift(1).to_numpy()
    f["hour"] = b["bucket"].dt.hour.astype(float).to_numpy()
    sigma = f["rvol_24"]
    f["sigma_h"] = sigma

    # --- CANDIDATE momentum features (decision-time observable) ---
    f["mom_3"] = rs.rolling(3, min_periods=2).sum().to_numpy()
    f["mom_9"] = rs.rolling(9, min_periods=5).sum().to_numpy()
    f["mom_12"] = rs.rolling(12, min_periods=6).sum().to_numpy()
    f["mom_36"] = rs.rolling(36, min_periods=18).sum().shift(5).to_numpy()
    f["mom_ewm"] = rs.ewm(halflife=6, min_periods=5).mean().to_numpy()
    f["mom_riskadj"] = (f["mom_short"] / sigma).to_numpy()           # Sharpe momentum
    f["mom_accel"] = (f["mom_short"] - rs.rolling(5).sum().shift(5)).to_numpy()  # recent vs older
    f["mom_consist"] = np.sign(rs).rolling(12, min_periods=6).mean().to_numpy()  # frac up
    f["mom_long_ra"] = (f["mom_long"] / sigma).to_numpy()
    # flow-weighted momentum (prior: FX flow ~ echoes price; test it anyway)
    f["flow_mom"] = pd.Series(b["flow_sum"].to_numpy()).rolling(5, min_periods=3).sum().to_numpy()

    ret_next = rs.shift(-1).to_numpy()
    f["ret_next_bps"] = ret_next
    f["target_z"] = ret_next / sigma.to_numpy()

    cand = ["mom_3", "mom_9", "mom_12", "mom_36", "mom_ewm", "mom_riskadj",
            "mom_accel", "mom_consist", "mom_long_ra", "flow_mom"]
    # Filter on BASELINE + target only (matches reg_signal_hunt.build_panel n).
    # Candidate columns kept with possible head-NaN; dropped per-candidate in wfo.
    finite = np.isfinite(f[BASE].to_numpy()).all(axis=1)
    finite &= np.isfinite(f["target_z"].to_numpy()) & (sigma.to_numpy() > 0)
    res = f[finite]
    if len(res) > 1:
        idx = res.index.to_numpy()
        gaps = np.where(np.diff(idx) != 1)[0] + 1
        res = res.drop(res.index[gaps])
    return res.reset_index(drop=True), cand


def wfo(panel, cols, q=0.95, n_folds=5):
    # drop rows where any of the selected feature cols is NaN (candidate warmup)
    panel = panel[np.isfinite(panel[cols].to_numpy()).all(axis=1)].reset_index(drop=True)
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[cols].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    sel_rows = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        pred = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])})
        sel_rows.append(df[df["pred"] >= df["pred"].quantile(q)])
    return pd.concat(sel_rows, ignore_index=True)


def bh_reject(pvals, alpha=0.1):
    p = np.asarray(pvals)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1)) / m
    passed = p[order] <= thresh
    rej = np.zeros(m, bool)
    if passed.any():
        kmax = np.where(passed)[0].max()
        rej[order[:kmax + 1]] = True
    return rej


def daily(d):
    return d.groupby(d["bucket"].dt.date)["net"].mean()


def main():
    panels = {}
    cand = None
    for sym in TIGHT:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        p, cand = build_panel_ext(freq_bars_ext(pl.read_parquet(src), "2h"))
        panels[sym] = p

    # ---- (a) standalone OOS IC of each candidate ----
    print("=== (a) standalone OOS Spearman IC of each candidate vs target_z (pooled) ===")
    ic_rows = []
    for c in cand:
        ics = []
        for p in panels.values():
            s = int(len(p) * 0.6)
            ic = spearmanr(p[c].to_numpy()[s:], p["target_z"].to_numpy()[s:]).statistic
            ics.append(ic)
        ic_rows.append((c, np.mean(ics)))
    for c, ic in sorted(ic_rows, key=lambda x: -abs(x[1])):
        print(f"  {c:>13} ic={ic:+.4f}")
    # baseline mom_short / mom_long IC for reference
    for c in ["mom_short", "mom_long"]:
        ics = [spearmanr(p[c].to_numpy()[int(len(p)*.6):], p["target_z"].to_numpy()[int(len(p)*.6):]).statistic
               for p in panels.values()]
        print(f"  {c:>13} ic={np.mean(ics):+.4f}  (baseline ref)")

    # ---- (b) incremental basket lift, baseline vs baseline+candidate ----
    print("\n=== (b) deployable top-5% basket: baseline vs baseline+candidate ===")
    # baseline
    base_sel = []
    for sym, p in panels.items():
        sel = wfo(p, BASE)
        sel["net"] = sel["act"] - razor_cost(sym)
        base_sel.append(sel)
    bsel = pd.concat(base_sel, ignore_index=True)
    bday = daily(bsel)
    bt, bp = ttest_1samp(bday, 0)
    print(f"  {'baseline':>20} net={bsel['net'].mean():+.3f} dayP={bp:.3f} n={len(bsel)}")

    rows = []
    for c in cand:
        sels = []
        for sym, p in panels.items():
            sel = wfo(p, BASE + [c])
            sel["net"] = sel["act"] - razor_cost(sym)
            sels.append(sel)
        csel = pd.concat(sels, ignore_index=True)
        cday = daily(csel)
        t, pv = ttest_1samp(cday, 0)
        # paired improvement on common days
        j = pd.concat([bday.rename("base"), cday.rename("cand")], axis=1).dropna()
        dt, dp = ttest_rel(j["cand"], j["base"]) if len(j) > 5 else (np.nan, np.nan)
        rows.append({"cand": c, "net": csel["net"].mean(), "dnet": csel["net"].mean() - bsel["net"].mean(),
                     "dayP": pv, "imp_t": float(dt), "imp_p": float(dp), "n": len(csel)})
    rdf = pd.DataFrame(rows)
    rdf["bh_imp"] = bh_reject(rdf["imp_p"].to_numpy(), alpha=0.1)
    rdf = rdf.sort_values("dnet", ascending=False)
    print(f"  {'cand':>13} {'net':>7} {'dnet':>7} {'dayP':>6} {'imp_t':>6} {'imp_p':>6} {'BH':>3}")
    for _, r in rdf.iterrows():
        print(f"  {r['cand']:>13} {r['net']:>+7.3f} {r['dnet']:>+7.3f} {r['dayP']:>6.3f} "
              f"{r['imp_t']:>+6.2f} {r['imp_p']:>6.3f} {'*' if r['bh_imp'] else '':>3}")
    print(f"\n  baseline net={bsel['net'].mean():+.3f}.  '*' = BH-FDR significant improvement over baseline.")


if __name__ == "__main__":
    main()
