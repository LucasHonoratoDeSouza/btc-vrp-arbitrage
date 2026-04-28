import os
import sys
from dataclasses import asdict

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_ohlc_csv, load_options_csv

DATA_DIR = os.path.join(ROOT, "data")
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


def save_backtest_outputs(result, prefix: str) -> None:
    result.equity_curve.to_csv(os.path.join(DATA_DIR, f"{prefix}_equity.csv"))
    trades = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades.empty:
        trades = pd.DataFrame(columns=TRADE_COLUMNS)
    trades.to_csv(os.path.join(DATA_DIR, f"{prefix}_trades.csv"), index=False)
    pd.DataFrame([result.metrics]).to_csv(
        os.path.join(DATA_DIR, f"{prefix}_metrics.csv"), index=False
    )


def main() -> None:
    snapshot_path = os.path.join(DATA_DIR, "deribit_option_snapshots.csv")
    if not os.path.exists(snapshot_path):
        raise RuntimeError(
            "Missing data/deribit_option_snapshots.csv. Run collect_deribit_option_snapshot.py first."
        )

    ohlc = load_ohlc_csv(os.path.join(DATA_DIR, "btc_1h.csv"))
    options = load_options_csv(snapshot_path)
    config = BacktestConfig(
        garch_window_hours=24 * 10,
        zscore_window=24 * 5,
        vrp_entry_z=0.8,
        vrp_exit_z=0.2,
        max_holding_hours=24 * 5,
        min_vrp_edge=0.02,
        max_bid_ask_spread_pct=0.20,
        min_option_bid=5.0,
        min_option_bid_size=0.1,
        min_option_ask_size=0.1,
        max_trade_stress_loss_pct=0.01,
    )
    result = run_backtest(ohlc, options, config)
    save_backtest_outputs(result, "rich_backtest")
    print(result.metrics)
    if result.diagnostics:
        print("Diagnostics:")
        for note in result.diagnostics:
            print("-", note)


if __name__ == "__main__":
    main()
