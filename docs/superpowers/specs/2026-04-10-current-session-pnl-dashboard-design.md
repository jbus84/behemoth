# Current-Session PnL Dashboard Design

## Context

The Grafana `Equity Matrix (PnL Pips)` panel currently reads `behemoth_equity_pips` from Prometheus as a range query. After `run_jforex_live.py` archives the previous `live_state.db` and starts a new session, the current DuckDB ledger is empty, but Grafana can still render prior-session values from Prometheus history. That makes the panel stale and misleading for current-session monitoring.

## Goal

Make the per-symbol realized PnL panel reflect only the current `live_state.db` session after restarts, without introducing a new Grafana datasource or plugin.

## Approach

1. Keep the existing Prometheus-backed panel.
2. Change the API exporter so `behemoth_equity_pips{symbol=...}` is rebuilt from current ledger rows on each refresh.
3. Clear any previously exported symbol series before writing the current snapshot, so an empty ledger emits no stale per-symbol PnL values.
4. Change the Grafana panel target from range mode to instant mode so it reads current state rather than historical samples from the selected dashboard window.

## Implementation Notes

- Add a small helper in `src/behemoth/api/server.py` that syncs realized-PnL gauges from `_state.get_ledger_stats()`.
- Have `_monitor_ledger()` call that helper each cycle.
- Add a regression test in `tests/test_api_server.py` that proves a previously exported symbol disappears when the next ledger snapshot is empty.
- Update `provisioning/dashboards/behemoth_alpha.json` so the `Equity Matrix (PnL Pips)` target is an instant query.

## Verification

- Targeted pytest for the new exporter regression.
- Existing `/metrics` format test still passes.
- Dashboard JSON inspection confirms the panel uses instant mode.
