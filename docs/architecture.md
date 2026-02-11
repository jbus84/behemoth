# Architecture

This page describes the runtime flow and the main components of the Behemoth system.

## System Flow

```mermaid
flowchart LR
  A[Bar data] --> B[Kalman filter]
  B --> C[Z-score + active leg]
  C --> D[Signal generator]
  D --> E[Risk gates]
  E -->|allowed| F[Create position]
  E -->|blocked| G[Reject trade]
  F --> H[Execution / broker]
  H --> I[Position close]
  I --> J[Account + guardrail update]
```

## Runtime Components

- **Signal engine**: `src/behemoth/core/*` computes Kalman states, Z‑scores, and active‑leg selection.
- **API**: `services/api/*` manages position state, guardrail, and risk limits.
- **Database**: Postgres stores positions, orders, and guardrail/account state.
- **Cache**: Redis is optional for hot position reads.

## Data Ownership

- **Market bars**: `data/global_*`
- **Events**: `data/events/events_*`
- **Analysis**: `data/analysis/*`

## Charts

Guardrail impact charts are maintained in `docs/figures/`:

![M5 guardrail monthly net](figures/m5_guardrail_monthly_net.png)
![M5 guardrail drawdown](figures/m5_guardrail_drawdown.png)
![M15 guardrail monthly net](figures/m15_guardrail_monthly_net.png)
![M15 guardrail drawdown](figures/m15_guardrail_drawdown.png)
