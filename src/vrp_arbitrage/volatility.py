from __future__ import annotations

import math
from typing import Tuple

import numpy as np
import pandas as pd
from scipy import optimize


def annualized_vol_from_hourly(var_per_hour: float) -> float:
    hours_per_year = 365.0 * 24.0
    return math.sqrt(var_per_hour * hours_per_year)


def garch11_neg_loglik(params: np.ndarray, returns: np.ndarray) -> float:
    omega, alpha, beta = params
    if omega <= 0 or alpha < 0 or beta < 0 or (alpha + beta) >= 0.999:
        return 1e12

    var = np.empty_like(returns)
    var[0] = np.var(returns, ddof=1) if len(returns) > 1 else 1e-6
    for t in range(1, len(returns)):
        var[t] = omega + alpha * returns[t - 1] ** 2 + beta * var[t - 1]
        if var[t] <= 0:
            return 1e12

    ll = -0.5 * (np.log(2.0 * np.pi) + np.log(var) + (returns ** 2) / var)
    return -float(np.sum(ll))


def fit_garch11(returns: pd.Series) -> Tuple[float, float, float]:
    x = returns.dropna().to_numpy()
    if len(x) < 50:
        return 1e-6, 0.05, 0.9

    sample_var = max(float(np.var(x, ddof=1)), 1e-10)
    init = np.array([sample_var * 0.05, 0.05, 0.9])
    bounds = [(1e-12, max(sample_var * 10.0, 1e-4)), (0.0, 1.0), (0.0, 1.0)]
    result = optimize.minimize(
        garch11_neg_loglik,
        init,
        args=(x,),
        bounds=bounds,
        method="L-BFGS-B",
        options={"maxiter": 120},
    )
    if not result.success:
        return sample_var * 0.05, 0.05, 0.9
    omega, alpha, beta = result.x
    if (alpha + beta) >= 0.999:
        beta = max(0.0, 0.98 - alpha)
    return float(omega), float(alpha), float(beta)


def _last_conditional_variance(
    returns: pd.Series, omega: float, alpha: float, beta: float
) -> float:
    x = returns.dropna().to_numpy()
    if len(x) == 0:
        return 0.0

    var = np.empty_like(x)
    var[0] = np.var(x, ddof=1) if len(x) > 1 else max(x[0] ** 2, 1e-10)
    for t in range(1, len(x)):
        var[t] = omega + alpha * x[t - 1] ** 2 + beta * var[t - 1]
    return float(max(omega + alpha * x[-1] ** 2 + beta * var[-1], 1e-12))


def forecast_garch11_vol_from_params(
    returns: pd.Series,
    params: Tuple[float, float, float],
    horizon_hours: int,
) -> Tuple[float, float]:
    omega, alpha, beta = params
    phi = alpha + beta
    if phi <= 0:
        return 0.0, 0.0

    var_t = _last_conditional_variance(returns, omega, alpha, beta)
    long_run_var = omega / (1.0 - phi)
    steps = np.arange(horizon_hours)
    var_path = long_run_var + (var_t - long_run_var) * (phi ** steps)
    mean_var = float(np.mean(var_path))
    return annualized_vol_from_hourly(mean_var), mean_var


def forecast_garch11_vol(returns: pd.Series, horizon_hours: int) -> Tuple[float, float]:
    params = fit_garch11(returns)
    return forecast_garch11_vol_from_params(returns, params, horizon_hours)


def rolling_garch_forecast(
    returns: pd.Series,
    window: int,
    horizon_hours: int,
    refit_interval: int = 24,
    min_vol: float = 0.05,
    max_vol: float = 3.0,
) -> pd.Series:
    out = []
    idx = returns.index
    params: Tuple[float, float, float] | None = None
    refit_interval = max(1, int(refit_interval))

    for i in range(len(returns)):
        if i < window:
            out.append(np.nan)
            continue

        window_slice = returns.iloc[i - window : i]
        if params is None or ((i - window) % refit_interval) == 0:
            params = fit_garch11(window_slice)
        vol, _ = forecast_garch11_vol_from_params(window_slice, params, horizon_hours)
        if vol > 0:
            vol = float(np.clip(vol, min_vol, max_vol))
        out.append(vol)

    return pd.Series(out, index=idx, name="rv_forecast")


def rolling_ewma_forecast(
    returns: pd.Series,
    span_hours: int,
    min_vol: float = 0.05,
    max_vol: float = 3.0,
) -> pd.Series:
    hourly_var = returns.pow(2).ewm(span=span_hours, adjust=False, min_periods=max(12, span_hours // 4)).mean()
    vol = np.sqrt(hourly_var * 365.0 * 24.0).shift(1)
    vol = vol.clip(lower=min_vol, upper=max_vol)
    return vol.rename("rv_ewma_forecast")
