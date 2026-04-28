from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import BacktestConfig
from .data import log_returns, normalize_option_type
from .pricing import bs_delta, bs_gamma, bs_vega, implied_vol
from .signals import zscore
from .volatility import rolling_ewma_forecast, rolling_garch_forecast


def rolling_percentile_rank(series: pd.Series, window: int) -> pd.Series:
    def rank_last(values: np.ndarray) -> float:
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return np.nan
        return float(np.mean(values <= values[-1]))

    return series.rolling(window, min_periods=max(12, window // 4)).apply(
        rank_last, raw=True
    )


def _annualized_realized_vol(returns: pd.Series, window: int) -> pd.Series:
    vol = returns.shift(1).rolling(window, min_periods=max(12, window // 3)).std(ddof=1)
    return (vol * math.sqrt(365.0 * 24.0)).rename(f"realized_vol_{window}h")


def _forward_realized_vol(returns: pd.Series, horizon: int) -> pd.Series:
    shifted = returns.shift(-1)
    vol = shifted.rolling(horizon, min_periods=horizon).std(ddof=1).shift(-(horizon - 1))
    return (vol * math.sqrt(365.0 * 24.0)).rename(f"future_rv_{horizon}h")


def _normalize_iv_series(iv_series: pd.Series) -> pd.Series:
    iv = iv_series.astype(float).sort_index().copy()
    if not iv.empty and float(iv.dropna().median()) > 3.0:
        iv = iv / 100.0
    return iv


def build_research_dataset(
    ohlc_df: pd.DataFrame,
    iv_series: pd.Series,
    config: BacktestConfig | None = None,
) -> pd.DataFrame:
    config = config or BacktestConfig()
    ohlc = ohlc_df.copy()
    ohlc["timestamp"] = pd.to_datetime(ohlc["timestamp"], utc=True)
    ohlc = ohlc.sort_values("timestamp")
    timestamps = pd.DatetimeIndex(ohlc["timestamp"])

    close = pd.Series(ohlc["close"].to_numpy(dtype=float), index=timestamps, name="close")
    volume = pd.Series(
        ohlc.get("volume", pd.Series(np.nan, index=ohlc.index)).to_numpy(dtype=float),
        index=timestamps,
        name="volume",
    )
    returns = log_returns(close)
    returns.index = timestamps

    weight = float(np.clip(config.garch_weight, 0.0, 1.0))
    if weight > 0.0:
        garch_forecast = rolling_garch_forecast(
            returns,
            config.garch_window_hours,
            config.forecast_horizon_hours,
            config.garch_refit_interval_hours,
            config.min_annual_vol,
            config.max_annual_vol,
        ).rename("rv_garch")
    else:
        garch_forecast = pd.Series(np.nan, index=returns.index, name="rv_garch")
    if weight < 1.0:
        ewma_forecast = rolling_ewma_forecast(
            returns,
            config.ewma_span_hours,
            config.min_annual_vol,
            config.max_annual_vol,
        ).rename("rv_ewma")
    else:
        ewma_forecast = pd.Series(np.nan, index=returns.index, name="rv_ewma")
    if weight <= 0.0:
        rv_forecast = ewma_forecast.copy()
    elif weight >= 1.0:
        rv_forecast = garch_forecast.copy()
    else:
        rv_forecast = weight * garch_forecast + (1.0 - weight) * ewma_forecast
    rv_forecast = rv_forecast.rename("rv_forecast")

    iv = _normalize_iv_series(iv_series)
    iv.index = pd.to_datetime(iv.index, utc=True)
    iv = iv.reindex(timestamps).ffill().rename("iv")
    vrp = (iv - rv_forecast).rename("vrp")

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": close.values,
            "volume": volume.values,
            "returns": returns.values,
            "iv": iv.values,
            "rv_garch": garch_forecast.values,
            "rv_ewma": ewma_forecast.values,
            "rv_forecast": rv_forecast.values,
            "vrp": vrp.values,
            "vrp_z": zscore(vrp, config.zscore_window).values,
            "iv_rank_30d": rolling_percentile_rank(iv.shift(1), 24 * 30).values,
            "vrp_rank_30d": rolling_percentile_rank(vrp.shift(1), 24 * 30).values,
            "abs_return_24h": np.log(close).diff(24).abs().shift(1).values,
            "trend_24h": np.log(close).diff(24).shift(1).values,
            "trend_72h": np.log(close).diff(72).shift(1).values,
            "volume_z_7d": zscore(volume.shift(1), 24 * 7).values,
        }
    ).set_index("timestamp")

    for window in [24, 72, 168, 336]:
        df[f"realized_vol_{window}h"] = _annualized_realized_vol(
            returns, window
        ).values
    df["rv_slope_24_168"] = df["realized_vol_24h"] - df["realized_vol_168h"]
    df["carry_score"] = df["vrp"] / df["rv_forecast"].replace(0.0, np.nan)

    for horizon in [24, 72, 168]:
        label = _forward_realized_vol(returns, horizon)
        df[label.name] = label.values
        df[f"forward_edge_{horizon}h"] = df["iv"] - df[label.name]

    return df.reset_index()


def enrich_option_history(options_df: pd.DataFrame, rate: float = 0.0) -> pd.DataFrame:
    df = options_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["expiry"] = pd.to_datetime(df["expiry"], utc=True)
    df["option_type"] = df["option_type"].apply(normalize_option_type)
    for column in ["bid", "ask", "mark", "underlying", "strike"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp", "expiry", "bid", "ask", "underlying", "strike"])
    df = df[(df["bid"] > 0.0) & (df["ask"] > 0.0) & (df["ask"] >= df["bid"])]

    df["mid"] = df["mark"].where(df["mark"] > 0.0, (df["bid"] + df["ask"]) * 0.5)
    df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"].replace(0.0, np.nan)
    df["time_years"] = (df["expiry"] - df["timestamp"]).dt.total_seconds() / (
        365.0 * 24.0 * 3600.0
    )
    df = df[(df["mid"] > 0.0) & (df["time_years"] > 0.0)]

    df["mark_iv"] = [
        implied_vol(price, spot, strike, time_years, rate, option_type)
        for price, spot, strike, time_years, option_type in zip(
            df["mid"],
            df["underlying"],
            df["strike"],
            df["time_years"],
            df["option_type"],
        )
    ]
    df["delta"] = [
        bs_delta(spot, strike, time_years, rate, vol, option_type)
        for spot, strike, time_years, vol, option_type in zip(
            df["underlying"],
            df["strike"],
            df["time_years"],
            df["mark_iv"],
            df["option_type"],
        )
    ]
    df["gamma"] = [
        bs_gamma(spot, strike, time_years, rate, vol)
        for spot, strike, time_years, vol in zip(
            df["underlying"], df["strike"], df["time_years"], df["mark_iv"]
        )
    ]
    df["vega"] = [
        bs_vega(spot, strike, time_years, rate, vol)
        for spot, strike, time_years, vol in zip(
            df["underlying"], df["strike"], df["time_years"], df["mark_iv"]
        )
    ]
    return df.sort_values(["timestamp", "expiry", "strike", "option_type"])
