
# Behemoth: Kalman + Meta Model (H1)

**Status**: Partially Implemented (Inference-Only)
**Strategy**: Kalman Z‑Score Momentum + Loss‑Streak Guardrail (Rule‑Based)
**Timeframe**: H1 (Hourly)

> [!IMPORTANT]
> **Implementation Note**: This repo currently provides **signal inference** only. Execution‑side risk controls described in the manual (kill‑zone, circuit breaker, Z‑based exits, etc.) are **not implemented** in code.

## 1. The Strategy
We generate signals using a centered **Kalman Filter** and a rule‑based MOM/guardrail policy (no ML).

*   **Logic**: Kalman estimates dynamic beta and spread error; rules select MOM entries and guardrail pauses after loss streaks.
*   **Note**: Claims about market neutrality and Monte Carlo safety are **legacy** and require revalidation against the current H1 pipeline.

## 2. Legacy 4H Portfolio (Not Revalidated)
These were part of the older 4H system and are retained for reference only.

| Engine | Pair | Sharpe Ratio | Role |
| :--- | :--- | :--- | :--- |
| **Monetary** | Gold / Silver | **5.22** | Core Alpha |
| **Commodity FX** | AUD / NZD | **1.90** | Consistency |
| **Energy** | Brent / CAD | **1.73** | Inflation Hedge |
| **US Tech** | Nasdaq / SPX | **1.38** | Volatility Harvest |
| **Euro FX** | EUR / GBP | **1.12** | Low Vol Income |
| **Euro Equity** | DAX / FTSE | **1.06** | Diversification |

## 3. Legacy Metrics (Not Revalidated)
*   **Median Sharpe**: 6.90 (Portfolio Mean)
*   **Max Drawdown**: 0.076 log units (Worst Case 99%)
*   **Effective Lookback**: **2 Bars** (8 Hours). Proven via Impulse Response Test.
*   **Risk of Loss**: 0.0% (Annual Basis, Simulated 10k Years).

## 4. Quickstart

### A. Run H1 Inference
Generate the latest H1 signal for a pair:
```bash
python3 scripts/inference_meta_model.py
```

### B. Legacy 4H Dashboard
Legacy dashboard for the 4H portfolio:
```bash
python3 scripts/monitor_pairs.py
```

### C. Core Docs
*   **[Master Manual](docs/STRATEGY_MASTER_MANUAL.md)**: Current H1 logic and execution notes.
*   **Walkthrough**: legacy H1 exploration notes removed with ML cleanup.
*   **[Red‑Team Debunk](debunk/REDTEAM_REPO_DEBUNK.md)**: Known gaps and risks.

## 5. Execution Rules (Documentation vs Code)
The manual documents several guards (kill‑zone, circuit breaker, Z‑based exits), but **only entry‑side signal rules** are currently implemented in the inference script.

## 6. Position API (FastAPI + Postgres + Redis)
This repo now includes a state management service for positions and orders.

Quick start (Docker Compose):
```bash
make up
make migrate
```

Local dev:
```bash
make api
```

API health:
```bash
curl http://localhost:8000/healthz
```

Migrations (CI/local without Compose):
```bash
make migrate-local
```

Postgres integration test (optional):
```bash
make test-postgres
```

---
*Built by Antigravity. Validation status is documented in `debunk/`.* 
