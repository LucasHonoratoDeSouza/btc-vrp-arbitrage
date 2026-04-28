import itertools
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv

DATA_DIR = os.path.join(ROOT, "data")


def main() -> None:
    ohlc = load_ohlc_csv(os.path.join(DATA_DIR, "btc_1h.csv"))
    iv = load_iv_csv(os.path.join(DATA_DIR, "btc_dvol_1h.csv"))
    empty_options = pd.DataFrame(
        columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
    )

    grid = {
        "vrp_entry_z": [0.35, 0.50],
        "min_vrp_edge": [0.025, 0.035],
        "max_holding_hours": [6, 12, 24],
    }
    rows = []
    for values in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), values))
        config = BacktestConfig(
            use_variance_proxy=True,
            garch_window_hours=24 * 7,
            garch_refit_interval_hours=72,
            ewma_span_hours=48,
            garch_weight=0.35,
            zscore_window=72,
            vrp_exit_z=0.2,
            variance_notional=100.0,
            variance_trade_cost=0.0008,
            kelly_fraction=0.75,
            max_contracts=1000.0,
            max_trade_stress_loss_pct=0.08,
            max_rv_percentile=0.90,
            max_abs_24h_return=0.12,
            vrp_entry_quantile=0.60,
            require_z_and_quantile=False,
            signal_confirmation_periods=2,
            cooldown_hours=3,
            **params,
        )
        result = run_backtest(ohlc, empty_options, config, iv_series=iv)
        row = {**params, **result.metrics}
        rows.append(row)
        print(row)

    out = pd.DataFrame(rows).sort_values(
        ["total_pnl", "stress_gap_pnl"], ascending=[False, False]
    )
    out_path = os.path.join(DATA_DIR, "parameter_sweep.csv")
    out.to_csv(out_path, index=False)

    lines = [
        "# Parameter Sweep",
        "",
        "This is diagnostic only; the sample is too short for production parameter selection.",
        "",
        "| vrp_entry_z | min_vrp_edge | max_holding_hours | trades | total_pnl | sharpe | max_dd | win_rate | stress_to_pnl |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in out.iterrows():
        lines.append(
            f"| {row['vrp_entry_z']:.2f} | {row['min_vrp_edge']:.3f} | {row['max_holding_hours']:.0f} | "
            f"{row['trades']:.0f} | {row['total_pnl']:.6f} | {row['sharpe']:.4f} | "
            f"{row['max_drawdown']:.4%} | {row['win_rate']:.1%} | {row['stress_to_pnl']:.2f} |"
        )
    report_path = os.path.join(DATA_DIR, "parameter_sweep.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Saved {out_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
