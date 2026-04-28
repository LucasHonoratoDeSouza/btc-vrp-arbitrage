# VRP Strategy Research Report

**Generated:** 2026-04-28  
**Dataset:** Deribit BTC-PERPETUAL OHLC + Deribit DVOL hourly, Mar-2021 -> Apr-2026  
**Verdict:** NOT READY FOR LIVE CAPITAL. Current results validate a DVOL/variance-proxy signal, not executable option PnL.

## 1. Readiness Gate

| Gate | Status | Reason |
|---|---|---|
| Point-in-time option chain | FAIL | No historical bid/ask option-chain dataset is used in the 5-year validation. |
| Executable PnL | FAIL | Main backtest uses DVOL as IV and a synthetic variance payoff. |
| Walk-forward discipline | PARTIAL | Test windows are out-of-sample for the selector, but adjacent windows overlap by 15 days. |
| Data quality | PASS | Extended OHLC and DVOL files are hourly, aligned, gap-free and duplicate-free. |
| Research signal | PASS | Proxy results are consistently positive across the sample after corrections. |

## 2. Continuous Proxy Backtest

This is the closest proxy equity curve because each strategy runs once over the full period. It is still not live-tradable PnL.

| Strategy | Final Capital | PnL | CAGR | Worst Month | Max DD | Sharpe | Trades | Win Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_return_target | 89,362 | 79,362 | 53.63% | -26.77% | -33.52% | 2.66 | 2290 | 82.36% |
| alpha_plus | 75,734 | 65,734 | 48.73% | -22.70% | -29.06% | 2.78 | 2313 | 82.27% |
| alpha_vol_breakout_guard | 63,504 | 53,504 | 43.68% | -18.69% | -24.02% | 3.01 | 2286 | 82.37% |
| alpha_current | 54,120 | 44,120 | 39.25% | -15.74% | -20.62% | 3.11 | 2313 | 82.27% |
| alpha_defensive | 49,476 | 39,476 | 36.82% | -14.39% | -18.78% | 3.21 | 2273 | 82.62% |
| alpha_carry_confirmed | 32,961 | 22,961 | 26.35% | -20.09% | -26.38% | 1.74 | 1510 | 79.27% |

## 3. Walk-Forward Diagnostics

The 119 windows are 30-day tests with 15-day steps. Adjacent test windows overlap; therefore `Overlap PnL Sum` must not be treated as deployable cumulative profit.

| Strategy | Windows | Overlap PnL Sum | Even Non-Overlap PnL | Odd Non-Overlap PnL | Avg Ret/Window | Median Ret/Window | Avg Sharpe | % Positive | Min PnL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_return_target | 119 | 162,294 | 81,018 | 81,276 | 13.64% | 7.81% | 3.73 | 89.1% | -2,281.04 |
| alpha_plus | 119 | 134,295 | 67,048 | 67,246 | 11.29% | 6.54% | 3.72 | 86.6% | -1,524.95 |
| alpha_vol_breakout_guard | 119 | 109,388 | 54,608 | 54,780 | 9.19% | 5.20% | 3.74 | 89.1% | -897.01 |
| alpha_current | 119 | 90,124 | 44,996 | 45,128 | 7.57% | 4.36% | 3.70 | 86.6% | -1,016.63 |
| alpha_defensive | 119 | 80,411 | 40,098 | 40,313 | 6.76% | 3.87% | 3.64 | 87.4% | -893.34 |
| alpha_carry_confirmed | 119 | 48,802 | 23,763 | 25,039 | 4.10% | 2.82% | 2.77 | 80.7% | -2,262.13 |

Best overlap-sum candidate: **alpha_return_target**.
Worst `alpha_return_target` window: fold 27, 2022-07-02 -> 2022-08-01, PnL -2,281.04.

## 4. Walk-Forward Selector

- Overlapping fold PnL sum: **144,643**
- Even non-overlap fold PnL: **72,225**
- Odd non-overlap fold PnL: **72,418**
- Positive overlapping windows: **87.4%** (104/119)
- Most selected: **alpha_return_target** (80/119 folds)

## 5. Regime Diagnostics

| Strategy | Regime | Windows | Overlap PnL Sum | Avg PnL | % Positive | Avg Sharpe |
|---|---|---:|---:|---:|---:|---:|
| alpha_carry_confirmed | calm | 62 | 30,964 | 499.4 | 83.9% | 3.27 |
| alpha_carry_confirmed | trending | 27 | 9,508 | 352.1 | 81.5% | 2.38 |
| alpha_carry_confirmed | volatile | 30 | 8,330 | 277.7 | 73.3% | 2.08 |
| alpha_current | calm | 62 | 51,890 | 836.9 | 91.9% | 4.26 |
| alpha_current | trending | 27 | 17,876 | 662.1 | 77.8% | 3.44 |
| alpha_current | volatile | 30 | 20,357 | 678.6 | 83.3% | 2.78 |
| alpha_defensive | calm | 62 | 45,805 | 738.8 | 90.3% | 4.15 |
| alpha_defensive | trending | 27 | 15,772 | 584.1 | 81.5% | 3.27 |
| alpha_defensive | volatile | 30 | 18,835 | 627.8 | 86.7% | 2.92 |
| alpha_plus | calm | 62 | 76,945 | 1,241.0 | 91.9% | 4.28 |
| alpha_plus | trending | 27 | 26,814 | 993.1 | 77.8% | 3.48 |
| alpha_plus | volatile | 30 | 30,536 | 1,017.9 | 83.3% | 2.80 |
| alpha_return_target | calm | 62 | 93,203 | 1,503.3 | 93.5% | 4.27 |
| alpha_return_target | trending | 27 | 32,678 | 1,210.3 | 81.5% | 3.54 |
| alpha_return_target | volatile | 30 | 36,413 | 1,213.8 | 86.7% | 2.80 |
| alpha_vol_breakout_guard | calm | 62 | 61,927 | 998.8 | 93.5% | 4.25 |
| alpha_vol_breakout_guard | trending | 27 | 22,551 | 835.2 | 81.5% | 3.53 |
| alpha_vol_breakout_guard | volatile | 30 | 24,909 | 830.3 | 86.7% | 2.89 |

## 6. Primary Candidate Window Detail

| Fold | Period | PnL | Return | Sharpe | Regime |
|---:|---|---:|---:|---:|---|
| 0 | 2021-05-23 -> 2021-06-22 | 91.5 | 0.91% | 0.37 | volatile |
| 1 | 2021-06-07 -> 2021-07-07 | 1,241.7 | 12.42% | 3.84 | volatile |
| 2 | 2021-06-22 -> 2021-07-22 | 3,307.0 | 33.07% | 7.40 | volatile |
| 3 | 2021-07-07 -> 2021-08-06 | 2,539.8 | 25.40% | 3.95 | volatile |
| 4 | 2021-07-22 -> 2021-08-21 | 3,126.0 | 31.26% | 4.17 | volatile |
| 5 | 2021-08-06 -> 2021-09-05 | 5,003.3 | 50.03% | 7.79 | trending |
| 6 | 2021-08-21 -> 2021-09-20 | 5,531.2 | 55.31% | 8.27 | volatile |
| 7 | 2021-09-05 -> 2021-10-05 | 3,469.4 | 34.69% | 7.42 | volatile |
| 8 | 2021-09-20 -> 2021-10-20 | 696.4 | 6.96% | 1.08 | volatile |
| 9 | 2021-10-05 -> 2021-11-04 | 1,874.0 | 18.74% | 2.34 | trending |
| 10 | 2021-10-20 -> 2021-11-19 | 3,099.8 | 31.00% | 3.86 | calm |
| 11 | 2021-11-04 -> 2021-12-04 | 2,400.5 | 24.00% | 3.49 | trending |
| 12 | 2021-11-19 -> 2021-12-19 | 514.2 | 5.14% | 1.01 | volatile |
| 13 | 2021-12-04 -> 2022-01-03 | 2,468.9 | 24.69% | 5.75 | calm |
| 14 | 2021-12-19 -> 2022-01-18 | 2,767.9 | 27.68% | 7.22 | calm |
| 15 | 2022-01-03 -> 2022-02-02 | 762.1 | 7.62% | 3.67 | volatile |
| 16 | 2022-01-18 -> 2022-02-17 | 373.2 | 3.73% | 2.17 | volatile |
| 17 | 2022-02-02 -> 2022-03-04 | 397.6 | 3.98% | 2.36 | volatile |
| 18 | 2022-02-17 -> 2022-03-19 | 377.8 | 3.78% | 1.70 | volatile |
| 19 | 2022-03-04 -> 2022-04-03 | 1,848.8 | 18.49% | 5.41 | calm |
| 20 | 2022-03-19 -> 2022-04-18 | 2,168.2 | 21.68% | 6.86 | calm |
| 21 | 2022-04-03 -> 2022-05-03 | 947.8 | 9.48% | 4.13 | trending |
| 22 | 2022-04-18 -> 2022-05-18 | 171.4 | 1.71% | 0.79 | volatile |
| 23 | 2022-05-03 -> 2022-06-02 | 1,025.4 | 10.25% | 3.27 | volatile |
| 24 | 2022-05-18 -> 2022-06-17 | 1,663.9 | 16.64% | 4.71 | volatile |
| 25 | 2022-06-02 -> 2022-07-02 | 1,416.2 | 14.16% | 4.33 | volatile |
| 26 | 2022-06-17 -> 2022-07-17 | 298.1 | 2.98% | 0.63 | volatile |
| 27 | 2022-07-02 -> 2022-08-01 | -2,281.0 | -22.81% | -1.82 | trending |
| 28 | 2022-07-17 -> 2022-08-16 | -498.0 | -4.98% | -0.22 | trending |
| 29 | 2022-08-01 -> 2022-08-31 | 3,005.3 | 30.05% | 7.58 | trending |
| 30 | 2022-08-16 -> 2022-09-15 | 1,711.6 | 17.12% | 3.17 | trending |
| 31 | 2022-08-31 -> 2022-09-30 | 232.8 | 2.33% | 0.51 | calm |
| 32 | 2022-09-15 -> 2022-10-15 | 3,803.7 | 38.04% | 6.11 | calm |
| 33 | 2022-09-30 -> 2022-10-30 | 6,632.9 | 66.33% | 9.75 | calm |
| 34 | 2022-10-15 -> 2022-11-14 | 4,005.9 | 40.06% | 8.27 | volatile |
| 35 | 2022-10-30 -> 2022-11-29 | 4,158.5 | 41.59% | 4.03 | volatile |
| 36 | 2022-11-14 -> 2022-12-14 | 9,110.2 | 91.10% | 6.96 | calm |
| 37 | 2022-11-29 -> 2022-12-29 | 11,785.1 | 117.85% | 9.93 | calm |
| 38 | 2022-12-14 -> 2023-01-13 | 10,728.7 | 107.29% | 10.29 | calm |
| 39 | 2022-12-29 -> 2023-01-28 | 4,762.9 | 47.63% | 7.87 | trending |
| 40 | 2023-01-13 -> 2023-02-12 | 840.7 | 8.41% | 3.41 | trending |
| 41 | 2023-01-28 -> 2023-02-27 | 916.2 | 9.16% | 4.72 | calm |
| 42 | 2023-02-12 -> 2023-03-14 | 256.4 | 2.56% | 0.81 | volatile |
| 43 | 2023-02-27 -> 2023-03-29 | -40.1 | -0.40% | -0.04 | volatile |
| 44 | 2023-03-14 -> 2023-04-13 | 869.6 | 8.70% | 1.91 | trending |
| 45 | 2023-03-29 -> 2023-04-28 | 1,096.4 | 10.96% | 2.26 | calm |
| 46 | 2023-04-13 -> 2023-05-13 | 372.5 | 3.72% | 2.07 | calm |
| 47 | 2023-04-28 -> 2023-05-28 | 1,133.3 | 11.33% | 5.78 | calm |
| 48 | 2023-05-13 -> 2023-06-12 | 675.4 | 6.75% | 1.95 | calm |
| 49 | 2023-05-28 -> 2023-06-27 | -1,345.5 | -13.46% | -2.05 | calm |
| 50 | 2023-06-12 -> 2023-07-12 | 33.1 | 0.33% | 0.17 | trending |
| 51 | 2023-06-27 -> 2023-07-27 | 780.6 | 7.81% | 2.85 | calm |
| 52 | 2023-07-12 -> 2023-08-11 | 1,236.6 | 12.37% | 8.70 | calm |
| 53 | 2023-07-27 -> 2023-08-26 | 1,702.0 | 17.02% | 8.79 | calm |
| 54 | 2023-08-11 -> 2023-09-10 | 1,249.2 | 12.49% | 5.01 | trending |
| 55 | 2023-08-26 -> 2023-09-25 | 1,372.5 | 13.72% | 5.24 | calm |
| 56 | 2023-09-10 -> 2023-10-10 | 439.0 | 4.39% | 1.24 | calm |
| 57 | 2023-09-25 -> 2023-10-25 | -490.1 | -4.90% | -1.12 | volatile |
| 58 | 2023-10-10 -> 2023-11-09 | 799.1 | 7.99% | 3.04 | volatile |
| 59 | 2023-10-25 -> 2023-11-24 | 2,105.5 | 21.05% | 8.27 | calm |
| 60 | 2023-11-09 -> 2023-12-09 | 2,377.5 | 23.78% | 10.37 | trending |
| 61 | 2023-11-24 -> 2023-12-24 | 1,163.0 | 11.63% | 3.23 | trending |
| 62 | 2023-12-09 -> 2024-01-08 | 503.9 | 5.04% | 0.81 | calm |
| 63 | 2023-12-24 -> 2024-01-23 | 426.4 | 4.26% | 0.76 | calm |
| 64 | 2024-01-08 -> 2024-02-07 | 2.8 | 0.03% | 0.05 | calm |
| 65 | 2024-01-23 -> 2024-02-22 | -603.6 | -6.04% | -1.01 | trending |
| 66 | 2024-02-07 -> 2024-03-08 | 38.4 | 0.38% | 0.19 | trending |
| 67 | 2024-02-22 -> 2024-03-23 | 1,430.9 | 14.31% | 4.09 | trending |
| 68 | 2024-03-08 -> 2024-04-07 | 4,135.1 | 41.35% | 7.27 | calm |
| 69 | 2024-03-23 -> 2024-04-22 | 3,892.7 | 38.93% | 6.85 | calm |
| 70 | 2024-04-07 -> 2024-05-07 | 915.4 | 9.15% | 2.76 | calm |
| 71 | 2024-04-22 -> 2024-05-22 | 1,039.1 | 10.39% | 4.64 | calm |
| 72 | 2024-05-07 -> 2024-06-06 | 1,212.3 | 12.12% | 4.77 | calm |
| 73 | 2024-05-22 -> 2024-06-21 | 1,790.2 | 17.90% | 7.06 | calm |
| 74 | 2024-06-06 -> 2024-07-06 | 1,366.4 | 13.66% | 6.18 | trending |
| 75 | 2024-06-21 -> 2024-07-21 | 632.9 | 6.33% | 6.52 | calm |
| 76 | 2024-07-06 -> 2024-08-05 | -136.7 | -1.37% | -0.78 | calm |
| 77 | 2024-07-21 -> 2024-08-20 | -406.2 | -4.06% | -2.39 | volatile |
| 78 | 2024-08-05 -> 2024-09-04 | 185.9 | 1.86% | 1.57 | volatile |
| 79 | 2024-08-20 -> 2024-09-19 | 256.4 | 2.56% | 1.50 | calm |
| 80 | 2024-09-04 -> 2024-10-04 | 603.2 | 6.03% | 2.58 | calm |
| 81 | 2024-09-19 -> 2024-10-19 | 1,657.1 | 16.57% | 7.20 | calm |
| 82 | 2024-10-04 -> 2024-11-03 | 2,667.9 | 26.68% | 8.53 | trending |
| 83 | 2024-10-19 -> 2024-11-18 | 2,092.5 | 20.92% | 7.02 | trending |
| 84 | 2024-11-03 -> 2024-12-03 | 762.7 | 7.63% | 4.54 | trending |
| 85 | 2024-11-18 -> 2024-12-18 | 809.8 | 8.10% | 4.86 | trending |
| 86 | 2024-12-03 -> 2025-01-02 | 607.1 | 6.07% | 2.79 | calm |
| 87 | 2024-12-18 -> 2025-01-17 | 1,648.8 | 16.49% | 4.66 | calm |
| 88 | 2025-01-02 -> 2025-02-01 | 1,370.2 | 13.70% | 4.41 | calm |
| 89 | 2025-01-17 -> 2025-02-16 | 222.0 | 2.22% | 1.50 | calm |
| 90 | 2025-02-01 -> 2025-03-03 | 1,008.3 | 10.08% | 6.22 | calm |
| 91 | 2025-02-16 -> 2025-03-18 | 769.4 | 7.69% | 4.77 | volatile |
| 92 | 2025-03-03 -> 2025-04-02 | 534.6 | 5.35% | 5.52 | volatile |
| 93 | 2025-03-18 -> 2025-04-17 | 130.8 | 1.31% | 0.68 | calm |
| 94 | 2025-04-02 -> 2025-05-02 | -53.7 | -0.54% | -0.15 | trending |
| 95 | 2025-04-17 -> 2025-05-17 | 611.5 | 6.12% | 3.25 | trending |
| 96 | 2025-05-02 -> 2025-06-01 | 578.3 | 5.78% | 6.13 | calm |
| 97 | 2025-05-17 -> 2025-06-16 | 755.2 | 7.55% | 7.96 | calm |
| 98 | 2025-06-01 -> 2025-07-01 | 783.9 | 7.84% | 7.18 | calm |
| 99 | 2025-06-16 -> 2025-07-16 | 816.8 | 8.17% | 7.68 | calm |
| 100 | 2025-07-01 -> 2025-07-31 | 783.3 | 7.83% | 8.52 | calm |
| 101 | 2025-07-16 -> 2025-08-15 | 463.5 | 4.63% | 6.80 | calm |
| 102 | 2025-07-31 -> 2025-08-30 | 35.1 | 0.35% | 0.44 | calm |
| 103 | 2025-08-15 -> 2025-09-14 | 110.6 | 1.11% | 1.44 | calm |
| 104 | 2025-08-30 -> 2025-09-29 | 718.5 | 7.18% | 6.49 | calm |
| 105 | 2025-09-14 -> 2025-10-14 | 515.3 | 5.15% | 4.53 | calm |
| 106 | 2025-09-29 -> 2025-10-29 | 164.6 | 1.65% | 2.99 | calm |
| 107 | 2025-10-14 -> 2025-11-13 | 108.2 | 1.08% | 1.11 | calm |
| 108 | 2025-10-29 -> 2025-11-28 | -136.6 | -1.37% | -1.39 | trending |
| 109 | 2025-11-13 -> 2025-12-13 | -797.2 | -7.97% | -2.48 | calm |
| 110 | 2025-11-28 -> 2025-12-28 | -619.8 | -6.20% | -1.89 | calm |
| 111 | 2025-12-13 -> 2026-01-12 | 419.3 | 4.19% | 3.10 | calm |
| 112 | 2025-12-28 -> 2026-01-27 | 614.5 | 6.15% | 4.77 | calm |
| 113 | 2026-01-12 -> 2026-02-11 | 26.7 | 0.27% | 0.24 | volatile |
| 114 | 2026-01-27 -> 2026-02-26 | -390.2 | -3.90% | -1.91 | volatile |
| 115 | 2026-02-11 -> 2026-03-13 | 51.9 | 0.52% | 0.33 | calm |
| 116 | 2026-02-26 -> 2026-03-28 | 332.9 | 3.33% | 3.36 | calm |
| 117 | 2026-03-13 -> 2026-04-12 | 319.3 | 3.19% | 1.32 | calm |
| 118 | 2026-03-28 -> 2026-04-27 | 232.4 | 2.32% | 0.99 | trending |

## 7. What Was Corrected

- Realized volatility now uses realized variance (`mean(return^2)`) instead of sample standard deviation, which is unstable for short holds.
- Trade PnL now excludes the entry bar return; only returns after entry and through exit are included.
- The simulator no longer opens a variance-proxy trade on the final timestamp of a test slice.
- Reports now label overlapping fold sums correctly and show even/odd non-overlapping diagnostics.
- Live-readiness language was downgraded: these are research candidates until tested with point-in-time options execution.

## 8. Live Implementation Blockers

- Build historical Deribit option-chain snapshots with bid/ask, sizes, open interest, greeks and mark IV.
- Replace DVOL proxy payoff with mark-to-market PnL of the exact straddle/strangle/condor legs to be traded.
- Calibrate the conservative margin/liquidation model against real exchange margin and add quote rejection/latency assumptions.
- Run paper trading and shadow live execution before risking capital.