# Ubiquitous Language Propagation Design

- **Status:** Draft for review
- **Date:** 2026-04-25
- **Target branch:** `docs/ubiquitous-language-propagation`
- **Target commit:** `269d7e9923cde827b88349c4ae2f3011f94b176f`
- **Scope:** Propagate the approved ubiquitous language for the active OCO governance/live system across current docs and operator-facing text without changing runtime semantics.
- **Out of scope:** Runtime code changes, artifact regeneration beyond docs build, historical document rewrites for archival completeness, or changes to promotion/restart logic.

## Goal

Make the repository speak a consistent domain language for:

- governance versus live execution
- process verdicts versus symbol deployment decisions
- research/fitting versus selection/hardening versus certification versus promotion
- acceptable live-versus-governance variance versus true parity failures

The goal is not a cosmetic wording pass. The goal is to reduce operational ambiguity in the authoritative docs and active operator surfaces so the same term is not used for different concepts.

## Why This Matters

Recent work established explicit vocabulary for:

- `Governance Runtime` and `Live Runtime`
- `PASS` / `FAIL` versus `GO` / `NO_GO`
- `Monthly Recert`, `Deployment Period`, and `Promotion`
- `Restart Eligibility` outcomes
- `Runtime Variance`, `Tolerance Band`, `Material Drift`, and `Parity Breach`

Those terms currently exist in the glossary, but much of the repo still uses older or overloaded language such as:

- "month" for both deployment scope and certification result
- "failed" for both process invalidity and symbol non-deployment
- "training" for mining, fitting, filtering, certification, and promotion
- "live should match" when the intended concept is semantic parity
- `NOGO` or `NO-GO` instead of canonical `NO_GO`

If those terms remain inconsistent across authoritative docs and operator text, the glossary will not materially change behavior.

## Rollout Boundary

This rollout covers four layers.

### 1. Canonical Vocabulary Layer

Must be updated intentionally:

- `UBIQUITOUS_LANGUAGE.md`
- `docs/STRATEGY_MASTER_MANUAL.md`
- active strategy-bible prose that defines stage roles or system boundaries

### 2. Operator Layer

Must be updated where the wording affects human decisions:

- operator-facing reports under `docs/analysis/`
- summary docs that communicate readiness, deployability, or required actions
- operator-oriented script/help/status text that leaks ambiguous terminology into workflows

### 3. Certification/Governance Layer

Should be updated where wording conflicts with the approved terminology:

- stage design/spec docs in active use
- docs that blur `FAIL` with `NO_GO`
- docs that blur `Deployment Period` with process result
- docs that imply exact live/outcome matching instead of semantic parity

### 4. Historical/Long-Tail Layer

Should be updated selectively:

- broader `docs/` sweep for repeated high-value terminology conflicts
- historical docs are patched where wording is actively misleading for current work
- historical phrasing is not exhaustively rewritten if it reflects superseded context and does not create current ambiguity

## Recommended Approach

Use an authority-first plus opportunistic broad sweep.

1. Lock down canonical vocabulary in the glossary and master manual.
2. Normalize active operator-facing docs and status/report wording.
3. Sweep broader documentation for repeated ambiguous terms.
4. Leave purely historical material mostly intact unless current readers could easily draw the wrong conclusion from it.

This approach balances consistency and speed while avoiding a noisy repo-wide editorial rewrite.

## Edit Strategy

The propagation is split into four editorial passes:

### Pass A: Canonical Definitions

Update the source-of-truth docs so they explicitly define:

- `Governance Runtime` versus `Live Runtime`
- process verdicts versus symbol decisions
- stage boundaries across mining, WFO, hardening, certification, and promotion
- parity language based on semantic alignment rather than exact outcome equality

### Pass B: Operator Semantics

Update active reports and human-facing summaries so:

- process failures read as `FAIL`
- symbol exclusions read as `NO_GO`
- deployment scope uses `Deployment Period`
- promotion and live restart are not conflated

### Pass C: Certification Semantics

Update governance and certification docs so:

- Stage 12/13/14 language aligns with the glossary
- `PASS / NO_GO` semantics remain visible
- exact outcome "matching" language is replaced with semantic parity language where appropriate
- allowed tolerance language is expressed through `Runtime Variance`, `Tolerance Band`, `Material Drift`, and `Parity Breach`

### Pass D: Long-Tail Cleanup

Sweep the wider docs tree for repeated high-value fixes such as:

- `NOGO` -> `NO_GO`
- `NO-GO` -> `NO_GO` in canonical/current docs
- vague "training" references where a specific stage term is more accurate
- vague "month" references where `Deployment Period` or `Monthly Recert` is clearly intended

## Concrete Mapping Rules

Edits must be semantic rather than blind search-and-replace.

### Runtime Terms

- Use `Governance Runtime` for the authoritative offline staged process when contrasted with production behavior.
- Use `Live Runtime` for the production trading process.
- Use `Authoritative Runtime` when the text refers to the trusted execution context regardless of whether it is governance or live.

### Process and Deployment Terms

- Use `Certification Run` for one bounded certification execution.
- Use `Monthly Recert` for the official promotion-gating certification run.
- Use `Promotion` only for approving the certified artifact/lock set.
- Use `Deployment Period` when referring to the governed period the artifacts apply to.
- Keep literal train/test month language where the doc is discussing WFO chronology rather than deployment semantics.

### Verdict Terms

- Use `FAIL` only for process or evidence invalidity.
- Use `PASS` only for successful process/evidence validity.
- Use `GO` or `NO_GO` for symbol deployment decisions.
- Prefer `PASS / NO_GO` where both process and symbol semantics are relevant.
- Normalize current authoritative docs toward `NO_GO` rather than `NOGO` or `NO-GO`.

### Research and Stage Terms

- Use `Opportunity Mining` for Stage 2 hypothesis generation.
- Use `Monthly WFO`, `Model Fit`, and `Threshold Fit` for Stage 3 fitting/scoring.
- Use `Reduced-Core Rolling`, `Stop-Limit Realism`, `Tick-Exact Verification`, and `Robustness Filter` for later hardening stages.
- Use `Certification Run` or explicit stage names for Stage 12/13/14 validation.
- Avoid using "training" as a blanket term when a stage-specific term is available.

### Parity and Tolerance Terms

- Use `semantic parity` for the governance/live alignment target.
- Use `Runtime Variance` for acceptable in-contract live differences.
- Use `Tolerance Band` for explicit allowable ranges.
- Use `Material Drift` when certification compatibility is in doubt.
- Use `Parity Breach` for out-of-contract live behavior requiring investigation or blocking action.
- Avoid saying live and governance must "match" unless exact equality is actually required by the document.

## File Selection Heuristics

The implementation should prioritize files that meet at least one of these conditions:

- they are authoritative current-state docs
- they are read by operators to make deployment or investigation decisions
- they are commonly opened during governance, recert, promotion, or live restart work
- they define or summarize stage semantics for the active OCO system
- they contain repeated ambiguous terminology that directly conflicts with the glossary

Files should be skipped or lightly touched when:

- they are clearly historical and not operator-relevant
- rewriting would distort a historical record rather than clarify current meaning
- the ambiguous term is part of quoted/generated evidence not meant to be editorialized

## Verification

Verification for this rollout should include:

- `git diff --check`
- `uv run mkdocs build`
- targeted grep review for the most important term families:
  - `FAIL`, `NO_GO`, `NOGO`, `NO-GO`
  - `Governance Runtime`, `Live Runtime`
  - `Promotion`, `Monthly Recert`, `Deployment Period`
  - `Runtime Variance`, `Material Drift`, `Parity Breach`

Success means:

- canonical docs reflect the approved vocabulary
- active operator-facing docs no longer rely on the most harmful overloaded terms
- the broader docs tree shows materially reduced terminology drift
- no runtime behavior or certification semantics are changed by the wording updates alone

## Risks And Mitigations

### Risk: Over-editing historical material

Mitigation:

- patch historical docs selectively
- preserve archival phrasing when it does not create current confusion

### Risk: Turning the rollout into blind search-and-replace

Mitigation:

- make edits semantically
- inspect the usage context before replacing high-traffic terms such as "month" or "training"

### Risk: Introducing contradictions between glossary and manual

Mitigation:

- update canonical docs first
- use the glossary as the reference point for subsequent edits

### Risk: Accidentally changing operator meaning

Mitigation:

- prefer minimal text changes that improve precision
- avoid changing thresholds, statuses, or policy semantics

## Acceptance Criteria

This design is acceptable when:

1. The rollout is performed in a dedicated worktree and branch.
2. Canonical docs adopt the approved vocabulary.
3. Operator-facing docs and active governance docs stop conflating process `FAIL` with symbol `NO_GO`.
4. Governance/live comparison language uses semantic parity terminology rather than exact-match shorthand.
5. The broader docs sweep reduces terminology drift without rewriting historical material indiscriminately.
6. `mkdocs build` still passes after the edits.
