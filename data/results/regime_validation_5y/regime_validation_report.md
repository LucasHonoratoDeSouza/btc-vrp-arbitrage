# Regime Validation
Fixed candidates are evaluated across rolling out-of-sample windows. With the default 30-day test and 15-day step, adjacent windows overlap by 15 days.
The selector chooses only from prior train windows, but summed PnL across all folds is a diagnostic, not a realizable equity curve.
## Candidate Summary
| Candidate | Windows | Overlap PnL Sum | Even Non-Overlap PnL | Avg Return | Median Return | Avg Sharpe | Min PnL | Positive Windows | Trades | Avg Stress/PnL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| alpha_return_target | 119 | 162294.215879 | 81018.360193 | 13.6382% | 7.8058% | 3.731 | -2281.038940 | 89.1% | 4414 | 16.47 |
| alpha_plus | 119 | 134294.760725 | 67048.310928 | 11.2853% | 6.5353% | 3.723 | -1524.946270 | 86.6% | 4459 | 10.20 |
| alpha_vol_breakout_guard | 119 | 109387.868843 | 54608.102591 | 9.1923% | 5.2039% | 3.741 | -897.012080 | 89.1% | 4406 | 16.37 |
| alpha_current | 119 | 90123.568335 | 44995.737878 | 7.5734% | 4.3568% | 3.702 | -1016.630846 | 86.6% | 4459 | 10.20 |
| alpha_defensive | 119 | 80411.191519 | 40098.196867 | 6.7572% | 3.8742% | 3.643 | -893.343082 | 87.4% | 4382 | 13.23 |
| alpha_carry_confirmed | 119 | 48801.956725 | 23762.563537 | 4.1010% | 2.8167% | 2.770 | -2262.126758 | 80.7% | 2915 | 29.80 |
## Regime PnL
| Candidate | Regime | Windows | Overlap PnL Sum | Avg PnL |
|---|---|---:|---:|---:|
| alpha_carry_confirmed | calm | 62 | 30964.050214 | 499.420165 |
| alpha_carry_confirmed | trending | 27 | 9507.965536 | 352.146872 |
| alpha_carry_confirmed | volatile | 30 | 8329.940975 | 277.664699 |
| alpha_current | calm | 62 | 51890.243993 | 836.939419 |
| alpha_current | trending | 27 | 17876.228199 | 662.082526 |
| alpha_current | volatile | 30 | 20357.096143 | 678.569871 |
| alpha_defensive | calm | 62 | 45804.631319 | 738.784376 |
| alpha_defensive | trending | 27 | 15771.522614 | 584.130467 |
| alpha_defensive | volatile | 30 | 18835.037585 | 627.834586 |
| alpha_plus | calm | 62 | 76944.774212 | 1241.044745 |
| alpha_plus | trending | 27 | 26814.342298 | 993.123789 |
| alpha_plus | volatile | 30 | 30535.644215 | 1017.854807 |
| alpha_return_target | calm | 62 | 93203.413643 | 1503.280865 |
| alpha_return_target | trending | 27 | 32678.114515 | 1210.300538 |
| alpha_return_target | volatile | 30 | 36412.687721 | 1213.756257 |
| alpha_vol_breakout_guard | calm | 62 | 61926.958420 | 998.821910 |
| alpha_vol_breakout_guard | trending | 27 | 22551.460183 | 835.239266 |
| alpha_vol_breakout_guard | volatile | 30 | 24909.450241 | 830.315008 |
## Walk-Forward Selector
- Overlapping fold PnL sum: **144642.807069**
- Even-fold non-overlap PnL sum: **72225.242150**
- Positive OOS windows: **87.4%**
| Fold | Selected | Train Score | Test PnL | Test Trades | Regime |
|---:|---|---:|---:|---:|---|
| 0 | alpha_defensive | -3022.883818 | 37.845294 | 36 | volatile |
| 1 | alpha_defensive | -2261.665445 | 602.765425 | 37 | volatile |
| 2 | alpha_defensive | -2272.824057 | 1643.314639 | 44 | volatile |
| 3 | alpha_return_target | 859.263807 | 2539.755028 | 47 | volatile |
| 4 | alpha_return_target | 2807.062467 | 3125.953618 | 46 | volatile |
| 5 | alpha_return_target | 3066.843374 | 5003.345233 | 44 | trending |
| 6 | alpha_return_target | 4621.066976 | 5531.200894 | 45 | volatile |
| 7 | alpha_return_target | 4575.636120 | 3469.357522 | 46 | volatile |
| 8 | alpha_return_target | 7802.607083 | 696.435626 | 44 | volatile |
| 9 | alpha_return_target | 5186.309131 | 1873.992211 | 41 | trending |
| 10 | alpha_return_target | 4757.148570 | 3099.753628 | 40 | calm |
| 11 | alpha_return_target | 1666.986373 | 2400.483395 | 40 | trending |
| 12 | alpha_return_target | 3364.109625 | 514.158409 | 38 | volatile |
| 13 | alpha_return_target | 3400.918891 | 2468.850032 | 41 | calm |
| 14 | alpha_return_target | 2243.537821 | 2767.857179 | 43 | calm |
| 15 | alpha_return_target | 1774.206298 | 762.083824 | 31 | volatile |
| 16 | alpha_return_target | 2943.391939 | 373.166565 | 33 | volatile |
| 17 | alpha_return_target | 2554.407205 | 397.603367 | 35 | volatile |
| 18 | alpha_return_target | 1034.159882 | 377.789079 | 31 | volatile |
| 19 | alpha_return_target | 396.522312 | 1848.758630 | 40 | calm |
| 20 | alpha_return_target | 537.909815 | 2168.213379 | 48 | calm |
| 21 | alpha_return_target | 1684.320526 | 947.845013 | 49 | trending |
| 22 | alpha_return_target | 2212.932868 | 171.440606 | 38 | volatile |
| 23 | alpha_return_target | 2143.132131 | 1025.364429 | 36 | volatile |
| 24 | alpha_return_target | 739.425672 | 1663.945214 | 36 | volatile |
| 25 | alpha_return_target | 1623.811350 | 1416.194627 | 34 | volatile |
| 26 | alpha_return_target | 1334.873985 | 298.066931 | 40 | volatile |
| 27 | alpha_plus | 2214.635320 | -1524.946270 | 45 | trending |
| 28 | alpha_plus | 1269.443595 | -449.000793 | 45 | trending |
| 29 | alpha_carry_confirmed | -308.213055 | 565.834315 | 31 | trending |
| 30 | alpha_carry_confirmed | 38.812768 | 628.389505 | 27 | trending |
| 31 | alpha_defensive | -35.082251 | 116.375346 | 41 | calm |
| 32 | alpha_return_target | 2218.219543 | 3803.713783 | 43 | calm |
| 33 | alpha_return_target | 1210.128785 | 6632.925882 | 43 | calm |
| 34 | alpha_return_target | 2756.624331 | 4005.924669 | 38 | volatile |
| 35 | alpha_return_target | 6256.918642 | 4158.526163 | 36 | volatile |
| 36 | alpha_return_target | 7125.117615 | 9110.155212 | 40 | calm |
| 37 | alpha_return_target | 6308.203463 | 11785.118399 | 40 | calm |
| 38 | alpha_return_target | 8701.843751 | 10728.659609 | 38 | calm |
| 39 | alpha_return_target | 15908.341409 | 4762.863006 | 36 | trending |
| 40 | alpha_return_target | 15934.553609 | 840.661604 | 38 | trending |
| 41 | alpha_return_target | 10349.573309 | 916.197573 | 38 | calm |
| 42 | alpha_return_target | 4954.598345 | 256.358925 | 34 | volatile |
| 43 | alpha_return_target | 983.788541 | -40.061900 | 29 | volatile |
| 44 | alpha_return_target | 432.043900 | 869.636632 | 36 | trending |
| 45 | alpha_return_target | 52.341039 | 1096.410916 | 39 | calm |
| 46 | alpha_return_target | 326.784018 | 372.462774 | 34 | calm |
| 47 | alpha_return_target | 743.162628 | 1133.343886 | 41 | calm |
| 48 | alpha_carry_confirmed | 773.463443 | 361.566617 | 26 | calm |
| 49 | alpha_return_target | 1354.653927 | -1345.518120 | 34 | calm |
| 50 | alpha_plus | 184.958503 | -142.038552 | 46 | trending |
| 51 | alpha_carry_confirmed | -163.272263 | 405.108961 | 25 | calm |
| 52 | alpha_carry_confirmed | -102.379361 | 467.616704 | 22 | calm |
| 53 | alpha_defensive | -26.335063 | 845.394155 | 37 | calm |
| 54 | alpha_return_target | 1203.563042 | 1249.235674 | 38 | trending |
| 55 | alpha_return_target | 1778.975625 | 1372.485610 | 45 | calm |
| 56 | alpha_return_target | 1752.010904 | 439.002988 | 44 | calm |
| 57 | alpha_return_target | 1756.439774 | -490.096127 | 40 | volatile |
| 58 | alpha_plus | 423.410887 | 697.686136 | 45 | volatile |
| 59 | alpha_carry_confirmed | 267.894906 | 829.062634 | 26 | calm |
| 60 | alpha_carry_confirmed | 330.006502 | 787.225279 | 27 | trending |
| 61 | alpha_return_target | 1786.338440 | 1162.998265 | 47 | trending |
| 62 | alpha_return_target | 2976.621052 | 503.885601 | 46 | calm |
| 63 | alpha_return_target | 2027.783377 | 426.417409 | 40 | calm |
| 64 | alpha_return_target | 923.507185 | 2.821214 | 36 | calm |
| 65 | alpha_carry_confirmed | 724.102302 | -15.496872 | 24 | trending |
| 66 | alpha_carry_confirmed | 621.070772 | 557.974833 | 22 | trending |
| 67 | alpha_carry_confirmed | 162.414027 | 856.558981 | 21 | trending |
| 68 | alpha_carry_confirmed | 311.846854 | 1661.468122 | 30 | calm |
| 69 | alpha_carry_confirmed | 858.629098 | 1544.230984 | 26 | calm |
| 70 | alpha_return_target | 4341.674138 | 915.422145 | 27 | calm |
| 71 | alpha_return_target | 4488.707671 | 1039.132391 | 37 | calm |
| 72 | alpha_return_target | 4322.596628 | 1212.266416 | 43 | calm |
| 73 | alpha_return_target | 1528.034988 | 1790.190506 | 44 | calm |
| 74 | alpha_return_target | 1737.680443 | 1366.437419 | 38 | trending |
| 75 | alpha_return_target | 1862.052021 | 632.884070 | 32 | calm |
| 76 | alpha_return_target | 1980.017066 | -136.677246 | 30 | calm |
| 77 | alpha_return_target | 1463.782944 | -406.150796 | 25 | volatile |
| 78 | alpha_vol_breakout_guard | -6.632923 | 123.965790 | 30 | volatile |
| 79 | alpha_current | -231.190332 | 149.497862 | 36 | calm |
| 80 | alpha_defensive | -6.058555 | 301.622511 | 34 | calm |
| 81 | alpha_defensive | 17.609430 | 828.548769 | 37 | calm |
| 82 | alpha_return_target | 718.842201 | 2667.859453 | 39 | trending |
| 83 | alpha_return_target | 1233.796033 | 2092.458868 | 33 | trending |
| 84 | alpha_return_target | 3125.198415 | 762.669967 | 39 | trending |
| 85 | alpha_return_target | 2687.862435 | 809.828338 | 43 | trending |
| 86 | alpha_return_target | 2117.871065 | 607.123509 | 37 | calm |
| 87 | alpha_return_target | 827.227886 | 1648.778665 | 39 | calm |
| 88 | alpha_return_target | 947.078696 | 1370.221282 | 36 | calm |
| 89 | alpha_return_target | 1569.349560 | 221.981896 | 35 | calm |
| 90 | alpha_return_target | 1302.528528 | 1008.335378 | 31 | calm |
| 91 | alpha_return_target | 1329.072234 | 769.394571 | 20 | volatile |
| 92 | alpha_plus | 637.759402 | 445.518430 | 25 | volatile |
| 93 | alpha_return_target | 933.686147 | 130.815452 | 32 | calm |
| 94 | alpha_return_target | 1191.187521 | -53.686684 | 33 | trending |
| 95 | alpha_current | -105.920145 | 339.742660 | 36 | trending |
| 96 | alpha_plus | 169.046797 | 408.627993 | 34 | calm |
| 97 | alpha_current | -41.603769 | 370.673810 | 36 | calm |
| 98 | alpha_return_target | 667.194577 | 783.945148 | 36 | calm |
| 99 | alpha_return_target | 884.922991 | 816.826663 | 31 | calm |
| 100 | alpha_return_target | 947.780834 | 783.347418 | 32 | calm |
| 101 | alpha_return_target | 1116.076459 | 463.477811 | 35 | calm |
| 102 | alpha_return_target | 1025.878197 | 35.093748 | 35 | calm |
| 103 | alpha_return_target | 840.966953 | 110.638300 | 39 | calm |
| 104 | alpha_plus | 167.819967 | 595.223394 | 40 | calm |
| 105 | alpha_plus | 112.417900 | 427.302045 | 28 | calm |
| 106 | alpha_return_target | 366.953568 | 164.618084 | 25 | calm |
| 107 | alpha_return_target | 506.438935 | 108.157051 | 30 | calm |
| 108 | alpha_return_target | 570.735785 | -136.599696 | 25 | trending |
| 109 | alpha_carry_confirmed | 6.144359 | -46.006503 | 20 | calm |
| 110 | alpha_current | -13.527749 | -338.785480 | 33 | calm |
| 111 | alpha_carry_confirmed | -190.230089 | 70.526870 | 25 | calm |
| 112 | alpha_carry_confirmed | -504.653896 | 221.747764 | 22 | calm |
| 113 | alpha_carry_confirmed | -151.288505 | -105.740170 | 10 | volatile |
| 114 | alpha_return_target | 503.961224 | -390.244516 | 19 | volatile |
| 115 | alpha_return_target | 134.329702 | 51.874868 | 28 | calm |
| 116 | alpha_defensive | -108.685313 | 163.135643 | 31 | calm |
| 117 | alpha_defensive | -171.376763 | 152.598992 | 39 | calm |
| 118 | alpha_defensive | -22.008394 | 121.506686 | 40 | trending |
