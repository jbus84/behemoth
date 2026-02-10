#!/usr/bin/env python3
import os
import sys

sys.path.append(os.getcwd())
from pipelines.analyze_guardrail_smoothing_slippage import main


if __name__ == "__main__":
    main()
