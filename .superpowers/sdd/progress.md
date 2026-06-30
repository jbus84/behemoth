# BoostLSS XS Anomaly Detection + Meta-Labeler — SDD progress

Base: ff6a910096e704cb67dc543f2a2fda9ac5dbb1ed
Plan: docs/superpowers/plans/2026-06-29-boostlss-xs-anomaly-meta-labeler.md

- Task 1: complete (commits ff6a9100..9b5f6b46, review clean; minor: tests lack module-scoped fixture + no CI skip guard)
- Task 2: complete (commit bef1fe60, review clean; note: tail_count_100 uses mad20[i] as threshold across window — causal but current-vol-standard interpretation; consider mad20[j] if feature proves uninformative)
- Task 3: complete (commits e16067bc..4689d5c9, review clean; fixed: dead _SYMBOL_CODES dict removed, xs_rank NaN guard added)
- Task 4: complete (commits a57b9087..e44ccc3d, review clean; StudentTLSS→GaussianLSS substitution; fold split is index-based not timestamp-based)
- Task 5: complete (commit d1861953, review clean; zero-MAD guard added; GaussianLSS no-nu path returns NaN)
- Task 6: complete (commit 5c37dd94, review clean; datetime64 compat fix; NaN train rows correctly propagated)
- Task 7: complete (commits b07ca056..323b3747, smoke test verified 2100 trade rows; fixed: meta_labeler KeyError on subset horizons + NaN-poisoned valid_mask)
- Final review fixes: complete (commits 4f091349..HEAD; C1 time-sort, C2 per-symbol targets, I1 per-fold thresholds, I2 embargo, dead StudentTLSS branch removed; 26 tests pass)
