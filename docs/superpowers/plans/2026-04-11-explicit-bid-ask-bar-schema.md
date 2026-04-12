# Explicit Bid/Ask Bar Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the canonical bar schema to explicit bid/ask field names everywhere, remove ambiguous legacy names and symbol-qualified mirrors, and rebuild the active-universe artifacts on the new strict contract.

**Architecture:** This is a producer-first hard schema rename. First rename the canonical schema and every producer that emits bars, then migrate every consumer to explicit side-qualified fields and add strict rejection for legacy artifacts. After code migration, regenerate the active-universe artifacts and docs so no mixed-schema outputs remain.

**Tech Stack:** Python, Polars, Pandas, DuckDB, FastAPI, Pytest, MkDocs

---

## File Map

**Primary producers**
- Modify: `src/behemoth/core/schemas.py`
- Modify: `src/behemoth/runtime/tick_aggregator.py`
- Modify: `src/behemoth/runtime/state.py`
- Modify: `scripts/build_global_tick_bars.py`
- Modify: `scripts/build_global_tick_bars_offset.py`
- Modify: `scripts/diagnose_live_replay.py`

**Primary consumers**
- Modify: `src/behemoth/core/features.py`
- Modify: `src/behemoth/api/server.py`
- Modify: `src/behemoth/runtime/barrier_manager.py`
- Modify: `scripts/build_tick_velocity_dataset.py`
- Modify: `scripts/build_tick_opportunity_ml_dataset.py`
- Modify: `scripts/run_tick_opportunity_mining.py`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py`
- Modify: `scripts/analyze_oco_stop_limit_tickfill.py`
- Modify: `scripts/select_oco_reduced_core_rolling.py`
- Modify: `scripts/verify_oco_tick_exact_shortlist.py`
- Modify: `scripts/analyze_oco_monthly_wfo_robustness.py`
- Modify: `scripts/audit_data_reliability.py`
- Modify: `scripts/validate_oco_docs_contract.py`

**Tests**
- Modify: `tests/test_tick_aggregator.py`
- Modify: `tests/test_runtime_schemas.py`
- Modify: `tests/test_duckdb_state.py`
- Modify: `tests/test_barrier_manager.py`
- Modify: `tests/test_api_server.py`
- Modify: `tests/test_diagnose_live_replay.py`
- Modify: `tests/test_oco_precompute_spread.py`
- Modify: `tests/test_tick_opportunity_ml_dataset.py`
- Modify: `tests/test_tick_opportunity_mining.py`
- Modify: `tests/test_oco_docs_contract.py`

**Generated outputs to rebuild after code lands**
- `data/global_tickbars/*`
- `data/analysis/tick_velocity/*`
- `data/analysis/tick_opportunity_mining/*`
- `docs/analysis/*`
- `site/*`

### Task 1: Lock The Canonical Schema Contract In Tests

**Files:**
- Modify: `tests/test_runtime_schemas.py`
- Modify: `tests/test_tick_aggregator.py`
- Modify: `tests/test_duckdb_state.py`
- Modify: `tests/test_diagnose_live_replay.py`

- [ ] **Step 1: Write failing schema-name tests**

```python
def test_bar_schema_uses_explicit_bid_names_only():
    bar = TickBar(
        symbol="EURUSD",
        timestamp=ts0,
        close_ts=ts1,
        open_bid=1.1000,
        high_bid=1.1010,
        low_bid=1.0990,
        close_bid=1.1005,
        high_ask=1.1012,
        close_ask=1.1007,
        spread=0.0002,
        tick_volume=100,
        hl_first=1,
        hl_pos_frac=0.4,
    )
    dumped = bar.model_dump()
    assert "open" not in dumped
    assert "high" not in dumped
    assert "low" not in dumped
    assert "close" not in dumped
    assert "ask" not in dumped
```

- [ ] **Step 2: Run targeted tests to verify RED**

Run:
```bash
uv run pytest -q \
  tests/test_runtime_schemas.py \
  tests/test_tick_aggregator.py \
  tests/test_duckdb_state.py \
  tests/test_diagnose_live_replay.py
```

Expected: failures referencing missing `open_bid` / `high_bid` / `low_bid` / `close_bid` or legacy names still present.

- [ ] **Step 3: Update runtime schema names**

```python
class TickBar(BaseModel):
    open_bid: float = Field(..., gt=0)
    high_bid: float = Field(..., gt=0)
    low_bid: float = Field(..., gt=0)
    close_bid: float = Field(..., gt=0)
    high_ask: float = Field(..., gt=0)
    close_ask: float = Field(..., gt=0)
    spread: float = Field(..., ge=0)
```

- [ ] **Step 4: Update runtime producers to emit explicit names**

```python
return TickBar(
    symbol=symbol,
    timestamp=ticks[0].timestamp,
    close_ts=ticks[-1].timestamp,
    open_bid=open_price,
    high_bid=high_price,
    low_bid=low_price,
    close_bid=close_price,
    high_ask=max(asks),
    close_ask=asks[-1],
    spread=float(np.mean(spreads)),
    ...
)
```

- [ ] **Step 5: Re-run targeted tests to verify GREEN**

Run:
```bash
uv run pytest -q \
  tests/test_runtime_schemas.py \
  tests/test_tick_aggregator.py \
  tests/test_duckdb_state.py \
  tests/test_diagnose_live_replay.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  src/behemoth/core/schemas.py \
  src/behemoth/runtime/tick_aggregator.py \
  src/behemoth/runtime/state.py \
  tests/test_runtime_schemas.py \
  tests/test_tick_aggregator.py \
  tests/test_duckdb_state.py \
  tests/test_diagnose_live_replay.py
git commit -m "refactor: rename canonical bar schema to explicit bid ask fields"
```

### Task 2: Rename Offline Bar Builders And Remove Legacy Mirrors

**Files:**
- Modify: `scripts/build_global_tick_bars.py`
- Modify: `scripts/build_global_tick_bars_offset.py`
- Modify: `tests/test_tick_aggregator.py`
- Modify: `tests/test_build_global_tick_bars_offset.py`

- [ ] **Step 1: Write failing builder tests for explicit offline schema**

```python
assert "open_bid" in bars.columns
assert "high_bid" in bars.columns
assert "low_bid" in bars.columns
assert "close_bid" in bars.columns
assert "high_ask" in bars.columns
assert "close_ask" in bars.columns
assert "open" not in bars.columns
assert "ask_EURUSD" not in bars.columns
assert "close_EURUSD" not in bars.columns
```

- [ ] **Step 2: Run builder tests to verify RED**

Run:
```bash
uv run pytest -q tests/test_tick_aggregator.py tests/test_build_global_tick_bars_offset.py
```

Expected: FAIL because the builder still emits `open/high/low/close/ask` and symbol-qualified mirrors.

- [ ] **Step 3: Rename offline builder outputs**

```python
schema={
    "open_bid": pl.Float64,
    "high_bid": pl.Float64,
    "low_bid": pl.Float64,
    "close_bid": pl.Float64,
    "high_ask": pl.Float64,
    "close_ask": pl.Float64,
    "spread": pl.Float64,
}
```

```python
.agg(
    pl.col("price").first().alias("open_bid"),
    pl.col("price").max().alias("high_bid"),
    pl.col("price").min().alias("low_bid"),
    pl.col("price").last().alias("close_bid"),
    pl.col("ask").max().alias("high_ask"),
    pl.col("ask").last().alias("close_ask"),
    pl.col("spread").mean().alias("spread"),
)
```

- [ ] **Step 4: Remove symbol-qualified mirror columns and legacy `ask` outputs**

```python
.select(
    "timestamp",
    "close_ts",
    "open_bid",
    "high_bid",
    "low_bid",
    "close_bid",
    "high_ask",
    "close_ask",
    "spread",
    ...
)
```

- [ ] **Step 5: Re-run builder tests to verify GREEN**

Run:
```bash
uv run pytest -q tests/test_tick_aggregator.py tests/test_build_global_tick_bars_offset.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  scripts/build_global_tick_bars.py \
  scripts/build_global_tick_bars_offset.py \
  tests/test_tick_aggregator.py \
  tests/test_build_global_tick_bars_offset.py
git commit -m "refactor: emit explicit bid ask offline bar schema"
```

### Task 3: Migrate Feature Extraction And Research Builders

**Files:**
- Modify: `src/behemoth/core/features.py`
- Modify: `scripts/build_tick_velocity_dataset.py`
- Modify: `scripts/build_tick_opportunity_ml_dataset.py`
- Modify: `tests/test_tick_opportunity_ml_dataset.py`

- [ ] **Step 1: Write failing feature-extraction tests**

```python
def test_extract_core_series_requires_explicit_bid_columns():
    df = pd.DataFrame({"close_bid": [1.0], "open_bid": [1.0], "high_bid": [1.1], "low_bid": [0.9]})
    close_bid, open_bid, high_bid, low_bid, *_ = _extract_core_series(df)
    assert float(close_bid.iloc[0]) == 1.0
```

```python
def test_extract_core_series_rejects_legacy_ambiguous_columns():
    df = pd.DataFrame({"close": [1.0], "open": [1.0], "high": [1.1], "low": [0.9]})
    with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
        _extract_core_series(df)
```

- [ ] **Step 2: Run research-builder tests to verify RED**

Run:
```bash
uv run pytest -q tests/test_tick_opportunity_ml_dataset.py tests/test_tick_opportunity_mining.py
```

Expected: FAIL because feature extraction still reads `open/high/low/close` or legacy fallback columns.

- [ ] **Step 3: Rename the core-series extraction contract**

```python
required = ["close_bid", "open_bid", "high_bid", "low_bid"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"legacy ambiguous bar schema unsupported: missing {missing}")

close_bid = df["close_bid"].astype(float)
open_bid = df["open_bid"].astype(float)
high_bid = df["high_bid"].astype(float)
low_bid = df["low_bid"].astype(float)
```

- [ ] **Step 4: Update downstream feature math to explicit bid naming**

```python
range_pips = (high_bid - low_bid) / pip
gap_abs = (open_bid - close_bid.shift(1)).abs() / pip
vel_h1 = (close_bid - close_bid.shift(1)) / pip
```

- [ ] **Step 5: Re-run research-builder tests to verify GREEN**

Run:
```bash
uv run pytest -q tests/test_tick_opportunity_ml_dataset.py tests/test_tick_opportunity_mining.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  src/behemoth/core/features.py \
  scripts/build_tick_velocity_dataset.py \
  scripts/build_tick_opportunity_ml_dataset.py \
  tests/test_tick_opportunity_ml_dataset.py \
  tests/test_tick_opportunity_mining.py
git commit -m "refactor: require explicit bid ask columns in research builders"
```

### Task 4: Migrate Runtime Strategy And API Consumers

**Files:**
- Modify: `src/behemoth/api/server.py`
- Modify: `src/behemoth/runtime/barrier_manager.py`
- Modify: `tests/test_barrier_manager.py`
- Modify: `tests/test_api_server.py`
- Modify: `tests/test_oco_precompute_spread.py`

- [ ] **Step 1: Write failing runtime/API tests**

```python
latest_bar = {
    "high_bid": 1.1005,
    "low_bid": 1.0990,
    "close_bid": 1.1001,
    "high_ask": 1.1007,
    "close_ask": 1.1003,
}
actions = mgr.evaluate_bar("EURUSD", 100, latest_bar["high_bid"], latest_bar["low_bid"], 0.0, 11, bar_high_ask=latest_bar["high_ask"])
assert actions
```

```python
with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
    _build_latest_bar_payload({"high": 1.1, "low": 1.0, "close": 1.05})
```

- [ ] **Step 2: Run runtime/API tests to verify RED**

Run:
```bash
uv run pytest -q tests/test_barrier_manager.py tests/test_api_server.py tests/test_oco_precompute_spread.py
```

Expected: FAIL because runtime and API still read ambiguous keys like `high`, `low`, `close`.

- [ ] **Step 3: Rename runtime/API field access**

```python
bar_high_bid = latest_bar["high_bid"]
bar_low_bid = latest_bar["low_bid"]
bar_close_bid = latest_bar["close_bid"]
bar_high_ask = latest_bar["high_ask"]
bar_close_ask = latest_bar["close_ask"]
```

```python
unrealized_pips = (
    (bar_close_bid - entry_price) / pip_size
    if side > 0
    else (entry_price - bar_close_ask) / pip_size
)
```

- [ ] **Step 4: Add strict legacy key rejection**

```python
legacy = {"open", "high", "low", "close", "ask"} & set(latest_bar)
if legacy:
    raise ValueError(f"legacy ambiguous bar schema unsupported: {sorted(legacy)}")
```

- [ ] **Step 5: Re-run runtime/API tests to verify GREEN**

Run:
```bash
uv run pytest -q tests/test_barrier_manager.py tests/test_api_server.py tests/test_oco_precompute_spread.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  src/behemoth/api/server.py \
  src/behemoth/runtime/barrier_manager.py \
  tests/test_barrier_manager.py \
  tests/test_api_server.py \
  tests/test_oco_precompute_spread.py
git commit -m "refactor: use explicit bid ask bar fields in runtime and api"
```

### Task 5: Migrate Mining, WFO, Tick-Exact, And Strict Legacy Rejection

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py`
- Modify: `scripts/analyze_oco_stop_limit_tickfill.py`
- Modify: `scripts/select_oco_reduced_core_rolling.py`
- Modify: `scripts/verify_oco_tick_exact_shortlist.py`
- Modify: `scripts/analyze_oco_monthly_wfo_robustness.py`
- Modify: `scripts/audit_data_reliability.py`
- Modify: `tests/test_oco_docs_contract.py`

- [ ] **Step 1: Write failing legacy-rejection tests for analysis consumers**

```python
with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
    load_bar_frame(pd.DataFrame({"close": [1.0], "high": [1.1], "low": [0.9]}))
```

```python
required_cols = {"open_bid", "high_bid", "low_bid", "close_bid", "high_ask", "close_ask", "spread"}
assert required_cols.issubset(set(frame.columns))
```

- [ ] **Step 2: Run the affected analysis tests to verify RED**

Run:
```bash
uv run pytest -q \
  tests/test_tick_opportunity_mining.py \
  tests/test_oco_docs_contract.py
```

Expected: FAIL because analysis readers still request `close/high/low` from parquet and docs expectations still mention legacy names.

- [ ] **Step 3: Rename all analysis readers to explicit field names**

```python
bars = pd.read_parquet(
    path,
    columns=["close_ts", "close_bid", "high_bid", "low_bid", "high_ask", "close_ask", "hl_first"],
)
close_bid = pd.to_numeric(bars["close_bid"], errors="coerce").to_numpy(dtype=float)
high_bid = pd.to_numeric(bars["high_bid"], errors="coerce").to_numpy(dtype=float)
low_bid = pd.to_numeric(bars["low_bid"], errors="coerce").to_numpy(dtype=float)
```

- [ ] **Step 4: Add shared strict schema validator**

```python
def require_explicit_bar_schema(columns: set[str]) -> None:
    legacy = {"open", "high", "low", "close", "ask"} & columns
    if legacy:
        raise ValueError(f"legacy ambiguous bar schema unsupported: {sorted(legacy)}")
```

- [ ] **Step 5: Re-run the affected analysis tests to verify GREEN**

Run:
```bash
uv run pytest -q \
  tests/test_tick_opportunity_mining.py \
  tests/test_oco_docs_contract.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  scripts/run_tick_opportunity_mining.py \
  scripts/run_tick_opportunity_monthly_wfo.py \
  scripts/analyze_oco_stop_limit_tickfill.py \
  scripts/select_oco_reduced_core_rolling.py \
  scripts/verify_oco_tick_exact_shortlist.py \
  scripts/analyze_oco_monthly_wfo_robustness.py \
  scripts/audit_data_reliability.py \
  scripts/validate_oco_docs_contract.py \
  tests/test_oco_docs_contract.py \
  tests/test_tick_opportunity_mining.py
git commit -m "refactor: enforce explicit bid ask schema in analysis pipeline"
```

### Task 6: Rebuild Active-Universe Artifacts On The New Schema

**Files:**
- Regenerate: `data/global_tickbars/*`
- Regenerate: `data/analysis/tick_velocity/*`
- Regenerate: `data/analysis/tick_opportunity_mining/*`
- Regenerate: `docs/analysis/*`
- Regenerate: `site/*`

- [ ] **Step 1: Rebuild canonical tick bars**

Run:
```bash
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --output-dir data/global_tickbars \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode utc_naive \
  --overwrite
```

Expected: all symbols rebuilt with explicit `*_bid` and ask-side columns only.

- [ ] **Step 2: Rebuild velocity datasets**

Run:
```bash
uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --bar-ticks-grid 100,1000,2000 \
  --overwrite
```

Expected: PASS with no legacy column lookup failures.

- [ ] **Step 3: Run the downstream retraining/rebuild path**

Run:
```bash
make retrain-all
```

Expected: PASS using only explicit bid/ask fields.

- [ ] **Step 4: Validate rebuilt parquet schema**

Run:
```bash
uv run python - <<'PY'
import pyarrow.parquet as pq
from pathlib import Path
path = Path("data/global_tickbars/EURUSD_100tick.parquet")
names = set(pq.read_schema(path).names)
required = {"open_bid","high_bid","low_bid","close_bid","high_ask","close_ask","spread"}
legacy = {"open","high","low","close","ask"}
assert required.issubset(names)
assert not (legacy & names)
print("schema ok")
PY
```

Expected: prints `schema ok`

- [ ] **Step 5: Commit generated outputs**

```bash
git add \
  data/global_tickbars \
  data/analysis/tick_velocity \
  data/analysis/tick_opportunity_mining \
  docs/analysis \
  site
git commit -m "build: regenerate artifacts on explicit bid ask schema"
```

### Task 7: Final Verification, Docs, And Merge Prep

**Files:**
- Modify: `docs/analysis/*` as regenerated
- Modify: `docs/strategy_bible/*` if regenerated
- Modify: `docs/superpowers/plans/2026-04-11-explicit-bid-ask-bar-schema.md`

- [ ] **Step 1: Run targeted regression suite**

Run:
```bash
uv run pytest -q \
  tests/test_runtime_schemas.py \
  tests/test_tick_aggregator.py \
  tests/test_duckdb_state.py \
  tests/test_barrier_manager.py \
  tests/test_api_server.py \
  tests/test_oco_precompute_spread.py \
  tests/test_tick_opportunity_ml_dataset.py \
  tests/test_tick_opportunity_mining.py \
  tests/test_oco_docs_contract.py
```

Expected: PASS

- [ ] **Step 2: Run docs contract and docs build**

Run:
```bash
uv run python scripts/validate_oco_docs_contract.py \
  --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv \
  --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv \
  --report-out docs/analysis/oco_docs_contract_report.md
uv run mkdocs build
```

Expected: PASS

- [ ] **Step 3: Run stage commands or record why pending**

Run:
```bash
make stage13-dukascopy-cert
make stage14-jforex-cert
```

Expected: PASS, or capture runtime-prerequisite reason if not available.

- [ ] **Step 4: Review diff for banned legacy names**

Run:
```bash
rg -n '\b(open|high|low|close|ask)\b' src scripts tests data/global_tickbars docs/analysis
```

Expected: only raw-tick contexts or intentionally non-bar domains remain; no canonical bar readers/writers should depend on ambiguous names.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "refactor: complete explicit bid ask bar schema migration"
```

