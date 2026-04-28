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
EMPTY_OPTIONS = pd.DataFrame(
    columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
)


BASE_PARAMS = {
    "use_variance_proxy": True,
    "garch_window_hours": 24 * 7,
    "garch_refit_interval_hours": 72,
    "variance_notional": 100.0,
    "variance_trade_cost": 0.0008,
    "kelly_fraction": 0.75,
    "max_contracts": 1000.0,
    "max_trade_stress_loss_pct": 0.08,
    "cooldown_hours": 3,
    "max_rv_percentile": 0.90,
    "max_abs_24h_return": 0.12,
}


def _run_window(
    ohlc: pd.DataFrame,
    iv: pd.Series,
    params: dict,
    entry_start: pd.Timestamp | None = None,
    entry_end: pd.Timestamp | None = None,
) -> dict:
    config = BacktestConfig(
        **BASE_PARAMS,
        entry_start_time=entry_start.isoformat() if entry_start is not None else None,
        entry_end_time=entry_end.isoformat() if entry_end is not None else None,
        **params,
    )
    result = run_backtest(ohlc, EMPTY_OPTIONS, config, iv_series=iv)
    return result.metrics


def _selection_score(row: dict) -> float:
    trades = float(row.get("trades", 0.0))
    if trades < 4:
        return -1e9 + float(row.get("total_pnl", 0.0))
    pnl = float(row.get("total_pnl", 0.0))
    stress_loss = abs(min(float(row.get("stress_gap_pnl", 0.0)), 0.0))
    drawdown = abs(float(row.get("max_drawdown", 0.0)))
    capture = float(row.get("vrp_capture_efficiency", 0.0))
    return pnl - 0.03 * stress_loss - 5000.0 * drawdown + 2.0 * capture


def _param_label(row: pd.Series) -> str:
    return (
        f"z={row['vrp_entry_z']}, edge={row['min_vrp_edge']}, "
        f"exit={row['vrp_exit_z']}, hold={row['max_holding_hours']}, win={row['zscore_window']}, "
        f"ewma={row['ewma_span_hours']}, garch_w={row['garch_weight']}, "
        f"q={row['vrp_entry_quantile']}, req={row['require_z_and_quantile']}"
    )


def main() -> None:
    ohlc = load_ohlc_csv(os.path.join(DATA_DIR, "btc_1h.csv"))
    iv = load_iv_csv(os.path.join(DATA_DIR, "btc_dvol_1h.csv"))
    start = ohlc["timestamp"].min()
    end = ohlc["timestamp"].max()

    grid = [
        {
            "vrp_entry_z": 0.35,
            "vrp_exit_z": 0.2,
            "min_vrp_edge": 0.025,
            "max_holding_hours": 6,
            "zscore_window": 72,
            "ewma_span_hours": 48,
            "garch_weight": 0.35,
            "require_z_and_quantile": False,
            "signal_confirmation_periods": 2,
            "vrp_entry_quantile": 0.60,
        },
        {
            "vrp_entry_z": 0.35,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.025,
            "max_holding_hours": 12,
            "zscore_window": 72,
            "ewma_span_hours": 48,
            "garch_weight": 0.35,
            "require_z_and_quantile": False,
            "signal_confirmation_periods": 2,
            "vrp_entry_quantile": 0.60,
        },
        {
            "vrp_entry_z": 0.35,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.025,
            "max_holding_hours": 24,
            "zscore_window": 72,
            "ewma_span_hours": 48,
            "garch_weight": 0.35,
            "require_z_and_quantile": False,
            "signal_confirmation_periods": 2,
            "vrp_entry_quantile": 0.60,
        },
        {
            "vrp_entry_z": 0.35,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.025,
            "max_holding_hours": 24,
            "zscore_window": 72,
            "ewma_span_hours": 48,
            "garch_weight": 0.35,
            "require_z_and_quantile": True,
            "signal_confirmation_periods": 1,
            "vrp_entry_quantile": 0.70,
        },
        {
            "vrp_entry_z": 0.50,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.025,
            "max_holding_hours": 48,
            "zscore_window": 72,
            "ewma_span_hours": 48,
            "garch_weight": 0.55,
            "require_z_and_quantile": False,
            "signal_confirmation_periods": 2,
            "vrp_entry_quantile": 0.60,
        },
        {
            "vrp_entry_z": 0.50,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.035,
            "max_holding_hours": 48,
            "zscore_window": 120,
            "ewma_span_hours": 72,
            "garch_weight": 0.55,
            "require_z_and_quantile": True,
            "signal_confirmation_periods": 1,
            "vrp_entry_quantile": 0.65,
        },
        {
            "vrp_entry_z": 0.65,
            "vrp_exit_z": 0.1,
            "min_vrp_edge": 0.035,
            "max_holding_hours": 72,
            "zscore_window": 120,
            "ewma_span_hours": 72,
            "garch_weight": 0.65,
            "require_z_and_quantile": True,
            "signal_confirmation_periods": 1,
            "vrp_entry_quantile": 0.70,
        },
        {
            "vrp_entry_z": 0.80,
            "vrp_exit_z": 0.2,
            "min_vrp_edge": 0.040,
            "max_holding_hours": 72,
            "zscore_window": 120,
            "ewma_span_hours": 96,
            "garch_weight": 0.70,
            "require_z_and_quantile": True,
            "signal_confirmation_periods": 2,
            "vrp_entry_quantile": 0.70,
        },
    ]
    train_days = 30
    test_days = 10
    step_days = 10
    rows = []
    fold = 0
    cursor = start
    while cursor + pd.Timedelta(days=train_days + test_days) <= end:
        train_start = cursor
        train_end = cursor + pd.Timedelta(days=train_days)
        test_end = train_end + pd.Timedelta(days=test_days)
        train_ohlc = ohlc[(ohlc["timestamp"] >= train_start) & (ohlc["timestamp"] < train_end)]
        test_ohlc = ohlc[(ohlc["timestamp"] >= train_end) & (ohlc["timestamp"] < test_end)]
        train_iv = iv.loc[train_start:train_end]
        warm_ohlc = ohlc[(ohlc["timestamp"] >= train_start) & (ohlc["timestamp"] < test_end)]
        warm_iv = iv.loc[train_start:test_end]
        if len(train_ohlc) < 24 * 14 or len(test_ohlc) < 24 * 5:
            cursor += pd.Timedelta(days=step_days)
            continue

        train_results = []
        for params in grid:
            metrics = _run_window(train_ohlc.reset_index(drop=True), train_iv, params)
            train_results.append({**params, **metrics, "selection_score": _selection_score(metrics)})
        selected = sorted(
            train_results,
            key=lambda row: row.get("selection_score", -1e9),
            reverse=True,
        )[0]
        selected_params = {
            key: selected[key]
            for key in [
                "vrp_entry_z",
                "vrp_exit_z",
                "min_vrp_edge",
                "max_holding_hours",
                "zscore_window",
                "ewma_span_hours",
                "garch_weight",
                "require_z_and_quantile",
                "signal_confirmation_periods",
                "vrp_entry_quantile",
            ]
        }
        test_metrics = _run_window(
            warm_ohlc.reset_index(drop=True),
            warm_iv,
            selected_params,
            entry_start=train_end,
            entry_end=test_end,
        )
        rows.append(
            {
                "fold": fold,
                "train_start": train_start,
                "train_end": train_end,
                "test_end": test_end,
                **selected_params,
                **{f"train_{k}": v for k, v in selected.items() if k not in selected_params},
                **{f"test_{k}": v for k, v in test_metrics.items()},
            }
        )
        print(rows[-1])
        fold += 1
        cursor += pd.Timedelta(days=step_days)

    out = pd.DataFrame(rows)
    out_path = os.path.join(DATA_DIR, "walk_forward_results.csv")
    out.to_csv(out_path, index=False)

    lines = [
        "# Walk-Forward VRP Diagnostics",
        "",
        "This is a research-control report. Passing this does not imply production readiness.",
        "",
    ]
    if out.empty:
        lines.append("No folds generated. Extend the dataset.")
    else:
        lines.append(f"Folds: **{len(out)}**")
        lines.append(f"Total out-of-sample PnL: **{out['test_total_pnl'].sum():.6f}**")
        lines.append(f"Average out-of-sample trades: **{out['test_trades'].mean():.2f}**")
        lines.append(f"Average out-of-sample Sharpe: **{out['test_sharpe'].mean():.3f}**")
        lines.extend(["", "| Fold | Params | Train Score | Train PnL | Test PnL | Test Trades | Test Stress/PnL |", "|---:|---|---:|---:|---:|---:|---:|"])
        for _, row in out.iterrows():
            lines.append(
                f"| {row['fold']} | {_param_label(row)} | {row['train_selection_score']:.6f} | "
                f"{row['train_total_pnl']:.6f} | {row['test_total_pnl']:.6f} | "
                f"{row['test_trades']:.0f} | {row['test_stress_to_pnl']:.2f} |"
            )
    report_path = os.path.join(DATA_DIR, "walk_forward_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved {out_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
