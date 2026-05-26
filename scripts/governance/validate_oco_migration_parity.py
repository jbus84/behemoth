#!/usr/bin/env python3
"""OCO migration parity gate with byte and semantic comparison modes."""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path

import pandas as pd


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


def compare_reference_to_candidate_semantic(
    ref_dir: Path,
    out_dir: Path,
    *,
    float_tolerance: float,
) -> list[str]:
    diffs: list[str] = []
    for ref_file in iter_reference_files(ref_dir):
        relative_path = ref_file.relative_to(ref_dir)
        candidate = out_dir / relative_path
        if not candidate.exists():
            diffs.append(f"MISSING: {candidate}")
            continue
        if not candidate.is_file():
            diffs.append(f"DIFF: {candidate}")
            continue
        reason = _semantic_diff_reason(
            ref_file=ref_file,
            candidate=candidate,
            float_tolerance=float_tolerance,
        )
        if reason:
            diffs.append(f"SEMANTIC_DIFF: {candidate}: {reason}")
    return diffs


def _semantic_diff_reason(
    *,
    ref_file: Path,
    candidate: Path,
    float_tolerance: float,
) -> str | None:
    suffix = ref_file.suffix.lower()
    if suffix == ".csv":
        return _csv_diff_reason(
            ref_file=ref_file,
            candidate=candidate,
            float_tolerance=float_tolerance,
        )
    if suffix == ".json":
        return _json_diff_reason(ref_file=ref_file, candidate=candidate)
    if not filecmp.cmp(ref_file, candidate, shallow=False):
        return "bytes differ for non-semantic artifact type"
    return None


def _csv_diff_reason(
    *,
    ref_file: Path,
    candidate: Path,
    float_tolerance: float,
) -> str | None:
    ref = _canonical_csv(ref_file)
    out = _canonical_csv(candidate)
    if list(ref.columns) != list(out.columns):
        return f"columns differ: ref={list(ref.columns)} out={list(out.columns)}"
    if len(ref) != len(out):
        return f"row count differs: ref={len(ref)} out={len(out)}"
    for col in ref.columns:
        ref_values = ref[col]
        out_values = out[col]
        ref_num = pd.to_numeric(ref_values, errors="coerce")
        out_num = pd.to_numeric(out_values, errors="coerce")
        if ref_num.notna().all() and out_num.notna().all():
            delta = (ref_num.astype(float) - out_num.astype(float)).abs()
            if bool((delta > float_tolerance).any()):
                return f"numeric column {col!r} differs beyond tolerance"
            continue
        if ref_values.astype(str).tolist() != out_values.astype(str).tolist():
            return f"column {col!r} differs"
    return None


def _canonical_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    df = df.reindex(sorted(df.columns), axis=1)
    for col in df.columns:
        df[col] = df[col].map(_normalize_scalar)
    sort_cols = [col for col in ("symbol", "family", "state_id", "month", "entry_month") if col in df]
    if not sort_cols:
        sort_cols = list(df.columns)
    return df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def _normalize_scalar(value: object) -> str:
    text = str(value).strip()
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower
    return text


def _json_diff_reason(*, ref_file: Path, candidate: Path) -> str | None:
    ref = _canonical_json(json.loads(ref_file.read_text(encoding="utf-8")))
    out = _canonical_json(json.loads(candidate.read_text(encoding="utf-8")))
    if ref != out:
        return "json payload differs"
    return None


def _canonical_json(value):
    if isinstance(value, dict):
        return {key: _canonical_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        canonical_items = [_canonical_json(item) for item in value]
        if all(isinstance(item, dict) and "state_id" in item for item in canonical_items):
            return sorted(canonical_items, key=lambda item: str(item["state_id"]))
        return canonical_items
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff OCO migration artifacts against a reference snapshot."
    )
    parser.add_argument("--ref-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=("byte", "semantic"), default="byte")
    parser.add_argument("--float-tolerance", type=float, default=1e-9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.ref_dir.is_dir():
        print(f"MISSING: reference directory {args.ref_dir}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "semantic":
        diffs = compare_reference_to_candidate_semantic(
            args.ref_dir,
            args.out_dir,
            float_tolerance=float(args.float_tolerance),
        )
    else:
        diffs = compare_reference_to_candidate(args.ref_dir, args.out_dir)
    if diffs:
        for diff in diffs:
            print(diff, file=sys.stderr)
        return 1

    if args.mode == "semantic":
        print("OCO migration parity: semantically equivalent on all artifacts.")
    else:
        print("OCO migration parity: byte-identical on all artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
