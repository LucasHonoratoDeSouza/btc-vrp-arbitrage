from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import BacktestConfig


def monte_carlo_robustness(
    ohlc_df: pd.DataFrame,
    options_df: pd.DataFrame,
    config: BacktestConfig,
    iv_series: pd.Series | None = None,
    n_sims: int = 1000,
    seed: int | None = None,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(n_sims):
        perturbed = BacktestConfig(**config.__dict__)
        perturbed.vrp_entry_z = max(0.0, config.vrp_entry_z + rng.normal(0, 0.2))
        perturbed.kurtosis_high = max(2.5, config.kurtosis_high + rng.normal(0, 0.3))
        bt = run_backtest(ohlc_df, options_df, perturbed, iv_series=iv_series)
        results.append(bt.metrics)
    return pd.DataFrame(results)
