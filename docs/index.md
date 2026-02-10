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

**Local build**
```bash
make docs
```
This runs MkDocs on `127.0.0.1:8001` only.
