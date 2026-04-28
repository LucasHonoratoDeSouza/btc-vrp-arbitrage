from __future__ import annotations

import math

from scipy import optimize
from scipy.stats import norm


def _d1_d2(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
) -> tuple[float, float]:
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol ** 2) * time_years) / (
        vol * math.sqrt(time_years)
    )
    d2 = d1 - vol * math.sqrt(time_years)
    return d1, d2


def black_scholes_price(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    if time_years <= 0 or vol <= 0:
        intrinsic = max(0.0, spot - strike) if option_type == "C" else max(0.0, strike - spot)
        return intrinsic
    d1, d2 = _d1_d2(spot, strike, time_years, rate, vol)
    if option_type == "C":
        return spot * norm.cdf(d1) - strike * math.exp(-rate * time_years) * norm.cdf(d2)
    return strike * math.exp(-rate * time_years) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def implied_vol(
    price: float,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    option_type: str,
    tol: float = 1e-6,
) -> float:
    if price <= 0 or time_years <= 0:
        return 0.0

    def objective(v: float) -> float:
        return black_scholes_price(spot, strike, time_years, rate, v, option_type) - price

    try:
        return optimize.brentq(objective, 1e-6, 5.0, xtol=tol)
    except ValueError:
        return 0.0


def bs_delta(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    if time_years <= 0 or vol <= 0:
        if option_type == "C":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    d1, _ = _d1_d2(spot, strike, time_years, rate, vol)
    if option_type == "C":
        return float(norm.cdf(d1))
    return float(norm.cdf(d1) - 1.0)


def bs_vega(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
) -> float:
    if time_years <= 0 or vol <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, time_years, rate, vol)
    return float(spot * norm.pdf(d1) * math.sqrt(time_years))


def bs_gamma(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    vol: float,
) -> float:
    if time_years <= 0 or vol <= 0 or spot <= 0:
        return 0.0
    d1, _ = _d1_d2(spot, strike, time_years, rate, vol)
    return float(norm.pdf(d1) / (spot * vol * math.sqrt(time_years)))
