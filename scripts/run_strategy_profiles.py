import os
import sys
from dataclasses import asdict

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv
from strategy_catalog import get_profiles

DATA_DIR = os.path.join(ROOT, "data")
EMPTY_OPTIONS = pd.DataFrame(
    columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
)
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

PROFILES = get_profiles()


def save_outputs(profile: str, result) -> dict:
    prefix = f"profile_{profile}"
    result.equity_curve.to_csv(os.path.join(DATA_DIR, f"{prefix}_equity.csv"))
    trades = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades.empty:
        trades = pd.DataFrame(columns=TRADE_COLUMNS)
    trades.to_csv(os.path.join(DATA_DIR, f"{prefix}_trades.csv"), index=False)
    metrics = dict(result.metrics)
    metrics["profile"] = profile
    metrics["avg_trade_notional"] = float(trades["notional"].mean()) if not trades.empty else 0.0
    metrics["total_fees"] = float(trades["fees"].sum()) if not trades.empty else 0.0
    pd.DataFrame([metrics]).to_csv(os.path.join(DATA_DIR, f"{prefix}_metrics.csv"), index=False)
    return metrics


def main() -> None:
    ohlc = load_ohlc_csv(os.path.join(DATA_DIR, "btc_1h.csv"))
    iv = load_iv_csv(os.path.join(DATA_DIR, "btc_dvol_1h.csv"))
    rows = []
    for name, config in PROFILES.items():
        result = run_backtest(ohlc, EMPTY_OPTIONS, config, iv_series=iv)
        metrics = save_outputs(name, result)
        rows.append(metrics)
        print(metrics)

    summary = pd.DataFrame(rows)
    summary = summary[
        [
            "profile",
            "trades",
            "total_pnl",
            "total_return",
            "sharpe",
            "sortino",
            "max_drawdown",
            "vrp_capture_efficiency",
            "stress_gap_pnl",
            "win_rate",
            "profit_factor",
            "stress_to_pnl",
            "avg_trade_notional",
            "total_fees",
        ]
    ]
    summary.to_csv(os.path.join(DATA_DIR, "strategy_profile_results.csv"), index=False)

    lines = [
        "# Strategy Profile Comparison",
        "",
        "Objective: maximize return with explicit risk controls, accepting higher tail risk in aggressive mode.",
        "",
        "| Profile | Trades | PnL | Return | Sharpe | Max DD | Win Rate | Stress/PnL | Avg Notional |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['profile']} | {row['trades']:.0f} | {row['total_pnl']:.6f} | "
            f"{row['total_return']:.4%} | {row['sharpe']:.3f} | {row['max_drawdown']:.4%} | "
            f"{row['win_rate']:.1%} | {row['stress_to_pnl']:.2f} | {row['avg_trade_notional']:.3f} |"
        )
    with open(os.path.join(DATA_DIR, "strategy_profile_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Saved {os.path.join(DATA_DIR, 'strategy_profile_results.csv')}")
    print(f"Report: {os.path.join(DATA_DIR, 'strategy_profile_report.md')}")


if __name__ == "__main__":
    main()
