### Auto Snapshot - Stage 10

- generated_at: `2026-04-12 17:21:09 UTC`
- Risk backlog is derived from current logical-audit failures.
- When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.

#### Key Results
| status                 |   failed_checks |
|:-----------------------|----------------:|
| no_open_audit_failures |               0 |

#### Interpretation Notes
- Risk backlog is derived from current logical-audit failures.
- When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.

#### Action Trigger Summary
| symbol   | metric_id                                        | band   | severity   | action_code   | action_summary                      | owner     |
|:---------|:-------------------------------------------------|:-------|:-----------|:--------------|:------------------------------------|:----------|
| AUDUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| AUDUSD   | FTMO_ALLOC_BLOCK_RATE                            | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| AUDUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| AUDUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| AUDUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| AUDUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| EURUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| EURUSD   | FTMO_ALLOC_BLOCK_RATE                            | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| EURUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| EURUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| EURUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| EURUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |

#### Plots
![stage_10_risk_matrix](../../figures/oco_bible/stage_10_risk_matrix.png)

- Risk SLA tracker not found; run `scripts/audit_oco_pipeline_logical_issues.py` with `--out-risk-sla-csv` to populate Stage 10 operational aging metrics.
