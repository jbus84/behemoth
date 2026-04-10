# Spread-Adjusted OCO Training Labels Design

## Problem

The OCO training pipeline builds bars from BID prices only and uses BID prices for both barrier detection and label calculation. In live trading, fills are priced differently:

- **BUY entry** (upper barrier touch): fills at **ASK** — the model pays the spread at entry
- **SELL exit** (closing a SELL with a market BUY): fills at **ASK** — the model pays the spread at exit

The current `target_gross_pips` label measures BID-to-BID round trips. Every live trade systematically underperforms the label by approximately one spread. For symbols with wide spreads relative to expected gross pips, this eliminates the edge entirely:

| Symbol | WFO avg gross pips | Live spread | Net after spread |
|--------|-------------------|-------------|-----------------|
| GBPUSD | +2.11 | ~0.70 | +1.41 |
| EURUSD | +1.35 | ~0.40 | +0.95 |
| USDJPY | +3.07 | ~0.57 | +2.50 |
| USDCHF | +1.00 | ~0.90 | +0.10 |
| AUDUSD | +0.92 | ~0.90 | +0.02 |
| USDCAD | +1.31 | ~1.20 | +0.11 |

USDCAD and AUDUSD are effectively breakeven once spread is correctly accounted for.

## Fix

Two targeted changes to label generation; one targeted change to the live barrier trigger; two new fields on the bar schema.

### Bar schema additions

Add `high_ask` and `close_ask` to every bar:

| Field | Definition | Used for |
|-------|-----------|----------|
| `high_ask` | `max(ask)` over all ticks in the bar | Upper barrier trigger (BUY) |
| `close_ask` | `last(ask)` of the bar (= last tick's ASK) | SELL exit label in training |

BID-based fields (`high`, `low`, `close`) are unchanged and continue to serve the existing feature pipeline.

### Training label correction — `_oco_precompute`

**BUY trigger** (`scripts/build_tick_opportunity_ml_dataset.py:368`):

```python
# before — BID reaches upper barrier
hu = high[idx] >= up_thr

# after — ASK reaches upper barrier
hu = high_ask[idx] >= up_thr
```

The BUY gross label formula is **unchanged**: `(close[exit_i] − ref) / pip − k`. When the ASK trigger fires, the ASK entry price equals `up_thr` (the barrier level), and the exit is at BID close of the horizon bar — which is exactly what the current formula computes. No formula change needed for BUY.

**SELL exit label** (`scripts/build_tick_opportunity_ml_dataset.py:405`):

```python
# before — BUY and SELL both exit at BID close
gross[use] = side[use].astype(float) * ((close[exit_i[use]] - ref[use]) / pip) - k

# after — SELL exits at ASK close; BUY exits at BID close (unchanged)
exit_price = np.where(
    side[use] == -1,
    close_ask[exit_i[use]],   # SELL: close at ASK
    close[exit_i[use]],        # BUY:  close at BID
)
gross[use] = side[use].astype(float) * ((exit_price - ref[use]) / pip) - k
```

`close_ask` is extracted from the bar DataFrame alongside `close`, `high_ask`, etc. at the top of `_oco_precompute`. If `close_ask` is missing or NaN for a bar, fall back to `close` (degrades to current behaviour).

Both `from_touch` and `from_start` hold modes are updated.

### Live barrier fix — `barrier_manager.py`

`evaluate_bar` gains a `bar_high_ask` parameter (default `0.0` for backwards compatibility):

```python
def evaluate_bar(
    self,
    symbol: str,
    bar_ticks: int,
    bar_high: float,
    bar_low: float,
    bar_hl_first: float,
    current_bar_idx: int,
    bar_high_ask: float = 0.0,
) -> list[dict]:
```

Line 146 becomes:

```python
up_touch = bar_high_ask >= upper   # ASK reaches upper barrier
dn_touch = bar_low <= lower        # BID reaches lower barrier — unchanged
```

When `bar_high_ask = 0.0` (default), `up_touch` will never fire on a live price (0.0 < any real upper barrier). Callers **must** pass the real value; the default exists only to avoid breaking existing unit tests.

### `tick_bars` table and `state.py`

Add two columns to the `tick_bars` DDL:

```sql
high_ask  DOUBLE,
close_ask DOUBLE
```

Update the INSERT (13 → 15 values) and the `get_latest_bar` SELECT to include `high_ask`.

### `TickAggregator._build_bar`

Compute `high_ask` and `close_ask` from the raw tick list:

```python
asks = [float(t.ask) for t in ticks]
high_ask = max(asks)
close_ask = asks[-1]
```

Add both to `IncomingTickBar` and return them in `_build_bar`.

### `IncomingTickBar` schema (`schemas.py`)

```python
high_ask: float = Field(..., gt=0, description="Max ASK price over all ticks in the bar")
close_ask: float = Field(..., gt=0, description="Last ASK price of the bar")
```

### `server.py` call site

Pass `bar_high_ask` from `latest_bar` to `evaluate_bar`:

```python
raw_actions = _barrier_manager.evaluate_bar(
    symbol=sym,
    bar_ticks=bt,
    bar_high=latest_bar["high_price"],
    bar_low=latest_bar["low_price"],
    bar_hl_first=latest_bar.get("hl_first", 0.0),
    current_bar_idx=latest_bar["row_id"],
    bar_high_ask=latest_bar.get("high_ask", 0.0),
)
```

### `diagnose_live_replay.py` — `_build_bars_from_ticks`

`_tick_price_frame` currently drops ask data early. Update `_build_bars_from_ticks` to also compute and emit `high_ask` and `close_ask` columns, matching the definition above, using the raw ask ticks before they are discarded.

## Pipeline rebuild

After the code changes are merged, a full rebuild is required:

**Step 0 — Label-patch diagnostic (fast, no retrain)**
Recompute `target_gross_pips` on existing locked prediction events by deducting the per-symbol median spread. Re-run `select_oco_reduced_core_rolling.py`. Confirm expected outcome: USDCAD and AUDUSD candidates drop out; GBPUSD, EURUSD, USDJPY remain viable. If unexpected results appear, investigate before committing to Steps 1–5.

**Step 1 — Rebuild ML dataset**
Re-run `build_tick_opportunity_ml_dataset.py` for all 6 symbols. New parquets include corrected `target_gross_pips`, `target_gross_pos`, and the `high_ask` / `close_ask` bar columns.

**Step 2 — Retrain models**
Re-run `run_monthly_build.py`. The trigger shift adds training events that the current models have never seen (bars where ASK hit the barrier but BID had not). Full retrain required.

**Step 3 — Re-run WFO**
Re-run `run_tick_opportunity_monthly_wfo.py`. Existing prediction parquets are stale after model retrain.

**Step 4 — Re-run candidate selection**
Re-run `select_oco_reduced_core_rolling.py`. Expected: USDCAD and AUDUSD candidates fail the spread-adjusted hurdle and are excluded from the new governance bundle.

**Step 5 — Promote new governance bundle**
Re-run `freeze_oco_live_governance.py` and `run_promote_live.py`. The new bundle will carry different candidate UIDs.

**Step 6 — Delete stale seed files**
`rm data/runtime/seed/*.parquet`. The governance fingerprint check (already merged) will force regeneration with the new UIDs on next API startup.

## Files modified

| File | Change |
|------|--------|
| `src/behemoth/core/schemas.py` | Add `high_ask`, `close_ask` to `IncomingTickBar` |
| `src/behemoth/runtime/tick_aggregator.py` | Compute `high_ask`, `close_ask` in `_build_bar` |
| `src/behemoth/runtime/state.py` | Add `high_ask`, `close_ask` to `tick_bars` DDL, INSERT, SELECT |
| `src/behemoth/runtime/barrier_manager.py` | Add `bar_high_ask` param; use for `up_touch` |
| `src/behemoth/api/server.py` | Pass `bar_high_ask` to `evaluate_bar` |
| `scripts/build_tick_opportunity_ml_dataset.py` | Fix `_oco_precompute` trigger and SELL exit label |
| `scripts/diagnose_live_replay.py` | Emit `high_ask`, `close_ask` from `_build_bars_from_ticks` |

## Tests

**`tests/test_oco_precompute_spread.py`**
- `test_buy_trigger_uses_ask`: bar sequence where `high_bid < upper_barrier` but `high_ask >= upper_barrier`; assert event fires as BUY with `target_gross_pos = 1`
- `test_sell_exit_label_uses_close_ask`: SELL event; assert `target_gross_pips = (dn_thr − close_ask_exit) / pip` — smaller than the bid-only label by exactly the exit bar's spread

**`tests/test_barrier_manager_spread.py`**
- `test_up_touch_fires_on_ask`: register scan, call `evaluate_bar` with `bar_high < upper` but `bar_high_ask >= upper`; assert `OPEN_MARKET BUY` returned
- `test_dn_touch_unchanged`: `bar_low <= lower` fires SELL regardless of `bar_high_ask`

**`tests/test_tick_aggregator_ask_columns.py`**
- `test_high_ask_is_max_ask_per_bar`: feed 100 ticks with known bid/ask; assert `bar.high_ask = max(ask)`
- `test_close_ask_is_last_ask_per_bar`: assert `bar.close_ask = ask` of tick 100
