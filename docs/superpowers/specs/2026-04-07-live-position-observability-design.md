# Live Position Observability Design

**Date:** 2026-04-07  
**Status:** Approved  

## Problem

During live demo sessions, there is no way to answer:
- Are admitted reservations broker-confirmed (filled) or still pending?
- How long has a position been open?
- What is the estimated unrealized P&L?
- What is the cross-symbol view of all open positions?

The existing `/trades/active` endpoint requires a `symbol` parameter and has no cross-symbol view. `behemoth_equity_pips` tracks realized P&L only. The `PENDING` + `broker_pos_id: null` state after many minutes may indicate an execution issue (orders not reaching the broker) but there is no surface to detect this.

## Use Cases

1. **Operational monitoring** — watch open position state in real-time during a live session
2. **Debugging** — determine whether `PENDING` reservations with `broker_pos_id: null` represent a stuck execution issue vs. normal transient state

## Approach

Python API owns the position summary entirely. No JForex changes required. Data sources:
- `account_risk_reservations` table — status, direction, `created_at`, `broker_pos_id`
- `trades` table — `entry_price` for broker-confirmed positions
- `audit_logs.features_json` — best-effort last known bar close price per symbol for unrealized P&L approximation

## API Endpoint

`GET /trades/open-summary`

Returns a cross-symbol view of all non-closed reservations.

**Response schema:**
```json
{
  "as_of_utc": "2026-04-07T14:15:00Z",
  "total_open": 2,
  "broker_confirmed": 0,
  "pending_broker_confirm": 2,
  "positions": [
    {
      "symbol": "USDCHF",
      "direction": "BUY",
      "status": "PENDING",
      "broker_confirmed": false,
      "broker_pos_id": null,
      "open_since_utc": "2026-04-07T14:03:12Z",
      "open_minutes": 12.5,
      "entry_price": null,
      "last_tick_price": 0.9005,
      "last_tick_age_seconds": 5,
      "estimated_unrealized_pips": null
    }
  ]
}
```

**Nullability rules:**
- `entry_price`: null for PENDING reservations with no broker confirmation (no trade record yet)
- `last_tick_price` and `last_tick_age_seconds`: null if `audit_logs` has no recent rows for the symbol
- `estimated_unrealized_pips`: null if either `entry_price` or `last_tick_price` is null

## File Writer

The same payload is written to `{report_dir}/runtime/live_position_summary.json` by a background asyncio loop started at API startup. Write cadence: every 5 seconds. Pattern matches the existing readiness status writer.

## Prometheus Metrics

Three new gauges registered at module level in `server.py`:

| Metric | Labels | Description |
|--------|--------|-------------|
| `behemoth_open_positions_total` | `symbol` | Count of non-closed reservations per symbol |
| `behemoth_open_position_age_seconds` | `symbol` | Wall-clock seconds since oldest open reservation |
| `behemoth_estimated_unrealized_pips` | `symbol` | Best-effort unrealized P&L (0.0 if no open positions) |

Gauges are updated as a side-effect of `_build_open_positions_summary()`, which is called by both the endpoint and the background writer.

## Grafana

New panels added to `provisioning/dashboards/behemoth_jforex.json`:

1. **Stat panel** — `sum(behemoth_open_positions_total)` — "Open Positions" (cross-symbol count)
2. **Time-series panel** — `behemoth_estimated_unrealized_pips{symbol}` per symbol — "Estimated Unrealized Pips"
3. **Table panel** — `behemoth_open_position_age_seconds{symbol}` and `behemoth_open_positions_total{symbol}` — "Open Position Age by Symbol"

## Implementation Locations

All changes are confined to Python. No JForex rebuild required.

### `src/behemoth/api/server.py`

- **Three new Prometheus gauges** at module level (alongside existing `METRIC_EQUITY_PIPS` etc.)
- **`_build_open_positions_summary(state, now)`** — calls `state.list_active_account_risk_reservations()` with no symbol filter, enriches each row with `entry_price` from `trades` (where `broker_pos_id` matches) and last-known price from `audit_logs.features_json`, updates gauges
- **`GET /trades/open-summary`** endpoint — calls `_build_open_positions_summary` and returns JSON
- **`_write_position_summary_loop()`** — async background task, writes `live_position_summary.json` every 5s; started via `asyncio.create_task` at startup alongside the existing `_monitor_ledger` task

### `provisioning/dashboards/behemoth_jforex.json`

Three new panel objects appended to the `panels` array.

## Error Handling

- If `audit_logs` has no rows for a symbol: `last_tick_price` and `estimated_unrealized_pips` are `null` — not an error condition
- If a reservation is PENDING with no broker fill: `entry_price` is `null` — this is the expected state and the endpoint surfaces it clearly
- The endpoint never errors on missing data; it degrades gracefully with nulls

## Testing

New unit tests covering:
- `_build_open_positions_summary` with mock reservation rows (PENDING + OPEN cases)
- `GET /trades/open-summary` returns correct response shape
- Gauge values updated correctly after summary build
- Background writer invocation (mock file write)
