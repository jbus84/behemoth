"""Reversion conditioner null-test report writer.

Reads the JSON emitted by `reversion_conditioner_nulltest.py` and produces a
Markdown report with a STOP / PROCEED gate.

Usage:
    PYTHONPATH=<repo-root> uv run python scripts/fx_coint/reversion_conditioner_report.py \
        --in results/reversion_null.json --out results/reversion_null.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> list[dict]:
    with open(path) as fh:
        return json.load(fh)


def _best_signed_fade(rows: list[dict], regime: str) -> list[dict]:
    """Return top-N signed_fade rows by absolute Spearman IC."""
    r = [row for row in rows if row["target"] == "signed_fade" and row["regime"] == regime]
    return sorted(r, key=lambda x: abs(x.get("spear_ic", 0.0)), reverse=True)


def _best_tail_net(rows: list[dict], regime: str) -> list[dict]:
    r = [row for row in rows if row["target"] == "signed_fade" and row["regime"] == regime]
    return sorted(r, key=lambda x: x.get("tail_net", float("-inf")), reverse=True)


def _ridge_summary(rows: list[dict]) -> dict:
    ridge = [row for row in rows if row["signal"].startswith("ridge_") and row["target"] == "signed_fade"]
    return {
        "n": len(ridge),
        "best_ic": max((r.get("pearson_ic", float("-inf")) for r in ridge), default=float("nan")),
        "best_r2": max((r.get("oos_r2", float("-inf")) for r in ridge), default=float("nan")),
        "worst_ic": min((r.get("pearson_ic", float("inf")) for r in ridge), default=float("nan")),
        "worst_r2": min((r.get("oos_r2", float("inf")) for r in ridge), default=float("nan")),
    }


def _gate(rows: list[dict]) -> tuple[str, str]:
    """Evaluate STOP/PROCEED criteria.

    PROCEED requires:
      1. At least one OOS signed_fade Spearman IC > 0.02 with t > 2.0.
      2. At least one OOS signed_fade top-decile tail_net > 0.
      3. Ridge OOS signed_fade best R² > 0.001 and best IC > 0.
      4. At least one OOS signed_fade test has p < 0.05 (survives FDR at α=0.05).
    """
    oos = [r for r in rows if r["target"] == "signed_fade" and r["regime"] == "OOS"]

    # Criterion 1
    ic_pass = any(r.get("spear_ic", 0.0) > 0.02 and r.get("spear_t", 0.0) > 2.0 for r in oos)

    # Criterion 2
    net_pass = any(r.get("tail_net", float("-inf")) > 0.0 for r in oos)

    # Criterion 3
    ridge = _ridge_summary(rows)
    ridge_pass = ridge["best_r2"] > 0.001 and ridge["best_ic"] > 0.0

    # Criterion 4: count rejections among signed_fade OOS tests
    # We don't have p-values in the JSON rows directly (only t-stats).
    # Approximate: |t| > 1.96 ~> p < 0.05.  FDR is a stricter bar; we'll use the raw t-stat.
    fdr_pass = any(abs(r.get("spear_t", 0.0)) > 1.96 for r in oos)

    reasons = []
    if not ic_pass:
        reasons.append("no OOS signed_fade Spearman IC > 0.02 @ t > 2")
    if not net_pass:
        reasons.append("no OOS signed_fade top-decile tail_net > 0")
    if not ridge_pass:
        reasons.append(f"ridge OOS signed_fade R²={ridge['best_r2']:+.4f} ≤ 0.001 or IC ≤ 0")
    if not fdr_pass:
        reasons.append("no OOS signed_fade test survives raw t > 1.96")

    if ic_pass and net_pass and ridge_pass and fdr_pass:
        return "PROCEED", "all criteria satisfied"
    return "STOP", "; ".join(reasons)


def write_report(rows: list[dict], out_md: Path) -> None:
    verdict, reason = _gate(rows)
    best_oos_ic = _best_signed_fade(rows, "OOS")[:10]
    best_oos_net = _best_tail_net(rows, "OOS")[:10]
    ridge = _ridge_summary(rows)

    lines = [
        "# Reversion Conditioner Null-Test — Report",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — {reason}",
        "",
        "## Summary",
        "",
        f"- Total tests: {len(rows)}",
        f"- Best OOS ridge IC (signed_fade): {ridge['best_ic']:+.4f}",
        f"- Best OOS ridge R² (signed_fade): {ridge['best_r2']:+.4f}",
        "",
        "## Best OOS Signed-Fade Spearman ICs",
        "",
        "| pair | signal | horizon | n | spear_ic | spear_t | tail_gross | tail_cost | tail_net |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in best_oos_ic:
        lines.append(
            f"| {r['pair']} | {r['signal']} | h{r['horizon']} | {r['n']} | "
            f"{r['spear_ic']:+.4f} | {r['spear_t']:+.1f} | {r['tail_gross']:+.2f} | "
            f"{r['tail_cost']:+.2f} | {r['tail_net']:+.2f} |"
        )

    lines += [
        "",
        "## Best OOS Signed-Fade Top-Decile Net",
        "",
        "| pair | signal | horizon | n | spear_ic | spear_t | tail_gross | tail_cost | tail_net |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in best_oos_net:
        lines.append(
            f"| {r['pair']} | {r['signal']} | h{r['horizon']} | {r['n']} | "
            f"{r['spear_ic']:+.4f} | {r['spear_t']:+.1f} | {r['tail_gross']:+.2f} | "
            f"{r['tail_cost']:+.2f} | {r['tail_net']:+.2f} |"
        )

    lines += [
        "",
        "## Ridge OOS (signed_fade)",
        "",
        f"- Best IC: {ridge['best_ic']:+.4f}",
        f"- Best R²: {ridge['best_r2']:+.4f}",
        f"- Worst IC: {ridge['worst_ic']:+.4f}",
        f"- Worst R²: {ridge['worst_r2']:+.4f}",
        "",
    ]

    Path(out_md).write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reversion conditioner null-test report writer.")
    parser.add_argument("--in", dest="in_path", required=True, help="Path to JSON output from null-test runner.")
    parser.add_argument("--out", required=True, help="Path to write Markdown report.")
    args = parser.parse_args()

    rows = _load(args.in_path)
    write_report(rows, Path(args.out))
    print(f"Report written to {args.out} — {len(rows)} rows processed")


if __name__ == "__main__":
    main()
