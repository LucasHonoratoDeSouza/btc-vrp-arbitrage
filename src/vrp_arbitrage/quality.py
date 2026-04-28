from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List

import numpy as np
import pandas as pd


@dataclass
class GateCheck:
    category: str
    check: str
    passed: bool
    severity: str
    value: str
    threshold: str
    detail: str


@dataclass
class InstitutionalReport:
    ready: bool
    score: float
    checks: List[GateCheck]
    recommendations: List[str]

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(check) for check in self.checks])


def _add(
    checks: List[GateCheck],
    category: str,
    check: str,
    passed: bool,
    severity: str,
    value: object,
    threshold: object,
    detail: str,
) -> None:
    checks.append(
        GateCheck(
            category=category,
            check=check,
            passed=bool(passed),
            severity=severity,
            value=str(value),
            threshold=str(threshold),
            detail=detail,
        )
    )


def _max_gap_hours(timestamps: pd.Series) -> float:
    if timestamps.empty or len(timestamps) < 2:
        return float("inf")
    diffs = timestamps.sort_values().diff().dropna().dt.total_seconds() / 3600.0
    return float(diffs.max()) if not diffs.empty else float("inf")


def _coverage_days(timestamps: pd.Series) -> float:
    if timestamps.empty:
        return 0.0
    return float((timestamps.max() - timestamps.min()).total_seconds() / 86400.0)


def _recommendations(checks: Iterable[GateCheck]) -> List[str]:
    failed = [check for check in checks if not check.passed]
    recs: List[str] = []
    if any(check.category == "data.options" for check in failed):
        recs.append(
            "Use full historical option-chain snapshots with bid/ask, sizes, volume, open interest, greeks and mark IV for every timestamp."
        )
        recs.append(
            "Do not select instruments from today's live chain for historical backtests; rebuild the tradable universe point-in-time."
        )
    if any(check.category == "sample" for check in failed):
        recs.append(
            "Extend the sample to at least 12 months for research and preferably 24+ months before evaluating tail-sensitive short-vol strategies."
        )
    if any(check.category == "backtest" for check in failed):
        recs.append(
            "Require at least 200 independent trades, run walk-forward parameter selection, and report confidence intervals via bootstrap."
        )
    if any(check.category == "risk" for check in failed):
        recs.append(
            "Constrain vega/gamma by capital, cap loss per structure, and size positions by expected shortfall rather than only fractional Kelly."
        )
    return recs


def institutional_quality_report(
    ohlc_df: pd.DataFrame,
    iv_df: pd.DataFrame,
    options_df: pd.DataFrame,
    metrics_by_name: dict[str, pd.DataFrame],
    trades_by_name: dict[str, pd.DataFrame],
) -> InstitutionalReport:
    checks: List[GateCheck] = []

    ohlc = ohlc_df.copy()
    if not ohlc.empty:
        ohlc["timestamp"] = pd.to_datetime(ohlc["timestamp"], utc=True)
    iv = iv_df.copy()
    if not iv.empty:
        iv["timestamp"] = pd.to_datetime(iv["timestamp"], utc=True)
    options = options_df.copy()
    if not options.empty:
        options["timestamp"] = pd.to_datetime(options["timestamp"], utc=True)
        options["expiry"] = pd.to_datetime(options["expiry"], utc=True)

    ohlc_days = _coverage_days(ohlc.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]")))
    _add(checks, "sample", "ohlc_history_days", ohlc_days >= 365, "critical", round(ohlc_days, 2), ">= 365", "BTC history is too short for institutional short-vol inference." )
    _add(checks, "data.ohlc", "ohlc_hourly_gaps", _max_gap_hours(ohlc.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]"))) <= 1.5, "major", round(_max_gap_hours(ohlc.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]"))), 2), "<= 1.5h", "Hourly OHLC should be continuous or explicitly imputed." )
    _add(checks, "data.ohlc", "ohlc_duplicates", not ohlc.get("timestamp", pd.Series(dtype=object)).duplicated().any(), "major", int(ohlc.get("timestamp", pd.Series(dtype=object)).duplicated().sum()), "0", "Duplicate bars break point-in-time simulation." )

    iv_days = _coverage_days(iv.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]")))
    _add(checks, "sample", "iv_history_days", iv_days >= 365, "critical", round(iv_days, 2), ">= 365", "DVOL history is too short for robust regime and tail analysis." )
    if not ohlc.empty and not iv.empty:
        overlap = len(set(ohlc["timestamp"]).intersection(set(iv["timestamp"])))
        coverage = overlap / max(len(ohlc), 1)
    else:
        coverage = 0.0
    _add(checks, "data.iv", "iv_ohlc_timestamp_overlap", coverage >= 0.98, "major", round(coverage, 4), ">= 0.98", "IV and underlying data need aligned timestamps." )

    required_option_cols = {
        "timestamp",
        "expiry",
        "strike",
        "option_type",
        "bid",
        "ask",
        "mark",
        "underlying",
    }
    missing_required = sorted(required_option_cols - set(options.columns))
    _add(checks, "data.options", "required_option_columns", not missing_required, "critical", missing_required or "none", "none", "Required option pricing columns must exist." )

    institutional_cols = {"bid_size", "ask_size", "volume", "open_interest", "mark_iv", "delta", "gamma", "vega"}
    missing_institutional = sorted(institutional_cols - set(options.columns))
    _add(checks, "data.options", "institutional_option_microstructure_columns", not missing_institutional, "critical", missing_institutional or "none", "none", "Institutional execution tests need depth/liquidity and greeks, not only OHLC candles." )

    option_days = _coverage_days(options.get("timestamp", pd.Series(dtype="datetime64[ns, UTC]")))
    _add(checks, "sample", "option_history_days", option_days >= 180, "critical", round(option_days, 2), ">= 180", "Option-chain sample is too short for strategy validation." )

    if not options.empty:
        rows_per_ts = options.groupby("timestamp").size()
        median_rows = float(rows_per_ts.median())
        unique_instruments = int(options[["expiry", "strike", "option_type"]].drop_duplicates().shape[0])
        max_gap = _max_gap_hours(options["timestamp"].drop_duplicates())
        crossed = int((options["bid"] > options["ask"]).sum()) if {"bid", "ask"} <= set(options.columns) else -1
        nonpositive = int(((options[["bid", "ask", "mark"]] <= 0).any(axis=1)).sum()) if {"bid", "ask", "mark"} <= set(options.columns) else -1
    else:
        median_rows = 0.0
        unique_instruments = 0
        max_gap = float("inf")
        crossed = -1
        nonpositive = -1

    _add(checks, "data.options", "option_rows_per_timestamp", median_rows >= 80, "critical", round(median_rows, 2), ">= 80", "A full BTC option chain usually needs many strikes and expiries per timestamp." )
    _add(checks, "data.options", "unique_option_instruments", unique_instruments >= 200, "major", unique_instruments, ">= 200", "Sparse instruments make smile and delta selection unstable." )
    _add(checks, "data.options", "option_hourly_gaps", max_gap <= 1.5, "major", round(max_gap, 2), "<= 1.5h", "Option snapshots must be continuous for mark-to-market and hedge simulation." )
    _add(checks, "data.options", "crossed_option_markets", crossed == 0, "critical", crossed, "0", "Bid must not be above ask." )
    _add(checks, "data.options", "nonpositive_option_prices", nonpositive == 0, "major", nonpositive, "0", "Zero or negative bid/ask/mark rows should be filtered or repaired." )

    for name, trades in trades_by_name.items():
        metrics = metrics_by_name.get(name, pd.DataFrame())
        n_trades = len(trades)
        _add(checks, "backtest", f"{name}_trade_count", n_trades >= 200, "critical", n_trades, ">= 200", "Too few trades for statistical inference." )
        if metrics.empty:
            continue
        row = metrics.iloc[0]
        pnl = float(row.get("total_pnl", 0.0))
        stress = float(row.get("stress_gap_pnl", 0.0))
        stress_ratio = abs(stress) / max(abs(pnl), 1e-9)
        _add(checks, "risk", f"{name}_stress_to_pnl", stress_ratio <= 5.0, "critical", round(stress_ratio, 2), "<= 5x", "Tail loss is too large versus realized edge." )
        dd = abs(float(row.get("max_drawdown", 0.0)))
        _add(checks, "risk", f"{name}_max_drawdown", dd <= 0.10, "major", round(dd, 4), "<= 10%", "Drawdown should be bounded under normal mark-to-market." )
        if not trades.empty and {"iv_at_entry", "rv_forecast_at_entry", "vrp_at_entry"} <= set(trades.columns):
            edge = trades["iv_at_entry"].astype(float) - trades["rv_forecast_at_entry"].astype(float)
            inconsistent = int((np.sign(edge.round(8)) != np.sign(trades["vrp_at_entry"].astype(float).round(8))).sum())
            _add(checks, "backtest", f"{name}_entry_edge_consistency", inconsistent == 0, "critical", inconsistent, "0", "Signal must match the IV/RV of the actually executed structure." )

    critical_failed = [check for check in checks if check.severity == "critical" and not check.passed]
    major_failed = [check for check in checks if check.severity == "major" and not check.passed]
    score = max(0.0, 100.0 - 12.0 * len(critical_failed) - 4.0 * len(major_failed))
    return InstitutionalReport(
        ready=not critical_failed,
        score=score,
        checks=checks,
        recommendations=_recommendations(checks),
    )
