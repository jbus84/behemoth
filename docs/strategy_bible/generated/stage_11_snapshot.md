### Auto Snapshot - Stage 11

- generated_at: `2026-04-12 17:21:09 UTC`
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Key Results
_empty_

#### Interpretation Notes
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Action Trigger Summary
| symbol   | metric_id                    | band   | severity   | action_code   | action_summary                      | owner     |
|:---------|:-----------------------------|:-------|:-----------|:--------------|:------------------------------------|:----------|
| AUDUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| AUDUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| AUDUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| EURUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| EURUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| EURUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| GBPUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| GBPUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| GBPUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| USDCAD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| USDCAD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| USDCAD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |

#### Plots
![stage_11_mc_lb95_by_scenario](../../figures/oco_bible/stage_11_mc_lb95_by_scenario.png)
![stage_11_mc_fill_vs_pnl](../../figures/oco_bible/stage_11_mc_fill_vs_pnl.png)
