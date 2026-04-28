# Strategy Parameter Comparison

Continuous columns are one full-period proxy backtest. Walk-forward columns are overlapping 30-day diagnostic windows.

| Strategy | Bucket | Notional | Kelly | Edge% | MaxStress% | RVPct | Hold(h) | Cont Ret% | Cont DD% | WF Win | WF Avg Ret% | WF % Pos |
|---|---|---:|---|---|---|---|---:|---|---|---|---|---|
| alpha_return_target | aggressive | 180 | 0.75 | 3.0 | 12 | 85 | 6 | 793.6 | -33.5 | 119 | 13.64 | 89.1% |
| alpha_current | balanced | 100 | 0.75 | 2.5 | 8 | 90 | 6 | 441.2 | -20.6 | 119 | 7.57 | 86.6% |
| alpha_plus | balanced | 150 | 0.75 | 2.5 | 10 | 90 | 6 | 657.3 | -29.1 | 119 | 11.29 | 86.6% |
| alpha_vol_breakout_guard | balanced | 120 | 0.75 | 3.0 | 8 | 75 | 6 | 535.0 | -24.0 | 119 | 9.19 | 89.1% |
| alpha_defensive | conservative | 90 | 0.75 | 3.5 | 6 | 90 | 6 | 394.8 | -18.8 | 119 | 6.76 | 87.4% |
| alpha_carry_confirmed | research | 120 | 0.75 | 2.5 | 8 | 90 | 12 | 229.6 | -26.4 | 119 | 4.10 | 80.7% |
| adaptive_alpha | balanced | 100 | 0.75 | 2.5 | 8 | 90 | 6 | - | - | - | - | - |
| conservative | conservative | 1 | 0.40 | 4.0 | 2 | 80 | 72 | - | - | - | - | - |
| balanced_garch | balanced | 10 | 0.75 | 2.0 | 6 | 90 | 96 | - | - | - | - | - |
| high_return | aggressive | 100 | 1.00 | 4.0 | 12 | 85 | 72 | - | - | - | - | - |
| max_return | research | 150 | 1.00 | 2.0 | 20 | 90 | 72 | - | - | - | - | - |
| overtrade_aggressive | research | 50 | 1.00 | 0.5 | 15 | 98 | 120 | - | - | - | - | - |

---

**Legend:**
- **Cont Ret% / Cont DD%** — full-period DVOL variance-proxy return/drawdown.
- **WF Avg Ret% / WF % Pos** — overlapping 30-day walk-forward diagnostics.
- These are not live option-chain execution metrics.