"""Classify a single symbol's retrain outcome for the retrain-all summary."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def classify_outcome(*, exit_code: int, schedule_csv: Path) -> str:
    """Return DEPLOY, NO_TRADE, or FAILED for one symbol's retrain run."""
    if exit_code != 0:
        return "FAILED"
    schedule_csv = Path(schedule_csv)
    if not schedule_csv.exists():
        return "FAILED"
    try:
        rows = len(pd.read_csv(schedule_csv))
    except pd.errors.EmptyDataError:
        rows = 0
    except Exception:
        return "FAILED"
    return "DEPLOY" if rows >= 1 else "NO_TRADE"


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a retrain outcome")
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--schedule-csv", required=True)
    args = parser.parse_args()
    print(classify_outcome(exit_code=args.exit_code, schedule_csv=Path(args.schedule_csv)))
    sys.exit(0)


if __name__ == "__main__":
    main()
