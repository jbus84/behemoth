"""Independent validation of the DAILY EURUSD+GBPUSD tail-long claim.

Claim under test (from behemoth-tail-wfo): daily (1d) long top-q on EURUSD+GBPUSD
survives where the 2h died — pooled q0.85 +9.2 bps/trade, both ERA halves positive,
no negative quarter.  This script reproduces it from scratch and stress-tests the
parts that look fragile:

  R1 reproduce  : pooled EUR+GBP daily q-sweep, day-clustered t + p.
  R2 honest CI  : day-block BOOTSTRAP 95% CI of the mean (heavy-tail robust; the
                  Student-t df~2-4 makes the t-test SE unreliable).
  R3 all 6 pairs: apply the SAME daily long-top-decile rule to every major.  If only
                  EUR/GBP work, the cell was cherry-picked from the sweep, not a factor.
  R4 vs naive   : does the Ridge prediction beat (a) long-every-day and (b) long by RAW
                  past-return (pure TSMOM)?  If not, the "model" adds nothing over drift.
  R5 multiplicity: the original search was ~5 q x 3 pairs x 2 freq = 30 cells; report
                  how the winner looks once you acknowledge the selection.

Usage:
    uv run python scripts/fx_coint/validate_daily_tail.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import FEATURE_COLS, build_panel  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440
ALL6 = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF"]
EURGBP = ["EURUSD", "GBPUSD"]
RNG = np.random.default_rng(0)

# realistic Pepperstone-Razor cost (commission-dominated)
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def daily_panel(sym):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = rsh.build_freq_bars(pl.read_parquet(src), "1d", session=(0, 24))
    return build_panel(bars, vol_lookback=5)


def wfo_trades(panel, q, n_folds=5, rank_by="pred"):
    """Long top-q basket per fold, ranked by `pred` (Ridge) or `r1` (raw momentum);
    return net (bps), bucket, raw r_1 and predicted score for each selected trade."""
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    r1 = panel["r_1"].to_numpy()
    bk = panel["bucket"].to_numpy()
    rows = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 20:
            continue
        sc = StandardScaler().fit(X[:split])
        pred = Ridge(alpha=1.0).fit(sc.transform(X[:split]), yz[:split]).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame({"pred": pred, "act": act[lo:hi], "r1": r1[lo:hi],
                           "bucket": pd.to_datetime(bk[lo:hi])})
        rows.append(df[df[rank_by] >= df[rank_by].quantile(q)])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def day_clustered(net, bucket):
    s = pd.Series(net, index=pd.to_datetime(bucket))
    daily = s.groupby(s.index.date).mean()
    if len(daily) < 3:
        return np.nan, np.nan, 0
    t, p = ttest_1samp(daily.to_numpy(), 0)
    return float(t), float(p), len(daily)


def block_bootstrap_ci(net, bucket, n_boot=5000):
    """Resample whole DAYS with replacement (preserves intraday clustering, robust to
    heavy tails) -> 95% CI and one-sided P(mean<=0) of the per-trade mean."""
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    days = list(s.groupby(level=0))
    day_arrays = [g.to_numpy() for _, g in days]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(day_arrays), len(day_arrays))
        means[b] = np.concatenate([day_arrays[i] for i in pick]).mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi), float((means <= 0).mean())


def pooled(pairs, q):
    nets, bks, r1s, preds = [], [], [], []
    for sym in pairs:
        tr = wfo_trades(daily_panel(sym), q)
        if tr.empty:
            continue
        nets.append((tr["act"] - cost(sym)).to_numpy())
        bks.append(tr["bucket"].to_numpy())
        r1s.append(tr["r1"].to_numpy())
        preds.append(tr["pred"].to_numpy())
    return (np.concatenate(nets), np.concatenate(bks),
            np.concatenate(r1s), np.concatenate(preds))


def main():
    print("=" * 78)
    print("R1 — reproduce pooled EUR+GBP daily q-sweep (net realistic Razor cost)")
    print("=" * 78)
    print(f"{'q':>5} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5} "
          f"{'boot95CI':>20} {'P(<=0)':>7}")
    for q in (0.80, 0.85, 0.90, 0.95):
        net, bk, _, _ = pooled(EURGBP, q)
        t, p, _ = day_clustered(net, bk)
        clo, chi, pneg = block_bootstrap_ci(net, bk)
        print(f"{q:>5.2f} {len(net):>5} {net.mean():>+8.2f} {t:>+6.2f} {p:>7.3f} "
              f"{(net > 0).mean() * 100:>4.0f}% [{clo:>+7.2f},{chi:>+7.2f}] {pneg:>7.3f}")

    print("\n" + "=" * 78)
    print("R3 — SAME daily long-top-decile (q0.85) on ALL 6 majors (cherry-pick check)")
    print("=" * 78)
    print(f"{'pair':>7} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5} {'pos_yrs':>7}")
    n_pos = 0
    for sym in ALL6:
        tr = wfo_trades(daily_panel(sym), 0.85)
        if tr.empty:
            continue
        net = (tr["act"] - cost(sym)).to_numpy()
        t, p, _ = day_clustered(net, tr["bucket"].to_numpy())
        yr = pd.Series(net, index=pd.to_datetime(tr["bucket"]).dt.year.to_numpy()).groupby(level=0).mean()
        pos = f"{int((yr > 0).sum())}/{len(yr)}"
        n_pos += net.mean() > 0
        print(f"{sym:>7} {len(net):>5} {net.mean():>+8.2f} {t:>+6.2f} {p:>7.3f} "
              f"{(net > 0).mean() * 100:>4.0f}% {pos:>7}")
    print(f"  -> {n_pos}/6 pairs net-positive.  (a real USD/momentum factor should be broad)")

    print("\n" + "=" * 78)
    print("R4 — does the Ridge prediction beat naive long & raw-momentum selection?")
    print("=" * 78)
    # baseline: long EVERY day; momentum: long top-15% by RAW r_1; model: top-15% by pred
    print(f"{'rule':>16} {'n':>5} {'meanNet':>8} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    # long-all
    all_net, all_bk = [], []
    for sym in EURGBP:
        p = daily_panel(sym)
        n = len(p)
        lo = int(n * 0.5) + 1
        all_net.append(p["ret_next_bps"].to_numpy()[lo:] - cost(sym))
        all_bk.append(p["bucket"].to_numpy()[lo:])
    an, ab = np.concatenate(all_net), np.concatenate(all_bk)
    t, p, _ = day_clustered(an, ab)
    print(f"{'long-all (OOS)':>20} {len(an):>5} {an.mean():>+8.2f} {t:>+6.2f} {p:>7.3f} "
          f"{(an > 0).mean() * 100:>4.0f}%")
    # raw momentum (rank by r_1) vs model (rank by pred), identical q
    for label, key in (("top-15% RAW r_1", "r1"), ("top-15% PRED (model)", "pred")):
        nets, bks = [], []
        for sym in EURGBP:
            tr = wfo_trades(daily_panel(sym), 0.85, rank_by=key)
            if tr.empty:
                continue
            nets.append((tr["act"] - cost(sym)).to_numpy())
            bks.append(tr["bucket"].to_numpy())
        nn, bb = np.concatenate(nets), np.concatenate(bks)
        t, p, _ = day_clustered(nn, bb)
        print(f"{label:>20} {len(nn):>5} {nn.mean():>+8.2f} {t:>+6.2f} {p:>7.3f} "
              f"{(nn > 0).mean() * 100:>4.0f}%")

    print("\nNotes: original search = 5 q x 3 pairs x 2 freq (~30 cells) + the 2h saga; the")
    print("daily EUR+GBP q0.85 winner must be read against that multiplicity.")


if __name__ == "__main__":
    main()
