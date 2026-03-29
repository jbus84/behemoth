## v0.2.1 (2026-03-29)

### Fix

- **ci**: skip registry tests when model artifacts are absent (#4)

## v0.2.0 (2026-03-29)

### Feat

- **ci**: add conventional commits, changelog, PR automation and methodology trail (#3)
- add THRESHOLD_PARITY_PASS to stage 14 certification
- pass training predictions dir to two-phase seeding
- two-phase seeding endpoint with training predictions
- add seed_training_predictions to StateManager
- add train_predictions and model_valid_through to lock JSON
- export training predictions parquet for live seeding
- make monthly recert the definitive gate
- add dukascopy demo certification dashboard panels
- integrate live symbol readiness into jforex strategy
- gate new jforex entries by symbol readiness
- add jforex broker bridge loader
- add live parquet warmup loader
- add live symbol readiness registry
- add jforex live readiness config defaults
- sync candidate artifacts in monthly recert
- sync candidate model artifacts from live locks
- wire close_reason and commission_ccy through JForex trade update payload
- add commission field to OrderEvent and fix all constructor call sites
- pass reservation_id, close_reason, commission_ccy through Python API
- add 7 new columns to trades table with open/close context
- call /state/seed_audit_history at startup before backfill sleep
- add POST /state/seed_audit_history endpoint for rolling threshold bootstrap
- add dukascopy_ticks_dir to AppConfig (BEHEMOTH_DUKASCOPY_TICKS_DIR)
- live win-rate gap diagnostics — checkpoint, diagnostic script, rolling threshold, warmup
- add jforex live readiness and demo certification flow
- add monthly-recert, promote-live, freeze-oco-dukascopy-candidate Makefile targets
- add run_promote_live.py promotion orchestrator
- add run_monthly_recert.py monthly recertification orchestrator
- add jforex-live Makefile target for live/demo session
- add run_jforex_live.py live session orchestrator
- close filled OCO positions after horizon bars to unblock eval-window lifecycle
- add PendingExit record and pendingExits field to SymbolRuntimeState
- add closePosition to ExecutionPort with stubs
- add JForex coverage-gap diagnostic script
- add full-stage14-cert Makefile target for monthly recertification
- add evaluated_at_utc to reconcile_jforex_outcomes outputs for Stage 14 staleness gate
- add staleness validation to Stage 14 — fail checks if input artifacts are >7 days old
- add outcome_parity and local_surrogate checks to Stage 14 certification gate
- add --lock-dir to extract_spotlight_ticks to eliminate cursor contamination
- emit per-trade outcome events (pnl_pips, side, fill/close price) from Stage14ArtifactWriter
- wire outcome reconciliation as Stage 14 final integration check
- write per-symbol outcome parity CSVs for cert validator consumption
- add per-event order matching and eval-window coverage to outcome reconciliation
- add eval-window filtering to reconcile_jforex_outcomes load_locked_predictions
- add JForex outcome parity reconciliation and Dukascopy matrix runner

### Fix

- **ci**: remove stray test_fetcher_bug.py that breaks CI
- remove tick-batch-size from shared args and restore legacy stub targets
- update threshold blocking response for new source values
- update test mocks for rolling threshold authority
- rolling computation is sole threshold authority in live mode
- accumulate test-day predictions in WFO rolling threshold
- allow nogo status in promote-live cert gate
- skip historical month refills near boundary edges
- clear orphaned tick vault lockfiles
- cap tick vault current-month refills at session end
- wire weekend gap filtering into tick vault scan
- move tick vault stubbing into tests
- harden tick vault session gap detection
- add dst-aware tick vault session boundaries
- finalize monthly recert nogo certification
- propagate local surrogate lock dir and zero-lock fallback
- align stage14 nogo to historical deployability
- allow stage14 and recert nogo for non-deployable symbols
- drop stage12 input from local surrogate validator
- allow local surrogate nogo and zero-lock windows
- normalize runtime event pass flags
- harden canonical jforex runtime event reads
- require canonical jforex runtime events in stage14
- avoid local surrogate port collisions during recert
- align jforex selected count to executable candidates
- keep monthly parity on eval window
- improve jforex parity replay instrumentation
- restore candidate model path and no-gate historical handling
- **jforex**: pace broker bridge polling
- **jforex**: harden broker bridge readiness logic
- **jforex**: contain broker bridge failures
- **jforex**: enforce broker bridge window contract
- **jforex**: reject empty live warmup windows
- **jforex**: align live warmup bridge anchor semantics
- **jforex**: reconcile live readiness snapshots to as-of time
- **jforex**: complete readiness registry state writer
- make live readiness test hermetic
- keep jforex live readiness env semantics
- archive promote-live from candidate models dir
- reject non-object sync lock payloads
- harden malformed sync lock handling
- harden candidate artifact sync failures
- fail sync when requested live lock is missing
- support legacy live audit trade schema
- preserve replay causal source indices
- harden live audit diagnostics queries
- restore predict evaluation timestamp contract
- preserve feature-matrix warmup masking
- sort audit_logs lookup by event_ts not close_ts in open_trade
- convert bar_ticks assert to log+skip to preserve per-symbol fault tolerance
- guard HTTPException in symbol loop + add idempotency note + assert uniform bar_ticks
- correct magnitude analysis — OCO from_touch pnl is variable, not bounded by barrier_pips
- resolve ModuleNotFoundError in reconcile_account_risk_reservations.py
- default tick-root to canonical dukascopy_ticks + refreshed capacity reports
- keep live jforex session alive under predict failures
- wait for jforex live connection before strategy start
- add --models-dir and --history-dir to jforex-live Makefile target
- move jforex-dukascopy-matrix start_ts to 2025-07-04 (Friday)
- move jforex-dukascopy-matrix start_ts to 2025-07-06 for proper warmup
- move jforex-dukascopy-matrix start_ts to 2025-07-05 for proper warmup
- delete stale active_oco_state.json before each real JForex tester run
- kill JForex tester on CSV completion instead of waiting for JVM shutdown
- load_runtime_events prefers real tester events over local surrogate events
- raise max_artifact_age_days default 7→35 days for monthly retraining cadence; refresh cert artifacts
- add -Duser.timezone=UTC to runJForexLive, @Execution(SAME_THREAD) to timezone test, clarify missing_inputs semantics
- raise signal_coverage_threshold default from 0.8 to 1.0
- use per-call Calendar.getInstance(UTC_TZ) instead of shared mutable static Calendar
- add UTC calendar to ParquetTickLoader JDBC, UTC JVM arg to runJForexTester, timezone regression test
- force JVM UTC timezone in runLocalJForexTester to fix spotlight parity
- spotlight surrogate uses tick-batch-size=100 to prevent bar-close miss
- reconciler overall_pass uses signal_coverage gate instead of order_coverage
- drain server stdout in background thread to prevent pipe buffer deadlock
- spotlight uses locked predictions source and raises coverage threshold to 0.8
- hoist lock_dir out of loop and add casing/pre-bars comments
- use order_coverage_pass unconditionally in compare_outcomes overall_pass
- bridge Stage 12 API parity check to read from Stage 13 summary CSV

### Refactor

- rewrite Makefile into logical sections
- rename governance/ftmo/ config directory to account_risk/
- rename ftmo_* references in live scripts to account_risk_*
- convert account_risk monitoring scripts from shims to standalone implementations
- rename ftmo_* to account_risk_* in server.py (config, models, endpoints, metrics)
- rename ftmo_* DB tables and state.py methods to account_risk_*
- rename FtmoAccountSnapshotRequest to AccountRiskSnapshotRequest
- merge ftmo.py into account.py, rename Ftmo* classes to AccountRisk*

## v2026.03.15 (2026-03-15)

### Feat

- add quality dev tooling (vulture, smellcheck, radon, xenon) and resolve quality debt
- **ml**: add feature importance tracking and reporting to monthly wfo
- **governance**: parameterize governance and registry paths
- **observability**: add Alertmanager provisioning script for secure SMTP setup
- **observability**: add email notification support via Alertmanager
- **observability**: add Automated Alerting and Dashboard-as-Code
- **observability**: integrate Prometheus and Grafana monitoring stack
- **governance**: automate optimal execution cap selection and unify across symbols
- achieve zero-drift in E2E simulation by aligning price source and bar boundaries
- **cbot**: add BehemothTradeManager.cs to version control and add Makefile deploy-cbot target
- end-to-end symbol onboarding pipeline + USDCAD/AUDUSD analysis
- H1 Portfolio Optimization & Breakdown Analysis
- sync equity from cTrader, optimize kalman/zscore performance, enhance internal equity tracking

### Fix

- train-only quality tiers + OCO capacity floor + threshold docs
- threshold parity + causal selection_pass
- remove test-metric selection bias + align L12 hash coverage
- snapshot git provenance once before lock writes
- governance hardening — full artifact hash coverage + git provenance gate
- red-team phase 3 — timestamp alignment, join integrity, causality, glossary
- **pipeline**: resolve Stage 5/6 collision and docs contract validation
- handle NaN in gate_tick_exact boolean mask (docs contract)
- **execution**: resolve round 3 red-teaming resilience flaws
- **execution**: resolve round 2 red-teaming execution fallacies
- **grafana**: assign stable datasource UID and update dashboard mapping
- **observability**: correct trade update labeling and add live verifier
- **oco**: update WFO configs to cross-year evaluation and fix state governance freeze for N+1 upcoming month lock
- **pipeline**: auto-generate live governance locks during onboarding

### Refactor

- remediate architectural smells (magic numbers, long methods) in features.py and tick_aggregator.py
- complete legacy purge and formalize 6-symbol universe
