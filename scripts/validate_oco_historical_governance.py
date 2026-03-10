#!/usr/bin/env python3
"""Validate month-scoped historical governance lock integrity."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def main() -> None:
    from src.behemoth.core.historical_governance_validation import (
        failed_checks,
        summarize_failures,
        validate_historical_governance,
    )

    p = argparse.ArgumentParser(description="Validate historical OCO governance locks")
    p.add_argument("--history-dir", default="configs/research/governance/oco_history")
    p.add_argument("--symbols", default="")
    p.add_argument("--months", default="")
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/oco_historical_governance_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/oco_historical_governance_issues.csv",
    )
    args = p.parse_args()

    checks = validate_historical_governance(
        Path(str(args.history_dir)),
        required_symbols=[s.upper() for s in _split_csv(str(args.symbols))],
        required_months=_split_csv(str(args.months)),
    )
    bad = failed_checks(checks)

    checks_df = pd.DataFrame([c.__dict__ for c in checks])
    issues_df = pd.DataFrame([c.__dict__ for c in bad])

    out_checks = Path(str(args.out_checks_csv))
    out_issues = Path(str(args.out_issues_csv))
    out_checks.parent.mkdir(parents=True, exist_ok=True)
    out_issues.parent.mkdir(parents=True, exist_ok=True)
    checks_df.to_csv(out_checks, index=False)
    issues_df.to_csv(out_issues, index=False)

    print(f"wrote checks: {out_checks} rows={len(checks_df)}")
    print(f"wrote issues: {out_issues} rows={len(issues_df)}")
    print(f"failed_checks={len(bad)}")
    if bad:
        print(summarize_failures(checks, limit=8))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
