# OCO Assumptions and Threat Model

## Objective
Make all major modeling, execution, and inference assumptions explicit, including invalidation conditions.

## Inputs
- Stage 1-10 artifacts and generated snapshots.

## Process
- Enumerate assumptions by layer.
- Map each assumption to a monitoring diagnostic.
- Define invalidation trigger and response.

## Exact Calculations
Not a calculation stage. Uses thresholds and diagnostics from Stage docs.

## Causality / Leakage Controls
- Any assumption that weakens time ordering is disallowed.
- Causality proofs rely on Stage 3 and leakage audit (`L01-L12`).

## Failure Modes
- Silent drift in execution behavior not captured by existing hard gates.
- Dependence on single-family behavior misread as universal edge.
- Overconfidence from partial metric interpretation.

## Interpretation Guide
Major assumptions:
- Data precision is sufficient for touch/overshoot analysis.
- Stop-limit replay approximates live fill mechanics.
- Cost regime remains within observed stress envelope.
- Reduced-core schedule remains causally selected month-by-month.

Invalidation examples:
- repeated high drift in Stage 4 execution diagnostics,
- logical/leakage gate failure,
- conservative LB turning negative.

## Validation Gates
- Assumptions are monitored; hard deployment control remains Stage 7/9 gates.

## Reproduction Commands
```bash
uv run python scripts/build_oco_strategy_bible.py \
  --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
```

## Traceability
- `docs/strategy_bible/generated/stage_01_snapshot.md`
- `docs/strategy_bible/generated/stage_04_snapshot.md`
- `docs/strategy_bible/generated/stage_08_snapshot.md`
- `docs/strategy_bible/generated/stage_09_snapshot.md`
