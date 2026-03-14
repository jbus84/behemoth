#!/usr/bin/env python3
"""Evaluate a replay/debug run against FTMO challenge rules."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.behemoth.risk.ftmo import FtmoProfile, load_ftmo_profile, trading_day_id


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FtmoEvalOutputs:
    summary_csv: Path
    timeline_csv: Path
    daily_ledger_csv: Path
    phase_report_md: Path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_to_utc(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    rows = con.execute(
        """
        SELECT lower(column_name)
        FROM information_schema.columns
        WHERE lower(table_name) = ?
        """,
        [str(table_name).lower()],
    ).fetchall()
    return {str(r[0]).lower() for r in rows}


def _safe_query(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _load_cbot_parameters(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return {}
    try:
        raw = json.loads(txt)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    params = raw.get("Parameters", {})
    return params if isinstance(params, dict) else {}


def _boolish(raw: Any, *, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _floatish(raw: Any) -> float | None:
    try:
        if raw is None or str(raw).strip() == "":
            return None
        return float(raw)
    except Exception:
        return None


def _normalize_surface(session: dict[str, Any]) -> str:
    if str(session.get("surface", "")).strip():
        return str(session["surface"]).strip().lower()
    if "recommended_cbot" in session:
        return "ctrader"
    return "surrogate"


def _parse_fx_ccy(sym: str) -> tuple[str, str] | None:
    txt = str(sym).upper().strip()
    if len(txt) != 6:
        return None
    return txt[:3], txt[3:]


def _pip_size_for_symbol(sym: str) -> float:
    txt = str(sym).upper().strip()
    return 0.01 if txt.endswith("JPY") else 0.0001


def _pip_value_per_unit_account_ccy(symbol: str, price: float, account_ccy: str) -> float | None:
    pair = _parse_fx_ccy(symbol)
    if pair is None:
        return None
    base, quote = pair
    acct = str(account_ccy).upper().strip()
    pip = _pip_size_for_symbol(symbol)
    px = max(float(price), 1e-12)
    if acct != "USD":
        return None
    if quote == acct:
        return float(pip)
    if base == acct:
        return float(pip) / px
    return None


def _load_trades(con: duckdb.DuckDBPyConnection, symbol: str, run_id: str | None) -> pd.DataFrame:
    cols = _table_columns(con, "trades")
    if not cols:
        return pd.DataFrame()
    run_expr = "run_id" if "run_id" in cols else "NULL::VARCHAR AS run_id"
    sql = f"""
        SELECT
            internal_trade_id,
            broker_pos_id,
            symbol,
            candidate_uid,
            side,
            entry_price,
            entry_ts,
            exit_price,
            exit_ts,
            pnl_pips,
            status,
            {run_expr}
        FROM trades
        WHERE upper(symbol) = ?
    """
    params: list[Any] = [str(symbol).upper().strip()]
    if "run_id" in cols and str(run_id or "").strip():
        sql += " AND coalesce(run_id, '') = ?"
        params.append(str(run_id).strip())
    df = _safe_query(con, sql, params)
    if df.empty:
        return df
    df["entry_ts"] = _safe_to_utc(df.get("entry_ts", pd.Series(dtype=object)))
    df["exit_ts"] = _safe_to_utc(df.get("exit_ts", pd.Series(dtype=object)))
    df["pnl_pips"] = pd.to_numeric(df.get("pnl_pips", pd.Series(dtype=float)), errors="coerce")
    df["entry_price"] = pd.to_numeric(df.get("entry_price", pd.Series(dtype=float)), errors="coerce")
    df["exit_price"] = pd.to_numeric(df.get("exit_price", pd.Series(dtype=float)), errors="coerce")
    return df


def _load_snapshots(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    cols = _table_columns(con, "ftmo_account_snapshots")
    if not cols:
        return pd.DataFrame()
    sql = """
        SELECT snapshot_ts, symbol, balance, equity
        FROM ftmo_account_snapshots
        WHERE upper(symbol) = ?
        ORDER BY snapshot_ts ASC
    """
    df = _safe_query(con, sql, [str(symbol).upper().strip()])
    if df.empty:
        return df
    df["snapshot_ts"] = _safe_to_utc(df.get("snapshot_ts", pd.Series(dtype=object)))
    df["balance"] = pd.to_numeric(df.get("balance", pd.Series(dtype=float)), errors="coerce")
    df["equity"] = pd.to_numeric(df.get("equity", pd.Series(dtype=float)), errors="coerce")
    return df


def _load_reservations(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    cols = _table_columns(con, "ftmo_risk_reservations")
    if not cols:
        return pd.DataFrame()
    df = _safe_query(
        con,
        """
        SELECT
            reservation_id,
            created_ts,
            updated_ts,
            symbol,
            candidate_uid,
            broker_pos_id,
            status,
            reserved_loss_ccy,
            barrier_pips,
            cap_pips,
            cost_est_pips,
            volume_units,
            side,
            source
        FROM ftmo_risk_reservations
        WHERE upper(symbol) = ?
        ORDER BY created_ts ASC
        """,
        [str(symbol).upper().strip()],
    )
    if df.empty:
        return df
    for col in ["created_ts", "updated_ts"]:
        df[col] = _safe_to_utc(df.get(col, pd.Series(dtype=object)))
    for col in ["reserved_loss_ccy", "barrier_pips", "cap_pips", "cost_est_pips", "volume_units"]:
        df[col] = pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce")
    return df


def _load_allocator_events(con: duckdb.DuckDBPyConnection, symbol: str) -> pd.DataFrame:
    cols = _table_columns(con, "ftmo_allocator_events")
    if not cols:
        return pd.DataFrame()
    df = _safe_query(
        con,
        """
        SELECT
            event_ts,
            symbol,
            candidate_uid,
            status,
            block_reason,
            reserved_loss_ccy,
            requested_volume_units,
            pred_prob,
            threshold_exec,
            risk_rank_score,
            reservation_id
        FROM ftmo_allocator_events
        WHERE upper(symbol) = ?
        ORDER BY event_ts ASC
        """,
        [str(symbol).upper().strip()],
    )
    if df.empty:
        return df
    df["event_ts"] = _safe_to_utc(df.get("event_ts", pd.Series(dtype=object)))
    return df


def _resolve_volume_units(
    trades: pd.DataFrame,
    reservations: pd.DataFrame,
    *,
    session: dict[str, Any],
    cbot_parameters: dict[str, Any],
) -> pd.DataFrame:
    out = trades.copy()
    out["volume_units"] = pd.NA
    out["volume_source"] = ""
    default_lot = _floatish(session.get("requested_lot_size"))
    if default_lot is None:
        default_lot = _floatish(cbot_parameters.get("LotSize"))
    default_units = None if default_lot is None else float(default_lot) * 100000.0

    if not reservations.empty:
        if "broker_pos_id" in reservations.columns:
            res_by_pos = (
                reservations.dropna(subset=["broker_pos_id", "volume_units"])
                .sort_values(["updated_ts", "created_ts"], na_position="last")
                .drop_duplicates(subset=["broker_pos_id"], keep="last")
                [["broker_pos_id", "volume_units"]]
                .rename(columns={"volume_units": "volume_units_by_pos"})
            )
            out = out.merge(res_by_pos, on="broker_pos_id", how="left")
            mask = out["volume_units_by_pos"].notna()
            out.loc[mask, "volume_units"] = out.loc[mask, "volume_units_by_pos"]
            out.loc[mask, "volume_source"] = "reservation_broker_pos_id"
            out = out.drop(columns=["volume_units_by_pos"])

        if "candidate_uid" in reservations.columns:
            res_by_candidate = (
                reservations.dropna(subset=["candidate_uid", "volume_units"])
                .sort_values(["updated_ts", "created_ts"], na_position="last")
                .drop_duplicates(subset=["candidate_uid"], keep="last")
                [["candidate_uid", "volume_units"]]
                .rename(columns={"volume_units": "volume_units_by_candidate"})
            )
            out = out.merge(res_by_candidate, on="candidate_uid", how="left")
            mask = out["volume_units"].isna() & out["volume_units_by_candidate"].notna()
            out.loc[mask, "volume_units"] = out.loc[mask, "volume_units_by_candidate"]
            out.loc[mask, "volume_source"] = "reservation_candidate_uid"
            out = out.drop(columns=["volume_units_by_candidate"])

    if default_units is not None:
        mask = out["volume_units"].isna()
        out.loc[mask, "volume_units"] = float(default_units)
        out.loc[mask, "volume_source"] = "session_default_lot"
    return out


def _enrich_trades_with_economics(
    trades: pd.DataFrame,
    *,
    profile: FtmoProfile,
    session: dict[str, Any],
    reservations: pd.DataFrame,
    cbot_parameters: dict[str, Any],
) -> pd.DataFrame:
    out = _resolve_volume_units(trades, reservations, session=session, cbot_parameters=cbot_parameters)
    if out.empty:
        return out
    symbol = str(session.get("symbol", "")).upper().strip()
    pip_size = _pip_size_for_symbol(symbol)
    acct = profile.currency
    price_ref = out.get("entry_price", pd.Series(dtype=float)).fillna(
        out.get("exit_price", pd.Series(dtype=float))
    )
    out["pip_value_per_unit_ccy"] = [
        _pip_value_per_unit_account_ccy(symbol, px, acct) if pd.notna(px) else None
        for px in price_ref
    ]
    out["gross_pnl_pips"] = pd.to_numeric(out.get("pnl_pips", pd.Series(dtype=float)), errors="coerce")
    out["commission_cost_pips"] = float(profile.cost_gate.replay_round_trip_cost_pips)
    out["slippage_cost_pips"] = float(profile.cost_gate.replay_slippage_floor_pips)
    out["ftmo_overlay_cost_pips"] = out["commission_cost_pips"] + out["slippage_cost_pips"]
    out["net_pnl_pips_after_ftmo"] = out["gross_pnl_pips"] - out["ftmo_overlay_cost_pips"]
    out["gross_pnl_ccy"] = (
        out["gross_pnl_pips"]
        * pd.to_numeric(out.get("volume_units", pd.Series(dtype=float)), errors="coerce")
        * pd.to_numeric(out.get("pip_value_per_unit_ccy", pd.Series(dtype=float)), errors="coerce")
    )
    out["commission_ccy"] = (
        out["commission_cost_pips"]
        * pd.to_numeric(out.get("volume_units", pd.Series(dtype=float)), errors="coerce")
        * pd.to_numeric(out.get("pip_value_per_unit_ccy", pd.Series(dtype=float)), errors="coerce")
    )
    out["slippage_ccy"] = (
        out["slippage_cost_pips"]
        * pd.to_numeric(out.get("volume_units", pd.Series(dtype=float)), errors="coerce")
        * pd.to_numeric(out.get("pip_value_per_unit_ccy", pd.Series(dtype=float)), errors="coerce")
    )
    out["ftmo_overlay_cost_ccy"] = out["commission_ccy"] + out["slippage_ccy"]
    out["net_pnl_ccy"] = out["gross_pnl_ccy"] - out["commission_ccy"] - out["slippage_ccy"]
    out["trade_day_id_entry"] = out.get("entry_ts", pd.Series(dtype=object)).apply(
        lambda ts: trading_day_id(
            ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            timezone_name=profile.daily_reset_timezone,
            reset_hour=profile.daily_reset_hour,
            reset_minute=profile.daily_reset_minute,
        )
        if pd.notna(ts)
        else None
    )
    out["trade_day_id_exit"] = out.get("exit_ts", pd.Series(dtype=object)).apply(
        lambda ts: trading_day_id(
            ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            timezone_name=profile.daily_reset_timezone,
            reset_hour=profile.daily_reset_hour,
            reset_minute=profile.daily_reset_minute,
        )
        if pd.notna(ts)
        else None
    )
    out["pip_size"] = float(pip_size)
    return out


def _infer_snapshot_offset(profile: FtmoProfile, snapshots: pd.DataFrame) -> float:
    if snapshots.empty:
        return 0.0
    first_bal = pd.to_numeric(snapshots.get("balance", pd.Series(dtype=float)), errors="coerce").dropna()
    if first_bal.empty:
        return 0.0
    return float(first_bal.iloc[0] - float(profile.initial_balance))


def _normalize_snapshots(
    snapshots: pd.DataFrame,
    *,
    profile: FtmoProfile,
) -> tuple[pd.DataFrame, float]:
    if snapshots.empty:
        return snapshots.copy(), 0.0
    out = snapshots.copy()
    offset = _infer_snapshot_offset(profile, out)
    out["balance_norm"] = pd.to_numeric(out.get("balance", pd.Series(dtype=float)), errors="coerce") - float(offset)
    out["equity_norm"] = pd.to_numeric(out.get("equity", pd.Series(dtype=float)), errors="coerce") - float(offset)
    return out, float(offset)


def _build_base_events(
    *,
    trades: pd.DataFrame,
    snapshots: pd.DataFrame,
    profile: FtmoProfile,
    start_ts: datetime | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    closed = trades.loc[
        trades.get("status", pd.Series(dtype=str)).astype(str).str.upper() == "CLOSED"
    ].copy()
    closed = closed.sort_values("exit_ts", na_position="last").reset_index(drop=True)
    cum_net = 0.0
    for row in closed.to_dict(orient="records"):
        if pd.isna(row.get("exit_ts")):
            continue
        cum_net += float(row.get("net_pnl_ccy") or 0.0)
        rows.append(
            {
                "ts_utc": row.get("exit_ts"),
                "event_type": "trade_close",
                "actual_balance_norm": float(profile.initial_balance + cum_net),
                "actual_equity_norm": float(profile.initial_balance + cum_net),
                "trade_internal_id": row.get("internal_trade_id"),
                "candidate_uid": row.get("candidate_uid"),
                "net_pnl_ccy": float(row.get("net_pnl_ccy") or 0.0),
                "gross_pnl_ccy": float(row.get("gross_pnl_ccy") or 0.0),
                "commission_ccy": float(row.get("commission_ccy") or 0.0),
                "slippage_ccy": float(row.get("slippage_ccy") or 0.0),
            }
        )
    for row in snapshots.to_dict(orient="records"):
        if pd.isna(row.get("snapshot_ts")):
            continue
        rows.append(
            {
                "ts_utc": row.get("snapshot_ts"),
                "event_type": "snapshot",
                "actual_balance_norm": float(row.get("balance_norm") or 0.0),
                "actual_equity_norm": float(row.get("equity_norm") or 0.0),
                "trade_internal_id": None,
                "candidate_uid": None,
                "net_pnl_ccy": 0.0,
                "gross_pnl_ccy": 0.0,
                "commission_ccy": 0.0,
                "slippage_ccy": 0.0,
            }
        )
    if start_ts is not None:
        rows.append(
            {
                "ts_utc": start_ts,
                "event_type": "phase_seed",
                "actual_balance_norm": float(profile.initial_balance),
                "actual_equity_norm": float(profile.initial_balance),
                "trade_internal_id": None,
                "candidate_uid": None,
                "net_pnl_ccy": 0.0,
                "gross_pnl_ccy": 0.0,
                "commission_ccy": 0.0,
                "slippage_ccy": 0.0,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "ts_utc",
                "event_type",
                "actual_balance_norm",
                "actual_equity_norm",
                "trade_internal_id",
                "candidate_uid",
                "net_pnl_ccy",
                "gross_pnl_ccy",
                "commission_ccy",
                "slippage_ccy",
            ]
        )
    events = pd.DataFrame(rows)
    events["ts_utc"] = _safe_to_utc(events.get("ts_utc", pd.Series(dtype=object)))
    events = events.sort_values(["ts_utc", "event_type"], na_position="last").reset_index(drop=True)
    return events


def _phase_specs(profile: FtmoProfile, *, phase_mode: str) -> list[tuple[str, float]]:
    mode = str(phase_mode).strip().lower()
    if mode == "phase1_only" or str(profile.mode).strip().lower() == "one_step":
        return [("phase1", float(profile.profit_target_phase1))]
    return [
        ("phase1", float(profile.profit_target_phase1)),
        ("phase2", float(profile.profit_target_phase2)),
    ]


def _serialize_detail(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def evaluate_session(
    *,
    session_path: Path,
    out_dir: Path | None = None,
    phase_mode: str | None = None,
    economics_mode: str | None = None,
    incomplete_verdict: str = "in_progress",
) -> dict[str, str]:
    session = _read_json(session_path)
    cbot_parameters = _load_cbot_parameters(
        Path(str(session.get("bundle_cbot_parameters", "")))
        if str(session.get("bundle_cbot_parameters", "")).strip()
        else None
    )
    effective_ftmo_enabled = _boolish(
        cbot_parameters.get(
            "EnableFtmoGuards",
            session.get("ftmo_enabled_override", session.get("ftmo_enabled")),
        ),
        default=False,
    )
    ftmo_profile_id = str(
        cbot_parameters.get("FtmoProfileId")
        or session.get("ftmo_profile_id")
        or "ftmo_10k_challenge_2step"
    )
    rules_path = Path(
        str(
            session.get("ftmo_rules_path")
            or REPO_ROOT / "configs" / "research" / "governance" / "ftmo" / "ftmo_rules.yaml"
        )
    )
    phase_mode_effective = str(
        phase_mode or session.get("ftmo_phase_mode") or "full_lifecycle"
    ).strip()
    economics_mode_effective = str(
        economics_mode or session.get("ftmo_economics_mode") or "repo_overlay"
    ).strip()
    profile = load_ftmo_profile(rules_path, ftmo_profile_id)

    runtime_db = Path(str(session.get("bundle_runtime_db") or session.get("runtime_db") or ""))
    dest_dir = out_dir or Path(str(session.get("bundle_dir") or session_path.parent))
    dest_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = dest_dir / "ftmo_challenge_summary.csv"
    timeline_csv = dest_dir / "ftmo_challenge_timeline.csv"
    daily_csv = dest_dir / "ftmo_daily_ledger.csv"
    report_md = dest_dir / "ftmo_phase_report.md"

    symbol = str(session.get("symbol", "")).upper().strip()
    run_id = str(session.get("run_id", "")).strip() or None
    start_ts = _safe_to_utc(pd.Series([session.get("start_ts")])).iloc[0]
    surface = _normalize_surface(session)

    if not runtime_db.exists():
        summary = pd.DataFrame(
            [
                {
                    "run_id": session.get("run_id", ""),
                    "symbol": symbol,
                    "surface": surface,
                    "feed_source": session.get("source", ""),
                    "source_root": session.get("source_root", session.get("tick_root", "")),
                    "ftmo_enabled": bool(session.get("ftmo_enabled", False)),
                    "effective_ftmo_enabled": bool(effective_ftmo_enabled),
                    "ftmo_profile_id": profile.profile_id,
                    "ftmo_profile_mode": profile.mode,
                    "ftmo_phase_mode": phase_mode_effective,
                    "ftmo_economics_mode": economics_mode_effective,
                    "ftmo_trade_cost_gate_mode": profile.cost_gate.trade_cost_gate_mode,
                    "overall_verdict": "missing_runtime_db",
                    "current_phase_id": "phase1",
                    "phases_passed": 0,
                    "phase_count": len(_phase_specs(profile, phase_mode=phase_mode_effective)),
                    "initial_balance_ccy": float(profile.initial_balance),
                    "final_balance_ccy": float(profile.initial_balance),
                    "final_equity_ccy": float(profile.initial_balance),
                    "realized_net_profit_ccy": 0.0,
                    "gross_profit_ccy": 0.0,
                    "commission_ccy": 0.0,
                    "slippage_ccy": 0.0,
                    "ftmo_overlay_cost_ccy": 0.0,
                    "gross_profit_pips": 0.0,
                    "ftmo_overlay_cost_pips": 0.0,
                    "net_profit_pips_after_ftmo": 0.0,
                    "closed_trade_count": 0,
                    "open_trade_count": 0,
                    "snapshot_rows": 0,
                    "snapshot_offset_ccy": 0.0,
                    "snapshot_mode": "missing_runtime_db",
                    "active_reservation_count": 0,
                    "active_reserved_loss_ccy": 0.0,
                    "allocator_event_rows": 0,
                    "missing_volume_trade_rows": 0,
                    "phase1_verdict": "",
                    "phase2_verdict": "",
                    "min_trading_days_required": int(profile.min_trading_days),
                    "trading_days_completed_total": 0,
                    "profit_target_phase1_ccy": float(profile.profit_target_phase1),
                    "profit_target_phase2_ccy": float(profile.profit_target_phase2),
                    "daily_loss_limit_ccy": float(profile.daily_loss_limit),
                    "max_loss_limit_ccy": float(profile.max_loss_limit),
                }
            ]
        )
        summary.to_csv(summary_csv, index=False)
        pd.DataFrame().to_csv(timeline_csv, index=False)
        pd.DataFrame().to_csv(daily_csv, index=False)
        report_md.write_text(
            f"# FTMO Challenge Evaluation: {session.get('run_id', '')}\n\n- overall_verdict: `missing_runtime_db`\n",
            encoding="utf-8",
        )
        return {
            "ftmo_challenge_summary_csv": str(summary_csv),
            "ftmo_challenge_timeline_csv": str(timeline_csv),
            "ftmo_daily_ledger_csv": str(daily_csv),
            "ftmo_phase_report_md": str(report_md),
        }

    con = duckdb.connect(str(runtime_db), read_only=True)
    try:
        trades = _load_trades(con, symbol, run_id)
        snapshots = _load_snapshots(con, symbol)
        reservations = _load_reservations(con, symbol)
        allocator_events = _load_allocator_events(con, symbol)
    finally:
        con.close()

    trades = _enrich_trades_with_economics(
        trades,
        profile=profile,
        session=session,
        reservations=reservations,
        cbot_parameters=cbot_parameters,
    )
    snapshots_norm, snapshot_offset = _normalize_snapshots(snapshots, profile=profile)
    events = _build_base_events(
        trades=trades,
        snapshots=snapshots_norm,
        profile=profile,
        start_ts=(start_ts.to_pydatetime() if hasattr(start_ts, "to_pydatetime") else start_ts) if pd.notna(start_ts) else None,
    )

    phase_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []

    active_reservations = reservations.loc[
        reservations.get("status", pd.Series(dtype=str)).astype(str).str.upper().isin(["PENDING", "OPEN"])
    ].copy()
    active_reserved_loss_ccy = float(
        pd.to_numeric(active_reservations.get("reserved_loss_ccy", pd.Series(dtype=float)), errors="coerce")
        .fillna(0.0)
        .sum()
    )

    entry_days = {}
    for row in trades.to_dict(orient="records"):
        entry_ts = row.get("entry_ts")
        if pd.isna(entry_ts):
            continue
        ts = entry_ts.to_pydatetime() if hasattr(entry_ts, "to_pydatetime") else entry_ts
        entry_days[str(row.get("internal_trade_id"))] = trading_day_id(
            ts,
            timezone_name=profile.daily_reset_timezone,
            reset_hour=profile.daily_reset_hour,
            reset_minute=profile.daily_reset_minute,
        )

    phase_specs = _phase_specs(profile, phase_mode=phase_mode_effective)
    overall_verdict = "not_applicable" if not effective_ftmo_enabled else str(incomplete_verdict)
    current_phase_id = phase_specs[0][0] if phase_specs else "phase1"
    phase_pass_count = 0
    phase_offset = 0.0
    last_phase_end_ts: pd.Timestamp | None = None
    completed_trade_ids: set[str] = set()

    for phase_seq, (phase_id, profit_target_ccy) in enumerate(phase_specs, start=1):
        phase_events = events.loc[
            events.get("ts_utc", pd.Series(dtype=object)).notna()
            & (
                events.get("ts_utc", pd.Series(dtype=object)) >= (
                    last_phase_end_ts if last_phase_end_ts is not None else pd.Timestamp.min.tz_localize("UTC")
                )
            )
        ].copy()
        if last_phase_end_ts is not None:
            phase_events = phase_events.loc[phase_events["ts_utc"] > last_phase_end_ts].copy()
        if phase_events.empty:
            phase_rows.append(
                {
                    "phase_id": phase_id,
                    "phase_seq": phase_seq,
                    "phase_verdict": str(incomplete_verdict),
                    "phase_passed": False,
                    "phase_failed": False,
                    "profit_target_ccy": float(profit_target_ccy),
                    "realized_net_profit_ccy": 0.0,
                    "trading_days_completed": 0,
                    "pass_ts": "",
                    "fail_ts": "",
                    "violation_code": "",
                }
            )
            overall_verdict = str(incomplete_verdict)
            current_phase_id = phase_id
            break

        day_state: dict[str, dict[str, Any]] = {}
        trading_days_seen: set[str] = set()
        phase_min_equity = float(profile.initial_balance)
        phase_realized_net = 0.0
        phase_verdict = str(incomplete_verdict)
        pass_ts = pd.NaT
        fail_ts = pd.NaT
        violation_code = ""

        for ev in phase_events.to_dict(orient="records"):
            ts = ev.get("ts_utc")
            if pd.isna(ts):
                continue
            ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            balance_ccy = float(ev.get("actual_balance_norm") or 0.0) - float(phase_offset)
            equity_ccy = float(ev.get("actual_equity_norm") or 0.0) - float(phase_offset)
            phase_realized_net = balance_ccy - float(profile.initial_balance)
            phase_min_equity = min(float(phase_min_equity), float(equity_ccy))
            day_id = trading_day_id(
                ts_dt,
                timezone_name=profile.daily_reset_timezone,
                reset_hour=profile.daily_reset_hour,
                reset_minute=profile.daily_reset_minute,
            )
            if day_id not in day_state:
                day_state[day_id] = {
                    "phase_id": phase_id,
                    "phase_seq": phase_seq,
                    "trading_day_id": day_id,
                    "day_start_balance_ccy": float(balance_ccy),
                    "day_end_balance_ccy": float(balance_ccy),
                    "min_equity_ccy": float(equity_ccy),
                    "day_net_pnl_ccy": 0.0,
                    "closed_trade_count": 0,
                    "trading_day_active": False,
                    "daily_loss_limit_ccy": float(profile.daily_loss_limit),
                    "max_loss_limit_ccy": float(profile.max_loss_limit),
                    "violation_code": "",
                }
            day_row = day_state[day_id]
            day_row["day_end_balance_ccy"] = float(balance_ccy)
            day_row["min_equity_ccy"] = min(float(day_row["min_equity_ccy"]), float(equity_ccy))

            trade_id = str(ev.get("trade_internal_id") or "").strip()
            if trade_id:
                day_row["day_net_pnl_ccy"] += float(ev.get("net_pnl_ccy") or 0.0)
                day_row["closed_trade_count"] += 1
                completed_trade_ids.add(trade_id)
                trade_entry_day = entry_days.get(trade_id)
                if trade_entry_day:
                    trading_days_seen.add(trade_entry_day)
                    if trade_entry_day == day_id:
                        day_row["trading_day_active"] = True

            daily_loss_used = max(0.0, float(day_row["day_start_balance_ccy"]) - float(day_row["min_equity_ccy"]))
            max_loss_used = max(0.0, float(profile.initial_balance) - float(phase_min_equity))
            day_row["daily_loss_used_ccy"] = float(daily_loss_used)
            day_row["max_loss_used_ccy"] = float(max_loss_used)

            event_violation = ""
            if max_loss_used >= float(profile.max_loss_limit):
                event_violation = "FTMO_MAX_LOSS_LIMIT_BREACH"
            elif daily_loss_used >= float(profile.daily_loss_limit):
                event_violation = "FTMO_DAILY_LOSS_LIMIT_BREACH"

            timeline_rows.append(
                {
                    "ts_utc": ts,
                    "phase_id": phase_id,
                    "phase_seq": phase_seq,
                    "event_type": ev.get("event_type"),
                    "trading_day_id": day_id,
                    "balance_ccy": float(balance_ccy),
                    "equity_ccy": float(equity_ccy),
                    "realized_net_profit_ccy": float(phase_realized_net),
                    "daily_loss_used_ccy": float(daily_loss_used),
                    "max_loss_used_ccy": float(max_loss_used),
                    "trading_days_completed": int(len(trading_days_seen)),
                    "active_reserved_loss_ccy": float(active_reserved_loss_ccy),
                    "violation_code": event_violation,
                    "detail_json": _serialize_detail(
                        {
                            "trade_internal_id": trade_id or None,
                            "candidate_uid": ev.get("candidate_uid"),
                            "net_pnl_ccy": ev.get("net_pnl_ccy"),
                            "gross_pnl_ccy": ev.get("gross_pnl_ccy"),
                            "commission_ccy": ev.get("commission_ccy"),
                            "slippage_ccy": ev.get("slippage_ccy"),
                        }
                    ),
                }
            )

            if event_violation:
                phase_verdict = "failed"
                violation_code = event_violation
                fail_ts = ts
                day_row["violation_code"] = event_violation
                overall_verdict = "failed"
                current_phase_id = phase_id
                break

            if (
                float(phase_realized_net) >= float(profit_target_ccy)
                and len(trading_days_seen) >= int(profile.min_trading_days)
            ):
                phase_verdict = "passed"
                pass_ts = ts
                current_phase_id = phase_id
                break

        for _, row in sorted(day_state.items(), key=lambda item: item[0]):
            daily_rows.append(row)

        phase_rows.append(
            {
                "phase_id": phase_id,
                "phase_seq": phase_seq,
                "phase_verdict": phase_verdict,
                "phase_passed": phase_verdict == "passed",
                "phase_failed": phase_verdict == "failed",
                "profit_target_ccy": float(profit_target_ccy),
                "realized_net_profit_ccy": float(phase_realized_net),
                "trading_days_completed": int(len(trading_days_seen)),
                "pass_ts": "" if pd.isna(pass_ts) else str(pass_ts),
                "fail_ts": "" if pd.isna(fail_ts) else str(fail_ts),
                "violation_code": violation_code,
            }
        )

        if phase_verdict == "failed":
            overall_verdict = "failed"
            break
        if phase_verdict != "passed":
            overall_verdict = str(incomplete_verdict)
            break

        phase_pass_count += 1
        current_phase_id = phase_id
        if pd.notna(pass_ts):
            last_phase_end_ts = pass_ts
            pass_row = timeline_rows[-1] if timeline_rows else None
            if pass_row is not None:
                phase_offset += max(
                    0.0,
                    float(pass_row.get("balance_ccy") or 0.0) - float(profile.initial_balance),
                )
            else:
                phase_offset += max(0.0, float(phase_realized_net))
        if phase_seq == len(phase_specs):
            overall_verdict = "passed"

    phase_df = pd.DataFrame(phase_rows)
    timeline_df = pd.DataFrame(timeline_rows)
    daily_df = pd.DataFrame(daily_rows)

    if timeline_df.empty:
        final_balance_ccy = float(profile.initial_balance)
        final_equity_ccy = float(profile.initial_balance)
    else:
        final_balance_ccy = float(timeline_df["balance_ccy"].iloc[-1])
        final_equity_ccy = float(timeline_df["equity_ccy"].iloc[-1])

    gross_total = float(pd.to_numeric(trades.get("gross_pnl_ccy", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    commission_total = float(pd.to_numeric(trades.get("commission_ccy", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    slippage_total = float(pd.to_numeric(trades.get("slippage_ccy", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    overlay_total = float(pd.to_numeric(trades.get("ftmo_overlay_cost_ccy", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    net_total = float(pd.to_numeric(trades.get("net_pnl_ccy", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    gross_total_pips = float(pd.to_numeric(trades.get("gross_pnl_pips", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    overlay_total_pips = float(pd.to_numeric(trades.get("ftmo_overlay_cost_pips", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    net_total_pips = float(pd.to_numeric(trades.get("net_pnl_pips_after_ftmo", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())

    summary = pd.DataFrame(
        [
            {
                "run_id": session.get("run_id", ""),
                "symbol": symbol,
                "surface": surface,
                "feed_source": session.get("source", ""),
                "source_root": session.get("source_root", session.get("tick_root", "")),
                "ftmo_enabled": bool(session.get("ftmo_enabled", False)),
                "effective_ftmo_enabled": bool(effective_ftmo_enabled),
                "ftmo_profile_id": profile.profile_id,
                "ftmo_profile_mode": profile.mode,
                "ftmo_phase_mode": phase_mode_effective,
                "ftmo_economics_mode": economics_mode_effective,
                "ftmo_trade_cost_gate_mode": profile.cost_gate.trade_cost_gate_mode,
                "overall_verdict": overall_verdict,
                "current_phase_id": current_phase_id,
                "phases_passed": int(phase_pass_count),
                "phase_count": int(len(phase_specs)),
                "initial_balance_ccy": float(profile.initial_balance),
                "final_balance_ccy": float(final_balance_ccy),
                "final_equity_ccy": float(final_equity_ccy),
                "realized_net_profit_ccy": float(net_total),
                "gross_profit_ccy": float(gross_total),
                "commission_ccy": float(commission_total),
                "slippage_ccy": float(slippage_total),
                "ftmo_overlay_cost_ccy": float(overlay_total),
                "gross_profit_pips": float(gross_total_pips),
                "ftmo_overlay_cost_pips": float(overlay_total_pips),
                "net_profit_pips_after_ftmo": float(net_total_pips),
                "closed_trade_count": int(
                    (trades.get("status", pd.Series(dtype=str)).astype(str).str.upper() == "CLOSED").sum()
                ),
                "open_trade_count": int(
                    (trades.get("status", pd.Series(dtype=str)).astype(str).str.upper() == "OPEN").sum()
                ),
                "snapshot_rows": int(len(snapshots)),
                "snapshot_offset_ccy": float(snapshot_offset),
                "snapshot_mode": "raw_snapshot_offset_normalized" if not snapshots.empty else "reconstructed_only",
                "active_reservation_count": int(len(active_reservations)),
                "active_reserved_loss_ccy": float(active_reserved_loss_ccy),
                "allocator_event_rows": int(len(allocator_events)),
                "missing_volume_trade_rows": int(
                    pd.to_numeric(trades.get("volume_units", pd.Series(dtype=float)), errors="coerce").isna().sum()
                ),
                "phase1_verdict": phase_df.loc[phase_df["phase_id"] == "phase1", "phase_verdict"].iloc[0]
                if not phase_df.loc[phase_df["phase_id"] == "phase1"].empty
                else "",
                "phase2_verdict": phase_df.loc[phase_df["phase_id"] == "phase2", "phase_verdict"].iloc[0]
                if not phase_df.loc[phase_df["phase_id"] == "phase2"].empty
                else "",
                "min_trading_days_required": int(profile.min_trading_days),
                "trading_days_completed_total": int(
                    pd.to_numeric(phase_df.get("trading_days_completed", pd.Series(dtype=float)), errors="coerce")
                    .fillna(0)
                    .max()
                    if not phase_df.empty
                    else 0
                ),
                "profit_target_phase1_ccy": float(profile.profit_target_phase1),
                "profit_target_phase2_ccy": float(profile.profit_target_phase2),
                "daily_loss_limit_ccy": float(profile.daily_loss_limit),
                "max_loss_limit_ccy": float(profile.max_loss_limit),
            }
        ]
    )

    summary.to_csv(summary_csv, index=False)
    timeline_df.to_csv(timeline_csv, index=False)
    daily_df.to_csv(daily_csv, index=False)

    report_lines = [
        f"# FTMO Challenge Evaluation: {session.get('run_id', '')}",
        "",
        f"- symbol: `{symbol}`",
        f"- surface: `{surface}`",
        f"- feed_source: `{session.get('source', '')}`",
        f"- effective_ftmo_enabled: `{bool(effective_ftmo_enabled)}`",
        f"- profile_id: `{profile.profile_id}`",
        f"- profile_mode: `{profile.mode}`",
        f"- phase_mode: `{phase_mode_effective}`",
        f"- economics_mode: `{economics_mode_effective}`",
        f"- trade_cost_gate_mode: `{profile.cost_gate.trade_cost_gate_mode}`",
        f"- overall_verdict: `{overall_verdict}`",
        f"- realized_net_profit_ccy: `{net_total:.2f}`",
        f"- gross_profit_ccy: `{gross_total:.2f}`",
        f"- ftmo_overlay_cost_ccy: `{overlay_total:.2f}`",
        f"- gross_profit_pips: `{gross_total_pips:.2f}`",
        f"- net_profit_pips_after_ftmo: `{net_total_pips:.2f}`",
        f"- commission_ccy: `{commission_total:.2f}`",
        f"- slippage_ccy: `{slippage_total:.2f}`",
        f"- final_balance_ccy: `{final_balance_ccy:.2f}`",
        f"- final_equity_ccy: `{final_equity_ccy:.2f}`",
        f"- active_reserved_loss_ccy: `{active_reserved_loss_ccy:.2f}`",
        "",
        "## Phases",
        "",
    ]
    if phase_df.empty:
        report_lines.append("- no phase rows generated")
    else:
        for row in phase_df.to_dict(orient="records"):
            report_lines.append(
                f"- {row.get('phase_id')}: verdict=`{row.get('phase_verdict')}` "
                f"net=`{float(row.get('realized_net_profit_ccy') or 0.0):.2f}` "
                f"target=`{float(row.get('profit_target_ccy') or 0.0):.2f}` "
                f"trading_days=`{int(row.get('trading_days_completed') or 0)}` "
                f"violation=`{row.get('violation_code') or ''}`"
            )
    report_md.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "ftmo_challenge_summary_csv": str(summary_csv),
        "ftmo_challenge_timeline_csv": str(timeline_csv),
        "ftmo_daily_ledger_csv": str(daily_csv),
        "ftmo_phase_report_md": str(report_md),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate a run against FTMO challenge rules")
    p.add_argument("--session-json", required=True)
    p.add_argument("--out-dir", default="")
    p.add_argument("--phase-mode", default="")
    p.add_argument("--economics-mode", default="")
    p.add_argument("--incomplete-verdict", default="in_progress")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    out = evaluate_session(
        session_path=Path(str(args.session_json)),
        out_dir=(Path(str(args.out_dir)) if str(args.out_dir).strip() else None),
        phase_mode=(str(args.phase_mode).strip() or None),
        economics_mode=(str(args.economics_mode).strip() or None),
        incomplete_verdict=str(args.incomplete_verdict),
    )
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
