#!/usr/bin/env python3
import os
import sys

sys.path.append(os.getcwd())
from pipelines.build_repro_manifest import main

if __name__ == "__main__":
    main()
