# Behemoth

A trading-system repo holding two working surfaces: a **straddle meta-labeling** research logic and a **live JForex execution scaffold**.

## Straddle logic — `scripts/boostlss_xs/`

A standalone BoostLSS-based cross-symbol straddle meta-labeler:

- `features.py` — tick-bar feature computation
- `flagging.py` — channel/straddle flagging
- `meta_labeler.py` / `meta_label_v2.py` — meta-labeling (side + size)
- `model.py` — BoostLSS walk-forward model (`BoostLssWFO`)
- `universe.py` — symbol universe loading
- `run.py`, `reversion_straddle.py`, `meta_label_straddle.py`, `causal_validation.py` — runners and validation

It is self-contained, writes outputs to `/tmp`, and is exercised by `tests/test_boostlss_xs_*.py`. It is not imported by the live runtime.

## Live JForex scaffold — `src/behemoth/{api,runtime,core,risk}` + `src/jforex/`

A FastAPI runtime + Dukascopy JForex (Kotlin/Gradle) broker adapter:

- `src/behemoth/api/server.py` — FastAPI app (`/health`, `/status`, `/metrics`, `/ticks`, `/bars`, `/trades`, `/risk/account*`, `/checkpoint`, `/open-summary`)
- `src/behemoth/api/predict_orchestrator.py` — prediction orchestrator
- `src/behemoth/runtime/` — state (DuckDB), tick aggregation, bar building
- `src/behemoth/core/` — schemas, features, feature engine/pipeline/validator, regime + horizon contracts
- `src/behemoth/risk/` — account risk allocation, barrier manager
- `src/jforex/` — Kotlin/Gradle broker adapter (`BehemothJForexStrategy`, `JForexLiveRunner`, local surrogate + tester runners)

The `/predict` endpoint is currently a **placeholder** returning empty predictions (`predictions: []`, `actions: []`). Wiring it to the boostlss_xs straddle logic is future work. Launch live with `make jforex-live` (requires broker creds in the shared root `.env`).

## Active symbol universe

`EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`

## Commands

```bash
make test          # pytest suite
make test-java     # JForex (Kotlin) tests
make quality       # ty + ruff + vulture + smellcheck + radon + xenon
make jforex-live   # launch the live scaffold
```

## Further reading

- `AGENTS.md` — operator guide (JForex structure, commands, testing)
- `UBIQUITOUS_LANGUAGE.md` — canonical vocabulary and verdict values
- `CONTEXT.md` — architecture overview
- [ADR 0005 — Dispersion Family Research Directions](adr/0005-dispersion-family-research-directions.md)

## Notes

- All code work happens in git worktrees; merge via PR, never commit directly to `main`.
- Verdict values are canonical: `PASS`, `FAIL`, `GO`, `NO_GO`.
- The previous OCO governance / tick-opportunity-mining / certification pipeline has been removed; GitHub history retains it.