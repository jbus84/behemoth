#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_REPO_ROOT))

from src.behemoth.ops.stage_dag import (  # noqa: E402 — sys.path setup above
    load_dag_contract,
    validate_contract,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _materialize_contract(src: Path, *, model_month: str, target_commit: str | None) -> Path:
    text = src.read_text(encoding="utf-8").replace("${MODEL_MONTH}", model_month)
    if target_commit:
        text = text.replace("${TARGET_COMMIT}", target_commit)
    tmp_path = src.parent / f".{src.stem}.{model_month}.materialized.yaml"
    tmp_path.write_text(text, encoding="utf-8")
    return tmp_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default="configs/research/governance/live_stage_dag.yaml")
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--target-commit", default="")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = _repo_root()
    contract_path = repo_root / args.contract
    materialized = _materialize_contract(
        contract_path,
        model_month=str(args.model_month),
        target_commit=str(args.target_commit).strip() or None,
    )
    try:
        contract = load_dag_contract(materialized)
        issues = validate_contract(contract, repo_root=repo_root)
    finally:
        materialized.unlink(missing_ok=True)

    payload = {
        "ok": not issues,
        "model_month": str(args.model_month),
        "issues": [issue.__dict__ for issue in issues],
    }
    if args.out_json:
        out_path = repo_root / args.out_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
