#!/usr/bin/env python3
"""Byte-identical OCO migration parity gate."""

from __future__ import annotations

import argparse
import filecmp
import sys
from pathlib import Path


def iter_reference_files(ref_dir: Path) -> list[Path]:
    return sorted(path for path in ref_dir.rglob("*") if path.is_file())


def compare_reference_to_candidate(ref_dir: Path, out_dir: Path) -> list[str]:
    diffs: list[str] = []
    for ref_file in iter_reference_files(ref_dir):
        relative_path = ref_file.relative_to(ref_dir)
        candidate = out_dir / relative_path
        if not candidate.exists():
            diffs.append(f"MISSING: {candidate}")
            continue
        if not candidate.is_file() or not filecmp.cmp(ref_file, candidate, shallow=False):
            diffs.append(f"DIFF: {candidate}")
    return diffs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff OCO migration artifacts byte-for-byte against a reference snapshot."
    )
    parser.add_argument("--ref-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.ref_dir.is_dir():
        print(f"MISSING: reference directory {args.ref_dir}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1g wires orchestrator output generation into this out_dir before comparison.
    diffs = compare_reference_to_candidate(args.ref_dir, args.out_dir)
    if diffs:
        for diff in diffs:
            print(diff, file=sys.stderr)
        return 1

    print("OCO migration parity: byte-identical on all artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
