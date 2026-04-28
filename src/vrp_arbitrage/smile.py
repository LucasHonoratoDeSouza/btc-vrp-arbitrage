from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy.interpolate import UnivariateSpline

from .pricing import implied_vol
from .types import SmilePoint


def compute_iv_smile(df: pd.DataFrame, rate: float) -> pd.DataFrame:
    df = df.copy()
    mid = (df["bid"] + df["ask"]) * 0.5
    time_years = (df["expiry"] - df["timestamp"]).dt.total_seconds() / (365.0 * 24.0 * 3600.0)
    df["iv"] = [
        implied_vol(p, s, k, t, rate, opt)
        for p, s, k, t, opt in zip(
            mid, df["underlying"], df["strike"], time_years, df["option_type"]
        )
    ]
    return df


def find_min_convexity_point(smile_df: pd.DataFrame, rate: float) -> Optional[SmilePoint]:
    if smile_df.empty:
        return None

    spot = float(smile_df["underlying"].iloc[0])
    expiry = smile_df["expiry"].iloc[0]
    time_years = (expiry - smile_df["timestamp"].iloc[0]).total_seconds() / (365.0 * 24.0 * 3600.0)
    forward = spot * math.exp(rate * time_years)

    curve = smile_df[["strike", "iv"]].dropna()
    curve = curve[curve["iv"] > 0]
    curve = curve.groupby("strike", as_index=False)["iv"].median().sort_values("strike")
    moneyness = np.log(curve["strike"].to_numpy() / forward)
    iv = curve["iv"].to_numpy()

    if len(iv) < 6:
        return None

    spline = UnivariateSpline(moneyness, iv, k=3, s=0.001)
    grid = np.linspace(moneyness.min(), moneyness.max(), 200)
    convexity = spline.derivative(n=2)(grid)
    idx = int(np.argmin(np.abs(convexity)))
    k_star = float(grid[idx])
    strike_star = float(forward * math.exp(k_star))
    iv_star = float(spline(k_star))

    return SmilePoint(
        timestamp=smile_df["timestamp"].iloc[0],
        expiry=expiry,
        strike=strike_star,
        iv=iv_star,
        convexity=float(convexity[idx]),
        forward=forward,
    )


def find_atm_point(smile_df: pd.DataFrame, rate: float) -> Optional[SmilePoint]:
    if smile_df.empty:
        return None

    spot = float(smile_df["underlying"].iloc[0])
    expiry = smile_df["expiry"].iloc[0]
    time_years = (expiry - smile_df["timestamp"].iloc[0]).total_seconds() / (
        365.0 * 24.0 * 3600.0
    )
    forward = spot * math.exp(rate * time_years)

    moneyness = np.log(smile_df["strike"].to_numpy() / forward)
    iv = smile_df["iv"].to_numpy()
    if len(iv) == 0:
        return None
    idx = int(np.argmin(np.abs(moneyness)))
    strike_star = float(smile_df["strike"].iloc[idx])
    iv_star = float(iv[idx])

    return SmilePoint(
        timestamp=smile_df["timestamp"].iloc[0],
        expiry=expiry,
        strike=strike_star,
        iv=iv_star,
        convexity=0.0,
        forward=forward,
    )


def compute_smile_points(options_df: pd.DataFrame, rate: float) -> List[SmilePoint]:
    points = []
    for (ts, expiry), group in options_df.groupby(["timestamp", "expiry"]):
        group = compute_iv_smile(group, rate)
        point = find_min_convexity_point(group, rate)
        if point is None:
            point = find_atm_point(group, rate)
        if point:
            points.append(point)
    return points
