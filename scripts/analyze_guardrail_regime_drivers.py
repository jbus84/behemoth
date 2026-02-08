#!/usr/bin/env python3
"""
Analyze regime drivers behind loss-streaks (why guardrail works).

We tag each trade with the loss-streak prior to entry and compare
feature distributions for:
- normal regime (prev_loss_streak <=1)
- loss-streak regime (prev_loss_streak >=2)

Outputs:
- data/analysis/<bar>_guardrail_regime_driver_summary.csv
- data/analysis/<bar>_guardrail_regime_driver_features.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15
import build_meta_dataset_v3_m5 as m5

OUT_DIR = "data/analysis"

Z_ENTRY = 1.5
Z_STOP = 4.0
Z_LOOKBACK = 750
LOSS_STREAK = 3
COOLDOWN_DAYS = 7

MIN_GAP = 20
MAX_HOLD = 500

FEATURES = [
    "beta_stability",
    "correlation_500",
    "spread_std",
    "vol_ratio",
    "trend_strength",
    "beta_mismatch",
    "vol_regime",
]


def _exit_hit(direction: int, z: float) -> bool:
    if direction == 1:
        return z < 0 or z > Z_STOP
    return z > 0 or z < -Z_STOP


def build_trades_with_features(mod) -> pd.DataFrame:
    trades = []
    for name, fx, fy, cx, cy, _, _ in mod.PAIRS:
        df = mod.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        betas, errors, ret_betas = mod.compute_kalman_states(y, x)
        z_scores = mod.compute_z_scores(errors, window=Z_LOOKBACK)

        last_entry = -10_000
        start_idx = max(Z_LOOKBACK, 500)
        for i in range(start_idx, len(y) - 2):
            z = z_scores[i]
            if abs(z) < Z_ENTRY or i - last_entry < MIN_GAP:
                continue

            beta = betas[i]
            if beta < 0.98:
                active_leg = "Y"
            elif beta > 1.02:
                active_leg = "X"
            else:
                continue

            direction = 1 if z > 0 else -1
            active = y if active_leg == "Y" else x
            entry_price = active[i]
            entry_ts = int(ts[i])

            exit_idx = min(i + MAX_HOLD, len(z_scores) - 1)
            for j in range(i + 1, exit_idx + 1):
                if _exit_hit(direction, z_scores[j]):
                    exit_idx = j
                    break

            pnl = float(direction * (active[exit_idx] - entry_price) * 10000.0)
            exit_ts = int(ts[exit_idx])

            # features at entry (causal)
            feats = mod.compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts)

            row = {
                "pair": name,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "pnl": pnl,
            }
            for f in FEATURES:
                row[f] = float(feats.get(f, 0.0))
            trades.append(row)
            last_entry = i

    return pd.DataFrame(trades).sort_values(["pair", "exit_ts"])


def add_prev_loss_streak(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades["prev_loss_streak"] = 0

    for pair, sub in trades.groupby("pair"):
        streak = 0
        for idx in sub.index:
            trades.loc[idx, "prev_loss_streak"] = streak
            pnl = trades.loc[idx, "pnl"]
            if pnl > 0:
                streak = 0
            else:
                streak += 1

    return trades


def summarize(trades: pd.DataFrame, label: str):
    # split regimes
    normal = trades[trades["prev_loss_streak"] <= 1]
    bad = trades[trades["prev_loss_streak"] >= 2]

    rows = []
    for name, sub in [("normal", normal), ("loss_streak", bad)]:
        row = {"label": label, "regime": name, "count": int(len(sub))}
        for f in FEATURES:
            row[f"{f}_mean"] = float(sub[f].mean()) if len(sub) else 0.0
            row[f"{f}_p50"] = float(sub[f].quantile(0.5)) if len(sub) else 0.0
            row[f"{f}_p95"] = float(sub[f].quantile(0.95)) if len(sub) else 0.0
        row["mean_pnl"] = float(sub["pnl"].mean()) if len(sub) else 0.0
        row["win_rate"] = float((sub["pnl"] > 0).mean()) if len(sub) else 0.0
        rows.append(row)

    # compute simple effect sizes (difference in means)
    effects = {"label": label, "regime": "effect_size"}
    for f in FEATURES:
        effects[f"{f}_mean"] = float(bad[f].mean() - normal[f].mean()) if len(bad) else 0.0
    effects["mean_pnl"] = float(bad["pnl"].mean() - normal["pnl"].mean()) if len(bad) else 0.0
    effects["win_rate"] = float((bad["pnl"] > 0).mean() - (normal["pnl"] > 0).mean()) if len(bad) else 0.0
    rows.append(effects)

    return pd.DataFrame(rows)


def per_feature_stats(trades: pd.DataFrame, label: str) -> pd.DataFrame:
    out = []
    normal = trades[trades["prev_loss_streak"] <= 1]
    bad = trades[trades["prev_loss_streak"] >= 2]

    for f in FEATURES:
        out.append({
            "label": label,
            "feature": f,
            "normal_mean": float(normal[f].mean()),
            "loss_streak_mean": float(bad[f].mean()),
            "diff": float(bad[f].mean() - normal[f].mean()),
            "normal_p50": float(normal[f].quantile(0.5)),
            "loss_streak_p50": float(bad[f].quantile(0.5)),
            "normal_p95": float(normal[f].quantile(0.95)),
            "loss_streak_p95": float(bad[f].quantile(0.95)),
        })

    return pd.DataFrame(out)


def run(mod, label: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    trades = build_trades_with_features(mod)
    trades = add_prev_loss_streak(trades)

    summary = summarize(trades, label)
    summary.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_regime_driver_summary.csv"), index=False)

    features = per_feature_stats(trades, label)
    features.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_regime_driver_features.csv"), index=False)

    print(f"Saved regime driver outputs for {label}")


def main() -> None:
    run(m5, "m5")
    run(m15, "m15")


if __name__ == "__main__":
    main()
