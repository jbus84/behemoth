#!/usr/bin/env python3
"""Validate offline-vs-API parity for OCO selection."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("validate_api_parity")

def run(
    *,
    symbol: str,
    predictions_parquet: Path,
    threshold_json: Path,
    tolerance: float = 0.0,
    allow_empty_month: bool = False,
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
    if not month:
        logger.error("threshold JSON missing model_month: %s", threshold_json)
        return False
    if month and "test_month" in df.columns:
        df = df[df["test_month"] == month].copy()

    if df.empty:
        msg = (
            "No predictions found in %s matching model_month %s for %s"
            % (predictions_parquet, month, symbol)
        )
        if allow_empty_month:
            logger.warning(msg)
            return True
        logger.error(msg)
        return False

    if "selected_exec" not in df.columns:
        logger.error("predictions parquet missing required column: selected_exec")
        return False
    if "pred_prob" not in df.columns or "close_ts" not in df.columns:
        logger.error("predictions parquet missing required columns: pred_prob/close_ts")
        return False
    
    schedule = thr_cfg.get("threshold_schedule", {})
    static_exec = float(thr_cfg.get("threshold_exec", 0.5))
    
    logger.info("Validating parity for %s month %s (%d rows)", symbol, month, len(df))

    # Re-calculate selected_exec using API lookup logic.
    def api_logic(row):
        close_ts = pd.to_datetime(row["close_ts"], utc=True)
        day_str = close_ts.strftime("%Y-%m-%d")

        # Mirror of server.py _build_predictions
        if schedule and day_str in schedule:
            thr = float(schedule[day_str])
        else:
            thr = static_exec

        return pd.Series(
            {
                "api_selected": (1 if row["pred_prob"] >= thr else 0),
                "api_threshold": thr,
                "lookup_key": day_str,
            }
        )

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
        print(
            mismatches[
                [
                    "close_ts",
                    "candidate_uid",
                    "pred_prob",
                    "selected_exec",
                    "api_selected",
                    "api_threshold",
                    "lookup_key",
                ]
            ]
            .head(20)
            .to_string()
        )
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
    p.add_argument(
        "--allow-empty-month",
        action="store_true",
        help="Allow passing when no predictions match model_month (not recommended).",
    )
    args = p.parse_args()

    success = run(
        symbol=args.symbol,
        predictions_parquet=args.predictions,
        threshold_json=args.threshold_json,
        tolerance=args.tolerance,
        allow_empty_month=bool(args.allow_empty_month),
    )
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
