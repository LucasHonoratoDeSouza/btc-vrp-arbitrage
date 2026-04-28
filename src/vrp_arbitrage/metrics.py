from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
import pandas as pd

from .types import Trade


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max.replace(0.0, np.nan)
    value = float(drawdown.min())
    return value if math.isfinite(value) else 0.0


def sharpe_ratio(returns: pd.Series, periods_per_year: float) -> float:
    mean = returns.mean()
    std = returns.std(ddof=1)
    if std == 0 or math.isnan(std):
        return 0.0
    return float((mean / std) * math.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: float) -> float:
    downside = returns[returns < 0].std(ddof=1)
    if downside == 0 or math.isnan(downside):
        return 0.0
    return float((returns.mean() / downside) * math.sqrt(periods_per_year))


def vrp_capture_efficiency(trades: List[Trade]) -> float:
    if not trades:
        return 0.0
    theoretical = 0.0
    for trade in trades:
        risk_scale = abs(trade.vega) if abs(trade.vega) > 0 else abs(trade.notional)
        theoretical += max(trade.vrp_at_entry, 0.0) * max(risk_scale, 1e-12)
    realized = sum(t.pnl for t in trades)
    if theoretical == 0:
        return 0.0
    return float(realized / theoretical)


def diagnose_backtest(metrics: Dict[str, float]) -> List[str]:
    notes = []
    if metrics.get("sharpe", 0.0) < 1.0:
        notes.append("Sharpe below 1.0: review hedge costs and consider a delta no-trade zone.")
    if metrics.get("max_drawdown", 0.0) < -0.2:
        notes.append("Drawdown elevated: use fractional Kelly sizing and add a vega stop.")
    if metrics.get("vrp_capture_efficiency", 0.0) < 0.2:
        notes.append("Weak signal: add a regime filter (on-chain volume or Fear & Greed).")
    return notes


def stress_test_gap(trades: List[Trade], crash_pct: float = -0.2) -> float:
    if not trades:
        return 0.0
    stressed = [t.stress_pnl for t in trades if t.stress_pnl != 0.0]
    if stressed:
        return float(sum(stressed))
    return float(sum(t.pnl for t in trades) * (1.0 + crash_pct))
