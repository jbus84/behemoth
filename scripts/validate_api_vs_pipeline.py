#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

from services.api.validation import summary_for_bar

OUT = Path("data/analysis/api_validation_report.json")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "m5": summary_for_bar("m5"),
        "m15": summary_for_bar("m15"),
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
