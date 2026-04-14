# OCO Stop-Entry Touch-Bar Close Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace optimistic barrier-price OCO entry economics with side-correct touch-bar executable-close entry semantics across labeling, verification, and runtime contract coverage.

**Architecture:** Keep the current architecture intact: CatBoost scores on the signal bar, Python registers a barrier scan, and later completed bars confirm breakout touches. The contract changes only the OCO economic model: BUY references anchor off `close_ask`, SELL references anchor off `close_bid`, and entries are priced at the touch-bar executable close rather than the barrier level.

**Tech Stack:** Python (`pandas`, `numpy`, `pytest`), FastAPI runtime state, DuckDB-backed runtime state, Java/JForex parity tests where needed.

---

## File Map

- Modify: `scripts/build_tick_opportunity_ml_dataset.py`
  - Owns OCO label construction and must become the canonical touch-bar-close entry implementation.
- Modify: `tests/test_oco_precompute_spread.py`
  - Owns focused red/green tests for OCO spread-aware trigger and entry semantics.
- Modify: `scripts/verify_oco_tick_exact_shortlist.py`
  - Must mirror the exact research contract for parity checks.
- Modify: `tests/test_verify_oco_tick_exact_shortlist.py`
  - Must lock verifier parity to the new side-correct reference/entry semantics.
- Modify: `src/behemoth/runtime/barrier_manager.py`
  - Runtime touch detection contract documentation and comments must match the new economics.
- Modify: `tests/test_barrier_manager.py`
  - Must cover scan reference and touch semantics expected by runtime.
- Modify: `src/behemoth/api/server.py`
  - Registration path must explicitly document and use the correct per-side signal-bar reference semantics where applicable.
- Modify: `docs/analysis/*` and regenerated artifact files
  - Produced only after implementation and retraining; do not hand-edit.

### Task 1: Fix OCO label economics in the label builder

**Files:**
- Modify: `scripts/build_tick_opportunity_ml_dataset.py`
- Test: `tests/test_oco_precompute_spread.py`

- [ ] **Step 1: Write the failing tests for side-correct references and touch-bar-close entries**

Add tests to `tests/test_oco_precompute_spread.py` that prove:

```python
def test_buy_trigger_anchors_off_signal_close_ask():
    # BUY should not trigger just because high_ask clears close_bid + barrier.
    # It must clear close_ask + barrier.
    ...

def test_buy_entry_uses_touch_bar_close_ask_not_barrier_price():
    # BUY touch occurs, and gross pips must use touch-bar close_ask as the entry.
    ...

def test_sell_entry_uses_touch_bar_close_bid_not_barrier_price():
    # SELL touch occurs, and gross pips must use touch-bar close_bid as the entry.
    ...
```

- [ ] **Step 2: Run the focused label tests and verify they fail**

Run:

```bash
uv run pytest -q tests/test_oco_precompute_spread.py
```

Expected:
- at least one new failure showing the current implementation still anchors BUY off `close_bid` or still prices entry at the barrier.

- [ ] **Step 3: Implement the minimal OCO label builder change**

Update `_oco_precompute(...)` in `scripts/build_tick_opportunity_ml_dataset.py` so the contract is:

```python
buy_ref = close_ask[i0]
sell_ref = close_bid[i0]
up_thr = buy_ref + k * pip
dn_thr = sell_ref - k * pip
...
hu = high_ask[idx] >= up_thr
hd = low_bid[idx] <= dn_thr
...
entry_price_use = np.where(
    side[use] == -1,
    close_bid[touch_i_abs[use]],
    close_ask[touch_i_abs[use]],
)
exit_price_use = np.where(
    side[use] == -1,
    close_ask[exit_i[use]],
    close_bid[exit_i[use]],
)
gross[use] = side[use].astype(float) * ((exit_price_use - entry_price_use) / pip)
```

Important details:
- keep `high_ask` / `low_bid` as touch detectors
- do not use barrier price as entry anymore
- keep `from_start` logic unchanged unless tests prove it must move too
- keep strict rejection of legacy ambiguous schema

- [ ] **Step 4: Run the focused label tests and verify they pass**

Run:

```bash
uv run pytest -q tests/test_oco_precompute_spread.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_oco_precompute_spread.py scripts/build_tick_opportunity_ml_dataset.py
git commit -m "fix: use touch bar close for oco entry economics"
```

### Task 2: Align the tick-exact verifier with the new entry contract

**Files:**
- Modify: `scripts/verify_oco_tick_exact_shortlist.py`
- Test: `tests/test_verify_oco_tick_exact_shortlist.py`

- [ ] **Step 1: Extend verifier tests to fail on barrier-price entry assumptions**

Add cases to `tests/test_verify_oco_tick_exact_shortlist.py` that lock:

```python
def test_recompute_first_touch_buy_trigger_uses_signal_close_ask():
    ...

def test_recompute_first_touch_buy_entry_uses_touch_bar_close_ask():
    ...

def test_recompute_first_touch_sell_entry_uses_touch_bar_close_bid():
    ...
```

These tests must distinguish:
- barrier-price entry
- touch-bar close entry

- [ ] **Step 2: Run verifier tests and verify they fail**

Run:

```bash
uv run pytest -q tests/test_verify_oco_tick_exact_shortlist.py
```

Expected:
- FAIL on the new entry/reference contract assertions

- [ ] **Step 3: Implement the verifier contract change**

Update `_recompute_first_touch(...)` in `scripts/verify_oco_tick_exact_shortlist.py` so it mirrors the label builder exactly:

```python
buy_ref = close_ask[i]
sell_ref = close_bid[i]
up_thr = buy_ref + k * float(pip)
dn_thr = sell_ref - k * float(pip)
...
entry_price_use = np.where(
    side_v[use] == -1,
    close_bid[touch_bar_i[use]],
    close_ask[touch_bar_i[use]],
)
exit_price_use = np.where(
    side_v[use] == -1,
    close_ask[exit_i[use]],
    close_bid[exit_i[use]],
)
gross_v[use] = side_v[use].astype(float) * ((exit_price_use - entry_price_use) / float(pip))
```

Ensure the partial explicit-schema read still requests:

```python
["close_ts", "close_bid", "high_bid", "low_bid", "high_ask", "close_ask", "hl_first"]
```

- [ ] **Step 4: Run verifier tests and verify they pass**

Run:

```bash
uv run pytest -q tests/test_verify_oco_tick_exact_shortlist.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_oco_tick_exact_shortlist.py tests/test_verify_oco_tick_exact_shortlist.py
git commit -m "fix: align oco tick exact verifier with touch bar close entry"
```

### Task 3: Bring runtime contract/tests into line with the new semantics

**Files:**
- Modify: `src/behemoth/runtime/barrier_manager.py`
- Modify: `src/behemoth/api/server.py`
- Test: `tests/test_barrier_manager.py`

- [ ] **Step 1: Add failing runtime contract tests**

Add tests to `tests/test_barrier_manager.py` that prove the runtime scan contract is documented and exercised as:

```python
def test_register_scan_tracks_side_correct_signal_reference_contract():
    ...

def test_completed_touch_bar_opens_market_without_barrier_fill_assumption():
    ...
```

These tests do not need to simulate broker fills. They need to lock:
- the scan is anchored on signal-bar reference semantics
- touch detection remains completed-bar based
- runtime is not documented as a perfect barrier-fill model

- [ ] **Step 2: Run runtime tests and verify they fail where contract text/code is stale**

Run:

```bash
uv run pytest -q tests/test_barrier_manager.py
```

Expected:
- failure in the new contract assertions or stale comments/docs

- [ ] **Step 3: Update runtime contract text and any supporting reference handling**

Make the runtime contract explicit in:
- `src/behemoth/runtime/barrier_manager.py`
- `src/behemoth/api/server.py`

Update comments/docstrings to state:

```python
# signal is scored on a completed bar
# BUY scans anchor on signal-bar close_ask
# SELL scans anchor on signal-bar close_bid
# completed future bars confirm touch via high_ask / low_bid
# live then submits a market order immediately after touch confirmation
```

If the current stored scan reference path is still single-field `ref_price`, make the minimal change necessary for correctness and clarity. If that forces a schema split, keep it focused and tested.

- [ ] **Step 4: Run runtime tests and verify they pass**

Run:

```bash
uv run pytest -q tests/test_barrier_manager.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/runtime/barrier_manager.py src/behemoth/api/server.py tests/test_barrier_manager.py
git commit -m "docs: align runtime barrier contract with touch bar close entry"
```

### Task 4: Smoke-test EURUSD on regenerated outputs

**Files:**
- Generated: `data/analysis/tick_opportunity_mining/**/EURUSD_*`
- Generated: `docs/analysis/eurusd_*`

- [ ] **Step 1: Regenerate EURUSD downstream artifacts**

Run:

```bash
uv run python scripts/run_tick_opportunity_mining.py --config configs/research/experiments/eurusd_tick_opportunity_mining.yaml
uv run python scripts/run_tick_opportunity_monthly_wfo.py --config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml --model-export-dir models/oco
uv run python scripts/analyze_oco_stop_limit_tickfill.py \
  --symbols EURUSD \
  --pred-paths data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet \
  --out-dir data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap
uv run python scripts/select_oco_reduced_core_rolling.py --config configs/research/experiments/eurusd_oco_reduced_core_rolling.yaml
uv run python scripts/verify_oco_tick_exact_shortlist.py \
  --symbol EURUSD \
  --dataset-dir data/analysis/tick_velocity \
  --pred-path data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet \
  --shortlist-state-csv data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv \
  --locked-quantile 0.9 \
  --selection-mode auto \
  --family-required oco_first_touch_clean \
  --oco-hold-mode from_touch \
  --oco-include-no-touch true
```

- [ ] **Step 2: Verify EURUSD tick-exact parity is green**

Run:

```bash
python - <<'PY'
import pandas as pd
d = pd.read_csv("data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_tick_exact_summary.csv")
print(d.to_dict(orient="records")[0])
PY
```

Expected:
- `overall_pass: True`
- no nonzero absolute-error metrics

- [ ] **Step 3: Compare EURUSD reduced-core outputs against the prior contract**

Run:

```bash
python - <<'PY'
import pandas as pd
old = pd.read_csv("/Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_summary.csv")
new = pd.read_csv("data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_summary.csv")
print("old", old.to_dict(orient="records")[0])
print("new", new.to_dict(orient="records")[0])
PY
```

Expected:
- a clear before/after read on row count, gross pips, and fill rate

- [ ] **Step 4: Commit regenerated EURUSD artifacts only if they are intentionally part of the branch**

```bash
git add data/analysis/tick_opportunity_mining docs/analysis models/oco
git commit -m "data: regenerate eurusd oco outputs for touch bar close contract"
```

Only do this if the branch is meant to carry generated artifacts at this stage.

### Task 5: Full active-universe retrain and final verification

**Files:**
- Generated: `data/analysis/tick_opportunity_mining/**/*`
- Generated: `docs/analysis/**/*`
- Generated: `models/oco/**/*`

- [ ] **Step 1: Run the full active-universe retrain**

Run from the authoritative worktree:

```bash
make retrain-all
```

If prepared upstream bars/velocity need rebuilding first, run:

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

uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --bar-ticks-grid 100,1000,2000 \
  --overwrite
```

- [ ] **Step 2: Run focused regression tests**

Run:

```bash
uv run pytest -q \
  tests/test_oco_precompute_spread.py \
  tests/test_verify_oco_tick_exact_shortlist.py \
  tests/test_barrier_manager.py
```

Expected:
- PASS

- [ ] **Step 3: Run docs contract if shared artifacts changed**

Run:

```bash
uv run python scripts/validate_oco_docs_contract.py \
  --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv \
  --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv \
  --report-out docs/analysis/oco_docs_contract_report.md
```

Expected:
- no new contract failures caused by the OCO entry contract shift

- [ ] **Step 4: Inspect final diff and summarize the strategy impact**

Run:

```bash
git status --short
```

Expected:
- only intentional code/artifact changes remain

Summarize:
- row-count shifts
- pips shifts
- parity result
- any symbols materially degraded by the more realistic entry contract

- [ ] **Step 5: Commit**

```bash
git add scripts src/behemoth tests data/analysis docs/analysis models/oco
git commit -m "feat: adopt touch bar close oco entry contract"
```

## Self-Review

- Spec coverage:
  - signal-bar side-correct references: covered in Tasks 1-3
  - touch-bar executable-close entry: covered in Tasks 1-2
  - runtime contract alignment: covered in Task 3
  - EURUSD smoke + full retrain: covered in Tasks 4-5
- Placeholder scan:
  - no `TODO` / `TBD` placeholders remain
  - all tasks include concrete files, commands, and expected outcomes
- Type consistency:
  - contract consistently uses `close_bid`, `close_ask`, `high_ask`, `low_bid`
  - no fallback to ambiguous bar names
