# 2026-05 Multi-Family Governance Trial — Findings & Pause Note

**Date:** 2026-05-28
**Branch:** `codex/multi-family-trial-2026-05`
**Status:** Paused after Stage 6 (Task 8) to consolidate findings.

---

## Purpose

Execute the full staged governance pipeline (Stages 2–9) for all 11 mining families across the 6-symbol universe (EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD) for model month 2026-05, producing a validated freeze bundle.

## Outcome

The trial did **not** reach a freeze. Its real value was diagnostic: a fresh multi-family run surfaced **four pre-existing pipeline defects** that the reused EURUSD/GBPUSD artifacts had masked. Three are fixed (PRs open); the fourth is characterised below. All four are instances of the **same root cause**: the pipeline organises artifacts *by library* but addresses them *by family* in scattered, inconsistent ways, with no single declared contract — exactly what ADR 0004 targets.

---

## Stages completed

| Stage | Task | Result |
|---|---|---|
| 2 mining | 4 | ✅ 4 new symbols mined; 7 library candidate files each, 10 families represented (no_touch empty) |
| 3 WFO | 5 | ✅ 66/66 prediction parquets (62 real, 4 legitimately empty) after the cache-key fix |
| 4 stop-limit | 6 | ✅ barrier-exit families; overshoot/cap stats per symbol (real data where exec-selected entries exist) |
| 5 reduced-core | 7 | ✅ 66/66 schedules after the config fix. **Verdict ladder: 21 PASS (non-empty), 45 FAIL (empty/NO_TRADE)** |
| 6 tick-exact | 8 | ⚠️ ran 21 PASS combos EXIT=0, but per-family verdicts collide by library (see Defect 4) |
| 9 freeze | 11 | not reached |

The 21 Stage-5 PASS combos are all directional-library families (directional 5, directional_inverse 6, directional_run 6, double_touch 2, pullback 2). All OCO, no_touch, and cross-symbol (symbol × family) pairs produced empty Stage-5 schedules this month — a legitimate "no profitable states" outcome, not an error.

---

## The four defects

### 1. WFO `_precompute` cache key unhashable — FIXED (PR #265)
`run_tick_opportunity_monthly_wfo.py` injects `params["horizons"]` (a list). Five families key their `_precompute` cache on `tuple(sorted(params.items()))`, which can't hash a list → `TypeError: unhashable type: 'list'`, crashing Stage 3 WFO for oco_first_touch/oco_asymmetric/double_touch/pullback/no_touch. Regression from `ea3a5b77`. Fix: `_freeze_params()` helper + regression test.

### 2. Mining summary + candidate by-library discoverability — ADR (PR #264)
`_build_summary` (run_tick_opportunity_mining.py:1502) only reports 3 of 7 libraries, so `candidate_summary.csv` looks like only directional+oco were mined. Candidate CSVs are per-library (`directional_candidates.csv` holds 5 families), non-obvious. Captured in ADR 0004 as motivating evidence; `_build_summary` flagged as a standalone follow-up fix.

### 3. Symbol-local reduced-core config generation — FIXED (PR #266)
New-symbol reduced-core configs were generated missing `barrier_keep: ''` (46 configs) and with family-named `candidate_csv` instead of the library file (16 configs), crashing Stage 5 with `cannot parse barrier` / FileNotFound. The EURUSD/GBPUSD configs were correct; the rest were aligned to that template. The guard test `test_symbol_local_family_configs.py` was strengthened to enforce both, so the onboarding contract can't regress.

### 4. Tick-exact output collides by library — OPEN
`verify_tick_exact_shortlist.py` writes `<SYMBOL>_<library>_tick_exact_summary.csv` to `reduced_core/`. The 5 directional-library families overwrite each other per symbol, so per-family Stage-6 verdicts (`overall_pass`) are lost — only the last family run per symbol survives. Surviving verdicts are mixed (some symbols 1.0 exact-match PASS, others 0.0 FAIL), but cannot be attributed to a family. **Not yet fixed.** Options: make tick-exact output family-qualified (code fix), or capture per-family output in-workflow (rename immediately after each run). Belongs with ADR 0004.

---

## Recommendation

The pipeline's per-family support is broken in at least four places, all the same root cause. Rather than continue patching stage-by-stage, prioritise the **ADR 0004 stage-contract refactor** (single declared family↔library↔artifact-name contract, imported by producers/consumers, enforced by a drift test) before attempting another full multi-family freeze. The three merged-pending fixes (#264/#265/#266) plus Defect 4 should fold into that work.

A narrower alternative: a multi-family freeze restricted to the families that already work cleanly end-to-end (those producing non-empty Stage-5 schedules with attributable Stage-6 verdicts) — but Defect 4 currently prevents trustworthy Stage-6 attribution even for those.

---

## Resumption state

- **Worktree:** `.worktrees/multi-family-trial-2026-05` (branch `codex/multi-family-trial-2026-05`), commits through `f69abca0` plus cherry-picked fixes for #265/#266.
- **Artifacts on disk (gitignored):** Stage 2–6 outputs under `data/analysis/tick_opportunity_mining/`. Stage-5 schedules canonicalised (oco→oco_first_touch, directional from `directional_rolling/`).
- **Bookkeeping:** `tmp/2026-05-trial/` holds per-stage drivers, result TSVs, and logs.
- **Open PRs:** #264 (ADR 0004), #265 (WFO cache-key fix), #266 (reduced-core config fix). Merging these lets the trial branch rebase off cherry-picks.
- **To resume:** fix Defect 4, then re-run Stage 6 with per-family capture, build the verdict ladder (Task 9), regenerate shared reports (Task 10), freeze (Task 11), validate (Task 12), PR (Task 13).
