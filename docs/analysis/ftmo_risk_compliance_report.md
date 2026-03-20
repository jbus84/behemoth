# FTMO Compliance Report

Compatibility note: this page documents FTMO and cBot-facing risk controls that remain available for compatibility and historical support. They are not the primary runtime centerline for the active OCO JForex-directed system.

## Objective
- Confirm compatibility runtime trade decisions respect the configured FTMO profile limits when that surface is enabled.

## Compatibility Runtime Profile
- Config path: `configs/research/governance/ftmo/ftmo_rules.yaml`
- Default profile id: `ftmo_10k_challenge_2step`

## Runtime Guardrails
- Account-level gates:
- daily loss hard limit + buffered limit
- max loss hard limit + buffered limit
- Reservation / allocator gates:
- reserved-loss budget and headroom checks
- Candidate-level trade-cost diagnostics:
- spread/commission/slippage viability is diagnostic-only by default (`warn` mode), not a hard block unless explicitly set to `enforce`

## API Endpoints
- `POST /risk/ftmo/snapshot`
- `GET /risk/ftmo/limits`
- `GET /risk/ftmo/status`

## Legacy cBot Integration
- Parameters:
- `Enable FTMO Guards`
- `FTMO Profile ID`
- `Hard Stop On Risk Block`
- cBot posts balance/equity snapshots and blocks entries on FTMO risk deny.

## Operator Checks
- `GET /risk/ftmo/limits` returns configured profile and buffered thresholds.
- `GET /risk/ftmo/status?symbol=<SYM>` returns current headroom and block reason.
- `/predict` rows include:
- `risk_blocked`
- `risk_block_reason`
- `risk_metrics_snapshot`

## Known Assumptions
- Daily reset timezone follows profile config (`Europe/Prague` for FTMO defaults).
- Stage 04 / Stage 11 remain the source of execution and slippage realism.
- FTMO evaluation uses realized replay/runtime trades plus the profile replay overlay cost, defaulting to a `0.5` pip round-trip commission.
