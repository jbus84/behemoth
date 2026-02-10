#!/usr/bin/env python3
"""
Full leak audit:
1) Feature recomputation vs stored dataset (causality + alignment).
2) Source scan for forward-looking index usage.
3) Tick->bar close audit vs global bars (causality of bar construction).

Outputs:
- data/analysis/m5_leak_audit_feature_mismatch.csv
- data/analysis/m15_leak_audit_feature_mismatch.csv
- data/analysis/m5_leak_audit_summary.csv
- data/analysis/m15_leak_audit_summary.csv
- data/analysis/m5_tick_bar_audit.csv
- data/analysis/m15_tick_bar_audit.csv
- debunk/LEAK_AUDIT.md
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

import sys

sys.path.append(os.path.join(os.getcwd(), "src"))
sys.path.append(os.path.join(os.getcwd(), "pipelines"))

import build_events_m5 as m5
import build_events_m15 as m15

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"
DEBUNK_PATH = Path("debunk/LEAK_AUDIT.md")

YEAR_MIN = 2018
YEAR_MAX = 2025

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 15),
]


def _scan_forward_index(module) -> list[str]:
    hits = []
    src = Path(module.__file__).read_text()
    for line in src.splitlines():
        if "i +" in line or "i+ " in line or "i+1" in line or "i+2" in line:
            if "i+0" in line or "i + 0" in line:
                continue
            if "i+1" in line or "i + 1" in line or "i+2" in line or "i + 2" in line:
                hits.append(line.strip())
    return hits


def _pair_map(module) -> Dict[str, Tuple[str, str, str, str]]:
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def _load_pair_data(module, fx, fy, cx, cy):
    df = module.load_pair_data(fx, fy, cx, cy)
    if df is None or len(df) == 0:
        return None
    x = np.log(df["X"].to_numpy())
    y = np.log(df["Y"].to_numpy())
    ts = df["timestamp"].to_numpy()
    if np.issubdtype(ts.dtype, np.datetime64):
        ts = ts.astype("datetime64[ns]").astype("int64").astype(object)
    else:
        ts = ts.astype("int64").astype(object)
    return ts, x, y


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [
        "z_entry","z_velocity","spread_std","beta_stability","signal_beta_lookback",
        "hedge_beta_lookback","beta_mismatch","z_lag1","z_lag2","z_lag3",
        "dz_lag1","dz_lag2","beta_lag1","beta_lag2","beta","vol_ratio",
        "correlation_500","trend_strength","hour","day_of_week","ret_X_16b","ret_Y_16b",
        "ret_X_1h","ret_Y_1h","atr_ratio","entry_atr","vol_regime",
    ]


def _audit_features(label, path, module, bar_minutes):  # pragma: no cover
    df = pd.read_csv(path)
    df["timestamp"] = df["timestamp"].astype("int64")
    feature_cols = _feature_columns(df)
    mismatches = {c: 0 for c in feature_cols}
    total = 0
    missing_ts = 0

    pair_info = _pair_map(module)
    for pair, (fx, fy, cx, cy) in pair_info.items():
        sub = df[df["pair"] == pair]
        if sub.empty:
            continue
        loaded = _load_pair_data(module, fx, fy, cx, cy)
        if loaded is None:
            continue
        ts, x, y = loaded
        idx_map = {int(t): i for i, t in enumerate(ts)}

        betas, errors, ret_betas = module.compute_kalman_states(y, x)
        z_scores = module.compute_z_scores(errors)

        for row in sub.itertuples(index=False):
            entry_ts = int(row.timestamp)
            idx = idx_map.get(entry_ts)
            if idx is None or idx >= len(z_scores):
                missing_ts += 1
                continue
            feats = module.compute_features_at_entry(idx, y, x, betas, errors, ret_betas, z_scores, ts)
            total += 1
            for c in feature_cols:
                val = getattr(row, c)
                calc = feats.get(c, None)
                if calc is None:
                    mismatches[c] += 1
                    continue
                if isinstance(val, (int, float)) and isinstance(calc, (int, float)):
                    if abs(val - calc) > 1e-6:
                        mismatches[c] += 1
                else:
                    if val != calc:
                        mismatches[c] += 1

    rows = []
    for c in feature_cols:
        rows.append({
            "feature": c,
            "mismatch_count": mismatches[c],
            "mismatch_rate": (mismatches[c] / total) if total else 0.0,
            "samples": total,
        })
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, f"{label}_leak_audit_feature_mismatch.csv"), index=False)
    summary = pd.DataFrame([{
        "label": label,
        "samples": total,
        "missing_timestamps": missing_ts,
        "max_mismatch_rate": out["mismatch_rate"].max() if not out.empty else 0.0,
    }])
    summary.to_csv(os.path.join(OUT_DIR, f"{label}_leak_audit_summary.csv"), index=False)
    return out, summary


def _global_bars(symbol_file: str, close_col: str) -> pd.Series:
    df = pd.read_parquet(symbol_file, columns=["timestamp", close_col])
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").astype("int64")
    bar_id = ts
    series = pd.Series(df[close_col].to_numpy(), index=bar_id, name=close_col)
    return series


def _tick_bar_audit(label: str, module, bar_minutes: int) -> pd.DataFrame:  # pragma: no cover
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    pair_info = _pair_map(module)
    symbol_map = {}
    for _, fx, fy, cx, cy, *_ in module.PAIRS:
        symbol_map[fx] = cx
        symbol_map[fy] = cy

    rows = []
    for sym_file, close_col in symbol_map.items():
        sym = sym_file.split("_")[0]
        tick_dir = os.path.join(TICK_ROOT, sym)
        if not os.path.isdir(tick_dir):
            continue

        global_path = os.path.join(f"data/global_{bar_minutes}m", sym_file)
        if not os.path.exists(global_path):
            continue
        global_series = _global_bars(global_path, close_col)

        total = 0
        gt_05 = 0
        gt_1 = 0
        gt_2 = 0
        diffs = []
        align_choice = "start"

        for fname in sorted(os.listdir(tick_dir)):
            m = re.search(r"_(\d{6})_ticks\.parquet$", fname)
            if not m:
                continue
            y = int(m.group(1)[:4])
            if y < YEAR_MIN or y > YEAR_MAX:
                continue
            path = os.path.join(tick_dir, fname)
            tick = pd.read_parquet(path, columns=["timestamp", "mid"])
            if tick.empty:
                continue
            ts = pd.to_datetime(tick["timestamp"], utc=True).astype("int64").to_numpy()
            price = tick["mid"].to_numpy()
            bar_id_start = (ts // bar_ns) * bar_ns
            bar_id_end = bar_id_start + bar_ns

            def _diffs(bar_id):
                df = pd.DataFrame({"bar_id": bar_id, "price": price})
                close = df.groupby("bar_id")["price"].last()
                merged = pd.DataFrame({"tick_close": close}).join(global_series, how="inner")
                if merged.empty:
                    return None
                diff = (merged["tick_close"] - merged[close_col]).abs()
                diff_bps = (diff / merged[close_col]) * 10000.0
                return diff_bps

            diff_start = _diffs(bar_id_start)
            diff_end = _diffs(bar_id_end)

            # choose alignment with lower mean diff
            if diff_start is None and diff_end is None:
                continue
            if diff_end is None or (diff_start is not None and diff_start.mean() <= diff_end.mean()):
                diff_bps = diff_start
                align_choice = "start"
            else:
                diff_bps = diff_end
                align_choice = "end"

            diffs.append(diff_bps)
            total += len(diff_bps)
            gt_05 += int((diff_bps > 0.5).sum())
            gt_1 += int((diff_bps > 1.0).sum())
            gt_2 += int((diff_bps > 2.0).sum())

        if total == 0:
            continue
        all_diffs = pd.concat(diffs, ignore_index=True)
        rows.append({
            "symbol": sym,
            "bars": total,
            "alignment": align_choice,
            "diff_bps_mean": float(all_diffs.mean()),
            "diff_bps_p95": float(all_diffs.quantile(0.95)),
            "diff_bps_p99": float(all_diffs.quantile(0.99)),
            "pct_gt_0.5bp": gt_05 / total,
            "pct_gt_1bp": gt_1 / total,
            "pct_gt_2bp": gt_2 / total,
        })

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, f"{label}_tick_bar_audit.csv"), index=False)
    return out


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DEBUNK_PATH.parent, exist_ok=True)

    lines = []
    lines.append("# Leak Audit Report\n")

    for label, path, module, bar_minutes in CONFIGS:
        lines.append(f"## {label.upper()} Audit\n")
        lines.append("### Feature Recompute vs Dataset\n")
        feats, summary = _audit_features(label, path, module, bar_minutes)
        lines.append(f"- samples: {int(summary['samples'].iloc[0])}\n")
        lines.append(f"- missing timestamps: {int(summary['missing_timestamps'].iloc[0])}\n")
        lines.append(f"- max mismatch rate: {summary['max_mismatch_rate'].iloc[0]:.6f}\n")

        lines.append("### Source Scan (forward index usage)\n")
        hits = _scan_forward_index(module)
        if hits:
            lines.append(f"- forward-index patterns: {len(hits)} (manual review required)\n")
        else:
            lines.append("- forward-index patterns: 0\n")

        lines.append("### Tick->Bar Close Audit\n")
        tick = _tick_bar_audit(label, module, bar_minutes)
        lines.append(f"- symbols audited: {tick.shape[0]}\n")
        if not tick.empty:
            lines.append(f"- mean close diff (bps): {tick['diff_bps_mean'].mean():.4f}\n")
            lines.append(f"- p95 close diff (bps): {tick['diff_bps_p95'].mean():.4f}\n")
            lines.append(f"- pct >1bp (avg): {tick['pct_gt_1bp'].mean():.4f}\n")
        lines.append("")

    DEBUNK_PATH.write_text("".join(lines))
    print(f"Saved {DEBUNK_PATH}")


if __name__ == "__main__":
    main()
