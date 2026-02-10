#!/usr/bin/env python3
import os
import sys

sys.path.append(os.getcwd())
from pipelines.analyze_guardrail_deep_dive import main


if __name__ == "__main__":
    main()
