# Tick Source Completeness Audit

- tick_root: `/Users/danielfisher/Desktop/dukascopy_ticks`
- symbols_checked: `6`
- months_checked: `11`
- total_symbol_months: `66`
- failing_symbol_months: `0`

## Summary
| symbol   |   month | exists   | has_required_schema   | row_count_gt_zero   | timestamp_utc_ok   | path                                                                           | status   | detail            |
|:---------|--------:|:---------|:----------------------|:--------------------|:-------------------|:-------------------------------------------------------------------------------|:---------|:------------------|
| AUDUSD   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202504_ticks.parquet | ok       | row_count=3061962 |
| AUDUSD   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202505_ticks.parquet | ok       | row_count=1331373 |
| AUDUSD   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202506_ticks.parquet | ok       | row_count=1240291 |
| AUDUSD   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202507_ticks.parquet | ok       | row_count=1251339 |
| AUDUSD   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202508_ticks.parquet | ok       | row_count=989707  |
| AUDUSD   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202509_ticks.parquet | ok       | row_count=1071831 |
| AUDUSD   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202510_ticks.parquet | ok       | row_count=1271717 |
| AUDUSD   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202511_ticks.parquet | ok       | row_count=1145391 |
| AUDUSD   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202512_ticks.parquet | ok       | row_count=1096341 |
| AUDUSD   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202601_ticks.parquet | ok       | row_count=1343132 |
| AUDUSD   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/AUDUSD/AUDUSD_202602_ticks.parquet | ok       | row_count=1647663 |
| EURUSD   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202504_ticks.parquet | ok       | row_count=3915597 |
| EURUSD   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202505_ticks.parquet | ok       | row_count=2423219 |
| EURUSD   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202506_ticks.parquet | ok       | row_count=2033530 |
| EURUSD   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202507_ticks.parquet | ok       | row_count=1558153 |
| EURUSD   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202508_ticks.parquet | ok       | row_count=1341789 |
| EURUSD   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202509_ticks.parquet | ok       | row_count=1493853 |
| EURUSD   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202510_ticks.parquet | ok       | row_count=1486567 |
| EURUSD   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202511_ticks.parquet | ok       | row_count=1231344 |
| EURUSD   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202512_ticks.parquet | ok       | row_count=1293972 |
| EURUSD   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202601_ticks.parquet | ok       | row_count=1506296 |
| EURUSD   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/EURUSD/EURUSD_202602_ticks.parquet | ok       | row_count=1330124 |
| GBPUSD   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202504_ticks.parquet | ok       | row_count=3633696 |
| GBPUSD   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202505_ticks.parquet | ok       | row_count=1971609 |
| GBPUSD   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202506_ticks.parquet | ok       | row_count=1819090 |
| GBPUSD   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202507_ticks.parquet | ok       | row_count=1819185 |
| GBPUSD   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202508_ticks.parquet | ok       | row_count=1456792 |
| GBPUSD   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202509_ticks.parquet | ok       | row_count=1690390 |
| GBPUSD   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202510_ticks.parquet | ok       | row_count=1796012 |
| GBPUSD   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202511_ticks.parquet | ok       | row_count=1654459 |
| GBPUSD   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202512_ticks.parquet | ok       | row_count=1644002 |
| GBPUSD   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202601_ticks.parquet | ok       | row_count=1808163 |
| GBPUSD   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/GBPUSD/GBPUSD_202602_ticks.parquet | ok       | row_count=1631274 |
| USDCAD   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202504_ticks.parquet | ok       | row_count=3382052 |
| USDCAD   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202505_ticks.parquet | ok       | row_count=1520982 |
| USDCAD   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202506_ticks.parquet | ok       | row_count=1533470 |
| USDCAD   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202507_ticks.parquet | ok       | row_count=1562901 |
| USDCAD   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202508_ticks.parquet | ok       | row_count=1380303 |
| USDCAD   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202509_ticks.parquet | ok       | row_count=1460499 |
| USDCAD   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202510_ticks.parquet | ok       | row_count=1597923 |
| USDCAD   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202511_ticks.parquet | ok       | row_count=1618456 |
| USDCAD   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202512_ticks.parquet | ok       | row_count=1660425 |
| USDCAD   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202601_ticks.parquet | ok       | row_count=1799947 |
| USDCAD   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCAD/USDCAD_202602_ticks.parquet | ok       | row_count=1604357 |
| USDCHF   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202504_ticks.parquet | ok       | row_count=3050163 |
| USDCHF   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202505_ticks.parquet | ok       | row_count=1910380 |
| USDCHF   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202506_ticks.parquet | ok       | row_count=1526856 |
| USDCHF   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202507_ticks.parquet | ok       | row_count=1292263 |
| USDCHF   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202508_ticks.parquet | ok       | row_count=1114380 |
| USDCHF   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202509_ticks.parquet | ok       | row_count=1105725 |
| USDCHF   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202510_ticks.parquet | ok       | row_count=1234438 |
| USDCHF   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202511_ticks.parquet | ok       | row_count=928468  |
| USDCHF   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202512_ticks.parquet | ok       | row_count=982263  |
| USDCHF   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202601_ticks.parquet | ok       | row_count=1285495 |
| USDCHF   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDCHF/USDCHF_202602_ticks.parquet | ok       | row_count=1112371 |
| USDJPY   |  202504 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202504_ticks.parquet | ok       | row_count=5547117 |
| USDJPY   |  202505 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202505_ticks.parquet | ok       | row_count=3149583 |
| USDJPY   |  202506 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202506_ticks.parquet | ok       | row_count=2417111 |
| USDJPY   |  202507 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202507_ticks.parquet | ok       | row_count=2170032 |
| USDJPY   |  202508 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202508_ticks.parquet | ok       | row_count=1806135 |
| USDJPY   |  202509 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202509_ticks.parquet | ok       | row_count=2033481 |
| USDJPY   |  202510 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202510_ticks.parquet | ok       | row_count=2381844 |
| USDJPY   |  202511 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202511_ticks.parquet | ok       | row_count=1999841 |
| USDJPY   |  202512 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202512_ticks.parquet | ok       | row_count=1917349 |
| USDJPY   |  202601 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202601_ticks.parquet | ok       | row_count=2201188 |
| USDJPY   |  202602 | True     | True                  | True                | True               | /Users/danielfisher/Desktop/dukascopy_ticks/USDJPY/USDJPY_202602_ticks.parquet | ok       | row_count=1994068 |

## Missing Or Invalid
_empty_
