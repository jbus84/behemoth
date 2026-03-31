"""Offline threshold seed — replay Dukascopy ticks through the model to pre-compute
pred_prob history for get_rolling_threshold().

Run this BEFORE starting the API. Writes one parquet per symbol to --seed-dir.
The API lifespan loads these on startup.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="")
    parser.add_argument(
        "--governance-dir",
        default="configs/research/governance/oco",
    )
    parser.add_argument("--models-dir", default="models/oco")
    parser.add_argument(
        "--ticks-dir",
        default="/Users/danielfisher/Desktop/dukascopy_ticks",
    )
    parser.add_argument("--seed-dir", default="data/runtime/seed")
    parser.add_argument("--days-back", type=int, default=20)
    return parser.parse_args()


def _seed_path(seed_dir: Path, symbol: str) -> Path:
    return seed_dir / f"{symbol.upper()}_threshold_seed.parquet"


def _is_fresh(seed_file: Path) -> bool:
    """Return True if seed file exists and covers up to yesterday or later."""
    if not seed_file.exists():
        return False
    try:
        df = pd.read_parquet(seed_file, columns=["close_ts"])
        if df.empty:
            return False
        max_ts = pd.Timestamp(df["close_ts"].max())
        if max_ts.tzinfo is None:
            max_ts = max_ts.tz_localize("UTC")
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=1)
        return max_ts >= cutoff
    except Exception as exc:
        print(f"  warning: {seed_file} freshness check failed ({exc}), will regenerate", flush=True)
        return False


def _load_ticks(ticks_dir: Path, symbol: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """Read Dukascopy tick parquets for the given date range."""
    sym_dir = ticks_dir / symbol
    if not sym_dir.exists():
        return pd.DataFrame()
    start_ym = start_dt.strftime("%Y%m")
    end_ym = end_dt.strftime("%Y%m")
    relevant = sorted(
        f
        for f in sym_dir.glob(f"{symbol}_*_ticks.parquet")
        if (ym := f.stem.removeprefix(f"{symbol}_").removesuffix("_ticks"))
        and start_ym <= ym <= end_ym
    )
    if not relevant:
        return pd.DataFrame()
    frames = [pd.read_parquet(f, columns=["timestamp", "bid", "ask"]) for f in relevant]
    df = pd.concat(frames, ignore_index=True)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
    df = (
        df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    return df


def _seed_symbol(
    symbol: str,
    registry,
    models_dir: Path,
    ticks_dir: Path,
    seed_dir: Path,
    days_back: int,
) -> bool:
    """Generate seed parquet for one symbol. Returns True on success."""
    from src.behemoth.core.features import FeatureConfig, compute_feature_matrix_from_bars
    from src.behemoth.core.schemas import IncomingTick, ModelFeatures
    from src.behemoth.runtime.tick_aggregator import TickAggregator

    binding = registry.get_model_binding(symbol)
    if not binding:
        print(f"  {symbol}: no model binding — skipping", flush=True)
        return True  # not a failure, just no model

    candidates = registry.get_candidates(symbol)
    if not candidates:
        print(f"  {symbol}: no candidates — skipping", flush=True)
        return True

    # Load model
    cbm_raw = str(binding.get("model_cbm_path", "")).strip()
    thr_raw = str(binding.get("model_threshold_json_path", "")).strip()
    if not cbm_raw or not thr_raw:
        print(f"  {symbol}: model paths not configured — FAILED", flush=True)
        return False
    cbm_path = Path(cbm_raw)
    thr_path = Path(thr_raw)
    if not cbm_path.exists() or not thr_path.exists():
        print(f"  {symbol}: model artifacts missing — FAILED", flush=True)
        return False

    try:
        from catboost import CatBoostClassifier
    except ImportError:
        print(f"  {symbol}: catboost not installed — FAILED", flush=True)
        return False

    model = CatBoostClassifier()
    model.load_model(str(cbm_path))
    thr_cfg = json.loads(thr_path.read_text())
    static_thr = float(thr_cfg.get("threshold_exec", 0.5))
    model_month = str(binding.get("model_month", "")).strip()

    # Load ticks
    now_ts = datetime.now(tz=timezone.utc)
    start_dt = now_ts - timedelta(days=days_back)
    df = _load_ticks(ticks_dir, symbol, start_dt, now_ts)
    if df.empty:
        print(f"  {symbol}: no tick data for last {days_back} days — FAILED", flush=True)
        return False

    # Aggregate bars
    bar_ticks = int(candidates[0].bar_ticks)
    agg = TickAggregator(bar_ticks=bar_ticks)
    ticks = [
        IncomingTick(
            symbol=symbol,
            timestamp=row.timestamp.to_pydatetime(),
            bid=float(row.bid),
            ask=float(row.ask),
        )
        for row in df.itertuples(index=False)
    ]
    bars = agg.add_ticks(ticks)
    if not bars:
        print(f"  {symbol}: no bars generated — FAILED", flush=True)
        return False

    bars_df = pd.DataFrame([b.model_dump() for b in bars])
    all_events = []

    for cand in candidates:
        canonical_uid = f"oco|{symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"

        features_df = compute_feature_matrix_from_bars(
            bars_df,
            symbol=symbol,
            bar_ticks=bar_ticks,
            horizon=cand.horizon,
            barrier_pips=cand.barrier_pips,
            cfg=FeatureConfig(),
        )
        if features_df is None or features_df.empty:
            continue

        valid_mask = features_df.notna().all(axis=1)
        valid_features = features_df[valid_mask]
        if valid_features.empty:
            continue

        X = valid_features[
            [
                "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
                "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z", "tick_rate_z",
                "hour_utc", "hl_first", "hl_first_mean_24", "hl_pos_frac_mean_24",
                "bar_ticks", "horizon", "barrier_pips",
            ]
        ].values

        pred_probs = model.predict_proba(X)[:, 1]
        valid_bars = bars_df.loc[valid_features.index]

        for i in range(len(valid_features)):
            row_feat = valid_features.iloc[i]
            feat_obj = ModelFeatures(**row_feat.to_dict())
            all_events.append(
                {
                    "close_ts": valid_bars.iloc[i]["close_ts"],
                    "symbol": symbol,
                    "candidate_uid": canonical_uid,
                    "pred_prob": float(pred_probs[i]),
                    "threshold": static_thr,
                    "features_json": feat_obj.model_dump_json(),
                    "model_month": model_month,
                    "run_id": "threshold_seed",
                }
            )

    if not all_events:
        print(f"  {symbol}: no valid prediction events — FAILED", flush=True)
        return False

    out_df = pd.DataFrame(all_events)
    seed_dir.mkdir(parents=True, exist_ok=True)
    out_path = _seed_path(seed_dir, symbol)
    out_df.to_parquet(out_path, index=False)
    print(f"  {symbol}: {len(all_events)} events → {out_path}", flush=True)
    return True


def main() -> None:
    args = _parse_args()
    from src.behemoth.core.registry import CandidateRegistry

    governance_dir = Path(args.governance_dir)
    models_dir = Path(args.models_dir)
    ticks_dir = Path(args.ticks_dir)
    seed_dir = Path(args.seed_dir)

    registry = CandidateRegistry.load(str(governance_dir), models_dir=models_dir)
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else registry.symbols
    )

    if not symbols:
        print("[seed] no symbols with model bindings — nothing to do", flush=True)
        sys.exit(0)

    print(f"[seed] seeding {len(symbols)} symbols (days_back={args.days_back})", flush=True)
    failed = []
    for sym in symbols:
        seed_file = _seed_path(seed_dir, sym)
        if _is_fresh(seed_file):
            print(f"  {sym}: seed file is fresh — skipping", flush=True)
            continue
        if not _seed_symbol(sym, registry, models_dir, ticks_dir, seed_dir, args.days_back):
            failed.append(sym)

    if failed:
        print(f"[seed] FAILED: {', '.join(failed)}", flush=True)
        sys.exit(1)
    print("[seed] done", flush=True)


if __name__ == "__main__":
    main()
