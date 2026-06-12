from __future__ import annotations

import json
from pathlib import Path


def _summary(rows: list[dict]) -> dict:
    def count(markup: str, verdict: str) -> int:
        return sum(1 for r in rows
                   if r["verdict_by_markup"].get(markup) == verdict)
    return {
        "n_rows": len(rows),
        "n_set_at_zero_markup": count("0.0", "SET"),
        "n_execution_gated_at_zero_markup": count("0.0", "EXECUTION_GATED"),
        "n_set_at_0_6_markup": count("0.6", "SET"),
    }


def write_report(rows: list[dict], out_json: Path, out_md: Path) -> None:
    payload = {"summary": _summary(rows), "rows": rows}
    Path(out_json).write_text(json.dumps(payload, indent=2, default=str))

    lines = ["# FX Cointegration Screen — Results", "", "## Summary", ""]
    for k, v in payload["summary"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Spreads", "",
              "| TF | Universe | Base | Hedge | %stat | FDR | HL | revfrac | "
              "floor | ceiling | Verdict@0.0 | @0.6 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['timeframe']} | {r['universe']} | {r['base']} | {r['hedge']} | "
            f"{r['fraction_stationary']:.2f} | {r['fdr_pass']} | {r['half_life']:.1f} | "
            f"{r['reversion_frac']:.2f} | {r['floor']:.2e} | {r['ceiling']:.2e} | "
            f"{r['verdict_by_markup'].get('0.0')} | {r['verdict_by_markup'].get('0.6')} |")
    Path(out_md).write_text("\n".join(lines) + "\n")
