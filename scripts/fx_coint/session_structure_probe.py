"""Session structure probe: London open, NY open, overlap effects on 1h bars.

Tests hypotheses from worktree doc:
- Morning (09-10 UTC): reversion
- Afternoon (12-16 UTC): momentum
- 11:00 spike in top-5% tail

Usage:
    uv run python scripts/fx_coint/session_structure_probe.py
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

rsh.FREQ_MINUTES.update({"1h": 60})
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def load_hourly(sym: str) -> pd.DataFrame:
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1h", session=(0, 24),
    )
    bars["ret_bps"] = np.log(bars["mid"]).diff() * 1e4
    bars = bars.set_index("bucket").sort_index()
    return bars


def boot_ci(net, buckets, n_boot=3000):
    if len(net) < 3:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(buckets).year)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def pos_years(net, buckets):
    yr = pd.Series(net, index=pd.to_datetime(buckets).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def line(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>20} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    print(f"  {label:>20} n={len(net):>5} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}]")


def session_probe(sym: str) -> dict:
    df = load_hourly(sym)
    r = df["ret_bps"].to_numpy()
    next_r = df["ret_bps"].shift(-1).to_numpy()
    hour = df.index.hour.to_numpy()
    contig = df["contig"].to_numpy()
    bk = df.index.to_numpy()
    c = cost(sym)

    results = {}
    for session_name, hrs in [
        ("London 07-09", [7, 8]),
        ("London 09-10", [9]),
        ("London 10-11", [10]),
        ("London 11-12", [11]),
        ("Overlap 12-16", [12, 13, 14, 15]),
        ("NY 13-16", [13, 14, 15]),
        ("NY 16-17", [16]),
        ("Evening 17-21", [17, 18, 19, 20]),
        ("Asia 00-07", [0, 1, 2, 3, 4, 5, 6]),
    ]:
        # Strategy 1: momentum (same direction)
        nets_mom = []
        bks_mom = []
        # Strategy 2: reversion (opposite direction)
        nets_rev = []
        bks_rev = []
        for i in range(len(r) - 1):
            if not contig[i] or not contig[i+1] or hour[i] not in hrs:
                continue
            if np.isnan(r[i]) or np.isnan(next_r[i]):
                continue
            # momentum
            nets_mom.append(next_r[i] - c if r[i] > 0 else -next_r[i] - c)
            bks_mom.append(bk[i])
            # reversion
            nets_rev.append(-next_r[i] - c if r[i] > 0 else next_r[i] - c)
            bks_rev.append(bk[i])

        results[session_name] = {
            "mom": (np.array(nets_mom), np.array(bks_mom)),
            "rev": (np.array(nets_rev), np.array(bks_rev)),
        }
    return results


def tail_session_probe(sym: str, pct: float = 0.05) -> dict:
    """Only for extreme moves (top-pct by |return|) within each session."""
    df = load_hourly(sym)
    r = df["ret_bps"].to_numpy()
    next_r = df["ret_bps"].shift(-1).to_numpy()
    hour = df.index.hour.to_numpy()
    contig = df["contig"].to_numpy()
    bk = df.index.to_numpy()
    c = cost(sym)

    results = {}
    for session_name, hrs in [
        ("London 07-09", [7, 8]),
        ("London 09-10", [9]),
        ("London 10-11", [10]),
        ("London 11-12", [11]),
        ("Overlap 12-16", [12, 13, 14, 15]),
        ("NY 13-16", [13, 14, 15]),
        ("Evening 17-21", [17, 18, 19, 20]),
    ]:
        nets_mom, bks_mom = [], []
        nets_rev, bks_rev = [], []
        # Find threshold
        mask = np.isin(hour, hrs) & contig & np.isfinite(r)
        abs_r = np.abs(r[mask])
        if len(abs_r) < 100:
            continue
        thr = np.quantile(abs_r, 1 - pct)
        for i in range(len(r) - 1):
            if not contig[i] or not contig[i+1] or hour[i] not in hrs:
                continue
            if np.isnan(r[i]) or np.isnan(next_r[i]) or abs(r[i]) < thr:
                continue
            nets_mom.append(next_r[i] - c if r[i] > 0 else -next_r[i] - c)
            bks_mom.append(bk[i])
            nets_rev.append(-next_r[i] - c if r[i] > 0 else next_r[i] - c)
            bks_rev.append(bk[i])
        results[session_name] = {
            "mom": (np.array(nets_mom), np.array(bks_mom)),
            "rev": (np.array(nets_rev), np.array(bks_rev)),
        }
    return results


def main():
    print("=" * 100)
    print("SESSION STRUCTURE PROBE — all bars, momentum vs reversion by session hour")
    print("=" * 100)
    for sym in PAIRS:
        print(f"\n### {sym} ###")
        res = session_probe(sym)
        for session, data in res.items():
            mom_net, mom_bk = data["mom"]
            rev_net, rev_bk = data["rev"]
            line(f"{session} MOM", mom_net, mom_bk)
            line(f"{session} REV", rev_net, rev_bk)

    print("\n" + "=" * 100)
    print("TAIL SESSION PROBE — top-5% |return| bars only, by session")
    print("=" * 100)
    for sym in PAIRS:
        print(f"\n### {sym} ###")
        res = tail_session_probe(sym, pct=0.05)
        for session, data in res.items():
            mom_net, mom_bk = data["mom"]
            rev_net, rev_bk = data["rev"]
            if len(mom_net) > 3:
                line(f"{session} MOM", mom_net, mom_bk)
            if len(rev_net) > 3:
                line(f"{session} REV", rev_net, rev_bk)


if __name__ == "__main__":
    main()
