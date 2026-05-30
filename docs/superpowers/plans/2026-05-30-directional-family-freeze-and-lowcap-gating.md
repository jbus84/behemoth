# Plan: Directional-Family Freeze Path + Low-Frequency Gating

- Date: 2026-05-30
- Status: Sketch (pending go/no-go on ADR 0005 promotion)
- Depends on: ADR 0005 (`docs/adr/0005-low-capacity-regime-track.md`), harness `scripts/evaluate_low_capacity_track.py` (PR #273)

## Problem

ADR 0005's 2026-05 evidence shows the only conservatively-profitable edge in the book is a small set of low-frequency `directional_inverse` states (net LB95 +0.92, 80% positive months) that the Stage-5 capacity floor discards, while the capacity-passing states it keeps are net-negative. Two structural gaps block deploying that edge:

1. **No freeze path for directional families.** The model-export + freeze pipeline is `oco_first_touch`-centric. The 2026-05 freeze produced **0 locks** because `oco_first_touch` is Stage-5 FAIL on all 6 symbols, and the directional families where the edge actually lives are never exported or frozen.
2. **No low-frequency admission gate.** Stage 5 admits states only via the capacity floor (`avg_month_rows >= 3000 OR annualized >= 3000`); there is no robustness-based admission path for sub-capacity states.

## Workstream A — Directional-family freeze path

Goal: a directional family that passes Stage-6 tick-exact (already fixed — all 5 directional-library families verify at exact_match 1.0 after PRs #269–#272) can be exported and frozen into a deployable lock.

Key files and the specific gaps:
- `scripts/onboard_symbol.py` — model export (`--model-export-dir`, `--skip-data`, `--eval-end-month`) currently emits `models/oco/<SYM>_oco_first_touch_model_<month>.cbm`. Needs to export per-(symbol, directional-family) models.
- `scripts/sync_candidate_model_artifacts.py` — `_source_artifacts_for_month` builds `<SYM>_<family>_model_<month>.cbm`; `_parse_barrier_from_state` only understands the `k<N>` barrier suffix. Directional states (e.g. `directional_inverse__high_activity__h3`) carry **no barrier suffix** — they are keyed by regime + horizon, not barrier distance. A directional-family state→artifact parse path is required (no barrier; key on `bar_ticks` + `state_id` + horizon).
- `scripts/run_monthly_build.py` (`--model-month`) — the freeze. Its bundle/lock generation is oco-centric; it must learn to emit locks for directional families. Confirm Stage-9 lock schema (`configs/research/governance/oco/*_oco_live_lock.json` shape) generalises to a directional family or needs a sibling lock type.
- Contract note: this rides on ADR 0004's stage-I/O direction — verdict-bearing artifacts must be keyed by `(symbol, family)`, not `(symbol, library)`.

Risks: the directional payoff is `side × y_fwd` (not a barrier OCO), so any downstream cert/execution assumption that a lock implies an OCO bracket order must be checked. oco_asymmetric/no_touch remain out of scope (Stage-5 FAIL / empty).

## Workstream B — Low-frequency gating track

Goal: promote the harness's robustness gate as an explicit, governed admission path alongside (not replacing) the capacity floor.

Key files:
- `scripts/select_reduced_core_regimes.py` — `capacity_pass_monthly_or_annual` (~line 989), floor constants `capacity_floor_monthly/annual=3000` (~lines 56–57). Add a parallel `lowfreq_pass` admission: `net_lb95 > 0 AND positive_month_share >= 0.6 AND n >= min_trades`, BH-corrected across the tested set — i.e. fold the harness logic (`_state_metrics`, `_apply_gates`, `_bh_correction` in `scripts/evaluate_low_capacity_track.py`) into the reduced-core selection as a second admission lane, tagging each admitted state with its lane.
- Decide and document: parallel lane vs lowering the floor. ADR 0005 favours a parallel lane so the two regimes stay under explicit, separate gates.
- Stage 2 `min_annual_fills=5000` (`scripts/run_tick_opportunity_mining.py` ~line 78) pre-filters before Stage 5 even sees a state — confirm the low-frequency admitted states survive Stage 2, or lower the Stage-2 floor for the low-frequency lane.

Risks: per-trade LB95 is a simplification; before deployment, validate with a block-bootstrap or per-month-weighted bound. The admitted set is concentrated (1 family, 2 symbols) — guard against over-fitting by requiring BH survival and a minimum positive-month share, both already in the gate.

## Sequencing

1. Workstream B first (cheaper, no retrain) — make the low-frequency lane visible in Stage-5 output so admitted states are first-class artifacts.
2. Then Workstream A (export + freeze) to make an admitted directional state deployable.
3. Re-run the certification ladder (Stage 12–14, root checkout only) on the first admitted directional lock as the end-to-end proof.

## Out of scope

oco_asymmetric / no_touch freeze paths; changing the directional tick-exact verifier (already correct); execution/broker integration beyond confirming the lock contract.
