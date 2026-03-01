#!/usr/bin/env python3
"""Validate pre-registered OCO rule-universe contract against live artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


REQUIRED_KEYS = {
    "registry_version",
    "effective_from_utc",
    "symbols",
    "allowed_families",
    "allowed_barrier_keep",
    "allowed_horizon_keep",
    "selection_mode_contract",
    "locked_runtime_contract",
    "change_control",
    "hash_sha256",
}

LOCKED_RUNTIME_KEYS = {
    "threshold_mode",
    "rolling_threshold_days",
    "rolling_threshold_min_history",
    "oco_hold_mode",
    "oco_include_no_touch",
    "execution_quantile",
}


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _canon_hash(obj: dict[str, Any]) -> str:
    payload = dict(obj)
    payload.pop("hash_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_csv_list(x: Any) -> set[str]:
    return {v.strip() for v in str(x).split(",") if v.strip()}


def _to_num_set(vals: list[Any]) -> set[int]:
    out: set[int] = set()
    for v in vals:
        try:
            out.add(int(float(v)))
        except Exception:
            continue
    return out


def _lock_for_symbol(lock_dir: Path, symbol: str) -> Path:
    return lock_dir / f"{str(symbol).lower()}_oco_live_lock.json"


def _reduced_states_for_symbol(base: Path, symbol: str) -> Path:
    s = str(symbol).upper()
    if s == "EURUSD":
        return base / "reduced_core" / "EURUSD_oco_reduced_states.csv"
    if s == "GBPUSD":
        return base / "reduced_core_gbpusd" / "GBPUSD_oco_reduced_states.csv"
    return base / "reduced_core_usdjpy" / "USDJPY_oco_reduced_states.csv"


def _add_check(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    check_id: str,
    check_name: str,
    passed: bool,
    severity_if_fail: str,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    comparator: str,
    source_path: Path | None,
    details: str = "",
) -> None:
    rows.append(
        {
            "symbol": symbol,
            "check_id": check_id,
            "check_name": check_name,
            "status": "pass" if bool(passed) else "fail",
            "severity_if_fail": str(severity_if_fail).lower(),
            "component": "rule_universe_registry",
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": comparator,
            "details": details,
            "source_path": str(source_path) if source_path is not None else "",
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def run(
    *,
    registry_yaml: Path,
    lock_dir: Path,
    mining_base: Path,
    symbols: list[str],
    out_checks_csv: Path,
    out_issues_csv: Path,
    out_report_md: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks_rows: list[dict[str, Any]] = []

    if yaml is None:
        raise RuntimeError("PyYAML required for registry validation")

    exists = registry_yaml.exists()
    _add_check(
        checks_rows,
        symbol="ALL",
        check_id="RU01",
        check_name="registry_yaml_exists",
        passed=exists,
        severity_if_fail="critical",
        metric_name="exists",
        metric_value=int(exists),
        threshold=1,
        comparator="==",
        source_path=registry_yaml,
    )
    if not exists:
        checks = pd.DataFrame(checks_rows)
        issues = pd.DataFrame(
            [
                {
                    "issue_id": "RU_RU01",
                    "symbol": "ALL",
                    "check_id": "RU01",
                    "severity": "critical",
                    "component": "rule_universe_registry",
                    "summary": "registry missing",
                    "details_json": json.dumps({"source_path": str(registry_yaml)}, sort_keys=True),
                }
            ]
        )
        out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
        out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
        out_report_md.parent.mkdir(parents=True, exist_ok=True)
        checks.to_csv(out_checks_csv, index=False)
        issues.to_csv(out_issues_csv, index=False)
        out_report_md.write_text(
            "# OCO Rule Universe Registry Report\n\n_missing registry_\n", encoding="utf-8"
        )
        return checks, issues

    obj = yaml.safe_load(registry_yaml.read_text(encoding="utf-8"))
    obj = obj if isinstance(obj, dict) else {}
    missing = sorted(list(REQUIRED_KEYS - set(obj.keys())))
    _add_check(
        checks_rows,
        symbol="ALL",
        check_id="RU02",
        check_name="registry_required_keys_present",
        passed=len(missing) == 0,
        severity_if_fail="critical",
        metric_name="missing_keys",
        metric_value=int(len(missing)),
        threshold=0,
        comparator="==",
        source_path=registry_yaml,
        details=",".join(missing),
    )

    expected_hash = str(obj.get("hash_sha256", "")).strip()
    actual_hash = _canon_hash(obj) if obj else ""
    _add_check(
        checks_rows,
        symbol="ALL",
        check_id="RU03",
        check_name="registry_hash_matches_payload",
        passed=bool(expected_hash) and (expected_hash == actual_hash),
        severity_if_fail="critical",
        metric_name="hash_match",
        metric_value=int(bool(expected_hash) and (expected_hash == actual_hash)),
        threshold=1,
        comparator="==",
        source_path=registry_yaml,
        details=json.dumps(
            {"expected_hash": expected_hash, "actual_hash": actual_hash}, sort_keys=True
        ),
    )

    reg_syms = {str(x).upper() for x in obj.get("symbols", []) if str(x).strip()}
    need_syms = {s.upper() for s in symbols}
    _add_check(
        checks_rows,
        symbol="ALL",
        check_id="RU04",
        check_name="registry_symbol_set_complete",
        passed=need_syms.issubset(reg_syms),
        severity_if_fail="high",
        metric_name="missing_symbols",
        metric_value=int(len(need_syms - reg_syms)),
        threshold=0,
        comparator="==",
        source_path=registry_yaml,
        details=",".join(sorted(list(need_syms - reg_syms))),
    )

    allowed_fam = {str(x) for x in obj.get("allowed_families", [])}
    allowed_bar = _to_num_set(list(obj.get("allowed_barrier_keep", [])))
    allowed_hor = _to_num_set(list(obj.get("allowed_horizon_keep", [])))
    sel_mode = str(obj.get("selection_mode_contract", ""))
    rt = (
        obj.get("locked_runtime_contract", {})
        if isinstance(obj.get("locked_runtime_contract"), dict)
        else {}
    )
    missing_rt = sorted(list(LOCKED_RUNTIME_KEYS - set(rt.keys())))
    _add_check(
        checks_rows,
        symbol="ALL",
        check_id="RU05",
        check_name="registry_locked_runtime_contract_keys",
        passed=len(missing_rt) == 0,
        severity_if_fail="high",
        metric_name="missing_locked_runtime_keys",
        metric_value=int(len(missing_rt)),
        threshold=0,
        comparator="==",
        source_path=registry_yaml,
        details=",".join(missing_rt),
    )

    for symbol in sorted(list(need_syms)):
        lock_path = _lock_for_symbol(lock_dir, symbol)
        lock_ok = lock_path.exists()
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="RU06",
            check_name="live_lock_exists",
            passed=lock_ok,
            severity_if_fail="critical",
            metric_name="lock_exists",
            metric_value=int(lock_ok),
            threshold=1,
            comparator="==",
            source_path=lock_path,
        )
        if not lock_ok:
            continue
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lrt = lock.get("locked_runtime", {}) if isinstance(lock, dict) else {}
        lock_fam = _parse_csv_list(lrt.get("family_keep", ""))
        lock_bar = _parse_csv_list(lrt.get("barrier_keep", ""))
        lock_hor = _parse_csv_list(lrt.get("horizon_keep", ""))
        lock_sel = str(lrt.get("selection_mode", "")).strip()
        runtime_match = (
            (lock_fam == {str(x) for x in allowed_fam})
            and ({str(x) for x in allowed_bar} == lock_bar)
            and ({str(x) for x in allowed_hor} == lock_hor)
            and (lock_sel == sel_mode)
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="RU07",
            check_name="lock_runtime_matches_registry_universe",
            passed=runtime_match,
            severity_if_fail="critical",
            metric_name="runtime_match",
            metric_value=int(runtime_match),
            threshold=1,
            comparator="==",
            source_path=lock_path,
            details=json.dumps(
                {
                    "lock_family_keep": sorted(list(lock_fam)),
                    "registry_families": sorted(list(allowed_fam)),
                    "lock_barrier_keep": sorted(list(lock_bar)),
                    "registry_barrier_keep": sorted([str(x) for x in allowed_bar]),
                    "lock_horizon_keep": sorted(list(lock_hor)),
                    "registry_horizon_keep": sorted([str(x) for x in allowed_hor]),
                    "lock_selection_mode": lock_sel,
                    "registry_selection_mode": sel_mode,
                },
                sort_keys=True,
            ),
        )

        rs_path = _reduced_states_for_symbol(mining_base, symbol)
        rs_ok = rs_path.exists()
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="RU08",
            check_name="reduced_states_exist",
            passed=rs_ok,
            severity_if_fail="high",
            metric_name="reduced_states_exists",
            metric_value=int(rs_ok),
            threshold=1,
            comparator="==",
            source_path=rs_path,
        )
        if not rs_ok:
            continue
        rs = pd.read_csv(rs_path)
        fam_vals = {
            str(x)
            for x in rs.get("family", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        }
        bar_vals = _to_num_set(rs.get("barrier_pips", pd.Series(dtype=float)).dropna().tolist())
        hor_vals = _to_num_set(rs.get("horizon", pd.Series(dtype=float)).dropna().tolist())
        reduced_match = (
            fam_vals.issubset(allowed_fam)
            and bar_vals.issubset(allowed_bar)
            and hor_vals.issubset(allowed_hor)
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="RU09",
            check_name="reduced_states_within_registry_universe",
            passed=reduced_match,
            severity_if_fail="high",
            metric_name="reduced_states_out_of_universe",
            metric_value=int(not reduced_match),
            threshold=0,
            comparator="==",
            source_path=rs_path,
            details=json.dumps(
                {
                    "families_found": sorted(list(fam_vals)),
                    "barriers_found": sorted(list(bar_vals)),
                    "horizons_found": sorted(list(hor_vals)),
                    "allowed_families": sorted(list(allowed_fam)),
                    "allowed_barriers": sorted(list(allowed_bar)),
                    "allowed_horizons": sorted(list(allowed_hor)),
                },
                sort_keys=True,
            ),
        )

    checks = pd.DataFrame(checks_rows).sort_values(["check_id", "symbol"]).reset_index(drop=True)
    fail = checks[checks["status"].astype(str).str.lower() != "pass"].copy()
    issues = (
        pd.DataFrame(
            [
                {
                    "issue_id": f"RU_{r['symbol']}_{r['check_id']}",
                    "symbol": r["symbol"],
                    "check_id": r["check_id"],
                    "severity": r["severity_if_fail"],
                    "component": "rule_universe_registry",
                    "summary": r["check_name"],
                    "details_json": json.dumps(
                        {
                            "metric_name": r["metric_name"],
                            "metric_value": r["metric_value"],
                            "threshold": r["threshold"],
                            "details": r.get("details", ""),
                            "source_path": r.get("source_path", ""),
                        },
                        sort_keys=True,
                    ),
                }
                for _, r in fail.iterrows()
            ]
        )
        if not fail.empty
        else pd.DataFrame(
            columns=[
                "issue_id",
                "symbol",
                "check_id",
                "severity",
                "component",
                "summary",
                "details_json",
            ]
        )
    )

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    issues.to_csv(out_issues_csv, index=False)

    lines: list[str] = []
    lines.append("# OCO Rule Universe Registry Report")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    lines.append(f"- registry_yaml: `{registry_yaml}`")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    if obj:
        lines.append("## Registry Snapshot")
        lines.append(
            _table(
                pd.DataFrame(
                    [
                        {"key": "registry_version", "value": obj.get("registry_version")},
                        {"key": "effective_from_utc", "value": obj.get("effective_from_utc")},
                        {"key": "symbols", "value": ",".join(sorted(list(reg_syms)))},
                        {"key": "allowed_families", "value": ",".join(sorted(list(allowed_fam)))},
                        {
                            "key": "allowed_barrier_keep",
                            "value": ",".join([str(x) for x in sorted(list(allowed_bar))]),
                        },
                        {
                            "key": "allowed_horizon_keep",
                            "value": ",".join([str(x) for x in sorted(list(allowed_hor))]),
                        },
                        {"key": "hash_sha256", "value": expected_hash},
                        {"key": "computed_hash_sha256", "value": actual_hash},
                    ]
                )
            )
        )
        lines.append("")
    lines.append("## Checks")
    lines.append(_table(checks))
    lines.append("")
    lines.append("## Issues")
    lines.append(_table(issues))
    out_report_md.write_text("\n".join(lines), encoding="utf-8")
    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Validate OCO rule-universe pre-registration")
    p.add_argument(
        "--registry-yaml", default="configs/research/governance/oco_rule_universe_registry.yaml"
    )
    p.add_argument("--lock-dir", default="configs/research/governance/oco")
    p.add_argument("--mining-base", default="data/analysis/tick_opportunity_mining")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/oco_rule_universe_registry_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/oco_rule_universe_registry_issues.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_rule_universe_registry_report.md")
    p.add_argument("--print-hash-only", action="store_true")
    args = p.parse_args()

    if args.print_hash_only:
        if yaml is None:
            raise RuntimeError("PyYAML required")
        obj = yaml.safe_load(Path(str(args.registry_yaml)).read_text(encoding="utf-8"))
        obj = obj if isinstance(obj, dict) else {}
        print(_canon_hash(obj))
        return

    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    checks, issues = run(
        registry_yaml=Path(str(args.registry_yaml)),
        lock_dir=Path(str(args.lock_dir)),
        mining_base=Path(str(args.mining_base)),
        symbols=symbols,
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        out_report_md=Path(str(args.report_out)),
    )
    failed = (
        int((checks["status"].astype(str).str.lower() != "pass").sum()) if not checks.empty else 0
    )
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"failed_checks={failed}")


if __name__ == "__main__":
    main()
