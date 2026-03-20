# Architecture & Walkthrough

The legacy stat-arb strategy has been fully deprecated. The active repository is now centered on the tick-based **Opportunity Cost Optimization (OCO)** research and governance pipeline.

## What Is Active

- Python remains the authoritative research, inference, and governance runtime.
- JForex is the active broker-adapter target.
- Generated artifacts and contract checks govern what is eligible for promotion.

## How The Pieces Fit Together

1. Raw ticks feed the tick-bar and velocity datasets.
2. OCO opportunity mining and monthly WFO produce ranked candidate flow.
3. Stop-limit realism, reduced-core selection, tick-exact verification, and robustness stages reduce that flow to governed deployable states.
4. Stage 9+ governance artifacts determine whether a symbol is actually promotion-ready.

## Recommended Reading Order

1. `docs/STRATEGY_MASTER_MANUAL.md`
2. `docs/strategy_bible/generated/pipeline_snapshot.md`
3. `docs/strategy_bible/` stage specs for the stage you are touching
4. `docs/strategy_bible/operator_runbook.md` for operational interpretation
5. `docs/analysis/index.md` for supporting evidence and diagnostics

## Practical Orientation

If you are changing strategy behavior, start with the strategy manual and the relevant stage spec. If you are checking current readiness, start with the generated pipeline snapshot, operator runbook, and analysis reports. Run `make docs` if you want the locally rendered site view.
