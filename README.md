# Behemoth

A trading-system repo holding two working surfaces: a **straddle meta-labeling** research logic and a **live JForex execution scaffold**.

## What This Repo Keeps

1. **Straddle logic** — `scripts/boostlss_xs/`
   A standalone BoostLSS-based cross-symbol straddle meta-labeler (features, flagging, meta-labeler, model, universe, walk-forward runner). It writes outputs to `/tmp` and is exercised by `tests/test_boostlss_xs_*.py`. It is not imported by the live runtime.

2. **Live JForex scaffold** — `src/behemoth/{api,runtime,core,risk}` + `src/jforex/` + `scripts/run_jforex_live.py`
   A FastAPI runtime + Dukascopy JForex (Kotlin/Gradle) broker adapter. The `/predict` endpoint is currently a **placeholder** that returns empty predictions (`predictions: []`, `actions: []`); wiring it to the boostlss_xs straddle logic is future work. The runtime scaffold (state, barriers, account risk, tick ingestion, Prometheus metrics) is intact and runs live via `make jforex-live`.

## Active Symbol Universe

- `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`

## Setup

```bash
mise install && uv sync
```

## Common Commands

```bash
make test          # run the pytest suite
make test-java     # run the JForex (Kotlin) tests
make quality       # full quality gate: ty + ruff + vulture + smellcheck + radon + xenon
make jforex-live   # launch the live JForex scaffold (FastAPI + JForex runner; needs broker creds)
make docs          # serve the mkdocs site locally
make docs-build    # build the mkdocs site
```

## Docs

- `AGENTS.md` — operator guide (JForex structure, commands, testing)
- `UBIQUITOUS_LANGUAGE.md` — canonical vocabulary and verdict values
- `CONTEXT.md` — architecture overview
- `docs/` — mkdocs site (landing page + ADR 0005)

## Notes

- All code work happens in git worktrees; merge via PR, never commit directly to `main`.
- Verdict values are canonical: `PASS`, `FAIL`, `GO`, `NO_GO`.
- The previous OCO governance / tick-opportunity-mining / certification pipeline has been removed; GitHub history retains it.