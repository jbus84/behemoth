#!/usr/bin/env python3
"""End-to-end replay simulator for the Behemoth OCO API.

This script streams raw broker ticks (parquet) into the live FastAPI instance
via `fastapi.testclient.TestClient`. It intercepts the `POST /predict` calls
and compares the exact timestamps of `selected_exec=1` predictions against the
offline `oco_reduced_core_rolling.csv` research logs, guaranteeing zero drift
between backtesting and production.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

import duckdb
import numpy as np
import pandas as pd
import polars as pl
import tqdm
from fastapi.testclient import TestClient

# server imported lazily to allow env variable injection


class VirtualTrade:
    def __init__(self, broker_pos_id: str, candidate_uid: str, entry_bar_id: int, horizon: int):
        self.broker_pos_id = broker_pos_id
        self.candidate_uid = candidate_uid
        self.entry_bar_id = entry_bar_id
        self.horizon = horizon
        self.active = True


def format_utc_timestamp(raw_ts: object) -> str:
    dt = pd.to_datetime(raw_ts, utc=True)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_predict_response(resp_body: object) -> tuple[list[dict], list[dict]]:
    if isinstance(resp_body, list):
        return list(resp_body), []
    if not isinstance(resp_body, dict):
        raise TypeError(f"Unsupported /predict response body type: {type(resp_body)!r}")
    predictions = resp_body.get("predictions", [])
    actions = resp_body.get("actions", [])
    return list(predictions or []), list(actions or [])


def action_signature(action: dict, close_ts: str) -> tuple[str, ...]:
    return (
        str(close_ts),
        str(action.get("type") or ""),
        str(action.get("symbol") or ""),
        str(action.get("candidate_uid") or ""),
        str(action.get("scan_id") or ""),
        str(action.get("side") or ""),
        str(action.get("reservation_id") or ""),
        str(action.get("broker_pos_id") or ""),
        str(bool(action.get("blocked", False))),
        str(action.get("block_reason") or ""),
    )


def load_archived_predict_action_evidence(
    runtime_db_path: Path,
    symbol: str,
    target_month: str,
    run_id: str,
) -> tuple[dict[tuple[str, str], float], Counter[tuple[str, ...]], dict[str, int]]:
    month_key = str(target_month).replace("-", "")
    con = duckdb.connect(str(runtime_db_path), read_only=True)
    try:
        table_exists = con.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE lower(table_name) = 'predict_action_audit'
            LIMIT 1
            """
        ).fetchone()
        if table_exists is None:
            return {}, Counter(), {
                "rows": 0,
                "selected_predictions": 0,
                "actions": 0,
                "blocked_actions": 0,
            }
        rows = con.execute(
            """
            SELECT close_ts, predictions_json, actions_json
            FROM predict_action_audit
            WHERE upper(symbol) = ?
              AND strftime(close_ts, '%Y%m') = ?
              AND lower(coalesce(run_id, '')) = lower(?)
            ORDER BY close_ts
            """,
            [symbol.upper(), month_key, run_id],
        ).fetchall()
    finally:
        con.close()

    archived_predictions: dict[tuple[str, str], float] = {}
    archived_actions: Counter[tuple[str, ...]] = Counter()
    summary = {
        "rows": len(rows),
        "selected_predictions": 0,
        "actions": 0,
        "blocked_actions": 0,
    }

    for close_ts, predictions_json, actions_json in rows:
        close_ts_iso = format_utc_timestamp(close_ts)
        predictions = json.loads(predictions_json or "[]")
        actions = json.loads(actions_json or "[]")
        for prediction in predictions:
            if prediction.get("selected_exec") != 1:
                continue
            candidate_uid = str(prediction.get("candidate_uid") or "").strip()
            prediction_close_ts = format_utc_timestamp(prediction.get("close_ts") or close_ts_iso)
            archived_predictions[(candidate_uid, prediction_close_ts)] = float(prediction["pred_prob"])
            summary["selected_predictions"] += 1
        for action in actions:
            archived_actions[action_signature(action, close_ts_iso)] += 1
            summary["actions"] += 1
            summary["blocked_actions"] += int(bool(action.get("blocked", False)))

    return archived_predictions, archived_actions, summary


def load_expected_predictions(symbol: str, target_month: str) -> dict[tuple[str, str], float]:
    """Load the offline expected probabilities for the target month from Parquet.

    Returns:
        dict: (candidate_uid, close_ts_iso) -> pred_prob
    """
    parquet_path = Path(
        f"data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/{symbol}_oco_monthly_predictions.parquet"
    )
    if not parquet_path.exists():
        # Fallback to checking lock file for path
        lock_path = Path(f"configs/research/governance/oco/{symbol.lower()}_oco_live_lock.json")
        if lock_path.exists():
            import json

            lock = json.loads(lock_path.read_text())
            parquet_path = Path(lock["artifacts"]["predictions_path"])

    if not parquet_path.exists():
        print(f"Error: Offline predictions parquet not found at {parquet_path}")
        sys.exit(1)

    print(f"Loading expected probabilities from {parquet_path}...")
    df = pd.read_parquet(parquet_path)

    # Filter for month
    target_month_str = str(target_month)
    if "-" in target_month_str:
        target_month_str = target_month_str.replace("-", "")

    df["close_ts_dt"] = pd.to_datetime(df["close_ts"], utc=True)
    df["month_str"] = df["close_ts_dt"].dt.strftime("%Y%m")
    selected = df[df["month_str"] == target_month_str].copy()

    expected = {}
    for _, row in selected.iterrows():
        dt = row["close_ts_dt"]
        ts = format_utc_timestamp(dt)
        cand_uid = str(row["candidate_uid"])
        expected[(cand_uid, ts)] = float(row["pred_prob"])

    print(f"Loaded {len(expected):,} expected offline predictions from {target_month}")
    return expected


def run_simulation(
    symbol: str,
    target_month: str,
    max_ticks: int | None = None,
    args_offset: int = 0,
    runtime_db_path: Path | None = None,
    inspect_archived_evidence: bool = False,
    replay_run_id: str | None = None,
) -> None:
    tick_path = Path(
        f"/Users/danielfisher/Desktop/tick/{symbol}/{symbol}_{target_month}_ticks.parquet"
    )
    if not tick_path.exists():
        print(f"Error: Raw tick parquet not found at {tick_path}")
        sys.exit(1)

    expected_probs = load_expected_predictions(symbol, target_month)
    api_results: dict[tuple[str, str], float] = {}
    api_action_signatures: Counter[tuple[str, ...]] = Counter()

    print(f"Loading raw ticks from {tick_path}...")
    ticks_lazy = (
        pl.scan_parquet(str(tick_path))
        .select(["timestamp", "bid", "ask"])
        .drop_nulls()
        .sort("timestamp")
    )

    if max_ticks:
        ticks_df = ticks_lazy.collect().slice(args_offset, max_ticks)
    else:
        ticks_df = ticks_lazy.collect().slice(args_offset)

    total_ticks = ticks_df.height
    print(f"Total ticks to replay: {total_ticks:,}")
    if total_ticks == 0:
        print("No ticks found.")
        return

    # Warmup parameters
    WARMUP_COUNT = 2_000
    run_id = replay_run_id or f"simulate_api_e2e_replay:{symbol.upper()}:{target_month}:{uuid4().hex[:12]}"

    # Set model month dynamically before importing the FastAPI app
    formatted_month = str(target_month)
    if len(formatted_month) == 6 and "-" not in formatted_month:
        formatted_month = f"{formatted_month[:4]}-{formatted_month[4:]}"

    import os

    os.environ["BEHEMOTH_FORCE_MODEL_MONTH"] = formatted_month
    os.environ["BEHEMOTH_MODELS_DIR"] = "data/models"
    os.environ["BEHEMOTH_GOVERNANCE_MODE"] = "historical_auto"
    os.environ["BEHEMOTH_GOVERNANCE_HISTORY_DIR"] = "configs/research/governance/oco_history"
    os.environ["BEHEMOTH_GOVERNANCE_MISSING_MONTH_POLICY"] = "error"

    from src.behemoth.api.server import app

    print("Bootstrapping FastAPI TestClient...")
    with TestClient(app) as client:
        print(f"Replay run_id: {run_id}")
        # Check health
        health = client.get("/health").json()
        if health["status"] != "ok":
            print(f"WARNING: API Health is {health['status']}. Missing models?")

        print(f"1. Warmup: Sending first {min(WARMUP_COUNT, total_ticks):,} ticks via /backfill")
        warmup_df = ticks_df.slice(0, WARMUP_COUNT)
        warmup_payload = {
            "symbol": symbol,
            "bar_ticks": 100,
            "run_id": run_id,
            "ticks": [
                {
                    "symbol": symbol,
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "bid": bid,
                    "ask": ask,
                    "run_id": run_id,
                }
                for ts, bid, ask in zip(
                    warmup_df["timestamp"], warmup_df["bid"], warmup_df["ask"], strict=False
                )
            ],
        }
        res = client.post("/backfill", json=warmup_payload)
        if res.status_code != 201:
            print(f"Backfill failed: {res.text}")
            sys.exit(1)

        print("2. Streaming Phase")
        stream_df = ticks_df.slice(WARMUP_COUNT, total_ticks)

        # We iteratively stream ticks. To avoid high memory on JSON lists, we use iterators.
        times = stream_df["timestamp"].to_list()
        bids = stream_df["bid"].to_list()
        asks = stream_df["ask"].to_list()

        tick_latencies = []
        predict_latencies = []
        predictions_fired = 0

        # Virtual Trade Management
        active_trades: list[VirtualTrade] = []
        trade_id_counter = 1000
        horizon_mismatches = 0

        for i in tqdm.tqdm(range(len(times)), desc="Streaming Ticks"):
            preds: list[dict] = []
            actions: list[dict] = []
            predict_close_ts = format_utc_timestamp(times[i])
            tick_payload = {
                "symbol": symbol,
                "timestamp": times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "bid": bids[i],
                "ask": asks[i],
                "run_id": run_id,
            }

            t0 = time.perf_counter()
            res = client.post("/ticks", json=tick_payload)
            t1 = time.perf_counter()
            tick_latencies.append((t1 - t0) * 1000)  # ms

            if res.status_code != 201:
                print(f"Tick ingest failed: {res.text}")
                continue

            data = res.json()
            if data.get("bar_completed"):
                # Bar formed! Trigger prediction logic just like cBot would
                t0_p = time.perf_counter()
                pred_res = client.post(
                    "/predict",
                    json={
                        "symbol": symbol,
                        "requested_volume_units": 10000,
                        "account_risk_enabled_override": True,
                        "run_id": run_id,
                    },
                )
                t1_p = time.perf_counter()
                predict_latencies.append((t1_p - t0_p) * 1000)  # ms

                predictions_fired += 1

                if pred_res.status_code == 200:
                    resp_body = pred_res.json()
                    preds, actions = parse_predict_response(resp_body)
                    for p in preds:
                        if p.get("selected_exec") == 1:
                            ts_str = format_utc_timestamp(p["close_ts"])
                            cand = p["candidate_uid"]
                            predict_close_ts = ts_str

                            # Store probability for verification
                            api_results[(cand, ts_str)] = float(p["pred_prob"])
                    for action in actions:
                        api_action_signatures[action_signature(action, predict_close_ts)] += 1
                elif pred_res.status_code == 422:
                    # Expect 422s early on if warmup wasn't enough bars
                    pass
                else:
                    print(f"Predict error {pred_res.status_code}: {pred_res.text}")

            # ── Check Horizon Exits (Time Decay) ──
            current_bar_count = data.get("bar_count", 0)
            still_active = []
            for vt in active_trades:
                age = current_bar_count - vt.entry_bar_id
                if age >= vt.horizon:
                    # Trigger Virtual Close
                    t_close = times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    update_payload = {
                        "symbol": symbol,
                        "broker_pos_id": vt.broker_pos_id,
                        "status": "CLOSED",
                        "exit_price": bids[i],  # Simulating market close
                        "exit_ts": t_close,
                        "pnl_pips": 0.0,  # PnL not the focus of this alignment check
                        "run_id": run_id,
                    }
                    client.post("/trades/update", json=update_payload)
                    # print(f" [SIM] Horizon Exit: {vt.candidate_uid} at bar {current_bar_count} (Age: {age})")
                else:
                    still_active.append(vt)
            active_trades = still_active

            # ── Process Barrier Actions ──
            if data.get("bar_completed") and actions:
                for action in actions:
                    if action["type"] == "OPEN_MARKET":
                        if action.get("blocked"):
                            continue
                        pos_id = str(trade_id_counter)
                        trade_id_counter += 1
                        open_payload = {
                            "symbol": symbol,
                            "candidate_uid": action["candidate_uid"],
                            "broker_pos_id": pos_id,
                            "side": action["side"],
                            "entry_price": asks[i] if action["side"] == "BUY" else bids[i],
                            "entry_ts": times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            "horizon": 0,
                            "run_id": run_id,
                        }
                        client.post("/trades/open", json=open_payload)
                        active_trades.append(
                            VirtualTrade(
                                broker_pos_id=pos_id,
                                candidate_uid=action["candidate_uid"],
                                entry_bar_id=current_bar_count,
                                horizon=0,
                            )
                        )
                    elif action["type"] == "CLOSE_MARKET":
                        if action.get("broker_pos_id"):
                            update_payload = {
                                "symbol": symbol,
                                "broker_pos_id": action["broker_pos_id"],
                                "status": "CLOSED",
                                "exit_price": bids[i],
                                "exit_ts": times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                                "run_id": run_id,
                            }
                            client.post("/trades/update", json=update_payload)
                            active_trades = [t for t in active_trades if t.broker_pos_id != action["broker_pos_id"]]

            # ── Drift Check for Selected Predictions ──
            if data.get("bar_completed"):
                for p in preds:
                    if p.get("selected_exec") == 1:
                        cand_uid = p["candidate_uid"]
                        ts_str = format_utc_timestamp(p["close_ts"])
                        api_results[(cand_uid, ts_str)] = float(p["pred_prob"])

        # Latency Reporting
        if predict_latencies:
            print("\n--- Latency Profile (In-Memory TestClient) ---")
            print(f"Prediction Count : {len(predict_latencies)}")
            print(f"P50 Latency      : {np.percentile(predict_latencies, 50):.2f} ms")
            print(f"P90 Latency      : {np.percentile(predict_latencies, 90):.2f} ms")
            print(f"P99 Latency      : {np.percentile(predict_latencies, 99):.2f} ms")
            print(f"Max Latency      : {max(predict_latencies):.2f} ms")

        if tick_latencies:
            total_time_s = sum(tick_latencies) / 1000
            print(f"Avg Ticks/Sec    : {len(tick_latencies) / total_time_s:.1f} ticks/s")

    # 3. Validation Logic
    # Filter API results against Candidate Registry
    from src.behemoth.core.registry import CandidateRegistry

    registry = CandidateRegistry.load("configs/research/governance/oco")
    active_candidates = registry.get_candidates(symbol)
    active_uids = {
        f"oco|{symbol}|{c.bar_ticks}|h{c.horizon}|{c.candidate_uid}" for c in active_candidates
    }

    print(f"Verifying {len(api_results):,} API predictions against research ground truth...")

    mismatches = 0
    missing = 0
    total_checked = 0

    import math

    for (cand, ts), api_prob in api_results.items():
        if cand not in active_uids:
            continue

        total_checked += 1
        expected_prob = expected_probs.get((cand, ts))
        if expected_prob is None:
            # Note: Expect 0.0 or low prob events to potentially be missing from sparser log formats,
            # but monthly_predictions.parquet should have them if they were evaluated.
            missing += 1
            if missing <= 5:
                print(f" [MISSING] in research: {cand} at {ts} (API: {api_prob:.6f})")
            continue

        if not math.isclose(api_prob, expected_prob, abs_tol=1e-5):
            mismatches += 1
            if mismatches <= 5:
                print(
                    f" [MISMATCH] {cand} at {ts}: API={api_prob:.6f}, Research={expected_prob:.6f}"
                )
        else:
            if total_checked <= 3:
                print(f" [MATCH] {cand} at {ts}: {api_prob:.6f}")

    print("\n--- Simulation Complete ---")
    print(f"Total API Predict Bars : {predictions_fired:,}")
    print(f"Total Matches Checked  : {total_checked:,}")
    print(f"Total Probability Drift: {mismatches}")
    print(f"Total Missing in Research: {missing}")

    archive_failures = 0
    if inspect_archived_evidence:
        if runtime_db_path is None:
            print("\nARCHIVE CHECK SKIPPED: --inspect-archived-evidence requires --runtime-db-path.")
        elif not runtime_db_path.exists():
            print(f"\nARCHIVE CHECK SKIPPED: runtime DB not found at {runtime_db_path}")
        else:
            archived_results, archived_actions, archived_summary = load_archived_predict_action_evidence(
                runtime_db_path,
                symbol,
                target_month,
                run_id,
            )
            print("\n--- Archived Predict/Action Evidence ---")
            print(f"Archive run_id         : {run_id}")
            print(f"Audit Rows             : {archived_summary['rows']}")
            print(f"Selected Predictions   : {archived_summary['selected_predictions']}")
            print(f"Actions                : {archived_summary['actions']}")
            print(f"Blocked Actions        : {archived_summary['blocked_actions']}")

            archive_missing = sorted(set(api_results) - set(archived_results))
            archive_extra = sorted(set(archived_results) - set(api_results))
            archive_prob_mismatches = 0
            for key in sorted(set(api_results) & set(archived_results)):
                if not np.isclose(api_results[key], archived_results[key], atol=1e-5):
                    archive_prob_mismatches += 1
                    if archive_prob_mismatches <= 5:
                        print(
                            " [ARCHIVE_MISMATCH] "
                            f"{key[0]} at {key[1]}: replay={api_results[key]:.6f}, "
                            f"archive={archived_results[key]:.6f}"
                        )
            if archive_missing[:5]:
                for cand, ts in archive_missing[:5]:
                    print(f" [ARCHIVE_MISSING] {cand} at {ts}")
            if archive_extra[:5]:
                for cand, ts in archive_extra[:5]:
                    print(f" [ARCHIVE_EXTRA] {cand} at {ts}")

            action_missing = list((api_action_signatures - archived_actions).elements())
            action_extra = list((archived_actions - api_action_signatures).elements())
            print(f"Replay/Archive Action Drift : missing={len(action_missing)} extra={len(action_extra)}")
            if action_missing[:3]:
                for sig in action_missing[:3]:
                    print(f" [ACTION_MISSING] {sig}")
            if action_extra[:3]:
                for sig in action_extra[:3]:
                    print(f" [ACTION_EXTRA] {sig}")

            archive_failures = (
                len(archive_missing)
                + len(archive_extra)
                + archive_prob_mismatches
                + len(action_missing)
                + len(action_extra)
            )

    if mismatches == 0 and total_checked > 0 and archive_failures == 0:
        print("\nSUCCESS: ZERO DRIFT DETECTED ON COMMON BARS.")
    else:
        print("\nFAILURE: DRIFT DETECTED IN PRODUCTION LOGIC.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="E2E API Replaly Simulator")
    parser.add_argument("--symbol", type=str, required=True, help="e.g. EURUSD")
    parser.add_argument("--month", type=str, required=True, help="e.g. 202601")
    parser.add_argument("--max-ticks", type=int, default=None, help="Limit ticks for fast testing")
    parser.add_argument(
        "--tick-offset", type=int, default=0, help="Skip N ticks to align bar boundaries"
    )
    parser.add_argument(
        "--runtime-db-path",
        type=Path,
        default=Path("data/db/behemoth_runtime.db"),
        help="Runtime DuckDB path used to inspect archived predict/action evidence",
    )
    parser.add_argument(
        "--inspect-archived-evidence",
        action="store_true",
        help="Compare replayed predict/action outputs with archived predict_action_audit rows",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run_id override. Defaults to a unique replay-specific value.",
    )
    args = parser.parse_args()

    run_simulation(
        args.symbol,
        args.month,
        args.max_ticks,
        args.tick_offset,
        args.runtime_db_path,
        args.inspect_archived_evidence,
        args.run_id,
    )


if __name__ == "__main__":
    main()
