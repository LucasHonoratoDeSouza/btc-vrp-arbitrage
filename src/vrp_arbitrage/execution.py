from __future__ import annotations

from typing import Optional

import pandas as pd


def pick_by_delta(df: pd.DataFrame, target_delta: float) -> Optional[pd.Series]:
    if "delta" not in df.columns:
        return None
    idx = (df["delta"] - target_delta).abs().idxmin()
    return df.loc[idx]


def post_only_price(side: str, best_bid: float, best_ask: float, tick_size: float) -> float:
    if side == "buy":
        price = min(best_bid, best_ask - tick_size)
    else:
        price = max(best_ask, best_bid + tick_size)
    return price


def simulate_post_only_fill(
    side: str,
    best_bid: float,
    best_ask: float,
    target_price: float,
    next_best_bid: float,
    next_best_ask: float,
) -> bool:
    if side == "buy":
        return next_best_ask <= target_price
    return next_best_bid >= target_price
