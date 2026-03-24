#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

FORBIDDEN_TERMS = [
    r"\bkalman\b",
    r"services/api",
    r"src/behemoth",
    r"pipelines/build_events",
    r"pipelines/simulate"
]

IGNORE_DIRS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "site", "data", "archive", "node_modules", "catboost_info", "logs"}
IGNORE_FILES = {"check_legacy_drift.py", "AGENTS.md", "Makefile"}

def run_sweep(repo_root: Path) -> int:
    issues_found = 0
    patterns = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_TERMS]

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for file in files:
            if file in IGNORE_FILES:
                continue
            if not file.endswith((".py", ".md", ".yaml", ".yml", "Makefile")):
                continue

            file_path = Path(root) / file

            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for i, line in enumerate(content.splitlines(), 1):
                for pattern in patterns:
                    if pattern.search(line):
                        print(f"ERROR: Legacy drift detected in {file_path.relative_to(repo_root)}:{i}")
                        print(f"       Found forbidden pattern '{pattern.pattern}'")
                        print(f"       Line: {line.strip()}")
                        issues_found += 1

    if issues_found > 0:
        print(f"\n[FAIL] {issues_found} legacy terms found. Clean these up to maintain the OCO architecture.")
        return 1

    print("[PASS] No legacy drift detected. Codebase is clean.")
    return 0

if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    sys.exit(run_sweep(repo_root))
