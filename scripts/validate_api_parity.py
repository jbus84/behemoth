#!/usr/bin/env python3
"""Validate offline-vs-API parity for OCO selection.

Usage:
    uv run python scripts/validate_api_parity.py --symbol EURUSD --month 2025-01
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("validate_api_parity")

def run(
    *,
    symbol: str,
    predictions_parquet: Path,
    threshold_json: Path,
    tolerance: float = 0.0,
) -> bool:
    if not predictions_parquet.exists():
        logger.error("Predictions parquet not found: %s", predictions_parquet)
        return False
    if not threshold_json.exists():
        logger.error("Threshold JSON not found: %s", threshold_json)
        return False

    df = pd.read_parquet(predictions_parquet)
    # Filter for symbol if ALL symbols are in one file (though usually per symbol)
    if "symbol" in df.columns:
         df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()

    with threshold_json.open() as f:
        thr_cfg = json.load(f)

    month = thr_cfg.get("model_month")
    if month and "test_month" in df.columns:
        df = df[df["test_month"] == month].copy()

    if df.empty:
        logger.warning("No predictions found in %s matching model_month %s for %s", predictions_parquet, month, symbol)
        return True
    
    schedule = thr_cfg.get("threshold_schedule", {})
    static_exec = float(thr_cfg.get("threshold_exec", 0.5))
    
    logger.info("Validating parity for %s month %s (%d rows)", symbol, month, len(df))

    # Re-calculate 'selected_exec' using the API lookup logic
    # (pred_prob >= threshold)
    
    def api_logic(row):
        close_ts = pd.to_datetime(row["close_ts"], utc=True)
        day_str = close_ts.strftime("%Y-%m-%d")
        
        # Mirror of server.py _build_predictions
        if schedule and day_str in schedule:
            thr = float(schedule[day_str])
        else:
            thr = static_exec
            
        return pd.Series({"api_selected": (1 if row["pred_prob"] >= thr else 0), "api_threshold": thr, "lookup_key": day_str})

    debug_df = df.apply(api_logic, axis=1)
    df = pd.concat([df, debug_df], axis=1)
    
    mismatches = df[df["selected_exec"].astype(int) != df["api_selected"].astype(int)]
    total = len(df)
    mismatch_count = len(mismatches)
    mismatch_rate = mismatch_count / total if total > 0 else 0.0

    if mismatch_count > 0:
        logger.error("Parity Failure: %d mismatches found! (Rate: %.4f)", mismatch_count, mismatch_rate)
        # Detailed sample of mismatches
        print("\nSample Mismatches:")
        print(mismatches[["close_ts", "candidate_uid", "pred_prob", "selected_exec", "api_selected", "api_threshold", "lookup_key"]].head(20).to_string())
        return mismatch_rate <= tolerance
    else:
        logger.info("Parity Success: 100%% match between offline and API logic.")
        return True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--threshold-json", type=Path, required=True)
    p.add_argument("--tolerance", type=float, default=0.0)
    args = p.parse_args()

    success = run(
        symbol=args.symbol,
        predictions_parquet=args.predictions,
        threshold_json=args.threshold_json,
        tolerance=args.tolerance
    )
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
