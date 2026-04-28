import argparse
import os
import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_ohlc_csv, normalize_option_type

TRADE_COLUMNS = [
    "entry_time",
    "exit_time",
    "strategy",
    "pnl",
    "vega",
    "vrp_at_entry",
    "iv_at_entry",
    "rv_forecast_at_entry",
    "notional",
    "fees",
    "hedge_cost",
    "stress_pnl",
]

REQUIRED_COLUMNS = {
    "timestamp",
    "expiry",
    "strike",
    "option_type",
    "bid",
    "ask",
    "mark",
    "underlying",
}
MICROSTRUCTURE_COLUMNS = {
    "bid_size",
    "ask_size",
    "volume",
    "open_interest",
    "mark_iv",
    "delta",
    "gamma",
    "vega",
}


def _load_options(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    df["expiry"] = pd.to_datetime(df["expiry"], utc=True, format="mixed")
    df["option_type"] = df["option_type"].apply(normalize_option_type)
    return df.sort_values(["timestamp", "expiry", "strike", "option_type"])


def _max_gap_hours(timestamps: pd.Series) -> float:
    unique = timestamps.sort_values().drop_duplicates()
    if unique.empty or len(unique) < 2:
        return float("inf")
    diffs = unique.diff().dropna()
    return float((diffs.dt.total_seconds() / 3600.0).max())


def _coverage_days(timestamps: pd.Series) -> float:
    if timestamps.empty:
        return 0.0
    return float((timestamps.max() - timestamps.min()).total_seconds() / 86400.0)


def _option_history_checks(
    options: pd.DataFrame,
    min_history_days: float,
    min_rows_per_timestamp: int,
    max_gap_hours: float,
) -> list[dict[str, object]]:
    checks = []

    missing_required = sorted(REQUIRED_COLUMNS - set(options.columns))
    missing_micro = sorted(MICROSTRUCTURE_COLUMNS - set(options.columns))
    checks.append(
        {
            "check": "required_columns",
            "passed": not missing_required,
            "value": missing_required or "none",
            "threshold": "none missing",
        }
    )
    checks.append(
        {
            "check": "microstructure_columns",
            "passed": not missing_micro,
            "value": missing_micro or "none",
            "threshold": "none missing",
        }
    )

    if options.empty or missing_required:
        checks.extend(
            [
                {
                    "check": "history_days",
                    "passed": False,
                    "value": 0.0,
                    "threshold": min_history_days,
                },
                {
                    "check": "rows_per_timestamp",
                    "passed": False,
                    "value": 0.0,
                    "threshold": min_rows_per_timestamp,
                },
                {
                    "check": "max_timestamp_gap_hours",
                    "passed": False,
                    "value": float("inf"),
                    "threshold": max_gap_hours,
                },
            ]
        )
        return checks

    history_days = _coverage_days(options["timestamp"])
    rows_per_ts = options.groupby("timestamp").size()
    median_rows = float(rows_per_ts.median()) if not rows_per_ts.empty else 0.0
    gap = _max_gap_hours(options["timestamp"])
    crossed = int((options["bid"].astype(float) > options["ask"].astype(float)).sum())
    nonpositive = int(
        (
            options[["bid", "ask", "mark", "underlying"]]
            .apply(pd.to_numeric, errors="coerce")
            .le(0.0)
            .any(axis=1)
        ).sum()
    )

    checks.extend(
        [
            {
                "check": "history_days",
                "passed": history_days >= min_history_days,
                "value": round(history_days, 2),
                "threshold": min_history_days,
            },
            {
                "check": "rows_per_timestamp",
                "passed": median_rows >= min_rows_per_timestamp,
                "value": round(median_rows, 2),
                "threshold": min_rows_per_timestamp,
            },
            {
                "check": "max_timestamp_gap_hours",
                "passed": gap <= max_gap_hours,
                "value": round(gap, 2),
                "threshold": max_gap_hours,
            },
            {
                "check": "crossed_markets",
                "passed": crossed == 0,
                "value": crossed,
                "threshold": 0,
            },
            {
                "check": "nonpositive_prices",
                "passed": nonpositive == 0,
                "value": nonpositive,
                "threshold": 0,
            },
        ]
    )
    return checks


def _write_gate_report(path: str, checks: list[dict[str, object]]) -> None:
    lines = [
        "# Executable Option Backtest Gate",
        "",
        "| Check | Passed | Value | Threshold |",
        "|---|---:|---:|---:|",
    ]
    for check in checks:
        lines.append(
            f"| {check['check']} | {check['passed']} | {check['value']} | {check['threshold']} |"
        )
    lines.append("")
    failed = [check for check in checks if not check["passed"]]
    if failed:
        lines.append("Status: **BLOCKED**. Provide point-in-time historical option-chain snapshots before trusting live execution metrics.")
    else:
        lines.append("Status: **PASSED**. Dataset is eligible for executable option-chain backtesting.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _save_outputs(result, output_dir: str, prefix: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    result.equity_curve.to_csv(os.path.join(output_dir, f"{prefix}_equity.csv"))
    trades = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades.empty:
        trades = pd.DataFrame(columns=TRADE_COLUMNS)
    trades.to_csv(os.path.join(output_dir, f"{prefix}_trades.csv"), index=False)
    pd.DataFrame([result.metrics]).to_csv(
        os.path.join(output_dir, f"{prefix}_metrics.csv"), index=False
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an executable option-chain backtest. This never falls back to DVOL proxy mode."
    )
    parser.add_argument("--ohlc", default=os.path.join(ROOT, "data", "extended", "btc_1h_8y.csv"))
    parser.add_argument("--options", default=os.path.join(ROOT, "data", "deribit_option_snapshots.csv"))
    parser.add_argument("--output-dir", default=os.path.join(ROOT, "data", "results", "executable_options"))
    parser.add_argument("--prefix", default="executable_options")
    parser.add_argument("--min-history-days", type=float, default=180.0)
    parser.add_argument("--min-rows-per-timestamp", type=int, default=80)
    parser.add_argument("--max-gap-hours", type=float, default=1.5)
    parser.add_argument("--allow-insufficient-data", action="store_true")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    gate_report = os.path.join(args.output_dir, f"{args.prefix}_gate.md")

    if not os.path.exists(args.options):
        checks = _option_history_checks(
            pd.DataFrame(),
            args.min_history_days,
            args.min_rows_per_timestamp,
            args.max_gap_hours,
        )
        _write_gate_report(gate_report, checks)
        raise RuntimeError(f"Missing option-chain history: {args.options}. Gate report: {gate_report}")

    ohlc = load_ohlc_csv(args.ohlc)
    options = _load_options(args.options)
    checks = _option_history_checks(
        options,
        args.min_history_days,
        args.min_rows_per_timestamp,
        args.max_gap_hours,
    )
    _write_gate_report(gate_report, checks)
    failed = [check for check in checks if not check["passed"]]
    if failed and not args.allow_insufficient_data:
        raise RuntimeError(f"Executable option-chain gate failed. Report: {gate_report}")

    overlap_start = max(ohlc["timestamp"].min(), options["timestamp"].min())
    overlap_end = min(ohlc["timestamp"].max(), options["timestamp"].max())
    ohlc = ohlc[(ohlc["timestamp"] >= overlap_start) & (ohlc["timestamp"] <= overlap_end)]
    options = options[(options["timestamp"] >= overlap_start) & (options["timestamp"] <= overlap_end)]
    if ohlc.empty or options.empty:
        raise RuntimeError("No timestamp overlap between OHLC and option-chain history.")

    config = BacktestConfig(
        use_variance_proxy=False,
        garch_weight=0.0,
        ewma_span_hours=48,
        zscore_window=72,
        vrp_entry_z=0.35,
        vrp_exit_z=0.20,
        min_vrp_edge=0.03,
        require_z_and_quantile=False,
        signal_confirmation_periods=2,
        cooldown_hours=3,
        max_holding_hours=6,
        base_contracts=1.0,
        min_contracts=0.01,
        max_contracts=50.0,
        max_trade_stress_loss_pct=0.02,
        max_bid_ask_spread_pct=0.25,
        min_option_bid=1.0,
        min_option_bid_size=0.05,
        min_option_ask_size=0.05,
        min_option_open_interest=0.0,
        enforce_option_margin=True,
        max_margin_utilization=0.50,
        maintenance_margin_fraction=0.50,
    )
    result = run_backtest(ohlc.reset_index(drop=True), options.reset_index(drop=True), config)
    _save_outputs(result, args.output_dir, args.prefix)
    print(result.metrics)
    print(f"Gate report: {gate_report}")


if __name__ == "__main__":
    main()
