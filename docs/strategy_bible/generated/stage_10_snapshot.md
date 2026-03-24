### Auto Snapshot - Stage 10

- generated_at: `2026-03-23 20:05:07 UTC`
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
| symbol   | metric_id                                        | band   | severity   | action_code           | action_summary         | owner     |
|:---------|:-------------------------------------------------|:-------|:-----------|:----------------------|:-----------------------|:----------|
| AUDUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT | green  | info       | A0_MONITOR            | within policy band     | risk      |
| AUDUSD   | FTMO_ALLOC_BLOCK_RATE                            | green  | info       | A0_MONITOR            | within policy band     | risk      |
| AUDUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  | green  | info       | A0_MONITOR            | within policy band     | risk      |
| AUDUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         | green  | info       | A0_MONITOR            | within policy band     | execution |
| AUDUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            | green  | info       | A0_MONITOR            | within policy band     | data      |
| AUDUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   | green  | info       | A0_MONITOR            | within policy band     | execution |
| EURUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | risk      |
| EURUSD   | FTMO_ALLOC_BLOCK_RATE                            | amber  | medium     | A1_REVIEW             | review and monitor     | risk      |
| EURUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  | amber  | medium     | A1_REVIEW             | review and monitor     | risk      |
| EURUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         | green  | info       | A0_MONITOR            | within policy band     | execution |
| EURUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            | green  | info       | A0_MONITOR            | within policy band     | data      |
| EURUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   | green  | info       | A0_MONITOR            | within policy band     | execution |

#### Details
| symbol   | severity_if_fail   |   total_checks |   failed_checks |
|:---------|:-------------------|---------------:|----------------:|
| AUDUSD   | critical           |              3 |               0 |
| AUDUSD   | high               |              5 |               0 |
| AUDUSD   | medium             |              2 |               0 |
| EURUSD   | critical           |              3 |               0 |
| EURUSD   | high               |              5 |               0 |
| EURUSD   | medium             |              2 |               0 |
| GBPUSD   | critical           |              3 |               0 |
| GBPUSD   | high               |              5 |               0 |
| GBPUSD   | medium             |              2 |               0 |
| USDCAD   | critical           |              3 |               0 |
| USDCAD   | high               |              5 |               0 |
| USDCAD   | medium             |              2 |               0 |
| USDCHF   | critical           |              3 |               0 |
| USDCHF   | high               |              5 |               0 |
| USDCHF   | medium             |              2 |               0 |
| USDJPY   | critical           |              3 |               0 |
| USDJPY   | high               |              5 |               0 |
| USDJPY   | medium             |              2 |               0 |

#### Plots
![stage_10_risk_matrix](../../figures/oco_bible/stage_10_risk_matrix.png)

- Risk SLA tracker exists but has no open rows. `source=data/analysis/tick_opportunity_mining/risk_sla_tracker.csv`
