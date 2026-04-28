"""
Central strategy catalog.

All BacktestConfig definitions live here. Scripts import from this module
instead of defining configs inline. Each entry carries metadata (risk_bucket,
purpose, oos_evidence) so future runs stay interpretable without digging
through git history.

risk_bucket values: "conservative" | "balanced" | "aggressive" | "research"

oos_evidence is populated from regime_validation runs. These are research
diagnostics from overlapping 30-day windows, not proof of live tradability. Keys:
  dataset, test_windows, avg_return_pct, pct_positive, avg_sharpe, min_pnl,
  validation_date (YYYY-MM-DD)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig


@dataclass
class StrategyEntry:
    name: str
    config: BacktestConfig
    risk_bucket: str
    purpose: str
    validate: bool = True  # include in regime_validation candidate set
    oos_evidence: dict[str, Any] = field(default_factory=dict)


def _base(**overrides) -> BacktestConfig:
    """Base EWMA-only VRP config; garch_weight=0 bypasses GARCH entirely."""
    params = dict(
        use_variance_proxy=True,
        garch_window_hours=24 * 7,
        garch_refit_interval_hours=72,
        ewma_span_hours=48,
        garch_weight=0.0,
        zscore_window=72,
        vrp_entry_z=0.35,
        vrp_exit_z=0.2,
        min_vrp_edge=0.025,
        require_z_and_quantile=False,
        signal_confirmation_periods=2,
        cooldown_hours=3,
        max_holding_hours=6,
        variance_notional=100.0,
        kelly_fraction=0.75,
        max_contracts=1000.0,
        max_trade_stress_loss_pct=0.08,
        max_rv_percentile=0.90,
        max_abs_24h_return=0.12,
        vrp_entry_quantile=0.60,
        variance_trade_cost=0.0008,
    )
    params.update(overrides)
    return BacktestConfig(**params)


# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

CATALOG: list[StrategyEntry] = [
    # -- VALIDATED PROXY CANDIDATES ------------------------------------------
    StrategyEntry(
        name="alpha_return_target",
        config=_base(
            variance_notional=180.0,
            max_trade_stress_loss_pct=0.12,
            min_vrp_edge=0.030,
            max_abs_24h_return=0.10,
            max_rv_percentile=0.85,
        ),
        risk_bucket="aggressive",
        purpose="Primary research candidate. Higher notional + tighter RV filter for maximum proxy VRP capture.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 13.638,
            "median_return_pct": 7.806,
            "pct_positive": 89.1,
            "avg_sharpe": 3.73,
            "min_pnl": -2281.04,
            "total_pnl": 162294.22,
            "validation_date": "2026-04-28",
            "notes": "Overlapping 30-day walk-forward diagnostics only; not live execution evidence.",
        },
    ),
    # ── BALANCED CANDIDATES ───────────────────────────────────────────────────
    StrategyEntry(
        name="alpha_current",
        config=_base(),
        risk_bucket="balanced",
        purpose="Baseline EWMA VRP. Reference point for comparing candidate improvements.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 7.573,
            "median_return_pct": 4.357,
            "pct_positive": 86.6,
            "avg_sharpe": 3.70,
            "min_pnl": -1016.63,
            "total_pnl": 90123.57,
            "validation_date": "2026-04-28",
        },
    ),
    StrategyEntry(
        name="alpha_plus",
        config=_base(
            variance_notional=150.0,
            max_trade_stress_loss_pct=0.10,
        ),
        risk_bucket="balanced",
        purpose="Moderate notional increase over alpha_current. Good risk/return tradeoff.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 11.285,
            "median_return_pct": 6.535,
            "pct_positive": 86.6,
            "avg_sharpe": 3.72,
            "min_pnl": -1524.95,
            "total_pnl": 134294.76,
            "validation_date": "2026-04-28",
        },
    ),
    StrategyEntry(
        name="alpha_vol_breakout_guard",
        config=_base(
            max_abs_24h_return=0.08,
            max_rv_percentile=0.75,
            min_vrp_edge=0.030,
            variance_notional=120.0,
            max_trade_stress_loss_pct=0.08,
        ),
        risk_bucket="balanced",
        purpose="Tighter vol-regime filter reduces drawdown in volatile windows.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 9.192,
            "median_return_pct": 5.204,
            "pct_positive": 89.1,
            "avg_sharpe": 3.74,
            "min_pnl": -897.01,
            "total_pnl": 109387.87,
            "validation_date": "2026-04-28",
        },
    ),
    StrategyEntry(
        name="alpha_defensive",
        config=_base(
            min_vrp_edge=0.035,
            max_trade_stress_loss_pct=0.06,
            variance_notional=90.0,
        ),
        risk_bucket="conservative",
        purpose="Lower notional and higher edge threshold. Suitable for risk-averse sizing.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 6.757,
            "median_return_pct": 3.874,
            "pct_positive": 87.4,
            "avg_sharpe": 3.64,
            "min_pnl": -893.34,
            "total_pnl": 80411.19,
            "validation_date": "2026-04-28",
        },
    ),
    # ── RESEARCH / FAILED CANDIDATES ─────────────────────────────────────────
    StrategyEntry(
        name="alpha_carry_confirmed",
        config=_base(
            require_z_and_quantile=True,
            signal_confirmation_periods=1,
            vrp_entry_quantile=0.70,
            max_holding_hours=12,
            variance_notional=120.0,
            max_trade_stress_loss_pct=0.08,
        ),
        risk_bucket="research",
        purpose="Stricter signal confirmation. Inferior risk-adjusted proxy result — do not promote.",
        oos_evidence={
            "dataset": "5y DVOL real — Mar-2021 to Apr-2026 (Deribit)",
            "test_windows": 119,
            "window_days": 30,
            "avg_return_pct": 4.101,
            "median_return_pct": 2.817,
            "pct_positive": 80.7,
            "avg_sharpe": 2.77,
            "min_pnl": -2262.13,
            "total_pnl": 48801.96,
            "validation_date": "2026-04-28",
            "notes": "Inferior risk-adjusted result and worst min PnL after corrected accounting.",
        },
    ),
    # ── GARCH-HYBRID PROFILES (run_strategy_profiles.py only) ────────────────
    StrategyEntry(
        name="adaptive_alpha",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 7,
            garch_refit_interval_hours=72,
            ewma_span_hours=48,
            garch_weight=0.35,
            zscore_window=72,
            vrp_entry_z=0.35,
            vrp_exit_z=0.2,
            min_vrp_edge=0.025,
            require_z_and_quantile=False,
            signal_confirmation_periods=2,
            cooldown_hours=3,
            max_holding_hours=6,
            variance_notional=100.0,
            kelly_fraction=0.75,
            max_contracts=1000.0,
            max_trade_stress_loss_pct=0.08,
            max_rv_percentile=0.90,
            max_abs_24h_return=0.12,
            vrp_entry_quantile=0.60,
            variance_trade_cost=0.0008,
        ),
        risk_bucket="balanced",
        purpose="Light GARCH blend (35%). More responsive forecast but slower warmup.",
        oos_evidence={},
    ),
    StrategyEntry(
        name="conservative",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 10,
            garch_refit_interval_hours=72,
            ewma_span_hours=96,
            garch_weight=0.70,
            zscore_window=24 * 5,
            vrp_entry_z=0.8,
            vrp_exit_z=0.2,
            min_vrp_edge=0.04,
            require_z_and_quantile=True,
            signal_confirmation_periods=2,
            cooldown_hours=8,
            max_holding_hours=24 * 3,
            variance_notional=1.0,
            kelly_fraction=0.4,
            max_contracts=10.0,
            max_trade_stress_loss_pct=0.02,
            max_rv_percentile=0.80,
            max_abs_24h_return=0.07,
        ),
        risk_bucket="conservative",
        purpose="Full GARCH + strict filters. Very low notional. Sanity baseline.",
        oos_evidence={},
    ),
    StrategyEntry(
        name="balanced_garch",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 10,
            garch_refit_interval_hours=72,
            ewma_span_hours=72,
            garch_weight=0.65,
            zscore_window=24 * 5,
            vrp_entry_z=0.6,
            vrp_exit_z=0.1,
            min_vrp_edge=0.02,
            require_z_and_quantile=True,
            signal_confirmation_periods=1,
            cooldown_hours=3,
            max_holding_hours=24 * 4,
            variance_notional=10.0,
            kelly_fraction=0.75,
            max_contracts=50.0,
            max_trade_stress_loss_pct=0.06,
            max_rv_percentile=0.90,
            max_abs_24h_return=0.10,
        ),
        risk_bucket="balanced",
        purpose="GARCH 65% blend + moderate notional. Mid-point between conservative and aggressive.",
        oos_evidence={},
    ),
    StrategyEntry(
        name="high_return",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 10,
            garch_refit_interval_hours=72,
            ewma_span_hours=96,
            garch_weight=0.70,
            zscore_window=24 * 5,
            vrp_entry_z=0.8,
            vrp_exit_z=0.2,
            min_vrp_edge=0.04,
            require_z_and_quantile=True,
            signal_confirmation_periods=2,
            cooldown_hours=6,
            max_holding_hours=24 * 3,
            variance_notional=100.0,
            kelly_fraction=1.0,
            max_contracts=1000.0,
            max_trade_stress_loss_pct=0.12,
            max_rv_percentile=0.85,
            max_abs_24h_return=0.10,
            variance_trade_cost=0.0008,
        ),
        risk_bucket="aggressive",
        purpose="GARCH + full Kelly + high notional. Research-grade aggressive GARCH path.",
        oos_evidence={},
    ),
    StrategyEntry(
        name="max_return",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 10,
            garch_refit_interval_hours=72,
            ewma_span_hours=72,
            garch_weight=0.65,
            zscore_window=24 * 5,
            vrp_entry_z=0.6,
            vrp_exit_z=0.2,
            min_vrp_edge=0.02,
            require_z_and_quantile=True,
            signal_confirmation_periods=1,
            cooldown_hours=2,
            max_holding_hours=24 * 3,
            variance_notional=150.0,
            kelly_fraction=1.0,
            max_contracts=1500.0,
            max_trade_stress_loss_pct=0.20,
            max_rv_percentile=0.90,
            max_abs_24h_return=0.12,
            variance_trade_cost=0.0010,
        ),
        risk_bucket="research",
        purpose="Max sizing, minimal constraints. Research bound — not for live use.",
        oos_evidence={},
    ),
    StrategyEntry(
        name="overtrade_aggressive",
        validate=False,
        config=BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 7,
            garch_refit_interval_hours=72,
            ewma_span_hours=48,
            garch_weight=0.55,
            zscore_window=24 * 3,
            vrp_entry_z=0.35,
            vrp_exit_z=0.0,
            min_vrp_edge=0.005,
            require_z_and_quantile=False,
            signal_confirmation_periods=1,
            cooldown_hours=0,
            max_holding_hours=24 * 5,
            variance_notional=50.0,
            kelly_fraction=1.0,
            max_contracts=200.0,
            max_trade_stress_loss_pct=0.15,
            max_rv_percentile=0.98,
            max_abs_24h_return=0.16,
            vrp_entry_quantile=0.55,
            variance_trade_cost=0.0008,
        ),
        risk_bucket="research",
        purpose="Stress-test: near-zero thresholds to find frequency ceiling. Not for production.",
        oos_evidence={},
    ),
]

# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

_BY_NAME: dict[str, StrategyEntry] = {e.name: e for e in CATALOG}


def get_all() -> dict[str, StrategyEntry]:
    return dict(_BY_NAME)


def get_candidates() -> dict[str, BacktestConfig]:
    """Candidates for regime_validation.py — validate=True entries only."""
    return {e.name: e.config for e in CATALOG if e.validate}


def get_profiles() -> dict[str, BacktestConfig]:
    """All profiles for run_strategy_profiles.py."""
    return {e.name: e.config for e in CATALOG}


def get_promoted() -> list[StrategyEntry]:
    """Strategies with validation diagnostics for research reports."""
    return [e for e in CATALOG if e.oos_evidence]
