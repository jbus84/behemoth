# Graph Report - /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry  (2026-04-20)

## Corpus Check
- 269 files · ~895,578 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3429 nodes · 10323 edges · 103 communities detected
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 4229 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]

## God Nodes (most connected - your core abstractions)
1. `ModelFeatures` - 221 edges
2. `StateManager` - 204 edges
3. `IncomingTickBar` - 199 edges
4. `IncomingTick` - 180 edges
5. `FeatureConfig` - 127 edges
6. `OcoPrediction` - 119 edges
7. `BarrierManager` - 119 edges
8. `TickAggregator` - 113 edges
9. `BarrierAction` - 99 edges
10. `run()` - 97 edges

## Surprising Connections (you probably didn't know these)
- `TDD tests for the candidate registry.` --uses--> `CandidateRegistry`  [INFERRED]
  /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/tests/test_registry.py → /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/src/behemoth/core/registry.py
- `Write a self-consistent lock file + fake model artifacts for one symbol.` --uses--> `CandidateRegistry`  [INFERRED]
  /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/tests/test_registry.py → /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/src/behemoth/core/registry.py
- `Self-consistent registry with EURUSD and GBPUSD, no real artifacts needed.` --uses--> `CandidateRegistry`  [INFERRED]
  /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/tests/test_registry.py → /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/src/behemoth/core/registry.py
- `test_build_symbol_aggregates_base_bars_from_files()` --calls--> `_build_symbol()`  [INFERRED]
  /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/tests/test_tick_aggregator.py → /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/scripts/build_global_tick_bars.py
- `test_verify_cert_requires_matching_month_status()` --calls--> `_verify_cert()`  [INFERRED]
  /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/tests/test_run_promote_live.py → /Users/danielfisher/repositories/behemoth/.worktrees/fix-usdjpy-bridge-retry/scripts/run_promote_live.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (300): AccountRiskProfile, BarrierManager, Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id, Expire active scans that predate the side-aware signal close columns.          L, Check if candidate has an active (SCANNING or HOLDING) scan., Retrieve a scan record by ID. Used for testing and diagnostics., Evaluate a completed bar against all active scans for this symbol.          Call, Move a scan from SCANNING to HOLDING. (+292 more)

### Community 1 - "Community 1"
Cohesion: 0.01
Nodes (60): isCloseMarket(), isOpenMarket(), BehemothJForexStrategy, BehemothStrategyCore, SymbolRuntimeState, BehemothStrategyCoreTest, BrokerBridgeLoader, BrokerBridgeLoaderTest (+52 more)

### Community 2 - "Community 2"
Cohesion: 0.01
Nodes (322): _add_check(), _latest(), main(), _parse_symbols(), _pip_size(), _resolve_source_path(), _robust_extreme_rate(), run() (+314 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (204): _(), a(), aa(), Ae(), ai(), an(), Ao(), ar() (+196 more)

### Community 4 - "Community 4"
Cohesion: 0.02
Nodes (120): build_all_1m_chunked(), main(), _extract_symbol(), main(), _parse_args(), _tick_files(), _canonical_candidate_uid(), _default_paths() (+112 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (136): _band(), _dt_utc(), _load_cap_pips(), main(), _parse_symbols(), run(), _summarize_symbol(), _table() (+128 more)

### Community 6 - "Community 6"
Cohesion: 0.03
Nodes (93): isConnected(), JForexLiveRunner, LiveClient, Sleeper, startStrategy(), FakeClient, JForexLiveRunnerTest, NoOpStrategy (+85 more)

### Community 7 - "Community 7"
Cohesion: 0.03
Nodes (82): HistoricalLockEntry, load(), Historical governance lock registry for month-aligned backtest inference.  Loads, Month-aware candidate/model registry for historical replay., HistoricalWarmupLoader, CandidateSpec, from_row(), load() (+74 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (99): run(), test_phase1_runs_and_produces_signal_section(), test_build_docs_catalog_outputs_manifest_and_index(), test_build_system_reference_docs_writes_all_pages_and_status(), test_build_operator_action_report_accepts_extra_metrics(), test_build_operator_action_report_outputs_status_and_docs(), test_build_run_delta_dashboard_outputs_changes(), _write_snap() (+91 more)

### Community 9 - "Community 9"
Cohesion: 0.04
Nodes (86): AccountRiskAllocator, AccountRiskBuffers, AccountRiskCostGate, evaluate_account_risk_limits(), evaluate_trade_guard(), evaluate_trade_risk_guard(), load_account_risk_profile(), _normalize_trade_cost_gate_mode() (+78 more)

### Community 10 - "Community 10"
Cohesion: 0.03
Nodes (103): _parse_barrier_from_state(), audit_symbol(), _default_configs(), _dt_utc(), _load_artifacts(), main(), _month_to_int(), _parse_symbols() (+95 more)

### Community 11 - "Community 11"
Cohesion: 0.04
Nodes (95): _apply_reduced_core_schedule_filter(), _bootstrap_lb95(), _build_state_key_from_candidate_uid(), main(), _max_survivable_cost_lb95_trade(), _normal_pvalue_mean_gt0(), _p_adjust_bonferroni(), _p_adjust_fdr_bh() (+87 more)

### Community 12 - "Community 12"
Cohesion: 0.04
Nodes (95): _cap_sweep(), _first_cross_overshoot_month(), main(), _oco_touch_arrays(), _parse_candidate_uid(), _pip_size(), _rebuild_touch_events(), run_symbol() (+87 more)

### Community 13 - "Community 13"
Cohesion: 0.05
Nodes (66): JForexConnectionTest, _derive_model_month(), main(), _materialize_bundle_models(), _repo_root(), _run_step(), _validate_model_month(), _bundle_models_dir() (+58 more)

### Community 14 - "Community 14"
Cohesion: 0.05
Nodes (68): _build_bars_from_ticks(), _build_report(), _build_report_with_skips(), _candidate_regime_name(), _latest_tick_files(), _load_model(), _load_states(), _load_thresholds() (+60 more)

### Community 15 - "Community 15"
Cohesion: 0.06
Nodes (56): canonical_runtime_events_path(), compare_outcomes(), _in_eval_window(), load_historical_lock_status(), load_runtime_events(), load_runtime_events_frame(), load_state_universe_uids(), main() (+48 more)

### Community 16 - "Community 16"
Cohesion: 0.08
Nodes (47): find_first_market_gap(), _friday_close_for_week(), get_fetchable_end(), get_missing_months(), get_parquet_info(), get_session_bounds_utc(), _handle_existing_lock(), is_expected_weekend_gap() (+39 more)

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (42): _as_bool(), DukascopyTestClientArtifactOutputs, generate_dukascopy_testclient_artifacts(), _normalise_symbol(), _now_utc(), _pick_value(), _as_mapping(), _bool_from_summary() (+34 more)

### Community 18 - "Community 18"
Cohesion: 0.09
Nodes (38): _build_manifest(), _default_paths(), _git_cmd(), _git_info(), _latest_model_pair(), _load_yaml(), main(), _model_date_key() (+30 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (34): _aggregate_overall(), analyze_symbol_month(), _apply_daily_lag(), _bar_summary(), _build_tick_bars(), _covered_days(), _dt_utc(), _duplicate_ratio() (+26 more)

### Community 20 - "Community 20"
Cohesion: 0.13
Nodes (27): audit_symbol(), _bootstrap_lb95(), _default_configs(), _dt_utc(), _load_detail(), _load_selected_predictions(), main(), _parse_symbols() (+19 more)

### Community 21 - "Community 21"
Cohesion: 0.19
Nodes (30): test_build_stage13_artifacts_emits_nogo_for_non_deployable_symbols(), test_build_stage13_artifacts_ignores_local_surrogate_summaries(), test_build_stage13_artifacts_keeps_primary_summary_contract_minimal(), test_build_stage13_artifacts_limits_outputs_to_requested_symbols(), test_build_stage13_artifacts_prefers_explicit_replay_over_fallback_summaries(), test_build_stage13_artifacts_rejects_header_only_runtime_events_artifact(), test_build_stage13_artifacts_reports_missing_inputs_with_expected_source_paths(), test_build_stage13_artifacts_reports_runtime_artifact_as_current_dukascopy_surface() (+22 more)

### Community 22 - "Community 22"
Cohesion: 0.28
Nodes (30): _(), a(), b(), c(), d(), E(), er(), f() (+22 more)

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (22): _check(), failed_checks(), HistoricalGovernanceCheck, Validation helpers for month-scoped historical governance locks., _sha256(), _sha256_cached(), summarize_failures(), validate_historical_governance() (+14 more)

### Community 24 - "Community 24"
Cohesion: 0.2
Nodes (15): _best_cap_for_symbol(), _dt_utc(), main(), _normal_draws(), _num_series(), _parse_symbols(), _prepare_detail(), run_for_symbol() (+7 more)

### Community 25 - "Community 25"
Cohesion: 0.24
Nodes (14): _build_canonical_map(), ClassifiedDoc, _classify_doc(), _doc_link(), _human_title(), _infer_stage(), _infer_symbol(), main() (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.23
Nodes (14): _(), a(), c(), d(), f(), i(), l(), m() (+6 more)

### Community 27 - "Community 27"
Cohesion: 0.21
Nodes (13): _(), a(), c(), e(), f(), i(), k(), l() (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.21
Nodes (13): a(), b(), c(), d(), e(), h(), i(), l() (+5 more)

### Community 29 - "Community 29"
Cohesion: 0.19
Nodes (14): a(), c(), d(), e(), f(), l(), m(), n() (+6 more)

### Community 30 - "Community 30"
Cohesion: 0.28
Nodes (13): a(), b(), c(), f(), i(), k(), l(), m() (+5 more)

### Community 31 - "Community 31"
Cohesion: 0.25
Nodes (12): audit_symbol(), _bootstrap_lb95(), _check_overlap_divergence(), _default_configs(), _dt_utc_mixed(), _load_selected_events(), main(), _parse_state_id() (+4 more)

### Community 32 - "Community 32"
Cohesion: 0.22
Nodes (13): _candidate_audit_section(), _format_report(), _load_con(), _magnitude_analysis_section(), main(), Report live pnl_pips distribution per symbol.      OCO uses from_touch hold mode, Check which candidate_uids are actually firing in live.      All live trades sho, Run all diagnostic checks and return structured report dict. (+5 more)

### Community 33 - "Community 33"
Cohesion: 0.21
Nodes (7): _(), i(), l(), n(), s(), t(), u()

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (11): _build_snapshot_tables(), _ensure_page_shell(), _fmt(), _generated_block(), _inject_block(), _latest_by_symbol(), main(), _read_csv() (+3 more)

### Community 35 - "Community 35"
Cohesion: 0.33
Nodes (10): a(), c(), f(), l(), m(), n(), o(), r() (+2 more)

### Community 36 - "Community 36"
Cohesion: 0.33
Nodes (10): a(), c(), d(), e(), l(), m(), n(), o() (+2 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (2): NoopExecutionPort, RecordingExecutionPort

### Community 38 - "Community 38"
Cohesion: 0.33
Nodes (7): a(), c(), e(), i(), s(), t(), u()

### Community 39 - "Community 39"
Cohesion: 0.29
Nodes (6): When day_str <= model_valid_through, the threshold should not block., When model_valid_through is empty, no expiry check applies., When day_str > model_valid_through, the threshold should block., test_model_valid_through_allows_valid_day(), test_model_valid_through_blocks_expired_models(), test_model_valid_through_empty_does_not_block()

### Community 40 - "Community 40"
Cohesion: 0.29
Nodes (1): LiveReadinessMetrics

### Community 41 - "Community 41"
Cohesion: 0.4
Nodes (2): s(), t()

### Community 42 - "Community 42"
Cohesion: 0.33
Nodes (1): ExecutionPort

### Community 43 - "Community 43"
Cohesion: 0.7
Nodes (4): e(), n(), r(), t()

### Community 44 - "Community 44"
Cohesion: 0.4
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 0.83
Nodes (3): generate_configs(), main(), _rewrite_content()

### Community 47 - "Community 47"
Cohesion: 0.5
Nodes (3): dashboard(), Lightweight monitoring dashboard for the Behemoth OCO strategy.  Served as a Fas, Serve the single-page monitoring dashboard.

### Community 48 - "Community 48"
Cohesion: 0.5
Nodes (1): BrokerHistoryPort

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (0): 

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (0): 

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (0): 

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Build from a state_universe row in the live lock JSON.

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Load exactly from per-symbol *_oco_live_lock.json files.

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Symbols that have at least one registered candidate.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (0): 

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (0): 

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (0): 

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (0): 

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (0): 

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (0): 

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (0): 

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (0): 

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (0): 

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (0): 

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (0): 

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (0): 

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (0): 

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (0): 

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (0): 

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (0): 

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (0): 

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (0): 

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (0): 

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (0): 

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (0): 

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (0): 

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (0): 

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (0): 

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (0): 

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (0): 

### Community 101 - "Community 101"
Cohesion: 1.0
Nodes (0): 

### Community 102 - "Community 102"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **144 isolated node(s):** `Write lock files and index for multiple symbols.      If *break_symbol* is set,`, `When required_symbols is set, broken locks for other symbols are ignored.`, `Stage 14 must include jforex_outcome_parity_pass as a check.`, `Stage 14 must include local_jforex_surrogate_pass as a prerequisite check.`, `Stage 14 is green only when all 7 checks pass.` (+139 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 50`** (2 nodes): `TinySegmenter()`, `tinyseg.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `conftest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `check_cols_parquet.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `build_repro_manifest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `lunr.he.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `lunr.hi.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `lunr.zh.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `lunr.ko.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `lunr.ja.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `lunr.te.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `lunr.stemmer.support.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `lunr.hy.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `lunr.vi.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `lunr.ta.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `lunr.ar.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `lunr.th.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `lunr.kn.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `lunr.sa.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `lunr.multi.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `lunr.jp.min.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Build from a state_universe row in the live lock JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Load exactly from per-symbol *_oco_live_lock.json files.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Symbols that have at least one registered candidate.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `MarketOrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `OrderEvent.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `OrderHandle.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `OrderEventType.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `RuntimeTick.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `OrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `TradeOpenRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `BackfillRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `ActiveTradePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `PredictRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `AccountSnapshotRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `PredictResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `TradeTouchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `TickIngestResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `TickBatchResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `ApiAckResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `FeedStatusSymbolPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `TickBatchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `IncomingTickPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `FeedStatusResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `TradeUpdateRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `SymbolReadinessState.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 101`** (1 nodes): `LiveReadinessSnapshot.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 102`** (1 nodes): `PredictionDecision.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StateManager` connect `Community 0` to `Community 9`, `Community 2`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `run()` connect `Community 8` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 16`, `Community 17`, `Community 18`, `Community 19`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `range()` connect `Community 11` to `Community 0`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 12`, `Community 14`, `Community 15`, `Community 19`, `Community 20`, `Community 31`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 545 inferred relationships involving `str` (e.g. with `test_build_artifacts_treats_zero_lock_idle_windows_as_execution_pass()` and `test_build_artifacts_falls_back_to_outcome_locked_count_for_zero_lock_windows()`) actually correct?**
  _`str` has 545 INFERRED edges - model-reasoned connections that need verification._
- **Are the 217 inferred relationships involving `ModelFeatures` (e.g. with `TestHealthEndpoint` and `TestMetricsEndpoint`) actually correct?**
  _`ModelFeatures` has 217 INFERRED edges - model-reasoned connections that need verification._
- **Are the 155 inferred relationships involving `StateManager` (e.g. with `TestHealthEndpoint` and `TestMetricsEndpoint`) actually correct?**
  _`StateManager` has 155 INFERRED edges - model-reasoned connections that need verification._
- **Are the 196 inferred relationships involving `IncomingTickBar` (e.g. with `TestHealthEndpoint` and `TestMetricsEndpoint`) actually correct?**
  _`IncomingTickBar` has 196 INFERRED edges - model-reasoned connections that need verification._