import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "pipelines"))

# Tests should not bind to the shared runtime DuckDB file unless they opt in.
os.environ.setdefault("BEHEMOTH_STATE_DB", "")
