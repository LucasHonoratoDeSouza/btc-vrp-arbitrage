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
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv
from strategy_catalog import get_candidates

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


def candidate_configs() -> dict[str, BacktestConfig]:
    return get_candidates()


def _objective(metrics: dict) -> float:
    trades = float(metrics.get("trades", 0.0))
    if trades < 5:
        return -1e9 + float(metrics.get("total_pnl", 0.0))
    pnl = float(metrics.get("total_pnl", 0.0))
    drawdown = abs(float(metrics.get("max_drawdown", 0.0)))
    stress_loss = abs(min(float(metrics.get("stress_gap_pnl", 0.0)), 0.0))
    capture = float(metrics.get("vrp_capture_efficiency", 0.0))
    return pnl - 0.02 * stress_loss - 5000.0 * drawdown + 4.0 * capture


def _nonoverlap_stats(df: pd.DataFrame, pnl_col: str) -> dict[str, float]:
    if df.empty:
        return {
            "even_sum": 0.0,
            "odd_sum": 0.0,
            "even_positive": 0.0,
            "odd_positive": 0.0,
        }
    even = df[df["fold"] % 2 == 0]
    odd = df[df["fold"] % 2 == 1]
    return {
        "even_sum": float(even[pnl_col].sum()) if not even.empty else 0.0,
        "odd_sum": float(odd[pnl_col].sum()) if not odd.empty else 0.0,
        "even_positive": float((even[pnl_col] > 0).mean()) if not even.empty else 0.0,
        "odd_positive": float((odd[pnl_col] > 0).mean()) if not odd.empty else 0.0,
    }


def _period_regime(test_ohlc: pd.DataFrame, iv: pd.Series) -> dict[str, object]:
    close = test_ohlc.set_index("timestamp")["close"].astype(float)
    returns = np.log(close).diff().dropna()
    rv = float(returns.std(ddof=1) * np.sqrt(365.0 * 24.0)) if len(returns) > 2 else 0.0
    period_return = float(close.iloc[-1] / close.iloc[0] - 1.0) if len(close) > 1 else 0.0
    max_abs_24h = float(np.log(close).diff(24).abs().max()) if len(close) > 24 else 0.0
    iv_slice = iv.loc[close.index.min() : close.index.max()]
    median_iv = float(iv_slice.median()) if not iv_slice.empty else np.nan
    if rv >= 0.75 or max_abs_24h >= 0.12:
        regime = "volatile"
    elif abs(period_return) >= 0.12:
        regime = "trending"
    else:
        regime = "calm"
    return {
        "regime": regime,
        "period_return": period_return,
        "realized_vol": rv,
        "median_iv": median_iv,
        "max_abs_24h_log_return": max_abs_24h,
    }


def _run_period(
    ohlc: pd.DataFrame,
    iv: pd.Series,
    config: BacktestConfig,
    train_start: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
) -> tuple[dict, object]:
    local = BacktestConfig(**asdict(config))
    local.entry_start_time = test_start.isoformat()
    local.entry_end_time = test_end.isoformat()
    window = ohlc[(ohlc["timestamp"] >= train_start) & (ohlc["timestamp"] < test_end)]
    iv_window = iv.loc[train_start:test_end]
    result = run_backtest(window.reset_index(drop=True), EMPTY_OPTIONS, local, iv_series=iv_window)
    return dict(result.metrics), result


def _write_candidate_outputs(output_dir: str, name: str, result) -> None:
    result.equity_curve.to_csv(os.path.join(output_dir, f"{name}_equity.csv"))
    trades = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades.empty:
        trades = pd.DataFrame(columns=TRADE_COLUMNS)
    trades.to_csv(os.path.join(output_dir, f"{name}_trades.csv"), index=False)
    pd.DataFrame([result.metrics]).to_csv(os.path.join(output_dir, f"{name}_metrics.csv"), index=False)


def _markdown_report(rows: pd.DataFrame, selector: pd.DataFrame) -> str:
    lines = [
        "# Regime Validation",
        "",
        "Fixed candidates are evaluated across rolling out-of-sample windows. With the default 30-day test and 15-day step, adjacent windows overlap by 15 days.",
        "The selector chooses only from prior train windows, but summed PnL across all folds is a diagnostic, not a realizable equity curve.",
        "",
    ]
    if rows.empty:
        lines.append("No validation windows generated.")
        return "\n".join(lines)

    summary = (
        rows.groupby("candidate")
        .agg(
            windows=("fold", "nunique"),
            overlapping_fold_pnl_sum=("total_pnl", "sum"),
            avg_return=("total_return", "mean"),
            median_return=("total_return", "median"),
            avg_sharpe=("sharpe", "mean"),
            min_pnl=("total_pnl", "min"),
            positive_windows=("total_pnl", lambda s: float((s > 0).mean())),
            trades=("trades", "sum"),
            avg_stress_to_pnl=("stress_to_pnl", "mean"),
        )
        .sort_values(["overlapping_fold_pnl_sum", "positive_windows"], ascending=False)
        .reset_index()
    )
    nonoverlap = (
        rows[rows["fold"] % 2 == 0]
        .groupby("candidate")["total_pnl"]
        .sum()
        .rename("even_nonoverlap_pnl_sum")
    )
    summary = summary.merge(nonoverlap, on="candidate", how="left")
    lines.extend(
        [
            "## Candidate Summary",
            "",
            "| Candidate | Windows | Overlap PnL Sum | Even Non-Overlap PnL | Avg Return | Median Return | Avg Sharpe | Min PnL | Positive Windows | Trades | Avg Stress/PnL |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['candidate']} | {row['windows']:.0f} | {row['overlapping_fold_pnl_sum']:.6f} | "
            f"{row['even_nonoverlap_pnl_sum']:.6f} | "
            f"{row['avg_return']:.4%} | {row['median_return']:.4%} | {row['avg_sharpe']:.3f} | "
            f"{row['min_pnl']:.6f} | {row['positive_windows']:.1%} | {row['trades']:.0f} | "
            f"{row['avg_stress_to_pnl']:.2f} |"
        )

    regime = (
        rows.groupby(["candidate", "regime"])["total_pnl"]
        .agg(["count", "sum", "mean"])
        .reset_index()
    )
    lines.extend(
        [
            "",
            "## Regime PnL",
            "",
            "| Candidate | Regime | Windows | Overlap PnL Sum | Avg PnL |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for _, row in regime.iterrows():
        lines.append(
            f"| {row['candidate']} | {row['regime']} | {row['count']:.0f} | "
            f"{row['sum']:.6f} | {row['mean']:.6f} |"
        )

    lines.extend(
        [
            "",
            "## Walk-Forward Selector",
            "",
            f"- Overlapping fold PnL sum: **{selector['test_total_pnl'].sum():.6f}**" if not selector.empty else "- No selector rows.",
            f"- Even-fold non-overlap PnL sum: **{_nonoverlap_stats(selector, 'test_total_pnl')['even_sum']:.6f}**" if not selector.empty else "",
            f"- Positive OOS windows: **{(selector['test_total_pnl'] > 0).mean():.1%}**" if not selector.empty else "",
            "",
            "| Fold | Selected | Train Score | Test PnL | Test Trades | Regime |",
            "|---:|---|---:|---:|---:|---|",
        ]
    )
    for _, row in selector.iterrows():
        lines.append(
            f"| {row['fold']:.0f} | {row['selected_candidate']} | {row['train_score']:.6f} | "
            f"{row['test_total_pnl']:.6f} | {row['test_trades']:.0f} | {row['regime']} |"
        )
    return "\n".join([line for line in lines if line != ""])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate fixed VRP strategy candidates over rolling regimes.")
    parser.add_argument("--ohlc", default=os.path.join(ROOT, "data", "btc_1h.csv"))
    parser.add_argument("--iv", default=os.path.join(ROOT, "data", "btc_dvol_1h.csv"))
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument(
        "--output-dir",
        default=os.path.join(ROOT, "data", "results", "regime_validation"),
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    ohlc = load_ohlc_csv(args.ohlc)
    iv = load_iv_csv(args.iv)
    configs = candidate_configs()

    overlap_start = max(ohlc["timestamp"].min(), iv.index.min())
    overlap_end = min(ohlc["timestamp"].max(), iv.index.max())
    ohlc = ohlc[(ohlc["timestamp"] >= overlap_start) & (ohlc["timestamp"] <= overlap_end)]
    iv = iv.loc[overlap_start:overlap_end]
    start = overlap_start
    end = overlap_end
    rows = []
    selector_rows = []
    latest_results = {}

    fold = 0
    cursor = start
    while cursor + pd.Timedelta(days=args.train_days + args.test_days) <= end:
        train_start = cursor
        test_start = cursor + pd.Timedelta(days=args.train_days)
        test_end = test_start + pd.Timedelta(days=args.test_days)
        train_ohlc = ohlc[(ohlc["timestamp"] >= train_start) & (ohlc["timestamp"] < test_start)]
        test_ohlc = ohlc[(ohlc["timestamp"] >= test_start) & (ohlc["timestamp"] < test_end)]
        if len(train_ohlc) < 24 * 30 or len(test_ohlc) < 24 * 20:
            cursor += pd.Timedelta(days=args.step_days)
            continue

        regime = _period_regime(test_ohlc, iv)
        train_scores = []
        test_metrics_by_candidate = {}
        for candidate, config in configs.items():
            train_metrics, _ = _run_period(
                ohlc, iv, config, train_start, train_start + pd.Timedelta(days=14), test_start
            )
            train_score = _objective(train_metrics)
            train_scores.append((candidate, train_score))

            test_metrics, result = _run_period(ohlc, iv, config, train_start, test_start, test_end)
            latest_results[candidate] = result
            test_metrics_by_candidate[candidate] = test_metrics
            rows.append(
                {
                    "fold": fold,
                    "train_start": train_start,
                    "test_start": test_start,
                    "test_end": test_end,
                    "candidate": candidate,
                    **regime,
                    **test_metrics,
                }
            )

        selected, score = sorted(train_scores, key=lambda item: item[1], reverse=True)[0]
        selected_metrics = test_metrics_by_candidate[selected]
        selector_rows.append(
            {
                "fold": fold,
                "train_start": train_start,
                "test_start": test_start,
                "test_end": test_end,
                "selected_candidate": selected,
                "train_score": score,
                **regime,
                **{f"test_{k}": v for k, v in selected_metrics.items()},
            }
        )
        print(
            f"Fold {fold}: selected={selected}, test_pnl={selected_metrics['total_pnl']:.4f}, "
            f"regime={regime['regime']}"
        )
        fold += 1
        cursor += pd.Timedelta(days=args.step_days)

    rows_df = pd.DataFrame(rows)
    selector_df = pd.DataFrame(selector_rows)
    rows_df.to_csv(os.path.join(args.output_dir, "candidate_windows.csv"), index=False)
    selector_df.to_csv(os.path.join(args.output_dir, "walk_forward_selector.csv"), index=False)

    for candidate, result in latest_results.items():
        _write_candidate_outputs(args.output_dir, f"latest_{candidate}", result)

    report = _markdown_report(rows_df, selector_df)
    report_path = os.path.join(args.output_dir, "regime_validation_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
