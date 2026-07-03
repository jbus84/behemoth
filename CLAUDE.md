# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Start Here

1. **`AGENTS.md`** — authoritative operator guide for this repo
2. **`UBIQUITOUS_LANGUAGE.md`** — canonical vocabulary (verdict values, column names, terms)
3. **`CONTEXT.md`** — architecture overview (for /improve-codebase-architecture)

---

## Essential

- All code work happens in **git worktrees** (see `AGENTS.md` section 1)
- Verdict values are canonical: `PASS`, `FAIL`, `GO`, `NO_GO` (no synonyms)
- The repo keeps two working surfaces: the **straddle logic** in `scripts/boostlss_xs/` and the **live JForex scaffold** in `src/behemoth/{api,runtime,core,risk}` + `src/jforex/`
- The FastAPI `/predict` endpoint is currently a **placeholder** returning empty predictions; wiring it to the boostlss_xs straddle logic is future work, not part of this repo's current state

---

## Quick Start

```bash
mise install && uv sync
uv run pytest -q tests/test_boostlss_xs_features.py tests/test_boostlss_xs_flagging.py \
  tests/test_boostlss_xs_meta_labeler.py tests/test_boostlss_xs_universe.py \
  tests/test_predict_placeholder.py tests/test_api_server_routes.py
make quality
```

Run the live JForex scaffold (requires broker creds in the shared root `.env`):

```bash
make jforex-live
```

See `AGENTS.md` for the full command reference, JForex runtime structure, and testing strategy.

---

## For Agents

Use skills in order: `/brainstorming` → `/superpowers:writing-plans` → `/superpowers:subagent-driven-development` → `/superpowers:verification-before-completion` → `/superpowers:requesting-code-review`.

For architecture analysis: `/improve-codebase-architecture` (reads `CONTEXT.md`).