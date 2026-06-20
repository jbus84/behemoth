"""Phase 0 Master Funnel: run all four families, rank, apply stopping rules.

Usage:
    uv run python scripts/fx_coint/phase0_scalp_funnel.py --symbol EURUSD --year 2024

Emits data/phase0_results.json (per-family metrics, ranking, stopping verdict).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.fx_coint.phase0_scalp_common import DEFAULT_COST_BPS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILIES = {
    "A": ("scripts/fx_coint/phase0_family_a.py", "--symbol"),
    "B": ("scripts/fx_coint/phase0_family_b.py", "--symbol"),
    "C": ("scripts/fx_coint/phase0_family_c.py", "--target"),
    "D": ("scripts/fx_coint/phase0_family_d.py", "--symbol"),
}


def run_family(family: str, symbol: str, year: int, horizons: list[int]) -> dict:
    script, flag = FAMILIES[family]
    cmd = [sys.executable, str(REPO_ROOT / script), flag, symbol, "--year", str(year)]
    if horizons:
        cmd += ["--horizons", *[str(h) for h in horizons]]
    print(f"Running Family {family}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(result.stderr)
        return {"family": family, "error": result.stderr, "results": {}}
    for line in reversed([ln for ln in result.stdout.splitlines() if ln.strip()]):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    # JSON is multi-line indented; fall back to parsing the whole stdout tail
    try:
        start = result.stdout.index("{")
        return json.loads(result.stdout[start:])
    except (ValueError, json.JSONDecodeError):
        return {"family": family, "error": "no JSON in stdout", "results": {}}


def rank_families(results: dict) -> list:
    ranked = []
    for fam, data in results.items():
        best_net, best_verdict = float("-inf"), "FAIL"
        for _h, m in data.get("results", {}).items():
            net = m.get("net_lb95_bps", float("-inf"))
            if net > best_net:
                best_net, best_verdict = net, m.get("verdict", "FAIL")
        ranked.append((fam, {"best_net_lb95_bps": best_net, "best_verdict": best_verdict, "raw": data}))
    ranked.sort(key=lambda x: x[1]["best_net_lb95_bps"], reverse=True)
    return ranked


def apply_stopping_rules(results: dict) -> str:
    """CONTINUE if >=1 PASS; STOP if 0 PASS and <=1 NEAR_MISS; else ADVANCE_NEAR_MISS."""
    npass = nmiss = 0
    for data in results.values():
        for m in data.get("results", {}).values():
            v = m.get("verdict", "FAIL")
            npass += v == "PASS"
            nmiss += v == "NEAR_MISS"
    if npass >= 1:
        return "CONTINUE"
    if npass == 0 and nmiss <= 1:
        return "STOP"
    return "ADVANCE_NEAR_MISS"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    args = p.parse_args()

    sym = args.symbol.upper()
    all_results = {fam: run_family(fam, sym, args.year, args.horizons) for fam in FAMILIES}
    ranked = rank_families(all_results)
    verdict = apply_stopping_rules(all_results)

    summary = {
        "symbol": sym, "year": args.year, "cost_bps": DEFAULT_COST_BPS.get(sym, 0.80),
        "ranking": [{"family": fam, **meta} for fam, meta in ranked],
        "stopping_rule": verdict,
        "pass_count": sum(m["best_verdict"] == "PASS" for _, m in ranked),
        "near_miss_count": sum(m["best_verdict"] == "NEAR_MISS" for _, m in ranked),
        "full_results": all_results,
    }
    out_path = REPO_ROOT / "data" / "phase0_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved summary: {out_path}\nStopping rule: {verdict}")


if __name__ == "__main__":
    main()
