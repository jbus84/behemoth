#!/usr/bin/env python3
"""Audit canonical monthly tick parquet source completeness."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import yaml

try:
    from scripts.canonical_tick_feed import DEFAULT_DUKASCOPY_ROOT, to_utc
except ModuleNotFoundError:
    from canonical_tick_feed import DEFAULT_DUKASCOPY_ROOT, to_utc


MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
MONTH_TAG_RE = re.compile(r"^\d{6}$")


@dataclass
class AuditRow:
    symbol: str
    month: str
    exists: bool
    has_required_schema: bool
    row_count_gt_zero: bool
    timestamp_utc_ok: bool
    path: str
    status: str
    detail: str


def _parse_symbols(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    return [part.strip().upper() for part in str(raw).split(",") if part.strip()]


def _parse_months(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    out: list[str] = []
    for token in str(raw).split(","):
        txt = token.strip()
        if not txt:
            continue
        if MONTH_TAG_RE.fullmatch(txt):
            out.append(txt)
            continue
        if MONTH_DIR_RE.fullmatch(txt):
            out.append(txt.replace("-", ""))
            continue
        raise ValueError(f"invalid month token: {txt!r}")
    return sorted(set(out))


def _load_registry_symbols(registry_path: Path) -> list[str]:
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    symbols = payload.get("symbols", [])
    return sorted({str(sym).upper().strip() for sym in symbols if str(sym).strip()})


def _load_history_months(history_dir: Path) -> list[str]:
    months = []
    for child in sorted(history_dir.iterdir()):
        if child.is_dir() and MONTH_DIR_RE.fullmatch(child.name):
            months.append(child.name.replace("-", ""))
    return sorted(set(months))


def _schema_check(path: Path) -> tuple[bool, bool, bool, str]:
    quoted = str(path).replace("'", "''")
    con = duckdb.connect()
    try:
        schema_df = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{quoted}')").fetchdf()
        cols = {
            str(row["column_name"]).strip().lower(): str(row["column_type"]).strip().upper()
            for _, row in schema_df.iterrows()
        }
        has_required_schema = {"timestamp", "bid", "ask"}.issubset(cols)
        if not has_required_schema:
            missing = sorted({"timestamp", "bid", "ask"} - set(cols))
            return False, False, False, f"missing_columns={','.join(missing)}"

        sample = con.execute(
            f"""
            SELECT
                try_cast(timestamp AS TIMESTAMP WITH TIME ZONE) AS timestamp,
                try_cast(bid AS DOUBLE) AS bid,
                try_cast(ask AS DOUBLE) AS ask
            FROM read_parquet('{quoted}')
            LIMIT 1000
            """
        ).fetchdf()
        count_df = con.execute(
            f"SELECT COUNT(*) AS row_count FROM read_parquet('{quoted}')"
        ).fetchdf()
    finally:
        con.close()

    row_count = int(count_df.iloc[0]["row_count"]) if not count_df.empty else 0
    row_count_gt_zero = row_count > 0
    if sample.empty:
        return True, row_count_gt_zero, False, "empty_sample"

    ts = to_utc(sample.get("timestamp", pd.Series(dtype=object)))
    timestamp_utc_ok = bool(ts.notna().all())
    detail = f"row_count={row_count}"
    if not timestamp_utc_ok:
        detail += "; timestamp_parse_failures_present=true"
    return True, row_count_gt_zero, timestamp_utc_ok, detail


def run(
    *,
    tick_root: Path,
    symbols: list[str],
    months: list[str],
    out_summary_csv: Path,
    out_missing_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[AuditRow] = []
    for symbol in symbols:
        for month in months:
            path = tick_root / symbol / f"{symbol}_{month}_ticks.parquet"
            exists = path.exists()
            if not exists:
                rows.append(
                    AuditRow(
                        symbol=symbol,
                        month=month,
                        exists=False,
                        has_required_schema=False,
                        row_count_gt_zero=False,
                        timestamp_utc_ok=False,
                        path=str(path),
                        status="missing",
                        detail="file_not_found",
                    )
                )
                continue

            has_schema, row_count_gt_zero, timestamp_utc_ok, detail = _schema_check(path)
            ok = exists and has_schema and row_count_gt_zero and timestamp_utc_ok
            rows.append(
                AuditRow(
                    symbol=symbol,
                    month=month,
                    exists=True,
                    has_required_schema=has_schema,
                    row_count_gt_zero=row_count_gt_zero,
                    timestamp_utc_ok=timestamp_utc_ok,
                    path=str(path),
                    status="ok" if ok else "invalid",
                    detail=detail,
                )
            )

    summary_df = (
        pd.DataFrame([row.__dict__ for row in rows])
        .sort_values(["symbol", "month"])
        .reset_index(drop=True)
    )
    missing_df = summary_df[summary_df["status"].astype(str) != "ok"].copy()

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_missing_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(out_summary_csv, index=False)
    missing_df.to_csv(out_missing_csv, index=False)

    lines = [
        "# Tick Source Completeness Audit",
        "",
        f"- tick_root: `{tick_root}`",
        f"- symbols_checked: `{len(symbols)}`",
        f"- months_checked: `{len(months)}`",
        f"- total_symbol_months: `{len(summary_df)}`",
        f"- failing_symbol_months: `{len(missing_df)}`",
        "",
        "## Summary",
        summary_df.to_markdown(index=False) if not summary_df.empty else "_empty_",
        "",
        "## Missing Or Invalid",
        missing_df.to_markdown(index=False) if not missing_df.empty else "_empty_",
        "",
    ]
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return summary_df, missing_df


def main() -> None:
    p = argparse.ArgumentParser(
        description="Audit canonical monthly parquet tick source completeness"
    )
    p.add_argument("--tick-root", default=str(DEFAULT_DUKASCOPY_ROOT))
    p.add_argument("--symbols", default="")
    p.add_argument(
        "--registry-path",
        default="configs/research/governance/oco_rule_universe_registry.yaml",
    )
    p.add_argument("--months", default="")
    p.add_argument(
        "--history-dir",
        default="configs/research/governance/oco_history",
        help="Used to infer required months when --months is omitted",
    )
    p.add_argument(
        "--out-summary-csv",
        default="data/analysis/tick_opportunity_mining/dukascopy_source_completeness_summary.csv",
    )
    p.add_argument(
        "--out-missing-csv",
        default="data/analysis/tick_opportunity_mining/dukascopy_source_completeness_missing.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/dukascopy_source_completeness_report.md",
    )
    args = p.parse_args()

    symbols = _parse_symbols(str(args.symbols))
    if not symbols:
        symbols = _load_registry_symbols(Path(str(args.registry_path)))
    months = _parse_months(str(args.months))
    if not months:
        months = _load_history_months(Path(str(args.history_dir)))
    if not symbols:
        raise ValueError("no symbols resolved for audit")
    if not months:
        raise ValueError("no months resolved for audit")

    summary_df, missing_df = run(
        tick_root=Path(str(args.tick_root)),
        symbols=symbols,
        months=months,
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_missing_csv=Path(str(args.out_missing_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote summary: {args.out_summary_csv} rows={len(summary_df)}")
    print(f"wrote missing: {args.out_missing_csv} rows={len(missing_df)}")
    print(f"wrote report: {args.report_out}")
    print(f"source_completeness_verdict={'green' if missing_df.empty else 'red'}")


if __name__ == "__main__":
    main()
