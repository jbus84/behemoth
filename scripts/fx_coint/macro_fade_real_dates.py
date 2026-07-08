"""Macro event fade with REAL central bank dates.

Tests: FOMC, ECB, BOE meeting dates — post-announcement fade over next 1-3 trading days.
Uses actual historical event dates, causal expanding thresholds, real cost.

Usage:
    uv run python scripts/fx_coint/macro_fade_real_dates.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def load_daily(sym: str) -> pd.DataFrame:
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1d", session=(0, 24),
    )
    bars["ret_bps"] = np.log(bars["mid"]).diff() * 1e4
    return bars.set_index("bucket").sort_index()


# Real central bank meeting dates (approximate — use known schedule)
# FOMC: 8 meetings/year, typically Wed
FOMC_DATES = [
    date(2018,1,31), date(2018,3,21), date(2018,5,2), date(2018,6,13),
    date(2018,8,1), date(2018,9,26), date(2018,11,8), date(2018,12,19),
    date(2019,1,30), date(2019,3,20), date(2019,5,1), date(2019,6,19),
    date(2019,7,31), date(2019,9,18), date(2019,10,30), date(2019,12,11),
    date(2020,1,29), date(2020,3,15), date(2020,4,29), date(2020,6,10),
    date(2020,7,29), date(2020,9,16), date(2020,11,5), date(2020,12,16),
    date(2021,1,27), date(2021,3,17), date(2021,4,28), date(2021,6,16),
    date(2021,7,28), date(2021,9,22), date(2021,11,3), date(2021,12,15),
    date(2022,1,26), date(2022,3,16), date(2022,5,4), date(2022,6,15),
    date(2022,7,27), date(2022,9,21), date(2022,11,2), date(2022,12,14),
    date(2023,2,1), date(2023,3,22), date(2023,5,3), date(2023,6,14),
    date(2023,7,26), date(2023,9,20), date(2023,11,1), date(2023,12,13),
    date(2024,1,31), date(2024,3,20), date(2024,5,1), date(2024,6,12),
    date(2024,7,31), date(2024,9,18), date(2024,11,7), date(2024,12,18),
    date(2025,1,29), date(2025,3,19), date(2025,5,7), date(2025,6,18),
]

# ECB: roughly monthly Thu
ECB_DATES = [
    date(2018,1,25), date(2018,3,8), date(2018,4,26), date(2018,6,14),
    date(2018,7,26), date(2018,9,13), date(2018,10,25), date(2018,12,13),
    date(2019,1,24), date(2019,3,7), date(2019,4,10), date(2019,6,6),
    date(2019,7,25), date(2019,9,12), date(2019,10,24), date(2019,12,12),
    date(2020,1,23), date(2020,3,12), date(2020,4,30), date(2020,6,4),
    date(2020,7,16), date(2020,9,10), date(2020,10,29), date(2020,12,10),
    date(2021,1,21), date(2021,3,11), date(2021,4,22), date(2021,6,10),
    date(2021,7,22), date(2021,9,9), date(2021,10,28), date(2021,12,16),
    date(2022,2,3), date(2022,3,10), date(2022,4,14), date(2022,6,9),
    date(2022,7,21), date(2022,9,8), date(2022,10,27), date(2022,12,15),
    date(2023,2,2), date(2023,3,16), date(2023,5,4), date(2023,6,15),
    date(2023,7,27), date(2023,9,14), date(2023,10,26), date(2023,12,14),
    date(2024,1,25), date(2024,3,7), date(2024,4,11), date(2024,6,6),
    date(2024,7,18), date(2024,9,12), date(2024,10,17), date(2024,12,12),
    date(2025,1,30), date(2025,3,6), date(2025,4,17), date(2025,6,5),
]

# BOE: roughly monthly Thu
BOE_DATES = [
    date(2018,2,8), date(2018,3,22), date(2018,5,10), date(2018,6,21),
    date(2018,8,2), date(2018,9,13), date(2018,11,1), date(2018,12,20),
    date(2019,2,7), date(2019,3,21), date(2019,5,2), date(2019,6,20),
    date(2019,8,1), date(2019,9,19), date(2019,11,7), date(2019,12,19),
    date(2020,1,30), date(2020,3,11), date(2020,5,7), date(2020,6,18),
    date(2020,8,6), date(2020,9,17), date(2020,11,5), date(2020,12,17),
    date(2021,2,4), date(2021,3,18), date(2021,5,6), date(2021,6,24),
    date(2021,8,5), date(2021,9,23), date(2021,11,4), date(2021,12,16),
    date(2022,2,3), date(2022,3,17), date(2022,5,5), date(2022,6,16),
    date(2022,8,4), date(2022,9,22), date(2022,11,3), date(2022,12,15),
    date(2023,2,2), date(2023,3,23), date(2023,5,11), date(2023,6,22),
    date(2023,8,3), date(2023,9,21), date(2023,11,2), date(2023,12,14),
    date(2024,2,1), date(2024,3,21), date(2024,5,9), date(2024,6,20),
    date(2024,8,1), date(2024,9,19), date(2024,11,7), date(2024,12,19),
    date(2025,2,6), date(2025,3,20), date(2025,5,8), date(2025,6,19),
]


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
        print(f"  {label:>16} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}]")


def event_study(sym, event_dates, hold_days=1, q_select=1.0, warmup=12):
    df = load_daily(sym)
    mid = df["mid"].to_numpy()
    idx = df.index
    r = df["ret_bps"].to_numpy()
    contig = df["contig"].to_numpy()
    c = cost(sym)

    hist_abs = []
    nets, bks = [], []

    for ed in event_dates:
        try:
            loc = idx.get_loc(pd.Timestamp(ed))
        except KeyError:
            continue
        if loc + 1 >= len(idx) or not contig[loc]:
            continue
        # Event day return (open -> close of event day)
        r_event = r[loc]
        if np.isnan(r_event):
            continue
        # Post-event
        post_loc = loc + hold_days
        if post_loc >= len(idx):
            continue
        if hold_days == 1 and not contig[loc+1]:
            continue
        r_post = (np.log(mid[post_loc]) - np.log(mid[loc])) * 1e4

        abs_move = abs(r_event)
        if len(hist_abs) >= warmup:
            thr = np.quantile(hist_abs, q_select)
            if abs_move >= thr:
                # FADE the event move
                net = -r_post - c if r_event > 0 else r_post - c
                nets.append(net)
                bks.append(idx[loc])
        hist_abs.append(abs_move)

    return np.array(nets), np.array(bks)


def continuation_study(sym, event_dates, hold_days=1, q_select=1.0, warmup=12):
    df = load_daily(sym)
    mid = df["mid"].to_numpy()
    idx = df.index
    r = df["ret_bps"].to_numpy()
    contig = df["contig"].to_numpy()
    c = cost(sym)

    hist_abs = []
    nets, bks = [], []

    for ed in event_dates:
        try:
            loc = idx.get_loc(pd.Timestamp(ed))
        except KeyError:
            continue
        if loc + 1 >= len(idx) or not contig[loc]:
            continue
        r_event = r[loc]
        if np.isnan(r_event):
            continue
        post_loc = loc + hold_days
        if post_loc >= len(idx):
            continue
        if hold_days == 1 and not contig[loc+1]:
            continue
        r_post = (np.log(mid[post_loc]) - np.log(mid[loc])) * 1e4

        abs_move = abs(r_event)
        if len(hist_abs) >= warmup:
            thr = np.quantile(hist_abs, q_select)
            if abs_move >= thr:
                # CHASE the event move
                net = r_post - c if r_event > 0 else -r_post - c
                nets.append(net)
                bks.append(idx[loc])
        hist_abs.append(abs_move)

    return np.array(nets), np.array(bks)


def main():
    print("=" * 96)
    print("MACRO EVENT FADE — real FOMC/ECB/BOE dates, causal thresholds, real cost")
    print("=" * 96)

    for event_name, dates in [("FOMC", FOMC_DATES), ("ECB", ECB_DATES), ("BOE", BOE_DATES)]:
        print(f"\n### {event_name} — {len(dates)} events ###")
        for hold in (1, 2):
            print(f"\n  Hold {hold}d after event:")
            print(f"  {'pair':>8} {'n':>4} {'fadeNet':>8} {'fadeT':>6} {'contNet':>8} {'contT':>6}")
            for sym in PAIRS:
                f_net, f_bk = event_study(sym, dates, hold_days=hold, q_select=1.0)
                c_net, c_bk = continuation_study(sym, dates, hold_days=hold, q_select=1.0)
                f_str = f"n={len(f_net):>3} net={f_net.mean():>+7.2f}" if len(f_net) > 2 else "n/a"
                c_str = f"net={c_net.mean():>+7.2f}" if len(c_net) > 2 else "n/a"
                print(f"  {sym:>8} {f_str} {c_str}")

    # Selective (top-50% event moves)
    print("\n" + "=" * 96)
    print("SELECTIVE: top-50% event-day moves only")
    print("=" * 96)
    for event_name, dates in [("FOMC", FOMC_DATES), ("ECB", ECB_DATES), ("BOE", BOE_DATES)]:
        print(f"\n### {event_name} — top-50% |event move| ###")
        for hold in (1, 2):
            print(f"\n  Hold {hold}d:")
            all_fade, all_cont = [], []
            all_fade_bk, all_cont_bk = [], []
            for sym in PAIRS:
                f_net, f_bk = event_study(sym, dates, hold_days=hold, q_select=0.50)
                c_net, c_bk = continuation_study(sym, dates, hold_days=hold, q_select=0.50)
                if len(f_net) > 2:
                    all_fade.append(f_net)
                    all_fade_bk.append(f_bk)
                if len(c_net) > 2:
                    all_cont.append(c_net)
                    all_cont_bk.append(c_bk)
                line(f"{sym} fade", f_net, f_bk)
                line(f"{sym} cont", c_net, c_bk)
            if all_fade:
                line(f"POOLED fade", np.concatenate(all_fade), np.concatenate(all_fade_bk))
            if all_cont:
                line(f"POOLED cont", np.concatenate(all_cont), np.concatenate(all_cont_bk))


if __name__ == "__main__":
    main()
