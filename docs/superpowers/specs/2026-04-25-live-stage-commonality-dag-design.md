# Live/Stage Commonality and DAG Process Design

- **Status:** Approved; implementation plan written.
- **Date:** 2026-04-25
- **Target branch:** `main`
- **Target commit:** `b46ca0bfc9037c796d3cda918207dd8e28de5137`
- **Scope:** Review commonality between promoted live runtime and Stage 12/13/14 certification logic; define a scorecard; design a process/DAG direction for certification, promotion, restart eligibility, and smoke checks.
- **Out of scope:** Code changes, Prefect implementation, live trading inside a DAG runner, rerunning certification, model retraining, governance lock edits, or changing current live runtime semantics.

## Problem

The current system has strong shared Python runtime components, but promotion and live deployment remain exposed to process drift. Recent incidents showed that correct code can still run against the wrong artifact root, stale promotion evidence, or an unexpected live state context. The highest remaining risk is not primarily "different math"; it is "right code, wrong branch, wrong artifact, wrong month, wrong lock, or wrong restart state."

The review needs to answer:

> How much of the logic that decides live behavior is genuinely shared with, or equivalently exercised by, Stage 12/13/14 certification?

This is not an outcome-parity review. Live trades can differ from replay because broker timing, spread, account state, and callbacks differ. The target is semantic parity: certification should catch live semantic drift before promotion.

## Evidence Reviewed

The design is based on the current `main` runtime at `b46ca0bf`, with particular attention to:

| Area | Evidence |
|---|---|
| Live launcher and preflight | `scripts/run_jforex_live.py` |
| Stage 12/13 wrapper | `scripts/run_stage12_stage13_certification.py` |
| Stage 14 certification | `scripts/validate_stage14_jforex_runtime_certification.py` |
| Monthly recert gate | `scripts/run_monthly_recert.py` |
| Promotion command | `scripts/run_promote_live.py` |
| Real JForex matrix | `scripts/run_jforex_dukascopy_matrix.py` |
| Local JForex surrogate matrix | `scripts/run_local_jforex_surrogate_matrix.py` |
| Feature source of truth | `src/behemoth/core/features.py` |
| Python prediction API | `src/behemoth/api/server.py` |
| Runtime state and thresholds | `src/behemoth/runtime/state.py` |
| Java/JForex runtime | `src/jforex/src/main/java/com/behemoth/jforex/` |
| Dependency hot spots | `graphify-out/GRAPH_REPORT.md` |

Graphify identifies the main shared abstractions as high-connectivity nodes: `ModelFeatures`, `IncomingTickBar`, `StateManager`, `IncomingTick`, `OcoPrediction`, `FeatureConfig`, `BarrierManager`, `TickAggregator`, `BarrierAction`, and `PredictResponse`. The scorecard should therefore judge commonality around these seams rather than around script names alone.

## Scoring Model

Each logic area is scored out of 100:

| Weight | Dimension | Meaning |
|---:|---|---|
| 30 | Shared source of truth | Direct code reuse or a single authoritative implementation. |
| 25 | Artifact/config contract | Same lock, model, threshold, symbol universe, month, and candidate binding. |
| 20 | Runtime dataflow equivalence | Stage and live exercise equivalent input/output flow. |
| 15 | Parity/certification coverage | Stage checks would catch drift before promotion. |
| 10 | Observability and fail-fast guards | Metrics, diagnostics, and hard stops surface invalid states. |

The score means:

- `90-100`: strongly shared; remaining differences are mostly operational.
- `75-89`: mostly aligned; gaps need hardening but current design is defensible.
- `60-74`: partially aligned; certification may miss important live behavior.
- `<60`: process or code path is too divergent for promotion confidence.

## Preliminary Commonality Scorecard

| Logic area | Score | Assessment |
|---|---:|---|
| Feature calculation and warmup | 90 | Strong shared Python feature code. The fixed `/predict/warmup` replays historical buffered bars through the model, aligning warmup calibration with backtest/stage semantics. Remaining risk is loader/count-policy divergence between Java bridge, API warmup, and stage harnesses. |
| Model/artifact/lock binding | 85 | Promoted locks, model-month binding, and runtime preflight checks are strong. Remaining risk is operational: local artifact roots and ignored runtime materialization can still point at the wrong evidence if the process permits it. |
| Symbol universe and GO/NO_GO | 80 | Registry/lock-driven promotion is mostly aligned. The process still needs sharper separation between process `FAIL` and symbol `NO_GO`, especially in stage reports and live deployment filters. |
| Prediction scoring and thresholds | 82 | Live and stage mostly go through the same API/model path. Rolling threshold warmup is materially improved. Remaining risk is duplicate threshold interpretation in diagnostics or replay scripts. |
| Barrier/OCO action generation | 72 | Python barrier/action logic is shared enough to certify behavior, but live broker timing and callback sequencing are only partially represented in replay/stage layers. |
| Java/JForex adapter behavior | 70 | Stage 14 exercises real and surrogate JForex paths, which is valuable. Remaining gap is that Java readiness/execution state is a second state machine beside Python governance. |
| Risk/account allocation | 65 | Live has real account/risk/reservation behavior. Stage paths often simulate, disable, or constrain this, so parity coverage is weaker. |
| Restart/reconciliation state | 70 | Recent hardening improves restart safety. Stage flows are mostly rebuild/stateless, while live must reconcile broker state, local DB, git state, and promoted locks. |
| Stage orchestration/evidence flow | 55 | Weakest area. The scripts are explicit, but dependencies are imperative and artifact freshness/provenance are not represented as a single graph. |
| Observability/diagnostics | 78 | Metrics and diagnostics exist, including rolling threshold integrity. The gap is that not all diagnostics are first-class stage verdict inputs. |

Overall preliminary commonality score: **75-78/100**.

Interpretation: the core feature/model/prediction path is reasonably aligned after the warmup fix. The process layer remains too easy to mis-run. The main hardening target is artifact and execution-context provenance, not immediate replacement of the trading runtime.

## Verdict Semantics

Process state and symbol deployment state must remain distinct:

| Term | Applies to | Meaning |
|---|---|---|
| `PASS` | Stage/process | The process ran correctly and produced valid evidence. |
| `FAIL` | Stage/process | The process or evidence is invalid. Promotion is blocked. |
| `GO` | Symbol | The symbol is deployable under the validated process output. |
| `NO_GO` | Symbol | The symbol is not deployable, but the process did not fail. |

Examples:

- Missing Stage 13 evidence for a required symbol is `FAIL`.
- Stale artifact root or wrong target branch is `FAIL`.
- A symbol that is intentionally quarantined after valid evaluation is `NO_GO`.
- A symbol with valid evidence and approved deployment state is `GO`.

This distinction should be applied consistently in Stage 12/13/14 reports, monthly recert summaries, promotion decisions, and live deployment filters.

## DAG Direction

Live trading should not be run inside Prefect or any DAG runner initially. The live process should remain a supervised runtime with strict preflight checks.

The DAG should govern the process around live:

1. Monthly build bundle
2. Stage 12 API parity
3. Stage 13 Dukascopy/TestClient certification
4. JForex Dukascopy matrix
5. Local JForex surrogate matrix
6. Stage 14 runtime certification
7. Promotion eligibility
8. Live preflight
9. Restart eligibility
10. Live smoke checks

The DAG is first a repository contract, not a new service. Prefect can be considered later as an execution backend only after the graph semantics are explicit and validated.

## Authoritative DAG Contract

Each node should declare:

| Field | Meaning |
|---|---|
| `node_id` | Stable DAG node name, for example `stage14_runtime_certification`. |
| `target_branch` | Expected branch, normally `main` for official promotion. |
| `target_commit` | Commit used for execution. |
| `inputs` | Required files, artifact roots, lock files, model directories, credentials, or broker prerequisites. |
| `outputs` | Files and reports produced by the node. |
| `freshness_policy` | Allowed age, required rebuild condition, or explicit immutable month/build id. |
| `provenance` | Source branch, commit, lock fingerprint, model month, symbol universe, input hashes, and execution timestamp. |
| `process_verdict` | `PASS` or `FAIL`. |
| `symbol_verdicts` | Per-symbol `GO` or `NO_GO`. |
| `failure_mode` | Structured reason for `FAIL`, for example `wrong_branch`, `stale_artifact`, `missing_input`, or `lock_mismatch`. |

Promotion must refuse evidence if any required node is stale, missing, wrong-branch, wrong-commit, wrong-month, lock-mismatched, or partially evaluated.

## Restart Eligibility

Restart eligibility is the preflight gate used when live is started after a crash, machine restart, operator restart, or planned deployment restart. It decides whether live can safely attach to preserved state.

It is not a request to clear the database. The default behavior should preserve live state. Clearing state should require an explicit operator action or flag because otherwise trade lifecycle tracking can be lost and broker positions can be orphaned.

A restart is eligible only when all required checks pass:

| Check | Required evidence |
|---|---|
| Git state | Running code is `main`, up to date, and at the expected commit. |
| Lock state | Promoted lock fingerprint matches runtime model/artifact set. |
| Model state | Model month, symbol universe, and candidate set match the promoted lock. |
| Symbol state | `GO`/`NO_GO` and quarantine state match the promoted deployment decision. |
| Local DB state | Stored run context matches the promoted lock and runtime session expectations. |
| Broker state | Open orders and positions reconcile against local execution state. |
| Barrier state | Pending barriers/orders are recoverable or entries are disabled until reconciliation completes. |
| API/JForex readiness | Python API, JForex bridge, warmup state, and metrics are reachable enough to prove readiness. |
| Artifact state | No stale historical root, wrong candidate month, or unapproved model artifact is in use. |

Restart eligibility returns one of:

| Result | Meaning |
|---|---|
| `RESTART_ELIGIBLE` | Safe to resume live with preserved state and normal entry behavior. |
| `RESTART_ELIGIBLE_DRAIN_ONLY` | Safe to start for reconciliation, monitoring, and managing existing exposure, but no new entries. |
| `RESTART_BLOCKED` | Do not start live because code, artifacts, broker state, or local state cannot be proven consistent. |

Crash flow:

1. Process crashes or machine restarts.
2. Operator or supervisor attempts live restart.
3. Restart eligibility runs before live entries are enabled.
4. If local state and broker state reconcile, live resumes normally.
5. If unresolved orders/barriers exist, live starts in drain-only/no-new-entries mode.
6. If code, artifacts, lock, broker state, or local DB state cannot be reconciled, restart is blocked.

## Prefect Adoption Plan

Prefect should not be the first implementation step. A DAG runner can make execution visible, but it cannot fix unclear semantics. The graph contract should be stabilized first.

Recommended phases:

| Phase | Action | Rationale |
|---|---|---|
| 1 | Document the current process graph and scorecard. | Establish shared language and baseline risk. |
| 2 | Add repo-native DAG/provenance validation. | Make wrong branch, stale artifact, wrong lock, and partial evidence structurally detectable. |
| 3 | Run dry-run graph validation against current artifacts. | Prove the graph catches known process risks before adding orchestration infrastructure. |
| 4 | Pilot Prefect on monthly recert and Stage 12/13/14 only. | Constrain risk to non-live certification workflows. |
| 5 | Optionally extend Prefect to promotion preflight and live smoke checks. | Use Prefect for orchestration and observability, not trade execution. |

Prefect should remain an execution backend. The repository DAG contract should remain the source of truth.

## Testing And Verification Strategy

This spec does not implement tests. Future implementation planning should include:

| Area | Verification |
|---|---|
| Scorecard | Review scores against current files and update when implementation changes move logic between layers. |
| Verdict semantics | Unit tests for `PASS`/`FAIL` versus `GO`/`NO_GO` aggregation. |
| DAG contract | Tests that stale inputs, wrong branch, wrong commit, lock mismatch, missing symbol evidence, and partial outputs fail validation. |
| Provenance | Tests that output manifests include commit, branch, model month, lock fingerprint, symbol universe, input hashes, and timestamp. |
| Restart eligibility | Tests for eligible, drain-only, and blocked restart outcomes using synthetic local DB plus broker snapshot inputs. |
| Prefect pilot | If adopted, compare Prefect flow output against repo-native DAG validation before trusting it for promotion. |

## Acceptance Criteria For This Design

The design is acceptable when:

1. The scorecard dimensions and preliminary scores are approved as the baseline review frame.
2. `FAIL` and `GO/NO_GO` semantics are explicitly separated.
3. Restart eligibility is defined as crash/restart-safe state preservation, not DB clearing.
4. The DAG direction keeps live trading outside orchestration initially.
5. Prefect is treated as a later execution backend, not the source of truth.
6. Future implementation requires a separate plan and PR.

