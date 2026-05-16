# Data Reliability Audit

- generated_at_utc: `2026-05-16 11:08:15 UTC`
- symbols: `AUDUSD,EURUSD,GBPUSD,USDCAD,USDCHF,USDJPY`
- source_pattern: `data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet`

## Symbol Summary
| symbol   |   checks_total |   checks_failed |   high_or_critical_failed |
|:---------|---------------:|----------------:|--------------------------:|
| AUDUSD   |              1 |               1 |                         1 |
| EURUSD   |              1 |               1 |                         1 |
| GBPUSD   |              1 |               1 |                         1 |
| USDCAD   |              1 |               1 |                         1 |
| USDCHF   |              1 |               1 |                         1 |
| USDJPY   |              1 |               1 |                         1 |

## Failed Checks
| symbol   | check_id   | check_name            | status   | severity_if_fail   | component        | metric_name   |   metric_value |   threshold | comparator   | details                                                               | source_path   | evaluated_at_utc     |
|:---------|:-----------|:----------------------|:---------|:-------------------|:-----------------|:--------------|---------------:|------------:|:-------------|:----------------------------------------------------------------------|:--------------|:---------------------|
| AUDUSD   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |
| EURUSD   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |
| GBPUSD   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |
| USDCAD   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |
| USDCHF   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |
| USDJPY   | DR00       | source_dataset_exists | fail     | critical           | data_reliability | source_exists |              0 |           1 | ==           | pattern=data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet |               | 2026-05-16T11:08:15Z |

## Outputs
- checks_csv: `data/analysis/tick_opportunity_mining/data_reliability_checks.csv`
- issues_csv: `data/analysis/tick_opportunity_mining/data_reliability_issues.csv`