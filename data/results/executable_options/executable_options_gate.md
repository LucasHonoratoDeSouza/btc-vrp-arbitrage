# Executable Option Backtest Gate

| Check | Passed | Value | Threshold |
|---|---:|---:|---:|
| required_columns | True | none | none missing |
| microstructure_columns | True | none | none missing |
| history_days | False | 0.0 | 180.0 |
| rows_per_timestamp | True | 176.0 | 80 |
| max_timestamp_gap_hours | True | 0.08 | 1.5 |
| crossed_markets | True | 0 | 0 |
| nonpositive_prices | True | 0 | 0 |

Status: **BLOCKED**. Provide point-in-time historical option-chain snapshots before trusting live execution metrics.