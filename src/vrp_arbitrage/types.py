from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass
class SmilePoint:
    timestamp: pd.Timestamp
    expiry: pd.Timestamp
    strike: float
    iv: float
    convexity: float
    forward: float


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    strategy: str
    pnl: float
    vega: float
    vrp_at_entry: float
    iv_at_entry: float
    rv_forecast_at_entry: float
    notional: float = 1.0
    fees: float = 0.0
    hedge_cost: float = 0.0
    stress_pnl: float = 0.0


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: List[Trade]
    metrics: Dict[str, float]
    diagnostics: List[str]


@dataclass
class OptionSpec:
    expiry: pd.Timestamp
    strike: float
    option_type: str
    side: str


@dataclass
class OptionLeg:
    expiry: pd.Timestamp
    strike: float
    option_type: str
    side: str
    qty: float
    entry_price: float
    entry_iv: float
    entry_delta: float
    entry_vega: float


@dataclass
class Position:
    entry_time: pd.Timestamp
    strategy: str
    legs: List[OptionLeg]
    hedge_qty: float
    entry_vrp: float
    entry_iv: float
    entry_rv: float
    entry_vega: float
    entry_cash: float
    entry_cash_flow: float = 0.0
    entry_spot: float = 0.0
    entry_fees: float = 0.0
    hedge_cost: float = 0.0
    margin_required: float = 0.0


@dataclass
class PendingEntry:
    activate_time: pd.Timestamp
    strategy: str
    legs: List[OptionLeg]
    entry_vrp: float
    entry_iv: float
    entry_rv: float
