# Unified Governance Framework Design

**Sub-project**: 1 of 5 (framework abstraction). Subsequent sub-projects implement family adapters (2–4) and deployment substrate (5).

**Date**: 2026-05-25

**Status**: Design approved; spec written; pending user review then implementation plan.

---

## Problem

The existing governance pipeline (`select_oco_reduced_core_rolling.py` → `verify_oco_tick_exact_shortlist.py` → `freeze_oco_historical_governance.py`, ~4,100 LOC) is hardcoded to OCO bracket strategies. It assumes:

- Barrier-touch payoffs (bid/ask + barrier-detection tick replay)
- OCO-specific selection metrics (`both_window_rate`, `p_up_first`)
- `family_keep: oco_first_touch` hardcoded in config schema
- Bracket-order deployment substrate (JForex)

The 8 non-OCO mining families (`directional`, `directional_inverse`, `directional_run`, `double_touch`, `pullback`, `no_touch`, `dollar_residual`, `dispersion_rank`, `lead_lag`) produce candidates but have no governance pipeline to convert them into deployable GO/NO_GO verdicts. After the 2026-05 perf sprint (PRs #217–#233), candidates are produced fast; the missing piece is governance.

## Goals

1. **One framework, many adapters**: a single governance pipeline that all 9 families flow through.
2. **GO/NO_GO at three granularities**: state-level, (symbol, family)-level, symbol-level.
3. **Strict configuration**: per-symbol YAML with no silent defaults; missing fields are hard errors.
4. **Monthly threshold lifetime**: thresholds are valid for one model_month only; freeze artifacts are tagged.
5. **Byte-identical OCO migration**: the existing OCO pipeline becomes the first adapter and produces byte-identical artifacts to the legacy code.
6. **LLM-friendly maintenance**: configs are declarative, hooks have narrow contracts, framework logic is centralized.

## Non-goals (deferred to follow-up sub-projects)

- Deployment encoding standardization across families (sub-project 5).
- Live trading substrate (JForex code paths beyond OCO; sub-project 5).
- New WFO target columns for non-OCO families (handled in sub-projects 2–4 per family).
- ML dataset integration with governance verdicts (sub-project 5).
- Generalizing the strategy bible / explainability reports (follow-up).

---

## Architecture

```
mined candidates (per family, per symbol)
         ↓
[Stage G1] State assembly       — group candidates per FamilyGovernanceConfig.state_key_cols
         ↓
[Stage G2] Rolling selection    — apply capacity floors + stability thresholds + selection_gates
         ↓
[Stage G3] Tick-exact verify    — one of 3 simulators (barrier_touch / forward_return / cross_symbol_residual)
         ↓
[Stage G4] State-level verdict  — each (symbol, family, state) → GO/NO_GO
         ↓
[Stage G5] Roll-up + freeze
         — (symbol, family) GO if ≥1 state GO
         — (symbol) GO if all required_families are GO
         — freeze artifacts written tagged with model_month
```

### Module layout

```
src/behemoth/governance/
  __init__.py
  families/
    base.py                       # FamilyGovernanceConfig dataclass, BaseFamilyGovernanceHooks
    oco_first_touch.py            # first adapter (migration target)
    # adapters for other 8 families land in sub-projects 2–4
  state_assembly.py               # Stage G1
  selection.py                    # Stage G2
  tick_exact_shared.py            # TickStreamProvider, summary stats
  tick_exact_barrier_touch.py     # Simulator 1
  tick_exact_forward_return.py    # Simulator 2
  tick_exact_cross_symbol.py      # Simulator 3
  verdict.py                      # Stages G4 + G5 (roll-up)
  freeze.py                       # freeze artifact writer
  errors.py                       # MissingGovernanceFieldError, etc.

scripts/governance/
  run_governance_all.py           # orchestrator: read symbol YAMLs, run all stages
  run_state_assembly.py           # G1 only (CLI wrapper)
  run_selection.py                # G2 only
  run_tick_exact.py               # G3 only
  emit_verdicts.py                # G4 + G5
  freeze.py                       # freeze artifact writing
  validate_oco_migration_parity.py # byte-identical parity gate
```

Each script in `scripts/governance/` is ≤ 100 lines: parse args, load YAML, instantiate adapter, call framework.

---

## The protocol

### Config dataclass

```python
@dataclass(frozen=True)
class FamilyGovernanceConfig:
    name: str
    state_key_cols: tuple[str, ...]
    wfo_target_col: str
    payoff_simulator: Literal["barrier_touch", "forward_return", "cross_symbol_residual"]
    selection_gate_cols: tuple[str, ...]
    schema_version: str
```

No default values on any field — every family adapter must declare all six. The framework reads this config and routes the family through the correct simulator + state assembly.

### Hook protocol

```python
class FamilyGovernanceHooks(Protocol):
    config: FamilyGovernanceConfig

    def derive_state_id(self, row: pd.Series) -> str:
        """Compose a deterministic state_id string from state_key_cols.
        Default impl reads state_key_cols in order; override for special formats."""

    def selection_gate(
        self, candidate_row: pd.Series, symbol_thresholds: dict[str, float]
    ) -> bool:
        """Return True if this candidate passes family-specific selection
        gates (e.g., OCO checks both_window_rate >= min_both_window_rate).
        Default impl returns True (no extra gates)."""

    def simulate_one_entry(
        self, tick_stream: pd.DataFrame, entry_bar: pd.Series, params: dict
    ) -> float:
        """Return realized pips for one fill. Called by the chosen payoff
        simulator's framework code."""

    def encode_freeze_artifact(
        self, qualified_states: pd.DataFrame, model_month: str
    ) -> dict:
        """Build the per-symbol per-family freeze JSON payload."""
```

Four hooks. `BaseFamilyGovernanceHooks` provides sensible defaults; adapters override only what's family-specific.

### Example adapter (OCO)

```python
oco_first_touch = FamilyGovernanceConfig(
    name="oco_first_touch",
    state_key_cols=("family", "barrier_pips", "horizon", "regime"),
    wfo_target_col="y_oco_first_touch_decided",
    payoff_simulator="barrier_touch",
    selection_gate_cols=("both_window_rate", "p_up_first"),
    schema_version="oco_v4.0",
)

class OcoFirstTouchHooks(BaseFamilyGovernanceHooks):
    config = oco_first_touch
    def selection_gate(self, row, thresholds):
        return (
            row["both_window_rate"] >= thresholds["min_both_window_rate"]
            and row["p_up_first"] >= thresholds["min_p_up_first"]
        )
    # encode_freeze_artifact, derive_state_id, simulate_one_entry inherited
```

A new family adapter is ~10–30 LOC: config + (optionally) one or two hook overrides.

---

## Configuration

### Single source of truth for field documentation

- **Dataclass docstrings** on every field of `FamilyGovernanceConfig` and `SymbolGovernanceConfig` (the YAML-loaded dataclass) — authoritative.
- **One commented template** at `configs/research/experiments/_governance_template.yaml` — heavy comments, used as copy-source for new symbols.
- **Per-symbol YAMLs stay terse** — no comments, just values. Eliminates comment drift across 6 symbols.

### Per-symbol YAML schema

Every field is required; missing fields are hard errors at load time.

```yaml
symbol: EURUSD
model_month: 2026-05
required_families:
  - directional_run
  - dollar_residual

families:
  directional_run:
    capacity_floor_monthly: 300
    capacity_floor_annual: 800
    max_state_churn: 0.45
    max_top_state_share: 0.35
    max_state_hhi: 0.25
    selection_gates: {}
    state_train_months: 2
    min_states: 1
    max_states: 12

  dollar_residual:
    # ... all required thresholds explicit ...
```

### Stage output paths

```
data/analysis/governance/<model_month>/
  state_schedules/
    <SYM>_<family>_state_schedule.csv
  tick_exact/
    <SYM>_<family>_tick_exact_summary.csv
    <SYM>_<family>_tick_exact_monthly.csv
  verdicts/
    <SYM>_state_verdicts.csv
    <SYM>_family_verdicts.csv
    symbol_verdicts.csv
  freeze/
    <SYM>_governance_frozen.json
```

For OCO migration parity (Phase 3), legacy paths under `data/analysis/tick_opportunity_mining/reduced_core_rolling/` are also written (as copies or symlinks) for one cycle to preserve downstream consumers.

---

## The 3 payoff simulators

Each simulator is a single module. Family adapters declare which to use via `payoff_simulator`. Result aggregation (per-state summary stats, per-month breakdown, divergence-from-WFO) is shared framework code in `tick_exact_shared.py`.

### Simulator 1: `barrier_touch`

- **Used by**: `oco_first_touch`, `oco_asymmetric`, `double_touch`, `pullback`, `no_touch`
- **Mechanics**: Replays bid/ask ticks forward from entry bar until barrier touch or horizon expiry. Realized pips = barrier hit price − entry price − spread − slippage.
- **Family-specific bit**: `simulate_one_entry` decides "is the barrier touched on this tick?" (single barrier vs asymmetric brackets vs two-phase A→B sweep).
- **Slippage knobs** (per-state YAML): `stop_limit_cap_pips`, `stop_limit_slippage_mode`, `stop_limit_min_fill_rate`. Same as existing OCO.

### Simulator 2: `forward_return`

- **Used by**: `directional`, `directional_inverse`, `directional_run`
- **Mechanics**: Market order at entry bar (bid or ask depending on side), held for `horizon` bars, exit at horizon bar's close. Realized pips = exit price − entry price − spread.
- **Family-specific bit**: `simulate_one_entry` declares the side (long/short, possibly conditional on `_dir_side_h{h}` or `run_sign`).
- **Slippage knobs** (per-state YAML): `entry_slippage_pips`, `assume_spread_at_exit`.

### Simulator 3: `cross_symbol_residual`

- **Used by**: `dollar_residual`, `dispersion_rank`, `lead_lag`
- **Mechanics**: Same payoff shape as `forward_return`, plus a cross-symbol freshness gate (the trigger condition's input must be observable at entry bar's `close_ts`; otherwise the entry is dropped).
- **Family-specific bit**: `simulate_one_entry` receives `cs_frame` alongside the entry frame's ticks; checks trigger condition at execution time (no look-ahead, no stale-data fills).
- **Slippage knobs**: same as `forward_return` plus `max_peer_staleness_seconds`.

### Shared infrastructure

```
src/behemoth/governance/tick_exact_shared.py
  class TickStreamProvider:        # returns bid/ask ticks for (symbol, time_range)
  def aggregate_state_summary(...)  # per-state realized P&L stats
  def aggregate_monthly_summary(...)
  def compare_to_wfo(...)           # divergence vs WFO prediction
```

The cross-symbol simulator extends `TickStreamProvider` to fetch peer streams too.

---

## OCO migration plan (byte-identical parity)

Constraint: byte-identical outputs (Option A from brainstorming). State schedules, tick-exact summaries, freeze JSON, model JSON must diff to zero against pre-migration outputs.

### Phase 1 — Build framework + OCO adapter (no production cutover)

- Implement `src/behemoth/governance/` with the OCO adapter.
- New pipeline writes to a parallel output dir: `data/analysis/governance/<model_month>/`.
- Existing scripts unchanged; nothing in production knows the new pipeline exists.

### Phase 2 — Parity test (gates the cutover)

- `scripts/governance/validate_oco_migration_parity.py` runs both pipelines on a frozen reference snapshot and byte-diffs every artifact.
- Frozen reference snapshots pinned in `tests/fixtures/governance_oco_reference/` per (symbol, model_month).
- Runs in CI as a gating check.
- **Fails loudly on any diff** — no rounding tolerance.

### Phase 3 — Cutover (atomic swap)

Once parity is byte-identical:
- `onboard_symbol.py` Stages 2f/3/4 switch to `scripts/governance/run_governance_all.py --family oco_first_touch --symbol <SYM>`.
- New pipeline writes both the canonical new path (`data/analysis/governance/`) and copies/symlinks to legacy paths for one cycle.
- Old scripts moved to `scripts/legacy/`.

### Phase 4 — Add the 8 new families (sub-projects 2–4)

Each new adapter is a separate implementation task. Adding a family does NOT touch OCO; the framework is the stable contract.

### Risk mitigations

- **Frozen reference snapshots** in `tests/fixtures/` — CI parity does not depend on live mining outputs.
- **Numerical determinism**: any RNG-driven path uses fixed seeds in parity tests.
- **Float formatting**: CSV writers use identical `float_format` + column ordering as legacy.
- **Schema versioning**: freeze JSON gains `schema_version: "oco_v4.0"` (captures the existing implicit version retroactively).

### Known parity hazards (must guard against)

- Dictionary iteration order in JSON output (use sorted keys everywhere).
- pandas `groupby + apply` row re-ordering (use `sort=False` and explicit re-sorts).
- `np.cov` ddof differences (mitigated by matching the legacy call signature).
- Timestamp timezone metadata (canonical UTC always).

---

## Testing & error handling

### Test layers

1. **Unit tests per framework module** (`tests/governance/`) — state assembly, selection, each simulator, verdict propagation.
2. **Adapter-contract tests** (`tests/governance/families/`) — every adapter passes a shared contract suite: `derive_state_id` deterministic, `selection_gate` callable, `encode_freeze_artifact` produces valid schema-versioned JSON, all `state_key_cols` exist in candidate input.
3. **OCO byte-identical parity test** (described above) — CI gate.
4. **End-to-end integration tests** (`tests/test_governance_pipeline_e2e.py`) — tiny synthetic CSV + YAML → run orchestrator → assert specific verdicts. One per family. Deterministic, <5s each.
5. **Per-symbol smoke test** post-mining — assert symbol-level verdict is emitted and freeze JSON is valid (regardless of GO vs NO_GO).

### Error handling — fail loudly, no silent defaults

**Config validation (at YAML load):**
- Missing required field → `MissingGovernanceFieldError(symbol, family, field)`
- `required_families` entry missing from `families` block → `RequiredFamilyMissingThresholdsError`
- `model_month` not in `YYYY-MM` format → `InvalidModelMonthError`
- Family name not in registry → `UnknownFamilyError`

**Data validation (at stage entry):**
- Candidate CSV missing any `state_key_cols` column → `CandidateSchemaError(missing_cols)`
- Tick stream gap for a required (symbol, time_range) → `TickStreamGapError(symbol, range)`
- Cross-symbol freshness gate fails → log + drop entry (this is data, not error)

**Verdict propagation:**
- Required family has 0 candidate rows → that family is automatically NO_GO, logged at WARNING.
- Family verdict missing in required-family roll-up → symbol verdict is NO_GO, logged at WARNING with reason.
- Freeze artifact write fails → halt pipeline, no partial artifacts.

**Live-system invariants (eventual deployment substrate):**
- Freeze artifact with `model_month` ≠ current cycle → live system refuses to load. Preserves the monthly-expiry / no-fallbacks invariant.

### Observability

Per-stage per-symbol summary log lines:

```
[gov 14:32:18] EURUSD: G1 state_assembly: 11 families × 102 states avg = 1,122 states total
[gov 14:32:19] EURUSD: G2 selection: 87 states passed (8 families had ≥1 GO state)
[gov 14:34:51] EURUSD: G3 tick_exact: 87 states verified, 23 NO_GO (P&L divergence), 64 GO
[gov 14:34:51] EURUSD: G4 state_verdicts: 64 GO / 1058 NO_GO
[gov 14:34:51] EURUSD: G5 symbol_verdict: GO (required: directional_run=GO, dollar_residual=GO)
```

---

## Implementation phases (within sub-project 1)

| Phase | Output | Gate to next phase |
|---|---|---|
| **1a** | Framework skeleton + dataclass + protocol + OCO adapter stub | Adapter imports cleanly, dataclass validates a real YAML |
| **1b** | Stage G1 (state assembly) for OCO | State schedule has same shape as current OCO output |
| **1c** | Stage G2 (selection) ported | Selected states match current OCO byte-for-byte on EURUSD reference |
| **1d** | Stage G3 (barrier_touch simulator) | Tick-exact matches existing `verify_oco_tick_exact_shortlist.py` byte-for-byte |
| **1e** | Stages G4 + G5 + freeze | Freeze artifact matches existing OCO freeze byte-for-byte |
| **1f** | Parity test in CI | All 6 symbols pass byte-identical → cutover approved |
| **1g** | Cutover via `onboard_symbol.py` | `make retrain-all` produces same artifacts as before |
| **1h** | `forward_return` simulator + unit tests | Simulator passes synthetic-input tests (no family adapter yet) |
| **1i** | `cross_symbol_residual` simulator + unit tests | Simulator passes synthetic-input tests (no family adapter yet) |

**Stop condition**: if parity diff is non-empty after 1c/1d/1e, halt before cutover. Don't proceed with a known parity gap.

After 1g, OCO is the proof of concept. After 1h+1i, sub-projects 2–4 just add adapters; framework is locked.

---

## Open items for the implementation plan

1. **Selection-gate column source**: do family-specific gate columns (e.g., `both_window_rate`) come from the mining candidate CSV, or recomputed at G2? OCO has them in the CSV today; new families with no gate columns are moot. Decision: read from CSV as-is for migration parity.
2. **`model_month` cycling**: who increments it? Presumably `make monthly-recert` does. Implementation phase must verify the wiring and add a check in `run_governance_all.py` that the YAML's `model_month` matches an expected current value.
3. **Freeze artifact consumption**: nothing in v1 consumes it, but sub-project 5 will. Minimal structure now: `symbol`, `family`, `model_month`, `qualified_states` array, `schema_version`. Same as OCO writes today.

---

## Success criteria

- All framework modules + OCO adapter implemented; tests green.
- `validate_oco_migration_parity.py` passes byte-identical for all 6 symbols on the reference snapshot.
- `make retrain-all` after cutover produces governance artifacts that match the pre-migration OCO artifacts byte-for-byte.
- New family adapters (in sub-projects 2–4) can be added in ≤30 LOC of new code per family (config + optional hook overrides) without touching the framework.
- Per-symbol YAML missing any required field produces a clear error message naming the symbol, family, and field.
