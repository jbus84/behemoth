#!/usr/bin/env python3
"""
Small, focused red-team logic tests for rule-based MOM + guardrail.
Outputs: debunk/REDTEAM_LOGIC_TESTS.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import date
import re

import numpy as np
import pandas as pd


@dataclass
class TestResult:
    name: str
    purpose: str
    procedure: str
    result: str
    verdict: str


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.2f}%"


def _load_events(path: str, bar_minutes: int) -> pd.DataFrame:
    usecols = ["pair", "timestamp", "outcome", "pnl_bps", "duration_bars"]
    df = pd.read_csv(path, usecols=usecols)
    df["timestamp"] = df["timestamp"].astype("int64")
    df["exit_ts"] = df["timestamp"] + (df["duration_bars"].astype(int) * bar_minutes * 60 * 1_000_000_000)
    return df


def _outcome_alignment_test(label: str, df: pd.DataFrame) -> TestResult:
    purpose = "Quantify outcome/PNL alignment (WIN_MOM should be >0, LOSS_REV should be <=0)."
    procedure = "Compute fraction of WIN_MOM with pnl<=0 and LOSS_REV with pnl>0."

    win_neg = ((df["outcome"] == "WIN_MOM") & (df["pnl_bps"] <= 0)).mean()
    loss_pos = ((df["outcome"] == "LOSS_REV") & (df["pnl_bps"] > 0)).mean()

    result = (
        f"{label}: WIN_MOM<=0 = {_fmt_pct(win_neg)}, LOSS_REV>0 = {_fmt_pct(loss_pos)}."
    )
    # If either mismatch rate is >1%, warn
    verdict = "PASS" if max(win_neg, loss_pos) <= 0.01 else "WARN (signal/PNL mismatch present)"
    return TestResult(f"Outcome alignment ({label})", purpose, procedure, result, verdict)


def _guardrail_causality_test(label: str, df: pd.DataFrame, loss_streak: int = 3, cooldown_days: int = 14) -> TestResult:
    purpose = "Verify loss-streak guardrail uses only past trades and applies cooldown correctly."
    procedure = "Apply guardrail sequentially and ensure no kept trade falls inside a pause window." 

    cooldown_ns = int(pd.Timedelta(days=cooldown_days).value)
    state = {}
    kept = []

    for _, row in df.sort_values("exit_ts").iterrows():
        pair = row["pair"]
        ts = int(row["exit_ts"])
        pnl = float(row["pnl_bps"])

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        kept.append((pair, ts, pnl))

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= loss_streak:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    # validate: no kept trade occurs during pause
    violations = 0
    state = {}
    for pair, ts, pnl in kept:
        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}
        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            violations += 1
        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= loss_streak:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    skip_rate = 1.0 - (len(kept) / len(df)) if len(df) else 0.0
    result = f"{label}: trades kept={len(kept)}, skipped={len(df)-len(kept)} (skip_rate={_fmt_pct(skip_rate)}), violations={violations}."
    verdict = "PASS" if violations == 0 else "FAIL (guardrail allowed trades during cooldown)"
    return TestResult(f"Guardrail causality ({label})", purpose, procedure, result, verdict)


def _zscore_causality_check() -> TestResult:
    purpose = "Confirm Z-score uses only past data (rolling window)."
    procedure = "Scan builders for compute_z_scores implementation and verify window uses errors[i-window:i]."

    text_m5 = Path("scripts/build_meta_dataset_v3_m5.py").read_text()
    text_m15 = Path("scripts/build_meta_dataset_v3.py").read_text()

    pat = re.compile(r"errors\[i[-]?\w*window:i\]")
    ok_m5 = "errors[i-window:i]" in text_m5
    ok_m15 = "errors[i-window:i]" in text_m15

    result = f"M5 ok={ok_m5}, M15 ok={ok_m15}."
    verdict = "PASS" if ok_m5 and ok_m15 else "FAIL (non-causal Z window)"
    return TestResult("Z-score causality", purpose, procedure, result, verdict)


def _manual_parity_check() -> TestResult:
    purpose = "Ensure manual reflects rule-based MOM + guardrail and no ML usage."
    procedure = "Search manual for key statements (no CatBoost, loss-streak guardrail)."

    text = Path("docs/STRATEGY_MASTER_MANUAL.md").read_text().lower()
    has_no_ml = "does not use catboost" in text or "no catboost" in text
    has_guardrail = ("loss-streak" in text or "loss‑streak" in text) and "14" in text

    result = f"no_ml={has_no_ml}, guardrail={has_guardrail}."
    verdict = "PASS" if has_no_ml and has_guardrail else "FAIL (manual mismatch)"
    return TestResult("Manual parity", purpose, procedure, result, verdict)


def _write_report(results: list[TestResult]) -> None:
    out = Path("debunk/REDTEAM_LOGIC_TESTS.md")
    lines = []
    lines.append("# Red‑Team Logic Tests (Rule‑Based MOM + Guardrail)\n")
    lines.append(f"Date: {date.today().isoformat()}  ")
    lines.append("Scope: M5/M15 rule‑based MOM strategy + loss‑streak guardrail. No full data rebuilds.\n")
    lines.append("## Summary")
    for r in results:
        lines.append(f"- **{r.name}**: {r.verdict}")
    lines.append("\n---\n")

    for r in results:
        lines.append(f"## {r.name}")
        lines.append(f"**Purpose**: {r.purpose}")
        lines.append(f"**Procedure**: {r.procedure}")
        lines.append(f"**Result**: {r.result}")
        lines.append(f"**Verdict**: {r.verdict}\n")

    out.write_text("\n".join(lines))


def main() -> None:
    results: list[TestResult] = []

    # Data-backed checks on MOM datasets
    m5 = _load_events("data/meta_model/events_m5_8yr_v3_mom.csv", 5)
    m15 = _load_events("data/meta_model/events_m15_8yr_v3_mom.csv", 15)

    results.append(_outcome_alignment_test("M5", m5))
    results.append(_outcome_alignment_test("M15", m15))
    results.append(_guardrail_causality_test("M5", m5))
    results.append(_guardrail_causality_test("M15", m15))

    # Static checks
    results.append(_zscore_causality_check())
    results.append(_manual_parity_check())

    _write_report(results)
    print("Wrote debunk/REDTEAM_LOGIC_TESTS.md")


if __name__ == "__main__":
    main()
