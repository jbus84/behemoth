# FTMO Compliance Report

## Objective
- Confirm runtime trade decisions respect the active FTMO profile limits.

## Active Runtime Profile
- Config path: `configs/research/governance/ftmo/ftmo_rules.yaml`
- Default profile id: `ftmo_10k_challenge_2step`

## Runtime Guardrails
- Account-level gates:
- daily loss hard limit + buffered limit
- max loss hard limit + buffered limit
- Candidate-level gate:
- spread + commission + slippage cost viability proxy

## API Endpoints
- `POST /risk/ftmo/snapshot`
- `GET /risk/ftmo/limits`
- `GET /risk/ftmo/status`

## cBot Integration
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
- Cost viability uses runtime feature `cost_est_pips` plus configured commission/slippage floors.
