# Behemoth Trading System

This site documents the **production rule‑based MOM strategy** and its API, risk controls, and validation. It is designed to be the single source of truth for how the system behaves in backtests and production.

**Key properties**
- **No ML inference**: the strategy is rule‑based (Kalman + Z‑score + guardrail).
- **Single‑leg execution**: we trade the active leg, not a hedged pair.
- **Hard risk gates**: max daily loss and max drawdown enforced at runtime.

**Where to start**
- `STRATEGY_MASTER_MANUAL.md` for the full system definition.
- `architecture.md` for system flow and major components.
- `api.md` for endpoints and state model.
- `risk_controls.md` for sizing and kill‑switches.

**Quickstart tasks**
- Build or refresh events: `scripts/build_events_m5.py`, `scripts/build_events_m15.py`
- Validate outputs vs baselines: `scripts/build_baselines.py`, then `uv run pytest -q`
- Replay into DB and verify API alignment: `scripts/replay_pipeline_to_db.py`, `scripts/validate_db_predictions_vs_pipeline.py`

**Local build**
```bash
make docs
```
This runs MkDocs on `127.0.0.1:8001` only.
