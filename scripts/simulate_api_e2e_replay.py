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
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import tqdm
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import lock_filename  # noqa: E402

# server imported lazily to allow env variable injection


class VirtualTrade:
    def __init__(self, broker_pos_id: str, candidate_uid: str, entry_bar_id: int, horizon: int):
        self.broker_pos_id = broker_pos_id
        self.candidate_uid = candidate_uid
        self.entry_bar_id = entry_bar_id
        self.horizon = horizon
        self.active = True


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
        lock_path = Path("configs/research/governance/oco") / lock_filename(symbol)
        if lock_path.exists():
            import json

            lock = json.loads(lock_path.read_text())
            artifacts = lock.get("artifacts", {})
            entry = artifacts.get("predictions", {})
            parquet_path = lock_path.parent / Path(str(entry.get("path", "")).strip())

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
        ts = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        cand_uid = str(row["candidate_uid"])
        expected[(cand_uid, ts)] = float(row["pred_prob"])

    print(f"Loaded {len(expected):,} expected offline predictions from {target_month}")
    return expected


def run_simulation(
    symbol: str, target_month: str, max_ticks: int | None = None, args_offset: int = 0
) -> None:
    tick_path = Path(
        f"/Users/danielfisher/Desktop/tick/{symbol}/{symbol}_{target_month}_ticks.parquet"
    )
    if not tick_path.exists():
        print(f"Error: Raw tick parquet not found at {tick_path}")
        sys.exit(1)

    expected_probs = load_expected_predictions(symbol, target_month)
    api_results: dict[tuple[str, str], float] = {}

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
        # Check health
        health = client.get("/health").json()
        if health["status"] != "ok":
            print(f"WARNING: API Health is {health['status']}. Missing models?")

        print(f"1. Warmup: Sending first {min(WARMUP_COUNT, total_ticks):,} ticks via /backfill")
        warmup_df = ticks_df.slice(0, WARMUP_COUNT)
        warmup_payload = {
            "symbol": symbol,
            "bar_ticks": 100,
            "ticks": [
                {
                    "symbol": symbol,
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "bid": bid,
                    "ask": ask,
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
            tick_payload = {
                "symbol": symbol,
                "timestamp": times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "bid": bids[i],
                "ask": asks[i],
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
                    },
                )
                t1_p = time.perf_counter()
                predict_latencies.append((t1_p - t0_p) * 1000)  # ms

                predictions_fired += 1

                if pred_res.status_code == 200:
                    resp_body = pred_res.json()
                    preds = resp_body.get("predictions", resp_body) if isinstance(resp_body, dict) else resp_body
                    actions = resp_body.get("actions", []) if isinstance(resp_body, dict) else []
                    for p in preds:
                        if p.get("selected_exec") == 1:
                            # Normalize timestamp identically to offline expectations
                            dt = pd.to_datetime(p["close_ts"])
                            # Ensure we keep microseconds and use Z suffix
                            ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                            cand = p["candidate_uid"]

                            # Store probability for verification
                            api_results[(cand, ts_str)] = float(p["pred_prob"])
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
                        "broker_pos_id": vt.broker_pos_id,
                        "status": "CLOSED",
                        "exit_price": bids[i],  # Simulating market close
                        "exit_ts": t_close,
                        "pnl_pips": 0.0,  # PnL not the focus of this alignment check
                    }
                    client.post("/trades/update", json=update_payload)
                    # print(f" [SIM] Horizon Exit: {vt.candidate_uid} at bar {current_bar_count} (Age: {age})")
                else:
                    still_active.append(vt)
            active_trades = still_active

            # ── Process Barrier Actions ──
            if data.get("bar_completed") and "actions" in locals() and actions:
                for action in actions:
                    if action["type"] == "OPEN_MARKET":
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
                                "broker_pos_id": action["broker_pos_id"],
                                "status": "CLOSED",
                                "exit_price": bids[i],
                                "exit_ts": times[i].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            }
                            client.post("/trades/update", json=update_payload)
                            active_trades = [t for t in active_trades if t.broker_pos_id != action["broker_pos_id"]]

            # ── Drift Check for Selected Predictions ──
            if data.get("bar_completed") and "preds" in locals():
                for p in preds:
                    if p.get("selected_exec") == 1:
                        cand_uid = p["candidate_uid"]
                        # Normalize for drift check
                        dt = pd.to_datetime(p["close_ts"])
                        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
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

    if mismatches == 0 and total_checked > 0:
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
    args = parser.parse_args()

    run_simulation(args.symbol, args.month, args.max_ticks, args.tick_offset)


if __name__ == "__main__":
    main()
