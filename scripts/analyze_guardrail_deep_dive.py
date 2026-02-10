#!/usr/bin/env python3
"""
Guardrail deep-dive diagnostics:
1) Loss definition sensitivity.
2) Conditional expectancy by streak length (per symbol + per session).
3) Trigger/skip rate stability by year + session.
4) Worst-month attribution + concentration risk.

Outputs (per timeframe):
- data/analysis/<bar>_guardrail_loss_def_sensitivity.csv
- data/analysis/<bar>_guardrail_conditional_by_symbol.csv
- data/analysis/<bar>_guardrail_conditional_by_session.csv
- data/analysis/<bar>_guardrail_trigger_rates.csv
- data/analysis/<bar>_guardrail_worst_months.csv
- data/analysis/<bar>_guardrail_concentration.csv
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 7

LOSS_THRESHOLDS = [0.0, -0.5, -1.0, -2.0]

SESSIONS = [
    ("Asia", 0, 7),
    ("London", 7, 13),
    ("New_York", 13, 21),
    ("Late", 21, 24),
]

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", 15),
]


def _session_name(hour: int) -> str:
    for name, start, end in SESSIONS:
        if start <= hour < end:
            return name
    return "Unknown"


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(
            trades=0,
            mean_pnl=0.0,
            total_pnl=0.0,
            max_dd=0.0,
            sharpe=0.0,
            sharpe_active=0.0,
            sharpe_trade=0.0,
        )
    pnl = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def _apply_guardrail(df: pd.DataFrame, loss_threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("exit_ts").copy()
    keep = []
    skipped = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
        pnl = float(row.pnl_bps)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None, "pauses": 0}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            skipped.append(row)
            continue

        keep.append(row)

        if pnl > loss_threshold:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0
                st["pauses"] += 1

    kept_df = pd.DataFrame(keep) if keep else df.iloc[:0]
    skipped_df = pd.DataFrame(skipped) if skipped else df.iloc[:0]
    return kept_df, skipped_df


def _annotate_streaks(df: pd.DataFrame, loss_threshold: float) -> pd.DataFrame:
    df = df.sort_values("exit_ts").copy()
    streaks = {}
    prev_list = []
    for row in df.itertuples(index=False):
        pair = row.pair
        pnl = float(row.pnl_bps)
        prev = streaks.get(pair, 0)
        prev_list.append(prev)
        if pnl > loss_threshold:
            streaks[pair] = 0
        else:
            streaks[pair] = prev + 1
    df["prev_loss_streak"] = prev_list
    df["streak_bucket"] = df["prev_loss_streak"].clip(upper=3)
    df.loc[df["prev_loss_streak"] >= 3, "streak_bucket"] = 3
    return df


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        dt = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce")
        df["year"] = dt.dt.year
        df["year_month"] = dt.dt.to_period("M").astype(str)
        df["session"] = df["hour"].map(_session_name)

        # 1) Loss definition sensitivity
        rows = []
        for thresh in LOSS_THRESHOLDS:
            kept, skipped = _apply_guardrail(df, thresh)
            base = _metrics(df)
            guard = _metrics(kept)
            rows.append({
                "loss_threshold_bps": thresh,
                "guardrail": False,
                **base,
                "skipped_trades": 0,
                "skip_rate": 0.0,
            })
            rows.append({
                "loss_threshold_bps": thresh,
                "guardrail": True,
                **guard,
                "skipped_trades": int(len(skipped)),
                "skip_rate": float(len(skipped) / max(len(df), 1)),
            })
        pd.DataFrame(rows).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_loss_def_sensitivity.csv"), index=False)

        # Default threshold for deeper analyses
        default_thresh = 0.0
        annotated = _annotate_streaks(df, default_thresh)

        # 2) Conditional expectancy by streak length (per symbol + session)
        rows_symbol = []
        rows_session = []
        for (pair, bucket), sub in annotated.groupby(["pair", "streak_bucket"]):
            pnl = sub["pnl_bps"].to_numpy()
            rows_symbol.append({
                "pair": pair,
                "streak_bucket": int(bucket),
                "trades": int(len(pnl)),
                "mean_pnl": float(np.mean(pnl)) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
            })
        for (session, bucket), sub in annotated.groupby(["session", "streak_bucket"]):
            pnl = sub["pnl_bps"].to_numpy()
            rows_session.append({
                "session": session,
                "streak_bucket": int(bucket),
                "trades": int(len(pnl)),
                "mean_pnl": float(np.mean(pnl)) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
            })
        pd.DataFrame(rows_symbol).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_conditional_by_symbol.csv"), index=False)
        pd.DataFrame(rows_session).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_conditional_by_session.csv"), index=False)

        # 3) Trigger/skip rate stability by year + session
        kept, skipped = _apply_guardrail(df, default_thresh)
        df["kept"] = False
        df.loc[kept.index, "kept"] = True
        df["skipped"] = ~df["kept"]

        rows_trig = []
        for (year, session), sub in df.groupby(["year", "session"]):
            rows_trig.append({
                "year": int(year),
                "session": session,
                "trades": int(len(sub)),
                "kept_trades": int(sub["kept"].sum()),
                "skipped_trades": int(sub["skipped"].sum()),
                "skip_rate": float(sub["skipped"].mean()) if len(sub) else 0.0,
            })
        pd.DataFrame(rows_trig).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_trigger_rates.csv"), index=False)

        # 4) Worst-month attribution + concentration
        monthly = df.groupby("year_month")["pnl_bps"].sum().sort_values()
        n_worst = max(1, int(len(monthly) * 0.05))
        worst_months = monthly.head(n_worst).index.tolist()

        guard_df, _ = _apply_guardrail(df, default_thresh)
        guard_monthly = guard_df.groupby("year_month")["pnl_bps"].sum()

        rows_worst = []
        base_total = float(monthly.loc[worst_months].sum())
        guard_total = float(guard_monthly.reindex(worst_months).fillna(0.0).sum())
        removed = (guard_total - base_total) / abs(base_total) if base_total != 0 else 0.0
        rows_worst.append({
            "worst_months": len(worst_months),
            "baseline_total_pnl": base_total,
            "guardrail_total_pnl": guard_total,
            "loss_removed_pct": removed * 100.0,
        })
        pd.DataFrame(rows_worst).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_worst_months.csv"), index=False)

        # Concentration: top-N pair share of total PnL
        rows_conc = []
        for n in [1, 3, 5]:
            base_pair = df.groupby("pair")["pnl_bps"].sum().sort_values(ascending=False)
            guard_pair = guard_df.groupby("pair")["pnl_bps"].sum().sort_values(ascending=False)
            base_share = float(base_pair.head(n).sum() / base_pair.sum()) if base_pair.sum() else 0.0
            guard_share = float(guard_pair.head(n).sum() / guard_pair.sum()) if guard_pair.sum() else 0.0
            rows_conc.append({
                "top_n": n,
                "baseline_share": base_share,
                "guardrail_share": guard_share,
            })
        pd.DataFrame(rows_conc).to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_concentration.csv"), index=False)

        print(f"Saved guardrail deep-dive outputs for {label}")


if __name__ == "__main__":
    main()
