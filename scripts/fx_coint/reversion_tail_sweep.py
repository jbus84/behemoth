"""Mean-reversion tail sweep across timeframes (30m -> 1d) to COMPLEMENT the
momentum tail strategy.  Where does fading the tails turn net-positive?

For each timeframe we form a decision-time reversion signal (vol-normalized recent
move) and trade a FADE-THE-TAILS book over the next bar:
  - oversold  (bottom-q of recent move) -> LONG  (expect bounce):  pnl = +ret_next - cost
  - overbought(top-q   of recent move)  -> SHORT (expect fade):    pnl = -ret_next - cost
Pool both legs = the reversion book.  The mirror (momentum book) net = -revGross - cost,
so at most one side clears cost; revGross's SIGN tells which regime the tail is in.

The rule is FIXED (no fitting -> no overfit), so we use the full panel with day-clustered
inference + a day-block bootstrap CI, and BH-FDR across the freq x signal grid (multiplicity).
No leakage: signal uses returns up to bar t; the trade captures bar t+1.

Usage:
    uv run python scripts/fx_coint/reversion_tail_sweep.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402
from scripts.fx_coint.reg_signal_hunt import build_panel  # noqa: E402

rsh.FREQ_MINUTES.update({"30m": 30, "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
                         "2d": 2880, "1w": 10080})
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
FREQS = ["30m", "1h", "2h", "4h", "1d", "2d", "1w"]
RNG = np.random.default_rng(0)

COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def panel_for(sym, freq):
    sess = (7, 21) if freq in ("30m", "1h", "2h", "4h") else (0, 24)
    vlb = {"1d": 5, "2d": 4, "1w": 3}.get(freq, 24)
    bars = rsh.build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
                               freq, session=sess)
    p = build_panel(bars, vol_lookback=vlb)
    return p if len(p) >= 80 else None


def fade_book(panel, sym, signal_col, q):
    """Fade the tails of `signal_col` (a recent-move proxy). Return per-trade net (bps,
    cost-paid, direction-correct) and bucket. Long oversold, short overbought."""
    s = panel[signal_col].to_numpy()
    ret = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    hi_thr = np.quantile(s, q)
    lo_thr = np.quantile(s, 1 - q)
    over = s >= hi_thr      # overbought -> short
    under = s <= lo_thr     # oversold -> long
    c = cost(sym)
    net = np.r_[ret[under] - c, -ret[over] - c]          # long leg, short leg
    gross = np.r_[ret[under], -ret[over]]                # reversion gross
    bkt = np.r_[bk[under], bk[over]]
    return gross, net, bkt


def day_clustered(net, bucket):
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    daily = s.groupby(level=0).mean()
    if len(daily) < 3:
        return np.nan, np.nan
    t, p = ttest_1samp(daily.to_numpy(), 0)
    return float(t), float(p)


def boot_ci(net, bucket, n_boot=3000):
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def pos_years(net, bucket):
    yr = pd.Series(net, index=pd.to_datetime(bucket).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def bh_reject(pvals, alpha=0.1):
    p = np.asarray(pvals)
    m = len(p)
    order = np.argsort(p)
    passed = p[order] <= alpha * np.arange(1, m + 1) / m
    rej = np.zeros(m, bool)
    if passed.any():
        rej[order[:np.where(passed)[0].max() + 1]] = True
    return rej


SIGNALS = {"fade_r1": "r_1", "fade_momS": "mom_short"}


def daily_series(sym):
    """Daily mid + bps log-returns (gap-broken), one bar series per pair."""
    bars = rsh.build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
                               "1d", session=(0, 24))
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def horizon_book(sym, lookback, H, q):
    """On daily bars: fade the past-`lookback`-day vol-normalized move, hold H days
    forward, NON-OVERLAPPING (step every H bars). Returns per-trade net (bps) + bucket."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)
    sig = (rs.rolling(lookback, min_periods=lookback // 2).sum()
           / (rs.rolling(20, min_periods=10).std() * np.sqrt(lookback))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (np.log(mid[H:]) - np.log(mid[:n - H])) * 1e4  # H-day forward return
    idx = np.arange(0, n, H)                                     # non-overlapping grid
    idx = idx[np.isfinite(sig[idx]) & np.isfinite(fwd[idx])]
    s, f, b = sig[idx], fwd[idx], bk[idx]
    hi, lo = np.quantile(s, q), np.quantile(s, 1 - q)
    over, under = s >= hi, s <= lo
    c = cost(sym)
    net = np.r_[f[under] - c, -f[over] - c]   # long oversold, short overbought
    return net, np.r_[b[under], b[over]]


def horizon_sweep(q=0.90, lookback=10):
    print("\n" + "=" * 92)
    print("PART 2 — SAME-PHENOMENON test: fade extended move on DAILY bars, sweep HOLD horizon H")
    print(f"  (pooled EUR/GBP/JPY, fade past-{lookback}d move top/bottom {int((1-q)*100)}%, "
          f"non-overlapping, net Razor cost)")
    print("=" * 92)
    print(f"{'H(days)':>8} {'n':>5} {'gross/H':>8} {'net':>8} {'t':>6} {'p':>7} "
          f"{'hit':>5} {'posYrs':>7} {'boot95CI':>20}")
    for H in (1, 2, 3, 5, 10, 20):
        nets, bks = [], []
        for sym in TIGHT:
            net, bk = horizon_book(sym, lookback, H, q)
            nets.append(net)
            bks.append(bk)
        net = np.concatenate(nets)
        bk = np.concatenate(bks)
        # non-overlapping -> trades ~independent; t-test on trade net + day-block boot
        t, pv = ttest_1samp(net, 0) if len(net) > 2 else (np.nan, np.nan)
        clo, chi = boot_ci(net, bk)
        py, ny = pos_years(net, bk)
        gross_per_day = (net.mean() + cost("EURUSD")) / H
        print(f"{H:>8} {len(net):>5} {gross_per_day:>+8.3f} {net.mean():>+8.3f} {t:>+6.2f} "
              f"{pv:>7.3f} {(net > 0).mean()*100:>4.0f}% {py}/{ny:>2} [{clo:>+7.2f},{chi:>+7.2f}]")
    print("\n  If net & significance GROW with H (peaking ~5-20d), the daily-1bar reversion and the")
    print("  weekly mean-reversion edge are the SAME phenomenon at different holding cadence.")


def main():
    q = 0.90
    print(f"MEAN-REVERSION TAIL SWEEP — fade top/bottom {int((1-q)*100)}% recent move, "
          f"pooled EUR/GBP/JPY, net Razor cost\n")
    print(f"{'freq':>5} {'signal':>9} {'n':>5} {'revGross':>9} {'revNet':>8} "
          f"{'dayT':>6} {'dayP':>7} {'hit':>5} {'posYrs':>7} {'boot95CI':>20} {'regime':>5}")
    rows = []
    for freq in FREQS:
        panels = {s: panel_for(s, freq) for s in TIGHT}
        for slabel, scol in SIGNALS.items():
            g, n, b = [], [], []
            for sym, p in panels.items():
                if p is None:
                    continue
                gg, nn, bb = fade_book(p, sym, scol, q)
                g.append(gg)
                n.append(nn)
                b.append(bb)
            if not n:
                continue
            gross = np.concatenate(g)
            net = np.concatenate(n)
            bk = np.concatenate(b)
            t, pv = day_clustered(net, bk)
            py, ny = pos_years(net, bk)
            rows.append({"freq": freq, "sig": slabel, "n": len(net), "gross": gross.mean(),
                         "net": net.mean(), "t": t, "p": pv, "bk": bk, "net_arr": net,
                         "hit": (net > 0).mean(), "py": f"{py}/{ny}",
                         "regime": "REV" if gross.mean() > 0 else "MOM"})
    bh = bh_reject([r["p"] for r in rows])
    for r, sig in zip(rows, bh, strict=False):
        clo, chi = boot_ci(r["net_arr"], r["bk"])
        star = " *" if (sig and r["net"] > 0) else ""
        print(f"{r['freq']:>5} {r['sig']:>9} {r['n']:>5} {r['gross']:>+9.3f} {r['net']:>+8.3f} "
              f"{r['t']:>+6.2f} {r['p']:>7.3f} {r['hit']*100:>4.0f}% {r['py']:>7} "
              f"[{clo:>+7.2f},{chi:>+7.2f}] {r['regime']:>5}{star}")
    print("\n  revGross>0 => tail MEAN-REVERTS (fade is the edge); <0 => tail CONTINUES (momentum).")
    print("  revNet = revGross - cost.  '*' = BH-FDR significant net-positive reversion book.")


if __name__ == "__main__":
    main()
    horizon_sweep()
