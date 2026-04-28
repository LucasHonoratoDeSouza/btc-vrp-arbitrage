import os
import sys
from dataclasses import asdict

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv, load_options_csv

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


def save_backtest_outputs(result, output_dir: str, prefix: str) -> None:
    result.equity_curve.to_csv(os.path.join(output_dir, f"{prefix}_equity.csv"))
    trades_df = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=TRADE_COLUMNS)
    trades_df.to_csv(
        os.path.join(output_dir, f"{prefix}_trades.csv"), index=False
    )
    pd.DataFrame([result.metrics]).to_csv(
        os.path.join(output_dir, f"{prefix}_metrics.csv"), index=False
    )


def main() -> None:
    ohlc_df = load_ohlc_csv("data/btc_1h.csv")
    options_path = "data/deribit_options_1h.csv"
    if os.path.exists(options_path) and os.path.getsize(options_path) > 0:
        options_df = load_options_csv(options_path)
    else:
        options_df = pd.DataFrame(
            columns=[
                "timestamp",
                "expiry",
                "strike",
                "option_type",
                "bid",
                "ask",
                "mark",
                "underlying",
            ]
        )
    iv_series = None
    config = BacktestConfig()
    if options_df.empty:
        dvol_path = "data/btc_dvol_1h.csv"
        if not os.path.exists(dvol_path):
            raise RuntimeError(
                "data/deribit_options_1h.csv is empty and data/btc_dvol_1h.csv "
                "is missing. Run: python scripts/run_full_pipeline.py --days 60"
            )
        iv_series = load_iv_csv(dvol_path)
        config = BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 10,
            zscore_window=24 * 5,
            vrp_entry_z=0.8,
            vrp_exit_z=0.2,
            max_holding_hours=24 * 5,
        )

    result = run_backtest(ohlc_df, options_df, config, iv_series=iv_series)
    save_backtest_outputs(result, os.path.join(ROOT, "data"), "local_backtest")

    print(result.metrics)
    if result.diagnostics:
        print("Diagnostics:")
        for note in result.diagnostics:
            print("-", note)


if __name__ == "__main__":
    main()
