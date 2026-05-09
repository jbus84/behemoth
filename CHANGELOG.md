## v0.29.0 (2026-05-09)

### Feat

- deepen architecture — 10 refactoring candidates (#158)

### Fix

- add missing OrderIntent.java from architecture deepening

## v0.28.0 (2026-05-09)

### Feat

- Wave 6.6 - Horizon-Aware Feature Config (#157)

## v0.27.0 (2026-05-09)

### Feat

- Wave 6.5 - Account Risk Allocator Port (#156)

## v0.26.0 (2026-05-09)

### Feat

- Wave 6.4 - Scan State Machine extraction (#155)

## v0.25.0 (2026-05-09)

### Feat

- Wave 6.3 - Regime Quantiles Contract (#154)

## v0.24.0 (2026-05-09)

### Feat

- Waves 6.1-6.2 - Warmup parity validation and audit trail persistence (#153)

## v0.23.0 (2026-05-09)

### Feat

- ReservationStateMachine — dedicated module with explicit transitions (#152)

## v0.22.0 (2026-05-09)

### Feat

- BarTouchSemantics — extract hl_first tie-breaking logic (#151)
- Add account_risk_reservation_audit table to schema
- Add account_risk_reservation_audit table to schema (#150)
- Dedup warmup formula in FeatureConfig (#149)

## v0.21.0 (2026-05-09)

### Feat

- Add account_risk_reservation_audit table to schema
- Add account_risk_reservation_audit table to schema (#150)
- Dedup warmup formula in FeatureConfig (#149)
- WarmupBoundaryVerifier — observable warmup gate status (#148)

## v0.20.3 (2026-05-09)

### Refactor

- introduce RuntimeAppState container as the seam for future server.py extractions (#147)
- introduce RuntimeArtifact registry for the live runtime/ directory (#146)

## v0.20.2 (2026-05-08)

### Refactor

- extract feature_parity diagnostic module + fix tz-merge bug (#145)
- introduce ReconciliationCycle to enforce snapshot→mutate→finalize ordering (#144)

## v0.20.1 (2026-05-08)

### Fix

- complete PredictionOrchestrator step 5/7 — restore /predict correctness (#143)

## v0.20.0 (2026-05-08)

### Feat

- Grafana panel + Prometheus metric for restart_verdict (#141)

### Fix

- re-reconcile after reset cleanup so report reflects post-reset state (#142)
- thread-safe DuckDB store and warmup_bars delegation after FeatureEngine refactor (#140)

## v0.19.2 (2026-05-08)

### Fix

- surface RESTART_BLOCKED verdict in live_symbol_readiness.json (#139)

## v0.19.1 (2026-05-08)

### Fix

- default BEHEMOTH_RECORD_RAW_TICKS to true (#138)

## v0.19.0 (2026-05-08)

### Feat

- live threshold diagnostics (#137)

### Refactor

- complete opportunities #2-#7 for predict pipeline deepening (#136)

## v0.18.0 (2026-05-08)

### Feat

- wire PredictionOrchestrator into /predict endpoint (Wave 5 Integration) (#135)
- make state protocols runtime-checkable for structural verification (#134)

### Refactor

- decouple BarrierManager from DuckDB with StateStore abstraction (#132)
- type AccountRiskDecision with full evaluation context (#131)

## v0.17.2 (2026-05-08)

### Refactor

- extract FeatureComputationEngine from StateManager (#130)

## v0.17.1 (2026-05-08)

### Refactor

- align state_readers protocols with actual StateManager interface (#129)

## v0.17.0 (2026-05-08)

### Feat

- wire ReservationLifecycle into StateManager for audit trail (#128)

### Refactor

- integrate architectural deepening opportunities 2,3,5,6,8 (#127)

## v0.16.2 (2026-05-08)

### Refactor

- implement opportunities #7 (OrderSubmissionPort) and #8 (state_readers consolidation)
- implement opportunity #6 (FeatureConfig schema validation)
- implement opportunities #2 (BarrierEvaluationContext) and #4 (ReservationLifecycle)
- implement architectural deepening opportunities (#1, #5)
- implement opportunities #10 (cache lifecycle) and #12 (transaction boundaries)
- consolidate shallow modules and deepen seams (7-8 of 12)
- deepen boundaries and formalize protocols (5-6 of 12)
- deepen architectural seams (1-4 of 12 opportunities)

## v0.16.1 (2026-05-07)

### Refactor

- extract runtime architecture seams

## v0.16.0 (2026-05-07)

### Feat

- extract GovernanceValidator module from procedural validation logic
- extract HistoricalPredictionStage module from prediction payload caching

### Refactor

- enforce BarContext-only interface in BarrierManager

## v0.15.3 (2026-05-07)

### Fix

- harden JForexExecutionPort against shutdown race and error leaks (#124)

## v0.15.2 (2026-05-07)

### Fix

- route JForex engine operations through strategy thread via executeTask (#123)

## v0.15.1 (2026-05-07)

### Refactor

- deepen runtime execution boundaries - seam implementation (#122)
- deepen runtime execution boundaries (#121)

## v0.15.0 (2026-05-06)

### Feat

- add LIVE_INSTANCE tracking and constructor registration log to JForexMetrics (#119)

### Fix

- wire JForex predict metrics timer in SymbolWorker (#118)
- uppercase threshold-parity status in Stage 14 certification (#116)

## v0.14.0 (2026-05-06)

### Feat

- JForex live health monitor for async tick decoupling demo (#114)
- async tick decoupling — move HTTP I/O to per-symbol worker thread (#112)

### Fix

- force JVM exit after broker snapshot to prevent Gradle daemon hang (#115)
- align matrix and live warmup load to candidate bar_ticks (#107)
- floor bridge bar count at parquet warmup initial value (#106)
- hard-stop startup if tick data is stale (> 3 days) (#105)

### Refactor

- rename outcome-parity columns to canonical governance / runtime vocab (#111)

## v0.13.1 (2026-04-27)

### Fix

- add 300s timeout to offline seed subprocess to prevent startup hang (#104)

## v0.13.0 (2026-04-27)

### Feat

- parity audit harness — 9 runtime contract checks + CLI runner (#102)
- backport Grafana dashboard improvements from parity branch (#101)
- live stage DAG hardening — provenance, restart eligibility, drain-only gate (#95)

### Fix

- add --no-daemon to gradle invocations to prevent startup hang (#103)
- close 11 raw _con.execute leaks — add StateManager seam methods (#100)
- eliminate RestartVerdict in favour of canonical RestartEligibility (#99)
- align certification verdict values with ubiquitous language (#98)
- harden live stage DAG promotion and restart fixes (#96)

## v0.12.1 (2026-04-24)

### Fix

- fail fast on live artifact drift
- freeze threshold json runtime fields (#92)
- prefer lock runtime thresholds in live model load (#91)
- lower rolling threshold min history to 300 (#90)

## v0.12.0 (2026-04-22)

### Feat

- reconcile live restart state before launch (#80)

### Fix

- expose live deployment state in status (#81)
- accept month-scoped stage14 recert report provenance (#79)

## v0.11.2 (2026-04-21)

### Fix

- pass recert replay window into stage13 (#78)

## v0.11.1 (2026-04-21)

### Fix

- scope monthly recert stage13 to month bundle (#77)
- repair certification and promotion provenance flow (#75)
- default live runtime to promoted governance locks (#73)

## v0.11.0 (2026-04-17)

### Feat

- demo-live vs offline model comparison report script (#70)

## v0.10.0 (2026-04-16)

### Feat

- certify executable-side oco contract (#65)

### Fix

- clear hardcoded eval_end_month in candidate WFO configs and promote 2026-03 live governance (#67)
- reclassify backfill publish failure as retryable bridge error
- promote 2026-03 live governance and repair monthly-recert pipeline
- clear hardcoded eval_end_month in candidate WFO configs and promote 2026-03 live governance
- start jforex live before warmup (#66)

## v0.9.1 (2026-04-12)

### Fix

- align tick exact verifier with spread aware oco semantics
- use close bid in fx snapshot helpers
- wire explicit bid schema through api and velocity builder

### Refactor

- enforce explicit bid ask schema in analysis pipeline
- use explicit bid ask bar fields in runtime and api
- require explicit bid ask columns in research builders
- emit explicit bid ask offline bar schema
- rename canonical bar schema to explicit bid ask fields

## v0.9.0 (2026-04-11)

### Feat

- diagnose_live_replay emits high_ask and close_ask from _build_bars_from_ticks
- _oco_precompute uses high_ask for BUY trigger and close_ask for SELL exit label
- pass bar_high_ask from tick_bars state to barrier manager evaluate_bar
- barrier_manager up_touch uses bar_high_ask (ASK price) for BUY trigger
- add high_ask and close_ask columns to tick_bars DDL and state manager
- add high_ask and close_ask fields to IncomingTickBar and TickAggregator

### Fix

- align ask aggregation with bid filtering in _build_bars_from_ticks
- remove unused pytest import from test_oco_precompute_spread
- clarify TestHoldCompletion test intent with explicit bar_high_ask values
- use latest buffered tick bid for unrealized pips instead of stale bar close (#62)
- count broker-open positions separately (#61)

## v0.8.3 (2026-04-10)

### Fix

- color unrealized pips by sign

## v0.8.2 (2026-04-10)

### Fix

- retry startup bridge failures on fresh ticks

## v0.8.1 (2026-04-10)

### Fix

- clamp jforex bridge requests to broker last tick
- make equity panel current-session authoritative (#57)
- Open Positions — Age (min) column converts seconds to minutes (#56)
- seed governance fingerprint check prevents stale threshold seeds (#55)
- Active OCO Groups line visibility + Entries Allowed state-timeline panel (#54)
- Open Positions table — correct legend format and zero-value filter (#53)
- bridge transient retry + wire entry gate (#52)
- catch OSError in _poll_health to handle connection reset during API startup (#51)

## v0.8.0 (2026-04-09)

### Feat

- combine position age panels into single sorted table (#50)

## v0.7.0 (2026-04-09)

### Feat

- orphaned reservation cleanup + position age in bars (#49)

## v0.6.5 (2026-04-09)

### Fix

- replace Open Position Age table with stat panel per symbol (#48)

## v0.6.4 (2026-04-09)

### Fix

- fill rate double-count + unrealized pips stat panel per symbol (#47)

## v0.6.3 (2026-04-09)

### Fix

- dashboard panel accuracy improvements (#46)

## v0.6.2 (2026-04-09)

### Fix

- replace Order Submit vs Fill timeseries with fill rate stat + unconfirmed stat + clean symbol-aggregated timeseries (#45)

## v0.6.1 (2026-04-09)

### Fix

- correct prometheus scrape port for behemoth-api (8001 → 8000)

## v0.6.0 (2026-04-09)

### Feat

- live position observability (open-summary endpoint + metrics + Grafana) (#38)

### Fix

- complete observability improvements missed in PR #43 auto-merge (#44)
- replace stale prometheus alerts and fix grafana pips unit (#43)
- wire BEHEMOTH_GOVERNANCE_DIR to latest history month in jforex-live (#42)
- use JForex order label (not broker_pos_id) when closing positions (#41)
- pass candidateUid, reservationId, horizon from OPEN_MARKET action to /trades/open (#40)
- release risk reservation when barrier scan expires (#39)

## v0.5.1 (2026-04-07)

### Fix

- seed strategy core tick seq from bridge result after backfill (#37)

## v0.5.0 (2026-04-07)

### Feat

- consolidate live sessions into single archive DB (#36)

## v0.4.1 (2026-04-07)

### Fix

- archive live_state.db on startup so each session starts clean (#35)
- promote-live now copies model files to oco_dukascopy_candidate (#34)
- increase JForex connection timeout from 30s to 120s (#33)

## v0.4.0 (2026-04-07)

### Feat

- auto-detect last complete month as default eval_end_month (#31)

### Fix

- certify USDCAD for stage 14 and freeze 2026-03 governance (#32)

## v0.3.3 (2026-04-06)

### Fix

- block instead of static-fallback when rolling threshold unavailable (#30)
- quality gate, api test isolation, hermetic registry tests (#29)
- repair stage14 pre-monday certification contract (#28)

## v0.3.2 (2026-04-05)

### Fix

- certify historical no-go symbols in stage13
- harden stage13 jforex replay parity
- tighten stage13 runtime artifact completeness gate

## v0.3.1 (2026-04-05)

### Fix

- align stage12 stage13 defaults and prereqs

## v0.3.0 (2026-04-05)

### Feat

- normalize stage12 stage13 certification outputs
- add unified stage12 stage13 orchestrator
- add dukascopy testclient artifact producer
- replace OCO stop-limit pairs with bar-level barrier manager (#17)

### Fix

- forward models dir to stage13 replay runner
- derive stage13 lock dir from model month
- make unified certification runner executable
- repair stage13 dukascopy python gate (#24)

### Refactor

- port stage14 certification to execution lifecycle (#23)

## v0.2.12 (2026-03-31)

### Fix

- add repo root to sys.path in seed script
- offline threshold seed to unblock API during startup (#16)

## v0.2.11 (2026-03-31)

### Fix

- gate /health on lifespan completion to prevent startup race condition

## v0.2.10 (2026-03-31)

## v0.2.9 (2026-03-31)

### Fix

- accept Java surrogate camelCase variables in PredictRequest payload

## v0.2.8 (2026-03-30)

### Fix

- correct Makefile python one-liner syntax (#12)

## v0.2.7 (2026-03-29)

### Fix

- **ci**: checkout PR head ref for commit validation (#10)

## v0.2.6 (2026-03-29)

### Refactor

- drop misleading _2025 suffix from config names and output dirs (#9)

## v0.2.5 (2026-03-29)

### Fix

- freeze-oco predictions path fallback for base WFO directory

## v0.2.4 (2026-03-29)

### Fix

- **ci**: fix vulture dead code errors and relax xenon thresholds (#7)

## v0.2.3 (2026-03-29)

### Fix

- **ci**: fix lint, format, and test errors across codebase (#6)

## v0.2.2 (2026-03-29)

### Fix

- **ci**: correct train_cache tuple type annotation (#5)

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
