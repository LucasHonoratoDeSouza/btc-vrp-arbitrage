from __future__ import annotations

from typing import List

import pandas as pd

from .config import BacktestConfig
from .types import SmilePoint


def rolling_kurtosis(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window).kurt()


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std(ddof=1)
    return (series - mean) / std


def select_strategy(kurtosis_value: float, config: BacktestConfig) -> str:
    return "iron_condor" if kurtosis_value >= config.kurtosis_high else "short_strangle"


def compute_vrp_signal(smile_points: List[SmilePoint], rv_forecast: pd.Series) -> pd.Series:
    if not smile_points:
        return pd.Series(dtype=float, name="vrp")
    df = pd.DataFrame(
        {
            "timestamp": [p.timestamp for p in smile_points],
            "iv": [p.iv for p in smile_points],
        }
    )
    df = df.groupby("timestamp", as_index=True)["iv"].median().to_frame()
    merged = df.join(rv_forecast, how="left")
    merged["vrp"] = merged["iv"] - merged["rv_forecast"]
    return merged["vrp"]
