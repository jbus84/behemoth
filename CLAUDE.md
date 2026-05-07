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
- Stage 12–14 certification runs from **root checkout only** (requires broker creds + local artifacts)
- Verdict values are canonical: `PASS`, `FAIL`, `GO`, `NO_GO` (no synonyms)
- `data/analysis/tick_opportunity_mining/` is governance-locked truth; regenerate via `make retrain-all`

---

## Quick Start

```bash
mise install && uv sync
uv run pytest -q tests/test_oco_docs_contract.py tests/test_tick_opportunity_mining.py
make monthly-recert MODEL_MONTH=2026-02
```

See `AGENTS.md` sections 4–6 for full command reference, scripts, and testing strategy.

---

## For Agents

Use skills in order: `/brainstorming` → `/superpowers:writing-plans` → `/superpowers:subagent-driven-development` → `/superpowers:verification-before-completion` → `/superpowers:requesting-code-review`.

For architecture analysis: `/improve-codebase-architecture` (reads `CONTEXT.md`).
