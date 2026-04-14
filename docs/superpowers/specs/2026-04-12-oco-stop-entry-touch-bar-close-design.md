# OCO Stop-Entry Touch-Bar Close Contract

- Target branch: `feat-explicit-bid-ask-bar-schema`
- Target baseline: `origin/main` at or after PR `#64`
- Date: `2026-04-12`

## Problem

The current OCO pipeline mixes two different execution models:

1. Breakout detection is side-aware and stop-like:
   - BUY touch uses executable ASK highs
   - SELL touch uses executable BID lows
2. Entry economics are still optimistic:
   - the labeler effectively assumes fill at the barrier price derived from the signal-bar reference

This is internally inconsistent with the live runtime. The live system:

1. runs CatBoost on a completed signal bar
2. registers a barrier scan for selected candidates
3. evaluates future completed bars for a breakout touch
4. submits a market order immediately after a touch is confirmed on that completed bar

So live behavior is not a perfect barrier-price fill model. It is a completed-bar breakout confirmation model followed by immediate market entry.

## Goal

Keep the current fast architecture:

1. score on signal-bar close
2. wait for breakout touch
3. enter immediately once the touch is confirmed

But correct the execution contract so training, verification, and runtime all use coherent side-aware economics.

## Contract

### 1. Signal-bar reference

The signal-bar reference must be side-correct:

- BUY reference: signal-bar `close_ask`
- SELL reference: signal-bar `close_bid`

This replaces the current asymmetric contract that anchors both directions off `close_bid`.

### 2. Trigger contract

Future-bar touch detection must be:

- BUY trigger when `high_ask >= signal_close_ask + barrier`
- SELL trigger when `low_bid <= signal_close_bid - barrier`

This preserves stop-style breakout semantics while using executable-side prices.

### 3. Entry contract

When a touch is confirmed on a completed bar, entry must be modeled at the executable close of that same touch bar:

- BUY entry price = touch-bar `close_ask`
- SELL entry price = touch-bar `close_bid`

This is the intended approximation for the current live system because the runtime submits a market order immediately after the completed touch bar is processed.

### 4. Exit contract

Exit pricing remains side-aware and unchanged:

- long exit uses later `close_bid`
- short exit uses later `close_ask`

### 5. Hold timing

`from_touch` semantics remain intact:

- the holding horizon begins from the touch bar
- the exit close is taken after the configured holding window from that touch bar

## Non-goals

This change does not switch the strategy to:

- next-bar-close entry
- next-bar-open entry
- literal intrabar tick-exact stop-fill simulation
- pre-placed broker stop orders

Those are different strategy contracts and require separate design.

## Why This Contract

This contract matches the live system better than the current barrier-fill approximation:

- the system does not place actual stop orders ahead of time
- it reacts after a completed bar confirms the touch
- it then sends a market order

So touch-bar executable close is a better approximation than perfect barrier fill.

It is also still materially faster than a delayed next-bar-entry strategy.

## Expected Impact

Compared with the current optimistic barrier-fill labels:

- BUY entries will usually worsen because they move from a barrier-level fill to touch-bar `close_ask`
- SELL entries will usually worsen because they move from a barrier-level fill to touch-bar `close_bid`
- some previously profitable events may become neutral or negative
- CatBoost labels, WFO predictions, reduced-core selection, and governance outputs will all shift

This is expected and desired. The point is to improve live alignment, not preserve historical optimistic metrics.

## Required Code Changes

### Research / labeling

Update `scripts/build_tick_opportunity_ml_dataset.py`:

- require `close_ask` in addition to current explicit fields
- split reference price by side:
  - BUY reference from signal-bar `close_ask`
  - SELL reference from signal-bar `close_bid`
- detect touch using:
  - `high_ask >= close_ask + barrier`
  - `low_bid <= close_bid - barrier`
- compute entry price from touch-bar close:
  - BUY entry = `close_ask[touch_bar]`
  - SELL entry = `close_bid[touch_bar]`
- keep exits side-aware as they already are

### Tick-exact verifier

Update `scripts/verify_oco_tick_exact_shortlist.py`:

- mirror the exact same side-correct reference, trigger, entry, and exit rules
- ensure parity is checked against touch-bar-close entry economics, not barrier-price economics

### Runtime / live contract

Update runtime docs and tests around:

- `src/behemoth/runtime/barrier_manager.py`
- `src/behemoth/api/server.py`
- relevant JForex/core tests

Important nuance:

- live order submission remains the same for now
- the main task is to ensure the documented and verified runtime contract matches the new research contract closely enough

## Verification Requirements

Before claiming the contract change is correct:

1. targeted unit tests must cover:
   - BUY trigger anchored off `close_ask`
   - SELL trigger anchored off `close_bid`
   - BUY entry at touch-bar `close_ask`
   - SELL entry at touch-bar `close_bid`
2. tick-exact verifier must pass on regenerated symbol outputs
3. EURUSD must be rerun first as the smoke test
4. then full active-universe retraining must be rerun
5. reduced-core and tick-exact outputs must be compared against the prior spread-aware-but-optimistic contract

## Acceptance Criteria

The change is accepted when:

- no OCO label path uses barrier-price entry economics anymore
- no BUY trigger is anchored off `close_bid`
- no SELL trigger is anchored off `close_ask`
- verifier and labeler share the same execution contract
- retrained outputs exist for the active universe
- parity is green on regenerated results

## Open Question Resolved

This design chooses:

- stop-style breakout detection
- touch-bar executable-close entry approximation

It explicitly does **not** choose:

- perfect barrier fill
- next-bar-close entry

That is the correct tradeoff for alignment with the current live architecture.
