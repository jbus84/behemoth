#!/usr/bin/env python3
import os
import sys

sys.path.append(os.getcwd())
from pipelines.build_events_m15 import build_dataset


if __name__ == "__main__":
    build_dataset()
