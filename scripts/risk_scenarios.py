import math
import os
import argparse

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")


def stressed_realized_vol(crash_pct: float, gap_hours: int = 4, horizon_hours: int = 168) -> float:
    hourly_gap = math.log(max(1e-6, 1.0 + crash_pct)) / gap_hours
    returns = np.zeros(max(horizon_hours, gap_hours + 1))
    returns[:gap_hours] = hourly_gap
    return float(np.std(returns, ddof=1) * math.sqrt(365.0 * 24.0))


def scenario_pnl(trades: pd.DataFrame, crash_pct: float, vol_add: float) -> float:
    if trades.empty:
        return 0.0
    rv = stressed_realized_vol(crash_pct)
    pnl = 0.0
    for _, trade in trades.iterrows():
        entry_iv = float(trade.get("iv_at_entry", 0.0))
        stressed_exit_vol = max(rv, entry_iv + vol_add)
        notional = float(trade.get("notional", 1.0))
        fees = float(trade.get("fees", 0.0))
        pnl += notional * (entry_iv**2 - stressed_exit_vol**2) - fees
    return float(pnl)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scenario matrix for a backtest trade file.")
    parser.add_argument("--prefix", default="real_backtest")
    args = parser.parse_args()

    trades_path = os.path.join(DATA_DIR, f"{args.prefix}_trades.csv")
    trades = pd.read_csv(trades_path) if os.path.exists(trades_path) else pd.DataFrame()
    crashes = [-0.05, -0.10, -0.20, -0.30]
    vol_shocks = [0.0, 0.10, 0.25, 0.50]
    rows = []
    for crash in crashes:
        for vol_add in vol_shocks:
            rows.append(
                {
                    "crash_pct": crash,
                    "vol_add": vol_add,
                    "scenario_pnl": scenario_pnl(trades, crash, vol_add),
                    "stressed_rv": stressed_realized_vol(crash),
                }
            )
    out = pd.DataFrame(rows)
    out_path = os.path.join(DATA_DIR, f"{args.prefix}_risk_scenarios.csv")
    out.to_csv(out_path, index=False)

    pivot = out.pivot(index="crash_pct", columns="vol_add", values="scenario_pnl")
    lines = [
        f"# Risk Scenario Matrix: {args.prefix}",
        "",
        "Rows are BTC gap scenarios over 4 hours. Columns are additive adverse IV shocks applied to exit volatility.",
        "",
        "| Crash | +0 vol | +10 vol pts | +25 vol pts | +50 vol pts |",
        "|---:|---:|---:|---:|---:|",
    ]
    for crash, row in pivot.iterrows():
        lines.append(
            f"| {crash:.0%} | {row.get(0.0, 0.0):.6f} | {row.get(0.10, 0.0):.6f} | "
            f"{row.get(0.25, 0.0):.6f} | {row.get(0.50, 0.0):.6f} |"
        )
    report_path = os.path.join(DATA_DIR, f"{args.prefix}_risk_scenarios.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved {out_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
