#!/usr/bin/env python3
"""
Integrity audit for MOM strategy datasets (M5/M15).
Focus: causality, data integrity, PnL reconciliation, guardrail timing sensitivity.

Outputs:
- debunk/INTEGRITY_AUDIT.md
- data/analysis/integrity_audit_summary.csv
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
from pipelines import build_events_m5 as m5
from pipelines import build_events_m15 as m15


@dataclass
class TFConfig:
    label: str
    events_path: str
    module: object
    bar_minutes: int
    max_hold: int


CONFIGS = [
    TFConfig("m5", "data/events/events_m5_8yr_v3_mom.csv", m5, 5, 500),
    TFConfig("m15", "data/events/events_m15_8yr_v3_mom.csv", m15, 15, 500),
]

OUT_MD = Path("debunk/INTEGRITY_AUDIT.md")
OUT_CSV = Path("data/analysis/integrity_audit_summary.csv")

LOSS_STREAK = 3
COOLDOWN_DAYS = 14


@dataclass
class TestResult:
    name: str
    status: str
    details: str


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnls: np.ndarray, timestamps: np.ndarray) -> dict:
    if len(pnls) == 0:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    return dict(
        trades=int(len(pnls)),
        mean_pnl=float(np.mean(pnls)),
        total_pnl=float(np.sum(pnls)),
        max_dd=_max_dd(pnls),
        sharpe=sharpe_daily(pnls, timestamps),
    )


def _load_pair_data(module, fx, fy, cx, cy):
    df = module.load_pair_data(fx, fy, cx, cy)
    if df is None:
        return None
    x = np.log(df["X"].to_numpy())
    y = np.log(df["Y"].to_numpy())
    ts = df["timestamp"].to_numpy()
    if np.issubdtype(ts.dtype, np.datetime64):
        ts = ts.astype("datetime64[ns]").astype("int64")
    else:
        ts = ts.astype("int64")
    return ts, x, y


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def _mode_delta(deltas: np.ndarray) -> int:
    if len(deltas) == 0:
        return 0
    values, counts = np.unique(deltas, return_counts=True)
    return int(values[np.argmax(counts)])


def _apply_guardrail(df: pd.DataFrame, ts_field: str) -> pd.DataFrame:
    df = df.sort_values(ts_field).copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(getattr(row, ts_field))
        pnl = float(row.pnl_bps)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        keep.append(row)

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    if not keep:
        return df.iloc[:0]
    return pd.DataFrame(keep)


def _concurrency_max(entry_ts: np.ndarray, exit_ts: np.ndarray) -> int:
    events = []
    for s, e in zip(entry_ts, exit_ts):
        events.append((int(s), 1))
        events.append((int(e), -1))
    events.sort(key=lambda x: (x[0], x[1]))  # exits before entries at same ts
    cur = 0
    max_cur = 0
    for _, delta in events:
        cur += delta
        if cur > max_cur:
            max_cur = cur
    return max_cur


def _scan_outcome_usage() -> list[str]:
    hits = []
    pattern = re.compile(r"\boutcome\b")
    for root, _, files in os.walk("scripts"):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            try:
                text = Path(path).read_text()
            except Exception:
                continue
            if "outcome" in text:
                for line in text.splitlines():
                    if pattern.search(line):
                        hits.append(f"{path}:{line.strip()}")
    return hits


def _feature_lookahead_scan(module) -> bool | None:
    if not hasattr(module, "compute_features_at_entry"):
        return None
    try:
        src = inspect.getsource(module.compute_features_at_entry)
    except Exception:
        return None
    pattern = re.compile(r"i\s*\+\s*\d")
    return bool(pattern.search(src))


def _audit_timeframe(cfg: TFConfig) -> tuple[list[TestResult], dict]:
    results: list[TestResult] = []
    df = pd.read_csv(cfg.events_path)
    df["timestamp"] = df["timestamp"].astype("int64")

    bar_ns = int(pd.Timedelta(minutes=cfg.bar_minutes).value)
    # simulate_trade uses entry_idx + (max_hold - 1) for timeouts
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= cfg.max_hold).astype(int)
    df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

    pair_info = _pair_map(cfg.module)
    pair_cache = {}
    idx_cache = {}

    # Data integrity: timestamp regularity per pair
    dup_total = 0
    irregular_total = 0
    total_diffs = 0
    mode_delta = None

    for name in pair_info:
        fx, fy, cx, cy = pair_info[name]
        loaded = _load_pair_data(cfg.module, fx, fy, cx, cy)
        if loaded is None:
            continue
        ts, x, y = loaded
        pair_cache[name] = (ts, x, y)
        idx_cache[name] = {int(t): i for i, t in enumerate(ts)}
        deltas = np.diff(ts)
        if len(deltas) == 0:
            continue
        md = _mode_delta(deltas)
        mode_delta = md if mode_delta is None else mode_delta
        dup_total += int((deltas == 0).sum())
        irregular_total += int((deltas != md).sum())
        total_diffs += len(deltas)

    if total_diffs == 0:
        results.append(TestResult("Timestamp regularity", "WARN", "No deltas available."))
    else:
        irregular_rate = irregular_total / total_diffs
        dup_rate = dup_total / total_diffs
        status = "PASS"
        if irregular_rate > 0.30 or dup_rate > 0.001:
            status = "WARN"
        results.append(
            TestResult(
                "Timestamp regularity",
                status,
                f"mode_delta_ns={mode_delta}, irregular_rate={irregular_rate:.2%}, dup_rate={dup_rate:.3%}",
            )
        )

    # Core counters
    missing_ts = 0
    missing_pair = 0
    early_count = 0
    invalid_duration = 0
    invalid_active_leg = 0
    out_of_range = 0

    pnl_diff_abs = []
    pnl_diff_gt = 0
    pnl_diff_max = 0.0

    nextbar_delta = []
    nextbar_flip = 0

    entry_ts_list = []
    exit_ts_list = []

    # Universe stability counts
    df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year
    years = list(range(2018, 2026))
    pair_year_counts = df.groupby(["pair", "year"]).size().unstack(fill_value=0)
    unstable_pairs = []
    for pair, row in pair_year_counts.iterrows():
        zeros = [y for y in years if row.get(y, 0) == 0]
        # check any 2+ consecutive years missing
        consec = 0
        max_consec = 0
        for y in years:
            if row.get(y, 0) == 0:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        if max_consec >= 2:
            unstable_pairs.append((pair, max_consec))

    # Iterate trades
    for row in df.itertuples(index=False):
        pair = row.pair
        if pair not in pair_cache:
            missing_pair += 1
            continue
        ts, x, y = pair_cache[pair]
        idx_map = idx_cache[pair]

        entry_ts = int(row.timestamp)
        entry_idx = idx_map.get(entry_ts)
        if entry_idx is None:
            missing_ts += 1
            continue

        if entry_idx < 500:
            early_count += 1

        duration = int(row.duration_bars)
        if duration <= 0 or duration > cfg.max_hold:
            invalid_duration += 1

        exit_idx = entry_idx + (duration - 1 if duration >= cfg.max_hold else duration)
        if exit_idx >= len(ts):
            out_of_range += 1
            continue

        active_leg = row.active_leg
        if active_leg not in ("X", "Y"):
            invalid_active_leg += 1
            continue

        direction = 1 if row.side == "LONG" else -1
        active = y if active_leg == "Y" else x

        pnl_calc = direction * (active[exit_idx] - active[entry_idx]) * 10000.0
        diff = pnl_calc - float(row.pnl_bps)
        abs_diff = abs(diff)
        pnl_diff_abs.append(abs_diff)
        pnl_diff_max = max(pnl_diff_max, abs_diff)
        if abs_diff > 0.1:
            pnl_diff_gt += 1

        # Next-bar entry sensitivity
        if entry_idx + 1 < len(active):
            pnl_next = direction * (active[exit_idx] - active[entry_idx + 1]) * 10000.0
            delta = pnl_next - float(row.pnl_bps)
            nextbar_delta.append(delta)
            if (pnl_next > 0) != (float(row.pnl_bps) > 0):
                nextbar_flip += 1

        entry_ts_list.append(entry_ts)
        exit_ts_list.append(int(row.exit_ts))

    # Entry index check
    status = "PASS" if early_count == 0 else "FAIL"
    results.append(
        TestResult(
            "Z-window entry index",
            status,
            f"entries_before_500={early_count}",
        )
    )

    # Missing timestamp alignment
    total_rows = len(df)
    missing_rate = missing_ts / max(total_rows, 1)
    status = "PASS" if missing_rate < 0.001 else "WARN"
    results.append(
        TestResult(
            "Entry timestamp alignment",
            status,
            f"missing_ts={missing_ts} ({missing_rate:.2%}), missing_pair={missing_pair}",
        )
    )

    # Duration bounds
    status = "PASS" if invalid_duration == 0 and out_of_range == 0 else "FAIL"
    results.append(
        TestResult(
            "Duration bounds",
            status,
            f"invalid_duration={invalid_duration}, out_of_range={out_of_range}",
        )
    )

    # Active leg validity
    status = "PASS" if invalid_active_leg == 0 else "FAIL"
    results.append(
        TestResult(
            "Active leg validity",
            status,
            f"invalid_active_leg={invalid_active_leg}",
        )
    )

    # PnL reconciliation
    if pnl_diff_abs:
        abs_arr = np.asarray(pnl_diff_abs)
        mismatch_rate = pnl_diff_gt / len(abs_arr)
        status = "PASS"
        if mismatch_rate > 0.05:
            status = "FAIL"
        elif mismatch_rate > 0.01:
            status = "WARN"
        results.append(
            TestResult(
                "PnL recompute",
                status,
                f"mean_abs={abs_arr.mean():.4f}, p95_abs={np.quantile(abs_arr, 0.95):.4f}, max_abs={pnl_diff_max:.4f}, mismatch_rate>{0.1:.1f}bps={mismatch_rate:.2%}",
            )
        )

    # Next-bar entry sensitivity
    if nextbar_delta:
        delta_arr = np.asarray(nextbar_delta)
        delta_mean = float(delta_arr.mean())
        flip_rate = nextbar_flip / len(delta_arr)
        status = "PASS" if delta_mean >= -1.0 else "WARN"
        results.append(
            TestResult(
                "Next-bar entry sensitivity",
                status,
                f"delta_mean={delta_mean:.3f} bps, delta_p95={np.quantile(delta_arr, 0.95):.3f}, flip_rate={flip_rate:.2%}",
            )
        )

    # Guardrail timing sensitivity (entry vs exit ordering)
    guard_exit = _apply_guardrail(df, "exit_ts")
    guard_entry = _apply_guardrail(df, "timestamp")
    m_exit = _metrics(guard_exit["pnl_bps"].to_numpy(), guard_exit["exit_ts"].to_numpy())
    m_entry = _metrics(guard_entry["pnl_bps"].to_numpy(), guard_entry["exit_ts"].to_numpy())

    trade_diff = (m_entry["trades"] - m_exit["trades"]) / max(m_exit["trades"], 1)
    mean_diff = m_entry["mean_pnl"] - m_exit["mean_pnl"]
    status = "PASS"
    if abs(trade_diff) > 0.05 or abs(mean_diff) > 1.0:
        status = "WARN"
    results.append(
        TestResult(
            "Guardrail timing sensitivity",
            status,
            f"entry_vs_exit: trade_diff={trade_diff:.2%}, mean_diff={mean_diff:.3f} bps",
        )
    )

    # Universe stability
    if unstable_pairs:
        pairs_str = ", ".join([f"{p}({c}y)" for p, c in unstable_pairs[:10]])
        results.append(
            TestResult(
                "Universe stability",
                "WARN",
                f"pairs_with>=2_consecutive_zero_years: {pairs_str}" + (" ..." if len(unstable_pairs) > 10 else ""),
            )
        )
    else:
        results.append(TestResult("Universe stability", "PASS", "no multi-year gaps"))

    # Concurrency
    max_conc = _concurrency_max(np.asarray(entry_ts_list), np.asarray(exit_ts_list))
    results.append(TestResult("Max concurrent trades", "INFO", f"max_open={max_conc}"))

    # Data summary
    summary = {
        "timeframe": cfg.label,
        "trades": len(df),
        "missing_ts": missing_ts,
        "invalid_duration": invalid_duration,
        "invalid_active_leg": invalid_active_leg,
        "early_entries": early_count,
        "pnl_abs_mean": float(np.mean(pnl_diff_abs)) if pnl_diff_abs else 0.0,
        "pnl_abs_p95": float(np.quantile(pnl_diff_abs, 0.95)) if pnl_diff_abs else 0.0,
        "nextbar_delta_mean": float(np.mean(nextbar_delta)) if nextbar_delta else 0.0,
        "guardrail_trade_diff": trade_diff,
        "guardrail_mean_diff": mean_diff,
        "max_concurrent": max_conc,
    }

    return results, summary


def main() -> None:
    all_results = []
    summaries = []

    # Feature lookahead scan
    lookahead_m5 = _feature_lookahead_scan(m5)
    lookahead_m15 = _feature_lookahead_scan(m15)

    for cfg in CONFIGS:
        results, summary = _audit_timeframe(cfg)
        all_results.append((cfg.label, results))
        summaries.append(summary)

    # Outcome usage scan
    outcome_hits = _scan_outcome_usage()
    allowed_prefixes = (
        "scripts/build_mfe_mae",
        "scripts/redteam_logic_tests.py",
    )
    unexpected = [
        h
        for h in outcome_hits
        if not h.startswith(allowed_prefixes)
        and not h.startswith("scripts/integrity_audit.py")
    ]

    # Write report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# Integrity Audit Report\n")
    lines.append(f"Date: {date.today().isoformat()}  ")
    lines.append("Scope: MOM strategy datasets (M5/M15) + guardrail timing sensitivity\n")

    for label, results in all_results:
        lines.append(f"## {label.upper()} Results")
        for r in results:
            lines.append(f"- **{r.name}**: {r.status} — {r.details}")
        lines.append("")

    # Feature lookahead
    lines.append("## Feature Lookahead Scan")
    if lookahead_m5 is None:
        lines.append("- M5 compute_features_at_entry contains i+? skipped (features removed)")
    else:
        lines.append(f"- M5 compute_features_at_entry contains i+? {lookahead_m5}")
    if lookahead_m15 is None:
        lines.append("- M15 compute_features_at_entry contains i+? skipped (features removed)")
    else:
        lines.append(f"- M15 compute_features_at_entry contains i+? {lookahead_m15}")
    lines.append("")

    # Outcome usage
    lines.append("## Outcome Usage Scan")
    if outcome_hits:
        lines.append("Occurrences of 'outcome' in scripts:")
        for hit in outcome_hits[:50]:
            lines.append(f"- {hit}")
        if len(outcome_hits) > 50:
            lines.append(f"- ... ({len(outcome_hits) - 50} more)")
    else:
        lines.append("- No 'outcome' usages found.")
    if unexpected:
        lines.append("Unexpected outcome usage (needs review):")
        for hit in unexpected[:20]:
            lines.append(f"- {hit}")
        if len(unexpected) > 20:
            lines.append(f"- ... ({len(unexpected) - 20} more)")
    else:
        lines.append("- No unexpected outcome usage.")

    OUT_MD.write_text("\n".join(lines))

    # Write summary CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summaries).to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
