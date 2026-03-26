# Dukascopy Demo Certification Design

## Goal

Add a thin operational certification layer around the existing Dukascopy demo paper-trading path so tomorrow's market-open run can prove that all 6 symbols:

- load the intended models and rules
- reach `READY`
- ingest live ticks
- produce valid live `/predict` activity once bars advance
- remain able to trade even if some symbols do not emit a signal during the observation window

This is not a new trading-runtime project. The runtime readiness pipeline already exists. The remaining work is operator workflow, monitoring visibility, and certification evidence.

## Current State

The repo already has:

- `make jforex-live` to launch the Python API and JForex live/demo session
- `make observability-up` to launch Prometheus, Alertmanager, and Grafana
- a provisioned Grafana dashboard at `provisioning/dashboards/behemoth_jforex.json`
- JForex Prometheus metrics on `127.0.0.1:9464/metrics`
- per-symbol readiness state in `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json`
- automatic Makefile `.env` loading from the repo root or current checkout

What is missing is a verification-specific monitoring and operator flow that makes tomorrow's demo certification obvious, repeatable, and auditable.

## Recommended Approach

Extend the existing JForex observability path instead of creating a second monitoring stack.

This design:

- keeps `make observability-up` as the canonical monitoring bootstrap
- extends the existing JForex Grafana dashboard with readiness and certification panels
- adds one operator target for the demo certification flow
- adds a short operator checklist for tomorrow's run

This is preferred over a new standalone dashboard because it avoids duplicating runtime panels and keeps the operator experience centered on one known dashboard.

## Scope

### In Scope

- extend the provisioned JForex Grafana dashboard with live-readiness and certification panels
- add a one-command Make target for the demo certification monitoring workflow
- document the certification run flow and pass/fail criteria
- make it easy to observe per-symbol readiness, staleness, entry gating, tick ingest, and predict-path health

### Out of Scope

- changing model selection logic
- changing rule-universe loading logic
- changing readiness-state semantics
- requiring every symbol to emit a trade during the certification window
- adding broker-side synthetic fault injection for this iteration

## Certification Standard

The certification claim is:

> The Dukascopy demo paper-trading workflow is operationally verified end to end when all 6 configured symbols load, reach `READY`, ingest live ticks, and demonstrate live `/predict` activity once bars advance, while remaining eligible to trade if a qualifying signal appears.

This does **not** require every symbol to place a demo trade during the window.

## Architecture

### 1. Existing Stack Reuse

Keep the current observability topology:

- Python API metrics
- JForex metrics
- Prometheus scrape via `prometheus.yml`
- Grafana provisioning via `provisioning/dashboards/`

No new service should be introduced.

### 2. Certification Dashboard Layer

Extend `provisioning/dashboards/behemoth_jforex.json` with a certification-focused section.

Required panels:

- readiness state by symbol
- entries allowed by symbol
- tick staleness seconds by symbol
- readiness transitions by symbol
- readiness timeouts by symbol
- tick ingest rate by symbol
- predict activity by symbol
- order submit/fill rate by symbol

The dashboard should make the following questions answerable at a glance:

- Are all 6 symbols loaded and alive?
- Have all 6 symbols reached `READY`?
- Is any symbol stale or paused?
- Is the predict path active for all 6 symbols once bars advance?
- Are any symbols timing out or flapping between states?

### 3. Runtime Evidence Surface

The certification run should rely on two evidence surfaces:

- Grafana/Prometheus for live observation
- `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json` for direct machine-readable readiness evidence

The runtime JSON remains the source for exact per-symbol readiness snapshots. Grafana is the live operator view.

### 4. Operator Target

Add a dedicated Make target for demo certification, for example:

- `demo-cert-monitor`

It should:

- ensure observability is up
- print the key URLs and file paths:
  - Grafana
  - Prometheus
  - JForex metrics endpoint
  - runtime readiness JSON path
- avoid changing `jforex-live` behavior

The actual live session can continue to run through `make jforex-live`, but the certification target should remove setup ambiguity.

## Metrics Contract For Certification

The certification view should use the following JForex metrics:

- `behemoth_jforex_live_readiness_state`
- `behemoth_jforex_live_entries_allowed`
- `behemoth_jforex_live_tick_staleness_seconds`
- `behemoth_jforex_live_readiness_transitions_total`
- `behemoth_jforex_live_readiness_timeouts_total`
- `behemoth_jforex_ticks_received_total`
- `behemoth_jforex_predict_calls_total`
- `behemoth_jforex_predict_warmup_422_total`
- `behemoth_jforex_predict_failures_total`
- `behemoth_jforex_orders_submitted_total`
- `behemoth_jforex_order_fills_total`

Predict-path proof for a symbol is satisfied when:

- it is `READY`
- live ticks are ingesting
- `predict_calls_total` increases after bars advance
- `predict_failures_total` is not rising materially
- `predict_warmup_422_total` is not continuing after readiness

## Dashboard Semantics

### Readiness State

Render readiness state as a discrete per-symbol status panel or state timeline using the existing numeric enum values from Java metrics.

Operator meaning:

- `READY` is the expected certification state
- `STALE_PAUSED` is a certification failure unless it recovers quickly
- `ERROR_PAUSED` is a certification failure

### Entries Allowed

Render a per-symbol yes/no panel.

Operator meaning:

- all 6 should be `allowed=true` once certification is complete

### Tick Staleness

Render per-symbol staleness seconds with a visible threshold at `30s`.

Operator meaning:

- healthy symbols remain below the threshold
- threshold breaches correspond to `STALE_PAUSED`

### Predict Health

Render per-symbol predict calls and failures.

Operator meaning:

- all 6 symbols should demonstrate live predict activity once bars advance
- symbols that remain quiet in trading are acceptable if predict activity exists and readiness remains healthy

## Operator Run Flow

Tomorrow's certification flow should be:

1. `make observability-up`
2. open Grafana
3. start the certification helper target
4. run `make jforex-live`
5. monitor readiness until all 6 symbols reach `READY`
6. confirm tick staleness remains healthy
7. confirm predict activity appears for all 6 symbols after bars advance
8. spot-check `runtime/live_symbol_readiness.json`
9. record pass/fail outcome and any symbol-level exceptions

## Pass / Conditional Fail / Fail

### Pass

- all 6 symbols reach `READY`
- all 6 symbols ingest live ticks
- all 6 symbols demonstrate live predict-path activity once bars advance
- no symbol remains stale or error-paused during the observation window

### Conditional Fail

- all 6 symbols reach `READY`, but one or more symbols later become stale
- all 6 symbols ingest ticks, but one or more symbols show missing or suspect predict-path activity

### Fail

- any symbol never reaches `READY`
- any symbol lands in `ERROR_PAUSED`
- any symbol remains `STALE_PAUSED`
- any symbol fails to demonstrate a live predict path during the certification window

## Documentation Changes

Update operator-facing docs to include:

- the certification purpose
- the monitoring stack startup
- the dashboard location
- the runtime readiness JSON path
- the exact pass/fail interpretation

## Testing And Verification

Before tomorrow's live demo run:

- verify the dashboard provisions cleanly
- verify the new Make target prints the correct monitoring/run information
- verify existing automated tests still pass

Tomorrow's market-open certification remains a manual operational check because it depends on external broker connectivity and live market ticks.

## Risks

### Existing Dashboard Drift

Risk:
- the existing JForex dashboard may not yet express readiness and predict-path health clearly enough

Mitigation:
- add a dedicated certification row rather than mixing signals loosely into the current generic panels

### Predict Activity Ambiguity

Risk:
- a symbol may be healthy but not emit obvious trading behavior during a short window

Mitigation:
- use predict-call activity, not trade occurrence, as the required proof

### Demo Environment Timing

Risk:
- market-open conditions can create short startup lag or temporary staleness

Mitigation:
- define explicit certification windows and pass/fail thresholds ahead of time

## Deliverables

- updated Grafana JForex dashboard with certification-focused panels
- one-command certification monitoring target in `Makefile`
- concise operator docs/checklist for tomorrow's demo certification
- manual market-open certification run using the Dukascopy demo account
