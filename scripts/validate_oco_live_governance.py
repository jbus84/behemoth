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
) -> tuple[bool, list[Check], dict[str, Any]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks: list[Check] = []

    artifacts = lock.get("artifacts", {})
    # Integrity checks against frozen paths and hashes.
    for label, pkey, hkey in [
        ("wfo_config_hash", "wfo_config_path", "wfo_config_sha256"),
        ("reduced_config_hash", "reduced_config_path", "reduced_config_sha256"),
        ("reduced_states_hash", "reduced_states_csv_path", "reduced_states_csv_sha256"),
    ]:
        p = Path(str(artifacts.get(pkey, "")))
        if not p.exists():
            checks.append(Check(label, False, f"missing {p}"))
            continue
        got = _sha256(p)
        exp = str(artifacts.get(hkey, ""))
        checks.append(Check(label, got == exp, f"expected={exp} got={got}"))

    # Runtime config lock checks if explicit files are provided.
    if wfo_config is not None and wfo_config.exists():
        cfg = _load_yaml(wfo_config)
        lr = lock.get("locked_runtime", {})
        for k in ["threshold_mode", "rolling_threshold_days", "rolling_threshold_min_history", "execution_quantile", "oco_hold_mode", "oco_include_no_touch"]:
            checks.append(Check(f"wfo_{k}", cfg.get(k) == lr.get(k), f"cfg={cfg.get(k)!r} lock={lr.get(k)!r}"))
    if reduced_config is not None and reduced_config.exists():
        cfg = _load_yaml(reduced_config)
        lr = lock.get("locked_runtime", {})
        for k in ["locked_quantile", "selection_mode", "family_keep", "barrier_keep", "horizon_keep"]:
            checks.append(Check(f"reduced_{k}", cfg.get(k) == lr.get(k), f"cfg={cfg.get(k)!r} lock={lr.get(k)!r}"))

    # State universe check (exact key-set match).
    if state_csv is not None and state_csv.exists():
        live = _states_key(pd.read_csv(state_csv))
        frozen = _states_key(pd.DataFrame(lock.get("state_universe", {}).get("rows", [])))
        live_key = set(map(tuple, live.to_records(index=False).tolist()))
        frozen_key = set(map(tuple, frozen.to_records(index=False).tolist()))
        missing = sorted(list(frozen_key - live_key))
        extra = sorted(list(live_key - frozen_key))
        ok = (len(missing) == 0) and (len(extra) == 0)
        checks.append(Check("state_universe_exact_match", ok, f"missing={len(missing)} extra={len(extra)}"))

    # Retrain cadence guard.
    m = str(mode).strip().lower()
    due, win_start, win_end = _retrain_window(lock, as_of=as_of)
    if m == "retrain":
        ok = win_start <= as_of <= win_end
        checks.append(Check("retrain_window", ok, f"as_of={as_of} window=[{win_start},{win_end}] due={due}"))
    else:
        ok = as_of <= win_end
        checks.append(Check("lock_not_expired_for_deploy", ok, f"as_of={as_of} expiry={win_end} due={due}"))

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
    p = argparse.ArgumentParser(description="Validate OCO deployment against frozen governance lock")
    p.add_argument("--lock-path", required=True)
    p.add_argument("--mode", choices=["deploy", "retrain"], default="deploy")
    p.add_argument("--as-of", default="")
    p.add_argument("--state-csv", default="")
    p.add_argument("--wfo-config", default="")
    p.add_argument("--reduced-config", default="")
    p.add_argument("--out-json", default="")
    args = p.parse_args()

    ok, checks, meta = run(
        lock_path=Path(str(args.lock_path)),
        mode=str(args.mode),
        as_of=_parse_date(str(args.as_of)),
        state_csv=Path(str(args.state_csv)) if str(args.state_csv).strip() else None,
        wfo_config=Path(str(args.wfo_config)) if str(args.wfo_config).strip() else None,
        reduced_config=Path(str(args.reduced_config)) if str(args.reduced_config).strip() else None,
    )
    payload = {
        "ok": bool(ok),
        "meta": meta,
        "checks": [{"name": c.name, "ok": bool(c.ok), "detail": c.detail} for c in checks],
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
