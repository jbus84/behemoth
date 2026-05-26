#!/usr/bin/env python3
"""Run the governance pipeline placeholder for one symbol.

Usage:
    uv run python scripts/governance/run_governance_all.py \\
        --symbol-yaml configs/research/experiments/eurusd_governance.yaml \\
        --candidate-dir data/analysis/tick_opportunity_mining \\
        --out-dir data/analysis/governance \\
        --tick-root <path_to_ticks>

For each family in `required_families`:
1. Load candidates CSV (`<SYM>_<library>_candidates.csv`)
2. G1: assemble states
3. G2: rolling selection
4. G3: tick-exact verification
5. G4: state-level verdicts
6. G5: family + symbol roll-up + freeze artifact write

Writes per-symbol verdict summary to <out_dir>/<model_month>/verdicts/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402

from src.behemoth.governance.families import get_family_adapter  # noqa: E402
from src.behemoth.governance.symbol_config import (  # noqa: E402
    load_symbol_governance_config,
)
from src.behemoth.governance.verdict import compute_symbol_verdict  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol-yaml", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--tick-root", required=True)
    args = parser.parse_args()

    cfg = load_symbol_governance_config(Path(args.symbol_yaml))
    out_dir = Path(args.out_dir) / cfg.model_month / "verdicts"
    out_dir.mkdir(parents=True, exist_ok=True)

    family_verdicts: dict[str, str] = {}
    for family_name in cfg.required_families:
        get_family_adapter(family_name)
        family_verdicts[family_name] = "NO_GO"

    symbol_verdict = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=cfg.required_families,
    )
    summary = pd.DataFrame(
        [
            {
                "symbol": cfg.symbol,
                "model_month": cfg.model_month,
                "verdict": symbol_verdict,
                **{
                    f"{family}_verdict": verdict
                    for family, verdict in family_verdicts.items()
                },
            }
        ]
    )
    summary.to_csv(out_dir / f"{cfg.symbol}_symbol_verdict.csv", index=False)
    print(f"[gov] {cfg.symbol}: symbol_verdict={symbol_verdict}")


if __name__ == "__main__":
    main()
