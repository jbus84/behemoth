"""Unified findings taxonomy for live diagnostic reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Classification = Literal["Material Drift", "Runtime Variance", "Incomplete Evidence", "Info"]
Severity = Literal["high", "medium", "info"]

FINDINGS_COLUMNS = ["symbol", "classification", "code", "severity", "summary"]


@dataclass(frozen=True)
class Finding:
    symbol: str
    classification: Classification
    code: str
    severity: Severity
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "classification": self.classification,
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
        }


def _numeric_row_value(row: pd.Series, column: str) -> float:
    try:
        value = row.get(column, float("nan"))
    except Exception:
        value = float("nan")
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_findings(
    *,
    results: list[dict[str, object]],
    signal_coverage_threshold: float = 0.8,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for result in results:
        symbol = str(result.get("symbol", "")).upper()
        signal_coverage_ratio = _numeric_row_value(
            pd.Series(result), "signal_coverage_ratio"
        )
        signal_coverage_pass = result.get("signal_coverage_pass", False)
        has_trades = result.get("has_trades", False)
        non_deployable_reason = result.get("non_deployable_reason", "")
        historical_deployable = result.get("historical_deployable", True)

        if not historical_deployable and non_deployable_reason:
            rows.append(
                {
                    "symbol": symbol,
                    "classification": "Incomplete Evidence",
                    "code": "NON_DEPLOYABLE_LOCK",
                    "severity": "medium",
                    "summary": f"Lock non-deployable: {non_deployable_reason}",
                }
            )
            continue

        if signal_coverage_ratio == 0.0 and not has_trades:
            rows.append(
                {
                    "symbol": symbol,
                    "classification": "Incomplete Evidence",
                    "code": "MISSING_RUNTIME_SIGNALS",
                    "severity": "medium",
                    "summary": "No runtime signals or trades observed for window.",
                }
            )
            continue

        if not signal_coverage_pass and has_trades:
            rows.append(
                {
                    "symbol": symbol,
                    "classification": "Runtime Variance",
                    "code": "SIGNAL_COVERAGE_LOW",
                    "severity": "medium",
                    "summary": (
                        f"Signal coverage {signal_coverage_ratio:.1%} "
                        f"below threshold {signal_coverage_threshold:.1%}."
                    ),
                }
            )
            continue

        if not signal_coverage_pass and not has_trades:
            rows.append(
                {
                    "symbol": symbol,
                    "classification": "Incomplete Evidence",
                    "code": "NO_RUNTIME_TRADES",
                    "severity": "medium",
                    "summary": "Runtime signals present but no trades submitted.",
                }
            )
            continue

        rows.append(
            {
                "symbol": symbol,
                "classification": "Info",
                "code": "NO_MATERIAL_FINDINGS",
                "severity": "info",
                "summary": "No material live governance deviation findings.",
            }
        )

    return pd.DataFrame(rows, columns=FINDINGS_COLUMNS)
