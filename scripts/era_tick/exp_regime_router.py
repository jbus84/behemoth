"""Regime router test: can an EARLY trend signal predict which days momentum wins?

The thesis (from the confident-momentum result): ride-momentum beats cost on trending days
and bleeds on chop. So we don't need the CatBoost models to be profitable — we only need
them (or any causal regime signal) to tell us, ahead of time, whether a day is trending.
This script tests that directly, fully causally:

  1. Classify each day from its MORNING only (07:00-09:00 UTC): morning realized range and
     morning directionality |close-open| / (high-low). These mirror the repo's regime gates
     (high_range_q70/q80, velocity) at day granularity.
  2. Trade the AFTERNOON out-of-sample (09:00-17:00) with confident momentum, and — for the
     regime-switching test — also with the fade policy.
  3. Ask: does the morning trend signal separate winning afternoons from losing ones? Then
     simulate a router (momentum on high-trend days, else fade/flat) and compare net vs the
     always-on baselines.

If high morning-range/directionality days are the net-positive momentum days, the router
works and the ordinary-day losses are cut. Net is raw Dukascopy cost.
"""

from __future__ import annotations

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import summarize
from scripts.era_tick.policy import ConfidentMomentumPolicy, NaiveFadePolicy
from scripts.era_tick.tick_replay import TickReplay

CLASSIFY_END = "09:00"
TRADE_START = "09:00"


def _weekdays(start: str, end: str) -> list[str]:
    days = pd.bdate_range(start=start, end=end)  # business days only
    return [d.strftime("%Y-%m-%d") for d in days]


def _morning_score(symbol: str, day: str) -> dict | None:
    replay = TickReplay.for_day(symbol, day, start_hhmm="07:00", end_hhmm=CLASSIFY_END)
    if len(replay) < 200:
        return None
    mids = replay.mids.to_numpy()
    pip = replay.pip
    rng_pips = (mids.max() - mids.min()) / pip
    directionality = abs(mids[-1] - mids[0]) / (mids.max() - mids.min() + 1e-12)
    return {"morning_range_pips": rng_pips, "morning_dir": directionality}


def _afternoon_net(symbol: str, day: str, policy) -> dict | None:
    replay = TickReplay.for_day(symbol, day, start_hhmm=TRADE_START, end_hhmm="17:00")
    if len(replay) == 0:
        return None
    eng = TickEngine(policy, FillModel(pip=replay.pip), record_trace=False)
    s = summarize(eng.run(replay).trades)
    return {"n": s.n_trades, "net_total": s.total_net_pips, "net_per_trade": s.net_pips_per_trade}


def _day_row(symbol: str, day: str) -> dict | None:
    score = _morning_score(symbol, day)
    if score is None:
        return None
    mom = _afternoon_net(symbol, day, ConfidentMomentumPolicy(enter_t=3.0))
    fade = _afternoon_net(symbol, day, NaiveFadePolicy())
    if mom is None or fade is None:
        return None
    return {
        "day": day,
        **score,
        "mom_n": mom["n"],
        "mom_net": round(mom["net_total"], 2),
        "fade_net": round(fade["net_total"], 2),
    }


def _router(df: pd.DataFrame, signal: str, thresh: float) -> dict:
    """Momentum on high-signal days, fade on the rest; report blended totals."""
    trend = df[signal] >= thresh
    blended = df["mom_net"].where(trend, df["fade_net"])
    return {
        "signal": signal,
        "thresh": round(thresh, 3),
        "trend_days": int(trend.sum()),
        "router_net": round(blended.sum(), 1),
        "always_mom": round(df["mom_net"].sum(), 1),
        "always_fade": round(df["fade_net"].sum(), 1),
        "mom_on_trend": round(df.loc[trend, "mom_net"].sum(), 1),
        "mom_on_chop": round(df.loc[~trend, "mom_net"].sum(), 1),
    }


def main() -> None:
    symbol = "EURUSD"
    days = _weekdays("2024-03-01", "2024-07-31")
    rows = [r for d in days if (r := _day_row(symbol, d))]
    df = pd.DataFrame(rows)
    print(f"{len(df)} tradable days\n")
    print(df.to_string(index=False))

    print("\n--- does the morning signal separate momentum winners? (Spearman) ---")
    for sig in ("morning_range_pips", "morning_dir"):
        rho = df[sig].corr(df["mom_net"], method="spearman")
        print(f"  corr({sig}, mom_net) = {rho:+.3f}")

    print("\n--- router: momentum on high-signal days, fade otherwise (median split) ---")
    for sig in ("morning_range_pips", "morning_dir"):
        print("  " + str(_router(df, sig, df[sig].median())))


if __name__ == "__main__":
    main()
