#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

from services.api.validation import compare_predictions_to_pipeline
from services.api.predict import PAIR_MAP

OUT = Path("data/analysis/api_prediction_alignment.json")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {}
    for bar, pairs in PAIR_MAP.items():
        report[bar] = []
        for name, *_ in pairs:
            summary = compare_predictions_to_pipeline(bar, name, ts_tolerance_ns=0)
            report[bar].append(summary)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
