# Remove look-ahead bias from OCO candidate mining

_Design — 2026-05-15_

## Problem

The OCO candidate mining pipeline emits two candidate families per
regime/horizon/barrier (`scripts/run_tick_opportunity_mining.py`, family
loop ~line 633):

- `oco_first_touch` — universe = `decided & reg_mask`
- `oco_first_touch_clean` — universe = `decided & reg_mask & (~both)`

`both` is `any_up & any_dn` computed by scanning `h` bars **forward** from
the signal bar — i.e. "did price touch *both* the +k and −k barrier within
the horizon." This is future information. At the decision point (the signal
bar's close) it cannot be known, and the live barrier manager transitions
SCANNING → HOLDING on the *first* touch, so it cannot filter on it.

The `oco_first_touch_clean` family's reported win rate is therefore
conditioned on a look-ahead filter. Measured impact: the deployed
`oco_first_touch_clean` candidates report ~70% win rate; the
look-ahead-free `oco_first_touch` win rate on the same data is ~44–47%
with negative mean P&L. The live system has been trading `clean` candidates
and cannot reproduce the 70% — live results sit at the honest ~46% basis,
which after the asymmetric win/loss sizing is a net loss.

The defect is not just the one family. It is that the pipeline has no
guard preventing a look-ahead-conditioned family from being mined,
selected, and promoted to live. This design removes the family **and**
closes the class of bug.

## Non-goals

- Finding a profitable strategy. If honest mining surfaces no tradeable
  `first_touch` candidate, that is a correct and acceptable outcome.
- Reframing `both` as a prediction target (whether whipsaw is predictable
  from causal features). That is a possible future research effort, out of
  scope here.
- Running the regenerate / retrain / re-freeze cycle. Those are `make`
  targets the operator runs after this code change merges; they require
  broker credentials and a root checkout.

## What is and is not look-ahead — verified

| Quantity | Forward-looking? | Reproducible live? | Verdict |
|---|---|---|---|
| `decided` (a barrier touched within `h`) | computed over horizon | yes — live expires un-touched scans, so the traded population matches | safe to filter on |
| `side` (first-touch direction) | within horizon | yes — live enters the side that touches first | safe |
| `gross` (enter-at-touch, hold `h` bars P&L) | within horizon | yes — matches live entry + hold | safe as outcome metric |
| `both` (both barriers touched within `h`) | within horizon, *after* first touch | **no** — first touch already commits the trade | **must not filter on** |
| `touch_step` | within horizon | partial | metric only, never a filter |

`both` is the only forward-looking quantity used as a candidate-universe
filter. `decided` is forward-computed but reproducible, because the live
system's behaviour (expire if no touch) matches the filter.

## Design

### 1. Core excision

`scripts/run_tick_opportunity_mining.py` — the family loop:

```python
for fam, fam_mask in [
    ("first_touch", decided & reg_mask),
    ("first_touch_clean", decided & reg_mask & (~both)),   # REMOVE this line
]:
```

becomes a single-family loop emitting only `first_touch`. Every candidate
the pipeline produces is then look-ahead-free.

`both_window_rate` remains a **reported descriptive metric** on each
candidate row — it characterises how whipsaw-prone a regime is, which is
useful diagnostic context. It is only harmful as a per-bar universe filter,
which it no longer is.

### 2. Look-ahead audit

As part of implementation, verify and record findings for:

- **`_oco_precompute_candidates` outputs** — confirm `both` is the only
  forward-looking field consumed as a *filter*; `side`/`decided`/`gross`
  are consumed only as direction/population/outcome.
- **Regime masks** — confirm mining computes regime membership causally
  (rolling or expanding quantiles), not full-dataset quantiles that would
  leak future distribution information into the regime label.
- **`quality_tier` / `selection_pass`** — confirm tier assignment uses
  train-only metrics (the code comment claims this; verify it).

Any look-ahead found is fixed in the same change; findings are appended to
this spec before implementation closes.

### 3. Structural guardrails

So a look-ahead-conditioned family cannot silently recur:

- **Rename** `both` → `both_touched_lookahead` in the
  `_oco_precompute_candidates` return dict, and docstring every returned
  field as either *decision-time* (safe to filter on) or *labelling-only*
  (outcome/metric only). A future `~both_touched_lookahead` filter is then
  self-evidently wrong in code review.
- **Contract test** — assert the family set the mining pipeline emits is
  exactly `{oco_first_touch}` (an allowlist). Any new family — a
  look-ahead one in particular — fails CI loudly and forces a deliberate
  allowlist update with review.
- **Governance lock loader** — reject any lock whose `state_id` contains
  `first_touch_clean`. Belt-and-braces: even a stale `clean` lock left on
  disk cannot be loaded into the live runtime. The rejection is a hard
  error with a clear message pointing at this design.

### 4. Tests and docs

- Update or remove tests that reference `first_touch_clean` (mining,
  registry, governance, docs-contract tests).
- Add the contract test from guardrail 3.
- Add a test that the governance lock loader rejects a `first_touch_clean`
  state_id.
- Update `UBIQUITOUS_LANGUAGE.md` and any docs-contract artefact that names
  the `first_touch_clean` family.

### 5. Downstream — operator actions after merge (not in this change)

`make retrain-all` (re-mine — honest candidates only) → `make monthly-build`
→ `make monthly-recert` → `make promote-live`. If no `first_touch` candidate
clears the selection gates, nothing deploys and the live system trades
nothing on the OCO strategy. That is the intended, accepted outcome.

## Components and isolation

| Unit | Responsibility | Depends on |
|---|---|---|
| `_oco_precompute_candidates` | produce per-bar decision-time + labelling-only quantities, clearly partitioned | bar frame |
| mining family loop | emit `first_touch` candidate rows only | precompute outputs |
| family allowlist contract test | fail CI if any non-allowlisted family is emitted | mining output |
| governance lock loader guard | refuse `first_touch_clean` locks at load time | lock JSON |

Each is independently testable: the precompute by field assertions, the
family loop by inspecting emitted `state_id`s, the contract test and loader
guard by direct unit tests.

## Error handling

- The lock-loader guard raises a hard error (not a warning) on a
  `first_touch_clean` `state_id`, with a message naming this design. A
  silent skip would reproduce the original failure mode — a defect hiding
  behind a downstream symptom.
- The contract test failure message explains *why* the family is rejected
  and what to do (audit the new family for look-ahead, then update the
  allowlist deliberately).

## Testing strategy

- Unit: `_oco_precompute_candidates` returns `both_touched_lookahead` (not
  `both`); mining emits only `oco_first_touch` state_ids.
- Contract: family allowlist test; lock-loader rejection test.
- Regression: existing mining / registry / governance tests pass after the
  `first_touch_clean` references are removed.
- Full suite + `make quality` green.

## Live-behaviour note

Guardrail 3's lock-loader rejection takes effect on deploy: the live
runtime will refuse the current `first_touch_clean` locks and stop trading
those candidates. This is intentional and is the point — but it is a
live-behaviour change, and deploy timing is the operator's call.
