#!/usr/bin/env python3
"""Validate OCO deployment against frozen governance lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return dict(obj)


def _states_key(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["symbol", "bar_ticks", "horizon", "state_id"]
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"states frame missing columns: {miss}")
    x = df[cols].drop_duplicates().copy()
    x["symbol"] = x["symbol"].astype(str).str.upper()
    x["bar_ticks"] = pd.to_numeric(x["bar_ticks"], errors="coerce").astype("Int64")
    x["horizon"] = pd.to_numeric(x["horizon"], errors="coerce").astype("Int64")
    x = x.dropna(subset=["bar_ticks", "horizon"]).copy()
    x = x.sort_values(cols).reset_index(drop=True)
    return x


def _normalize_live_state_frame(df: pd.DataFrame, *, lock_symbol: str) -> pd.DataFrame:
    x = df.copy()
    if "symbol" in x.columns and lock_symbol:
        x = x[x["symbol"].astype(str).str.upper() == lock_symbol].copy()
    if "test_month" in x.columns:
        months = (
            x["test_month"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        months = months[(months != "") & (months.str.lower() != "nan")]
        if not months.empty:
            latest_month = sorted(months.unique().tolist())[-1]
            x = x[x["test_month"].astype(str).str.strip() == latest_month].copy()
    return x


def _parse_date(raw: str | None) -> date:
    if raw and str(raw).strip():
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    return datetime.now(timezone.utc).date()


def _retrain_window(lock: dict[str, Any], *, as_of: date) -> tuple[date, date, date]:
    frozen = datetime.fromisoformat(str(lock["frozen_at_utc"]).replace("Z", "+00:00")).date()
    policy = lock.get("retrain_policy", {})
    cadence = int(policy.get("cadence_days", 30))
    window = int(policy.get("window_days", 3))
    due = frozen.fromordinal(frozen.toordinal() + cadence)
    start = due.fromordinal(due.toordinal() - window)
    end = due.fromordinal(due.toordinal() + window)
    _ = as_of
    return due, start, end


def run(
    *,
    lock_path: Path,
    mode: str,
    as_of: date,
    state_csv: Path | None,
    wfo_config: Path | None,
    reduced_config: Path | None,
    data_reliability_checks_csv: Path | None = None,
    leakage_checks_csv: Path | None = None,
    execution_risk_checks_csv: Path | None = None,
) -> tuple[bool, list[Check], dict[str, Any]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks: list[Check] = []
    lock_symbol = str(lock.get("symbol", "")).upper().strip()

    artifacts = lock.get("artifacts", {})
    # Integrity checks against frozen paths and hashes.
    for label, pkey, hkey, required in [
        ("wfo_config_hash", "wfo_config_path", "wfo_config_sha256", True),
        ("reduced_config_hash", "reduced_config_path", "reduced_config_sha256", True),
        ("reduced_states_hash", "reduced_states_csv_path", "reduced_states_csv_sha256", True),
        ("predictions_hash", "predictions_path", "predictions_sha256", True),
        ("model_cbm_hash", "model_cbm_path", "model_cbm_sha256", True),
        (
            "model_threshold_json_hash",
            "model_threshold_json_path",
            "model_threshold_json_sha256",
            True,
        ),
        ("tick_exact_summary_hash", "tick_exact_summary_path", "tick_exact_summary_sha256", True),
        ("reduced_summary_hash", "reduced_summary_path", "reduced_summary_sha256", False),
    ]:
        p_txt = str(artifacts.get(pkey, "")).strip()
        exp = str(artifacts.get(hkey, "")).strip()
        if not p_txt:
            if required:
                checks.append(Check(label, False, f"missing {pkey}"))
            continue
        p = Path(p_txt)
        if (not p.exists()) or p.is_dir():
            checks.append(Check(label, False, f"missing {p}"))
            continue
        got = _sha256(p)
        checks.append(Check(label, got == exp, f"expected={exp} got={got}"))

    model_month = str(artifacts.get("model_month", "")).strip()
    model_cbm_path = Path(str(artifacts.get("model_cbm_path", "")).strip()) if str(
        artifacts.get("model_cbm_path", "")
    ).strip() else None
    model_thr_path = Path(str(artifacts.get("model_threshold_json_path", "")).strip()) if str(
        artifacts.get("model_threshold_json_path", "")
    ).strip() else None
    if model_month:
        cbm_month = ""
        if model_cbm_path is not None:
            cbm_month = model_cbm_path.stem.split("_")[-1]
        checks.append(
            Check(
                "model_month_matches_cbm_name",
                bool(cbm_month) and (cbm_month == model_month),
                f"lock={model_month!r} cbm={cbm_month!r}",
            )
        )
        thr_month = ""
        if model_thr_path is not None and model_thr_path.exists():
            try:
                thr_month = str(
                    json.loads(model_thr_path.read_text(encoding="utf-8")).get("model_month", "")
                ).strip()
            except Exception:
                thr_month = ""
        checks.append(
            Check(
                "model_month_matches_threshold_json",
                bool(thr_month) and (thr_month == model_month),
                f"lock={model_month!r} threshold_json={thr_month!r}",
            )
        )

    # Tick-exact overall pass gate.
    te_pass = artifacts.get("tick_exact_overall_pass")
    checks.append(
        Check(
            "tick_exact_overall_pass",
            te_pass is True,
            f"tick_exact_overall_pass={te_pass!r} (must be True)",
        )
    )
    if "capacity_overall_pass" in artifacts:
        cap_pass = artifacts.get("capacity_overall_pass")
        checks.append(
            Check(
                "capacity_overall_pass",
                cap_pass is True,
                f"capacity_overall_pass={cap_pass!r} (must be True)",
            )
        )
        if "live_deployable" in artifacts:
            live_deployable = artifacts.get("live_deployable")
            expected_live_deployable = (te_pass is True) and (cap_pass is True)
            checks.append(
                Check(
                    "live_deployable_consistent",
                    isinstance(live_deployable, bool)
                    and (live_deployable == expected_live_deployable),
                    (
                        f"live_deployable={live_deployable!r} "
                        f"expected={expected_live_deployable!r}"
                    ),
                )
            )

    # Git provenance gate — lock must be produced from a clean worktree.
    git_info = lock.get("git", {})
    git_dirty = git_info.get("dirty", True)
    checks.append(
        Check(
            "lock_provenance_clean",
            git_dirty is False,
            f"git.dirty={git_dirty!r} (must be False)",
        )
    )

    # Runtime config lock checks if explicit files are provided.
    if wfo_config is not None and wfo_config.exists():
        cfg = _load_yaml(wfo_config)
        lr = lock.get("locked_runtime", {})
        for k in [
            "threshold_mode",
            "rolling_threshold_days",
            "rolling_threshold_min_history",
            "execution_quantile",
            "oco_hold_mode",
            "oco_include_no_touch",
        ]:
            checks.append(
                Check(f"wfo_{k}", cfg.get(k) == lr.get(k), f"cfg={cfg.get(k)!r} lock={lr.get(k)!r}")
            )
    if reduced_config is not None and reduced_config.exists():
        cfg = _load_yaml(reduced_config)
        lr = lock.get("locked_runtime", {})
        for k in [
            "locked_quantile",
            "selection_mode",
            "family_keep",
            "barrier_keep",
            "horizon_keep",
        ]:
            checks.append(
                Check(
                    f"reduced_{k}",
                    cfg.get(k) == lr.get(k),
                    f"cfg={cfg.get(k)!r} lock={lr.get(k)!r}",
                )
            )

    # State universe check (exact key-set match).
    effective_state_csv = state_csv
    if effective_state_csv is None:
        p_txt = str(artifacts.get("reduced_states_csv_path", "")).strip()
        if p_txt:
            effective_state_csv = Path(p_txt)
    if effective_state_csv is not None and effective_state_csv.exists():
        live_raw = pd.read_csv(effective_state_csv)
        live = _states_key(_normalize_live_state_frame(live_raw, lock_symbol=lock_symbol))
        frozen = _states_key(pd.DataFrame(lock.get("state_universe", {}).get("rows", [])))
        live_key = set(map(tuple, live.to_records(index=False).tolist()))
        frozen_key = set(map(tuple, frozen.to_records(index=False).tolist()))
        missing = sorted(list(frozen_key - live_key))
        extra = sorted(list(live_key - frozen_key))
        ok = (len(missing) == 0) and (len(extra) == 0)
        checks.append(
            Check("state_universe_exact_match", ok, f"missing={len(missing)} extra={len(extra)}")
        )

    # Data reliability gate (high/critical failures block deploy/retrain).
    if data_reliability_checks_csv is not None:
        if not data_reliability_checks_csv.exists():
            checks.append(
                Check(
                    "data_reliability_artifact_exists",
                    False,
                    f"missing {data_reliability_checks_csv}",
                )
            )
        else:
            dc = pd.read_csv(data_reliability_checks_csv)
            if "symbol" in dc.columns:
                dc = dc[dc["symbol"].astype(str).str.upper() == lock_symbol].copy()
            checks.append(
                Check(
                    "data_reliability_rows_present",
                    len(dc) > 0,
                    f"symbol={lock_symbol} rows={len(dc)} path={data_reliability_checks_csv}",
                )
            )
            if len(dc) > 0:
                status = (
                    dc.get("status", pd.Series(index=dc.index, dtype=str)).astype(str).str.lower()
                )
                severity = (
                    dc.get("severity_if_fail", pd.Series(index=dc.index, dtype=str))
                    .astype(str)
                    .str.lower()
                )
                failed = status != "pass"
                critical_fail = failed & (severity == "critical")
                high_fail = failed & (severity == "high")
                checks.append(
                    Check(
                        "data_reliability_no_critical_failures",
                        int(critical_fail.sum()) == 0,
                        f"critical_failed={int(critical_fail.sum())}",
                    )
                )
                checks.append(
                    Check(
                        "data_reliability_no_high_failures",
                        int(high_fail.sum()) == 0,
                        f"high_failed={int(high_fail.sum())}",
                    )
                )

    # Leakage/label integrity gate (high/critical failures block deploy/retrain).
    if leakage_checks_csv is not None:
        if not leakage_checks_csv.exists():
            checks.append(Check("leakage_artifact_exists", False, f"missing {leakage_checks_csv}"))
        else:
            lc = pd.read_csv(leakage_checks_csv)
            if "symbol" in lc.columns:
                lc = lc[lc["symbol"].astype(str).str.upper() == lock_symbol].copy()
            checks.append(
                Check(
                    "leakage_rows_present",
                    len(lc) > 0,
                    f"symbol={lock_symbol} rows={len(lc)} path={leakage_checks_csv}",
                )
            )
            if len(lc) > 0:
                status = (
                    lc.get("status", pd.Series(index=lc.index, dtype=str)).astype(str).str.lower()
                )
                severity = (
                    lc.get("severity_if_fail", pd.Series(index=lc.index, dtype=str))
                    .astype(str)
                    .str.lower()
                )
                failed = status != "pass"
                critical_fail = failed & (severity == "critical")
                high_fail = failed & (severity == "high")
                checks.append(
                    Check(
                        "leakage_no_critical_failures",
                        int(critical_fail.sum()) == 0,
                        f"critical_failed={int(critical_fail.sum())}",
                    )
                )
                checks.append(
                    Check(
                        "leakage_no_high_failures",
                        int(high_fail.sum()) == 0,
                        f"high_failed={int(high_fail.sum())}",
                    )
                )

    # Execution-risk preflight gate (high/critical failures block deploy/retrain).
    if execution_risk_checks_csv is not None:
        if not execution_risk_checks_csv.exists():
            checks.append(
                Check(
                    "execution_risk_artifact_exists", False, f"missing {execution_risk_checks_csv}"
                )
            )
        else:
            ec = pd.read_csv(execution_risk_checks_csv)
            if "symbol" in ec.columns:
                ec = ec[ec["symbol"].astype(str).str.upper() == lock_symbol].copy()
            checks.append(
                Check(
                    "execution_risk_rows_present",
                    len(ec) > 0,
                    f"symbol={lock_symbol} rows={len(ec)} path={execution_risk_checks_csv}",
                )
            )
            if len(ec) > 0:
                status = (
                    ec.get("status", pd.Series(index=ec.index, dtype=str)).astype(str).str.lower()
                )
                severity = (
                    ec.get("severity_if_fail", pd.Series(index=ec.index, dtype=str))
                    .astype(str)
                    .str.lower()
                )
                failed = status != "pass"
                critical_fail = failed & (severity == "critical")
                high_fail = failed & (severity == "high")
                checks.append(
                    Check(
                        "execution_risk_no_critical_failures",
                        int(critical_fail.sum()) == 0,
                        f"critical_failed={int(critical_fail.sum())}",
                    )
                )
                checks.append(
                    Check(
                        "execution_risk_no_high_failures",
                        int(high_fail.sum()) == 0,
                        f"high_failed={int(high_fail.sum())}",
                    )
                )

    # Retrain cadence guard.
    m = str(mode).strip().lower()
    due, win_start, win_end = _retrain_window(lock, as_of=as_of)
    if m == "retrain":
        ok = win_start <= as_of <= win_end
        checks.append(
            Check("retrain_window", ok, f"as_of={as_of} window=[{win_start},{win_end}] due={due}")
        )
    else:
        ok = as_of <= win_end
        checks.append(
            Check("lock_not_expired_for_deploy", ok, f"as_of={as_of} expiry={win_end} due={due}")
        )

    all_ok = all(c.ok for c in checks)
    meta = {
        "symbol": lock.get("symbol"),
        "mode": m,
        "as_of": str(as_of),
        "next_due": str(due),
        "window_start": str(win_start),
        "window_end": str(win_end),
    }
    return all_ok, checks, meta


def main() -> None:
    p = argparse.ArgumentParser(
        description="Validate OCO deployment against frozen governance lock"
    )
    p.add_argument("--lock-path", required=True)
    p.add_argument("--mode", choices=["deploy", "retrain"], default="deploy")
    p.add_argument("--as-of", default="")
    p.add_argument("--state-csv", default="")
    p.add_argument("--wfo-config", default="")
    p.add_argument("--reduced-config", default="")
    p.add_argument("--data-reliability-checks-csv", default="")
    p.add_argument("--leakage-checks-csv", default="")
    p.add_argument("--execution-risk-checks-csv", default="")
    p.add_argument("--out-json", default="")
    args = p.parse_args()

    ok, checks, meta = run(
        lock_path=Path(str(args.lock_path)),
        mode=str(args.mode),
        as_of=_parse_date(str(args.as_of)),
        state_csv=Path(str(args.state_csv)) if str(args.state_csv).strip() else None,
        wfo_config=Path(str(args.wfo_config)) if str(args.wfo_config).strip() else None,
        reduced_config=Path(str(args.reduced_config)) if str(args.reduced_config).strip() else None,
        data_reliability_checks_csv=Path(str(args.data_reliability_checks_csv))
        if str(args.data_reliability_checks_csv).strip()
        else None,
        leakage_checks_csv=Path(str(args.leakage_checks_csv))
        if str(args.leakage_checks_csv).strip()
        else None,
        execution_risk_checks_csv=Path(str(args.execution_risk_checks_csv))
        if str(args.execution_risk_checks_csv).strip()
        else None,
    )
    failed_checks = [c.name for c in checks if not c.ok]
    payload = {
        "ok": bool(ok),
        "status": "pass" if ok else "fail",
        "blocker": not ok,
        "meta": meta,
        "checks": [{"name": c.name, "ok": bool(c.ok), "detail": c.detail} for c in checks],
        "failed_checks": failed_checks,
    }
    if str(args.out_json).strip():
        out = Path(str(args.out_json))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote: {out}")
    for c in checks:
        mark = "PASS" if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
