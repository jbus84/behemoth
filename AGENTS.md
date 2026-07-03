# AGENTS Guide (Repo Onboarding)

This file is the fastest path to becoming productive in this repo.

## 0) Ubiquitous Language

This project has a canonical vocabulary defined in `UBIQUITOUS_LANGUAGE.md`. Before using any domain term, verdict value, or column name, read it and use only the canonical terms.

Key deployment decision terms:
- `PASS` — process completed correctly and produced valid evidence
- `FAIL` — process or evidence is invalid
- `GO` — symbol is eligible for deployment
- `NO_GO` — symbol intentionally not deployed; process did not fail

## 1) What Is Actually Active

The repo keeps two working surfaces:

- **Straddle logic** in `scripts/boostlss_xs/` — a standalone BoostLSS cross-symbol straddle meta-labeler (features, flagging, meta-labeler, model, universe, walk-forward runner). Self-contained; writes to `/tmp`; not imported by the live runtime.
- **Live JForex scaffold** in `src/behemoth/{api,runtime,core,risk}` + `src/jforex/` + `scripts/run_jforex_live.py` — a FastAPI runtime + Dukascopy JForex broker adapter. The `/predict` endpoint is a **placeholder** returning empty predictions pending wiring to the straddle logic.

The previous OCO governance / tick-opportunity-mining / stage certification pipeline has been removed; GitHub history retains it.

### Branch truth

- All code work happens in **git worktrees**; merge via PR, never commit directly to `main`.
- Specs and plans must name the target branch and target commit, and execution must run from a worktree created from that target branch at that commit (or a descendant).
- Branch-semantic drift at final verification is a hard stop, not a docs-patching opportunity.

## 2) Active Symbol Universe

- `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`

## 3) Core Data Paths

- Raw ticks (canonical, external local machine): `/Users/danielfisher/Desktop/dukascopy_ticks/<SYMBOL>/<SYMBOL>_YYYYMM_ticks.parquet`
- Tick bars: `data/global_tickbars/<SYMBOL>_{100,1000,2000}tick.parquet`
- Tick bars used by the straddle logic are loaded from parquet by `scripts/boostlss_xs/universe.py`.

Canonical raw tick parquet schema: `timestamp` (UTC), `bid`, `ask`, `mid`, `spread`, `log_return`.

## 4) JForex Runtime Structure

Gradle module: `src/jforex/`

- Main strategy entrypoint: `com.behemoth.jforex.BehemothJForexStrategy`
- Tester runner: `com.behemoth.jforex.JForexTesterRunner`
- Live runner: `com.behemoth.jforex.JForexLiveRunner`
- Local surrogate runner: `com.behemoth.jforex.LocalJForexTesterRunner`
- JForex Prometheus endpoint: `127.0.0.1:9464/metrics`
- Local surrogate Prometheus endpoint default: `127.0.0.1:9465/metrics`

### Thread Model

- **Strategy thread** (Dukascopy callback): enqueues `TickEvent` to `SymbolWorker` and returns immediately. `onTick` duration target: < 1 µs.
- **Worker thread** (one per symbol, `behemoth-worker-<SYMBOL>`): drains queue, builds bars, calls `/ticks` and `/predict`, executes orders inline.
- **Tester determinism**: `LocalJForexTesterRunner` and `JForexTesterRunner` call `symbolWorker.drain()` after each tick injection.
- **No disk-backed queue**: `LinkedTransferQueue` is unbounded in-memory. Queue-age alert fires if the worker falls behind.

## 5) Commands

```bash
mise install && uv sync        # setup
make test                      # pytest suite
make test-java                 # gradle :jforex-adapter:test
make quality                   # ty + ruff + vulture + smellcheck + radon + xenon
make jforex-live               # launch live scaffold (FastAPI + JForex runner; needs broker creds)
make docs                      # serve mkdocs site at 127.0.0.1:8001
make docs-build                # build mkdocs site
make pr                        # push + open a PR
```

`make jforex-live` runs `scripts/run_jforex_live.py`, which starts the FastAPI server (uvicorn `src.behemoth.api.server:app`), polls `/health`, then starts the JForex live runner (`gradle :jforex-adapter:runJForexLive`), and monitors/shuts down both. JForex-dependent commands must source the shared root `.env` before execution; do not commit `.envrc`.

## 6) Tooling

- Python: `uv` (toolchain pinned via `mise.toml`)
- Java/JForex: Gradle project in `src/jforex`
- Quality gate: `make quality` (run before any PR, not just pytest)

```bash
mise install
uv sync
gradle :jforex-adapter:test
```

Java conventions:
- Keep broker adapter code under `src/jforex/src/main/java/com/behemoth/jforex/`
- Use immutable records for wire/domain payloads where practical
- Put JUnit 5 tests under `src/jforex/src/test/java/`
- Keep JForex-specific code thin; Python remains the decision engine
- Shared Java strategy logic lives below the runtime shim so real JForex and local surrogate runs exercise the same core
- `SymbolWorker` owns per-symbol tick batching and HTTP I/O; cross-symbol shared state lives in `BehemothStrategyCore` and is accessed via `SymbolWorker.ActionCallbacks`

## 7) Common Pitfalls

- Some scripts still encode assumptions around historical symbol universes. If adding/removing symbols, check for hardcoded symbol sets.
- `uv run` can hit sandbox cache permission issues in restricted execution; rerun with elevated permissions when needed.
- Do not delete or rewrite user data under `/Users/danielfisher/Desktop/dukascopy_ticks` or `/Users/danielfisher/Desktop/tick` unless explicitly asked.
- "code/tests pass in worktree" and "live runs correctly against the broker" are different claims; do not collapse them.

## 8) Definition of Done for Agent Changes

Before finalizing substantial changes:

1. Relevant tests pass (`make test`, and `make test-java` if JForex code changed).
2. `make quality` is green (run before any PR, not just pytest).
3. `make docs-build` succeeds if docs changed.
4. `git status` is clean after commit, and changes are pushed if requested.