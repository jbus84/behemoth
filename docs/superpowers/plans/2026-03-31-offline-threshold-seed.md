# Offline Threshold Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the 10+ minute threshold seed computation out of the API into a standalone CLI script, so the API starts fast and stays responsive.

**Architecture:** A new CLI script (`scripts/seed_rolling_threshold.py`) reads Dukascopy tick parquets, runs CatBoost inference, and writes per-symbol seed parquets to `data/runtime/seed/`. The API's lifespan loads these seed files into `audit_logs` on startup in seconds. `run_jforex_live.py` calls the seed script before starting the API instead of making a blocking HTTP POST.

**Tech Stack:** Python, pandas, pyarrow, CatBoost, DuckDB (via StateManager), pytest

---

### Task 1: Create the standalone seed CLI script

**Files:**
- Create: `scripts/seed_rolling_threshold.py`

- [ ] **Step 1: Create the seed script with argument parsing and per-symbol freshness check**

Create `scripts/seed_rolling_threshold.py`:

```python
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


def _is_fresh(seed_file: Path, days_back: int) -> bool:
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
    except Exception:
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
    from src.behemoth.core.registry import _sha256
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
    cbm_path = Path(str(binding.get("model_cbm_path", "")))
    thr_path = Path(str(binding.get("model_threshold_json_path", "")))
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
        if _is_fresh(seed_file, args.days_back):
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
```

- [ ] **Step 2: Verify the script runs (dry run with no tick data)**

Run: `uv run python scripts/seed_rolling_threshold.py --ticks-dir /nonexistent --seed-dir /tmp/test_seed`

Expected: Script runs, prints "no tick data" for each symbol, exits non-zero (or "no symbols" if registry can't load — either confirms the script parses and imports correctly).

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_rolling_threshold.py
git commit -m "feat: add standalone seed_rolling_threshold CLI script

Replays Dukascopy tick parquets through CatBoost models offline,
writing per-symbol seed parquets to data/runtime/seed/. Includes
per-symbol freshness check to skip already-seeded symbols."
```

---

### Task 2: Add seed file loading to API lifespan

**Files:**
- Modify: `src/behemoth/api/server.py:525-526` (add seed loading before `_lifespan_ready = True`)

- [ ] **Step 4: Write the failing test**

Add to `tests/test_api_server.py` after the `TestSeedAuditHistory` class:

```python
class TestSeedFileLoading:
    def test_seed_parquet_loaded_into_audit_logs(self, client, tmp_path):
        """Seed parquets in BEHEMOTH_SEED_DIR are loaded into audit_logs on startup."""
        import pandas as pd
        from src.behemoth.api import server

        # Create a seed parquet with known data
        seed_df = pd.DataFrame(
            {
                "close_ts": [pd.Timestamp("2026-03-30T12:00:00", tz="UTC")],
                "symbol": ["TESTSYM"],
                "candidate_uid": ["oco|TESTSYM|100|h300|test_state"],
                "pred_prob": [0.75],
                "threshold": [0.5],
                "features_json": ["{}"],
                "model_month": ["2026-02"],
                "run_id": ["threshold_seed"],
            }
        )
        seed_file = tmp_path / "TESTSYM_threshold_seed.parquet"
        seed_df.to_parquet(seed_file, index=False)

        # Inject seed into audit_logs via the loader function
        assert server._state is not None
        server._load_seed_files(tmp_path)

        # Verify the row was inserted
        row = server._state._con.execute(
            "SELECT pred_prob FROM audit_logs WHERE symbol = 'TESTSYM' AND run_id = 'threshold_seed'"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 0.75) < 1e-6
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_api_server.py::TestSeedFileLoading::test_seed_parquet_loaded_into_audit_logs -v`

Expected: FAIL — `AttributeError: module 'src.behemoth.api.server' has no attribute '_load_seed_files'`

- [ ] **Step 6: Implement `_load_seed_files()` and call it in lifespan**

In `src/behemoth/api/server.py`, add this function after `_load_models()` (around line 560):

```python
def _load_seed_files(seed_dir: Path | None = None) -> None:
    """Load pre-computed threshold seed parquets into audit_logs."""
    import pandas as pd

    if seed_dir is None:
        seed_dir = Path(os.getenv("BEHEMOTH_SEED_DIR", "data/runtime/seed"))
    if not seed_dir.exists():
        logger.info("No seed directory at %s — skipping seed load", seed_dir)
        return
    parquets = sorted(seed_dir.glob("*_threshold_seed.parquet"))
    if not parquets:
        logger.info("No seed parquets found in %s", seed_dir)
        return
    total = 0
    for pq_path in parquets:
        try:
            df = pd.read_parquet(pq_path)
            if df.empty:
                continue
            events = []
            for row in df.itertuples(index=False):
                close_ts = row.close_ts
                if hasattr(close_ts, "to_pydatetime"):
                    close_ts = close_ts.to_pydatetime()
                events.append((
                    close_ts,
                    str(row.symbol),
                    str(row.candidate_uid),
                    float(row.pred_prob),
                    float(row.threshold),
                    str(row.features_json),
                    str(row.model_month),
                    str(row.run_id),
                ))
            _state.log_audit_event_batch(events)
            total += len(events)
            logger.info("Loaded %d seed events from %s", len(events), pq_path.name)
        except Exception as exc:
            logger.error("Failed to load seed file %s: %s", pq_path.name, exc)
    logger.info("Seed loading complete: %d total events", total)
```

In the `lifespan()` function, add the seed loading call after `_load_models()` (line 502) and before `logger.info("Behemoth API started...")` (line 525):

```python
    _models_dir = Path(_config.models_dir)
    _load_models()
    _load_seed_files()
    _account_risk_rules_path = Path(_config.account_risk_rules_path)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_api_server.py::TestSeedFileLoading::test_seed_parquet_loaded_into_audit_logs -v`

Expected: PASS

- [ ] **Step 8: Run all tests to check for regressions**

Run: `uv run python -m pytest tests/test_api_server.py -v`

Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: load seed parquets into audit_logs on API startup

Add _load_seed_files() called during lifespan init. Reads
*_threshold_seed.parquet from BEHEMOTH_SEED_DIR and bulk-inserts
into audit_logs so get_rolling_threshold() returns calibrated
values from the first live predict call."
```

---

### Task 3: Update `run_jforex_live.py` to call the seed script before the API

**Files:**
- Modify: `scripts/run_jforex_live.py:290-336` (replace `_seed_audit_history` call with subprocess seed)

- [ ] **Step 10: Replace the seed call in `main()`**

In `scripts/run_jforex_live.py`, replace lines 321-329:

```python
    try:
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy", flush=True)
        _seed_audit_history(
            list(cfg.symbols),
            base_url=f"http://{cfg.api_host}:{cfg.api_port}",
            train_predictions_dir=cfg.models_dir,
            model_month=_resolve_model_month(cfg),
        )
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
```

with:

```python
    # Run offline seed BEFORE starting the API
    print("[jforex-live] running offline threshold seed", flush=True)
    seed_result = subprocess.run(
        [
            sys.executable,
            "scripts/seed_rolling_threshold.py",
            "--symbols", ",".join(cfg.symbols),
            "--governance-dir", os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"),
            "--models-dir", cfg.models_dir,
            "--ticks-dir", os.getenv("BEHEMOTH_DUKASCOPY_TICKS_DIR", "/Users/danielfisher/Desktop/dukascopy_ticks"),
            "--seed-dir", str(_repo_root() / "data" / "runtime" / "seed"),
            "--days-back", "20",
        ],
        cwd=_repo_root(),
    )
    if seed_result.returncode != 0:
        print("[jforex-live] WARNING: offline seed failed — API will start without historical thresholds", flush=True)

    print("[jforex-live] starting API", flush=True)
    api_proc = _start_api(cfg)
    java_proc: subprocess.Popen[str] | None = None

    def _shutdown(_signum: int, frame: object) -> None:
        print("\n[jforex-live] shutting down", flush=True)
        if java_proc is not None:
            _stop_process(java_proc)
        _stop_process(api_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy", flush=True)
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
```

Note: The `_start_api` and `_shutdown` definitions move to after the seed call. The full restructured `main()` becomes:

```python
def main() -> None:
    cfg = _parse_args()

    for required in (
        "BEHEMOTH_JFOREX_JNLP_URI",
        "BEHEMOTH_JFOREX_USERNAME",
        "BEHEMOTH_JFOREX_PASSWORD",
    ):
        if not os.environ.get(required):
            raise SystemExit(f"Missing required env var: {required}")

    state_json = _repo_root() / cfg.report_dir / "runtime" / "active_oco_state.json"
    if state_json.exists():
        state_json.unlink()

    # Run offline seed BEFORE starting the API
    print("[jforex-live] running offline threshold seed", flush=True)
    seed_result = subprocess.run(
        [
            sys.executable,
            "scripts/seed_rolling_threshold.py",
            "--symbols", ",".join(cfg.symbols),
            "--governance-dir", os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"),
            "--models-dir", cfg.models_dir,
            "--ticks-dir", os.getenv("BEHEMOTH_DUKASCOPY_TICKS_DIR", "/Users/danielfisher/Desktop/dukascopy_ticks"),
            "--seed-dir", str(_repo_root() / "data" / "runtime" / "seed"),
            "--days-back", "20",
        ],
        cwd=_repo_root(),
    )
    if seed_result.returncode != 0:
        print("[jforex-live] WARNING: offline seed failed — API will start without historical thresholds", flush=True)

    print("[jforex-live] starting API", flush=True)
    api_proc = _start_api(cfg)
    java_proc: subprocess.Popen[str] | None = None

    def _shutdown(_signum: int, frame: object) -> None:
        print("\n[jforex-live] shutting down", flush=True)
        if java_proc is not None:
            _stop_process(java_proc)
        _stop_process(api_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy", flush=True)
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
        time.sleep(30)
        _warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
        print("[jforex-live] warmup complete, starting JForex runner", flush=True)
        java_proc = _start_live_runner(cfg)
        print(f"[jforex-live] running (symbols={','.join(cfg.symbols)})", flush=True)

        while True:
            if api_proc.poll() is not None:
                print(f"[jforex-live] API exited ({api_proc.returncode})", flush=True)
                if java_proc is not None:
                    _stop_process(java_proc)
                sys.exit(api_proc.returncode or 1)
            if java_proc is not None and java_proc.poll() is not None:
                print(f"[jforex-live] JForex exited ({java_proc.returncode})", flush=True)
                _stop_process(api_proc)
                sys.exit(java_proc.returncode or 1)
            time.sleep(5)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)
```

- [ ] **Step 11: Add `BEHEMOTH_SEED_DIR` to the API env in `_start_api()`**

In `_start_api()`, add the seed dir to the env dict (after `BEHEMOTH_STATE_DB`):

```python
    env.update(
        {
            "UV_CACHE_DIR": ".uv_cache",
            "BEHEMOTH_GOVERNANCE_MODE": "live",
            "BEHEMOTH_GOVERNANCE_HISTORY_DIR": cfg.history_dir,
            "BEHEMOTH_MODELS_DIR": cfg.models_dir,
            "BEHEMOTH_STATE_DB": str(state_db_path),
            "BEHEMOTH_SEED_DIR": str(_repo_root() / "data" / "runtime" / "seed"),
        }
    )
```

- [ ] **Step 12: Commit**

```bash
git add scripts/run_jforex_live.py
git commit -m "fix: run threshold seed offline before API startup

Replace the blocking _seed_audit_history() HTTP POST with a
subprocess call to seed_rolling_threshold.py that runs before
the API starts. The API loads the pre-computed seed parquets
on startup via BEHEMOTH_SEED_DIR, staying responsive from
the first request."
```

---

### Task 4: Add Makefile target and run full integration test

**Files:**
- Modify: `Makefile` (add `seed-threshold` target)

- [ ] **Step 13: Add `seed-threshold` Makefile target**

Add after the `jforex-live` target in the Makefile:

```makefile
seed-threshold:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/seed_rolling_threshold.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--governance-dir $(or $(GOVERNANCE_DIR),configs/research/governance/oco) \
		--models-dir $(or $(MODELS_DIR),models/oco) \
		--ticks-dir $(or $(TICKS_DIR),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--seed-dir $(or $(SEED_DIR),data/runtime/seed) \
		--days-back $(or $(DAYS_BACK),20)
```

- [ ] **Step 14: Run the seed script end-to-end**

Run: `make seed-threshold MODELS_DIR=models/oco`

Expected: Script seeds each symbol with model bindings, writes parquets to `data/runtime/seed/`, exits 0.

- [ ] **Step 15: Run all tests**

Run: `uv run python -m pytest tests/test_api_server.py -v`

Expected: All tests PASS

- [ ] **Step 16: Commit**

```bash
git add Makefile
git commit -m "build: add seed-threshold Makefile target

Convenience target for running the offline threshold seed
independently of the live runner."
```
