#!/usr/bin/env python3
"""Run a repo-first cBot surrogate replay without deploying to cTrader."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.replay_histdata_cbot_testclient import run as run_testclient_replay
except ModuleNotFoundError:
    from replay_histdata_cbot_testclient import run as run_testclient_replay
try:
    from scripts.evaluate_ftmo_challenge_run import evaluate_session as evaluate_ftmo_session
except ModuleNotFoundError:
    from evaluate_ftmo_challenge_run import evaluate_session as evaluate_ftmo_session
from scripts.canonical_tick_feed import (
    DEFAULT_DUKASCOPY_ROOT,
    DEFAULT_HISTDATA_ROOT,
    normalize_source,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SURROGATE_ROOT = REPO_ROOT / "data" / "analysis" / "backtest_reconcile" / "cbot_surrogate_runs"


def _parse_ts(name: str, raw: str) -> datetime:
    txt = str(raw).strip()
    if not txt:
        raise ValueError(f"{name} is required")
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    out = datetime.fromisoformat(txt)
    if out.tzinfo is None:
        return out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _bool_arg(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _default_run_id(symbol: str, start_ts: str, end_ts: str, *, source: str = "dukascopy") -> str:
    start = _parse_ts("start_ts", start_ts).strftime("%Y%m%dT%H%M%S")
    end = _parse_ts("end_ts", end_ts).strftime("%Y%m%dT%H%M%S")
    return f"{symbol.lower()}_{str(source).lower()}_{start}_{end}"


def _month_from_ts(raw: str) -> str:
    return _parse_ts("timestamp", raw).strftime("%Y-%m")


def _resolve_historical_lock_predictions_path(
    *,
    symbol: str,
    month: str,
    history_dir: Path,
) -> Path | None:
    try:
        from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
    except Exception:
        return None

    if not history_dir.exists():
        return None
    reg = HistoricalCandidateRegistry.load(history_dir)
    entry = reg.get_entry(str(symbol).upper().strip(), str(month).strip())
    if entry is None:
        return None
    pred_path = str(entry.model_binding.get("predictions_path", "")).strip()
    if not pred_path:
        return None
    return (REPO_ROOT / pred_path).resolve()


def _default_predictions_path(symbol: str, *, start_ts: str, history_dir: Path) -> Path:
    resolved = _resolve_historical_lock_predictions_path(
        symbol=symbol,
        month=_month_from_ts(start_ts),
        history_dir=history_dir,
    )
    if resolved is not None:
        return resolved
    sym = str(symbol).upper().strip()
    return (
        REPO_ROOT
        / "data"
        / "analysis"
        / "tick_opportunity_mining"
        / "wfo_2025_m3to1_oco_fullcap"
        / f"{sym}_oco_monthly_predictions.parquet"
    )


def _default_stoplimit_detail_path(symbol: str) -> Path:
    sym = str(symbol).upper().strip()
    return (
        REPO_ROOT
        / "data"
        / "analysis"
        / "tick_opportunity_mining"
        / "stop_limit_tickfill_fullcap"
        / f"{sym}_stop_limit_tickfill_detail.csv"
    )


def _default_reduced_core_schedule_path(symbol: str) -> Path:
    sym = str(symbol).upper().strip()
    return (
        REPO_ROOT
        / "data"
        / "analysis"
        / "tick_opportunity_mining"
        / "reduced_core_rolling"
        / f"{sym}_oco_reduced_state_schedule.csv"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_surrogate(
    *,
    symbol: str,
    start_ts: str,
    end_ts: str,
    run_id: str | None = None,
    source: str = "dukascopy",
    tick_root: Path = DEFAULT_HISTDATA_ROOT,
    dukascopy_root: Path = DEFAULT_DUKASCOPY_ROOT,
    warmup_ticks: int = 30000,
    lookback_days: int = 31,
    model_month: str = "",
    models_dir: Path = REPO_ROOT / "models" / "oco",
    history_dir: Path = REPO_ROOT / "configs" / "research" / "governance" / "oco_history",
    missing_month_policy: str = "error",
    historical_preflight_mode: str = "warn",
    historical_prediction_universe_mode: str = "tolerant",
    ftmo_enabled_override: bool = True,
    ftmo_rules_path: Path = REPO_ROOT / "configs" / "research" / "governance" / "ftmo" / "ftmo_rules.yaml",
    ftmo_profile_id: str = "ftmo_10k_challenge_2step",
    ftmo_phase_mode: str = "full_lifecycle",
    ftmo_economics_mode: str = "repo_overlay",
    ftmo_trade_cost_gate_mode: str = "warn",
    requested_lot_size: float = 0.05,
    enable_tick_batch: bool = True,
    tick_batch_size: int = 20,
    selected_time_tolerance_sec: float = 30.0,
    selected_parity_mode: str = "event_aligned",
    enable_sequence_fallback: bool = True,
    sequence_fallback_max_gap_sec: float = 21600.0,
    reset_runtime_db: bool = True,
    record_raw_ticks: bool = True,
    time_tolerance_sec: float = 30.0,
    price_tolerance_pips: float = 0.1,
    repo_predictions_parquet: Path | None = None,
    repo_stoplimit_detail_csv: Path | None = None,
    reduced_core_state_schedule_csv: Path | None = None,
) -> dict[str, Any]:
    sym = str(symbol).upper().strip()
    if not sym:
        raise ValueError("symbol is required")
    source_name = normalize_source(source)
    effective_tick_root = tick_root if source_name == "histdata" else dukascopy_root
    sid = str(run_id).strip() if str(run_id or "").strip() else _default_run_id(
        sym,
        start_ts,
        end_ts,
        source=source_name,
    )
    out_dir = SURROGATE_ROOT / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    predictions_path = repo_predictions_parquet or _default_predictions_path(
        sym,
        start_ts=start_ts,
        history_dir=history_dir,
    )
    stoplimit_detail_path = repo_stoplimit_detail_csv or _default_stoplimit_detail_path(sym)
    reduced_core_schedule_path = reduced_core_state_schedule_csv or _default_reduced_core_schedule_path(sym)

    runtime_db = out_dir / "runtime.db"
    events_json = out_dir / "events.json"
    summary_csv = out_dir / "execution_parity_summary.csv"
    checks_csv = out_dir / "execution_parity_checks.csv"
    mismatches_csv = out_dir / "execution_parity_mismatches.csv"
    report_out = out_dir / "execution_parity_report.md"
    local_summary_csv = out_dir / "surrogate_summary.csv"
    local_selected_mismatches_csv = out_dir / "surrogate_selected_mismatches.csv"
    local_runtime_selected_csv = out_dir / "surrogate_runtime_selected.csv"
    stage12_summary_csv = out_dir / "stage12_summary.csv"
    stage12_checks_csv = out_dir / "stage12_checks.csv"
    stage12_mismatches_csv = out_dir / "stage12_mismatches.csv"
    stage12_report_out = out_dir / "stage12_report.md"
    signal_gap_analysis_csv = out_dir / "surrogate_signal_gap_analysis.csv"
    signal_feature_diff_csv = out_dir / "surrogate_signal_feature_diff.csv"
    debug_http_trace_path = out_dir / "http_trace.ndjson"

    local_summary, execution_summary, execution_checks, execution_mismatches = run_testclient_replay(
        symbol=sym,
        tick_root=effective_tick_root,
        source=source_name,
        runtime_db=runtime_db,
        events_json=events_json,
        repo_predictions_parquet=predictions_path,
        repo_stoplimit_detail_csv=stoplimit_detail_path,
        reduced_core_state_schedule_csv=reduced_core_schedule_path,
        start_ts=start_ts,
        end_ts=end_ts,
        warmup_ticks=int(warmup_ticks),
        lookback_days=int(lookback_days),
        warmup_source="history_tail",
        phase_bar_ticks=100,
        tick_offset=0,
        model_month=str(model_month),
        models_dir=models_dir,
        history_dir=history_dir,
        missing_month_policy=str(missing_month_policy),
        historical_preflight_mode=str(historical_preflight_mode),
        historical_prediction_universe_mode=str(historical_prediction_universe_mode),
        ftmo_enabled_override=bool(ftmo_enabled_override),
        ftmo_rules_path=ftmo_rules_path,
        ftmo_profile_id=str(ftmo_profile_id),
        ftmo_trade_cost_gate_mode=str(ftmo_trade_cost_gate_mode),
        requested_lot_size=float(requested_lot_size),
        enable_tick_batch=bool(enable_tick_batch),
        tick_batch_size=int(tick_batch_size),
        selected_time_tolerance_sec=float(selected_time_tolerance_sec),
        selected_parity_mode=str(selected_parity_mode),
        enable_sequence_fallback=bool(enable_sequence_fallback),
        sequence_fallback_max_gap_sec=float(sequence_fallback_max_gap_sec),
        reset_runtime_db=bool(reset_runtime_db),
        record_raw_ticks=bool(record_raw_ticks),
        time_tolerance_sec=float(time_tolerance_sec),
        price_tolerance_pips=float(price_tolerance_pips),
        out_summary_csv=summary_csv,
        out_checks_csv=checks_csv,
        out_mismatches_csv=mismatches_csv,
        report_out=report_out,
        local_summary_csv=local_summary_csv,
        local_selected_mismatches_csv=local_selected_mismatches_csv,
        local_signal_gap_analysis_csv=signal_gap_analysis_csv,
        local_signal_feature_diff_csv=signal_feature_diff_csv,
        local_runtime_selected_csv=local_runtime_selected_csv,
        stage12_summary_csv=stage12_summary_csv,
        stage12_checks_csv=stage12_checks_csv,
        stage12_mismatches_csv=stage12_mismatches_csv,
        stage12_report_out=stage12_report_out,
        signal_gap_classify_window_sec=300.0,
        debug_run_id=sid,
        debug_http_trace_path=debug_http_trace_path,
    )

    session = {
        "run_id": sid,
        "symbol": sym,
        "source": source_name,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "tick_root": str(tick_root),
        "dukascopy_root": str(dukascopy_root),
        "source_root": str(effective_tick_root),
        "runtime_db": str(runtime_db),
        "events_json": str(events_json),
        "http_trace": str(debug_http_trace_path),
        "repo_predictions_parquet": str(predictions_path),
        "repo_stoplimit_detail_csv": str(stoplimit_detail_path),
        "reduced_core_state_schedule_csv": str(reduced_core_schedule_path),
        "out_dir": str(out_dir),
        "models_dir": str(models_dir),
        "history_dir": str(history_dir),
        "missing_month_policy": str(missing_month_policy),
        "historical_preflight_mode": str(historical_preflight_mode),
        "historical_prediction_universe_mode": str(historical_prediction_universe_mode),
        "ftmo_enabled": bool(ftmo_enabled_override),
        "ftmo_enabled_override": bool(ftmo_enabled_override),
        "ftmo_rules_path": str(ftmo_rules_path),
        "ftmo_profile_id": str(ftmo_profile_id),
        "ftmo_phase_mode": str(ftmo_phase_mode),
        "ftmo_economics_mode": str(ftmo_economics_mode),
        "ftmo_trade_cost_gate_mode": str(ftmo_trade_cost_gate_mode),
        "selected_time_tolerance_sec": float(selected_time_tolerance_sec),
        "selected_parity_mode": str(selected_parity_mode),
        "time_tolerance_sec": float(time_tolerance_sec),
        "requested_lot_size": float(requested_lot_size),
        "enable_tick_batch": bool(enable_tick_batch),
        "tick_batch_size": int(tick_batch_size),
        "local_summary_rows": int(len(local_summary)),
        "execution_summary_rows": int(len(execution_summary)),
        "execution_checks_rows": int(len(execution_checks)),
        "execution_mismatches_rows": int(len(execution_mismatches)),
        "signal_gap_analysis_csv": str(signal_gap_analysis_csv),
        "signal_feature_diff_csv": str(signal_feature_diff_csv),
        "surface": "surrogate",
    }
    session_json = out_dir / "surrogate_session.json"
    _write_json(session_json, session)
    session.update(
        evaluate_ftmo_session(
            session_path=session_json,
            out_dir=out_dir,
            phase_mode=str(ftmo_phase_mode),
            economics_mode=str(ftmo_economics_mode),
        )
    )
    _write_json(session_json, session)
    session["surrogate_session_json"] = str(session_json)
    return session


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a repo-first cBot surrogate replay")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start-ts", required=True)
    p.add_argument("--end-ts", required=True)
    p.add_argument("--run-id", default="")
    p.add_argument("--source", default="dukascopy")
    p.add_argument("--tick-root", default=str(DEFAULT_HISTDATA_ROOT))
    p.add_argument("--dukascopy-root", default=str(DEFAULT_DUKASCOPY_ROOT))
    p.add_argument("--warmup-ticks", type=int, default=30000)
    p.add_argument("--lookback-days", type=int, default=31)
    p.add_argument("--model-month", default="")
    p.add_argument("--models-dir", default=str(REPO_ROOT / "models" / "oco"))
    p.add_argument("--history-dir", default=str(REPO_ROOT / "configs" / "research" / "governance" / "oco_history"))
    p.add_argument("--missing-month-policy", default="error")
    p.add_argument("--historical-preflight-mode", default="warn")
    p.add_argument("--historical-prediction-universe-mode", default="tolerant")
    p.add_argument("--ftmo-enabled-override", default="true")
    p.add_argument(
        "--ftmo-rules-path",
        default=str(REPO_ROOT / "configs" / "research" / "governance" / "ftmo" / "ftmo_rules.yaml"),
    )
    p.add_argument("--ftmo-profile-id", default="ftmo_10k_challenge_2step")
    p.add_argument("--ftmo-phase-mode", default="full_lifecycle")
    p.add_argument("--ftmo-economics-mode", default="repo_overlay")
    p.add_argument("--ftmo-trade-cost-gate-mode", default="warn")
    p.add_argument("--requested-lot-size", type=float, default=0.05)
    p.add_argument("--enable-tick-batch", default="true")
    p.add_argument("--tick-batch-size", type=int, default=20)
    p.add_argument("--selected-time-tolerance-sec", type=float, default=30.0)
    p.add_argument("--selected-parity-mode", default="event_aligned", choices=["strict", "event_aligned"])
    p.add_argument("--enable-sequence-fallback", default="true")
    p.add_argument("--sequence-fallback-max-gap-sec", type=float, default=21600.0)
    p.add_argument("--reset-runtime-db", default="true")
    p.add_argument("--record-raw-ticks", default="true")
    p.add_argument("--time-tolerance-sec", type=float, default=30.0)
    p.add_argument("--price-tolerance-pips", type=float, default=0.1)
    p.add_argument("--repo-predictions-parquet", default="")
    p.add_argument("--repo-stoplimit-detail-csv", default="")
    p.add_argument("--reduced-core-state-schedule-csv", default="")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    out = run_surrogate(
        symbol=str(args.symbol),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        run_id=str(args.run_id).strip() or None,
        source=str(args.source),
        tick_root=Path(str(args.tick_root)),
        dukascopy_root=Path(str(args.dukascopy_root)),
        warmup_ticks=int(args.warmup_ticks),
        lookback_days=int(args.lookback_days),
        model_month=str(args.model_month),
        models_dir=Path(str(args.models_dir)),
        history_dir=Path(str(args.history_dir)),
        missing_month_policy=str(args.missing_month_policy),
        historical_preflight_mode=str(args.historical_preflight_mode),
        historical_prediction_universe_mode=str(args.historical_prediction_universe_mode),
        ftmo_enabled_override=_bool_arg(str(args.ftmo_enabled_override)),
        ftmo_rules_path=Path(str(args.ftmo_rules_path)),
        ftmo_profile_id=str(args.ftmo_profile_id),
        ftmo_phase_mode=str(args.ftmo_phase_mode),
        ftmo_economics_mode=str(args.ftmo_economics_mode),
        ftmo_trade_cost_gate_mode=str(args.ftmo_trade_cost_gate_mode),
        requested_lot_size=float(args.requested_lot_size),
        enable_tick_batch=_bool_arg(str(args.enable_tick_batch)),
        tick_batch_size=int(args.tick_batch_size),
        selected_time_tolerance_sec=float(args.selected_time_tolerance_sec),
        selected_parity_mode=str(args.selected_parity_mode),
        enable_sequence_fallback=_bool_arg(str(args.enable_sequence_fallback)),
        sequence_fallback_max_gap_sec=float(args.sequence_fallback_max_gap_sec),
        reset_runtime_db=_bool_arg(str(args.reset_runtime_db)),
        record_raw_ticks=_bool_arg(str(args.record_raw_ticks)),
        time_tolerance_sec=float(args.time_tolerance_sec),
        price_tolerance_pips=float(args.price_tolerance_pips),
        repo_predictions_parquet=(
            Path(str(args.repo_predictions_parquet))
            if str(args.repo_predictions_parquet).strip()
            else None
        ),
        repo_stoplimit_detail_csv=(
            Path(str(args.repo_stoplimit_detail_csv))
            if str(args.repo_stoplimit_detail_csv).strip()
            else None
        ),
        reduced_core_state_schedule_csv=(
            Path(str(args.reduced_core_state_schedule_csv))
            if str(args.reduced_core_state_schedule_csv).strip()
            else None
        ),
    )
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
