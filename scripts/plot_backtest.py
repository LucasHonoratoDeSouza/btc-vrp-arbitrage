import os
import sys
from glob import glob

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from pandas.errors import EmptyDataError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig
from vrp_arbitrage.data import load_iv_csv, log_returns
from vrp_arbitrage.volatility import rolling_garch_forecast

DATA_DIR = os.path.join(ROOT, "data")
PLOTS_DIR = os.path.join(DATA_DIR, "results", "plots")

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams["figure.dpi"] = 130
plt.rcParams["savefig.dpi"] = 160
plt.rcParams["axes.titleweight"] = "bold"


def _ensure_plots_dir() -> None:
    os.makedirs(PLOTS_DIR, exist_ok=True)


def _load_csv(path: str, date_cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, parse_dates=date_cols, date_format="mixed")
    except EmptyDataError:
        return pd.DataFrame()


def _save(fig: plt.Figure, filename: str) -> None:
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, filename), bbox_inches="tight")
    plt.close(fig)


def _drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def _hourly_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def load_backtest(prefix: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    equity = _load_csv(
        os.path.join(DATA_DIR, f"{prefix}_equity.csv"),
        ["timestamp"],
    )
    trades = _load_csv(
        os.path.join(DATA_DIR, f"{prefix}_trades.csv"),
        ["entry_time", "exit_time"],
    )
    metrics = _load_csv(os.path.join(DATA_DIR, f"{prefix}_metrics.csv"), [])
    return equity, trades, metrics


def plot_equity_drawdown(prefix: str, equity: pd.DataFrame) -> None:
    if equity.empty:
        return
    curve = equity.set_index("timestamp")["equity"].astype(float)
    dd = _drawdown(curve)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True, height_ratios=[2.2, 1])
    axes[0].plot(curve.index, curve.values, color="#1f77b4", linewidth=2)
    axes[0].set_title(f"{prefix}: equity curve")
    axes[0].set_ylabel("Equity")

    axes[1].fill_between(dd.index, dd.values * 100.0, 0.0, color="#d62728", alpha=0.35)
    axes[1].plot(dd.index, dd.values * 100.0, color="#d62728", linewidth=1.4)
    axes[1].set_title("Drawdown")
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    _save(fig, f"{prefix}_equity_drawdown.png")


def plot_returns(prefix: str, equity: pd.DataFrame) -> None:
    if equity.empty:
        return
    curve = equity.set_index("timestamp")["equity"].astype(float)
    returns = _hourly_returns(curve)
    rolling_vol = returns.rolling(24 * 7).std(ddof=1) * np.sqrt(365 * 24)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.histplot(returns[returns != 0.0] * 100.0, bins=35, kde=True, ax=axes[0], color="#4c78a8")
    axes[0].set_title(f"{prefix}: hourly return distribution")
    axes[0].set_xlabel("Hourly return (%)")

    axes[1].plot(rolling_vol.index, rolling_vol.values, color="#f58518", linewidth=2)
    axes[1].set_title("Rolling 7d annualized equity volatility")
    axes[1].set_ylabel("Volatility")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    _save(fig, f"{prefix}_returns_volatility.png")


def plot_trade_pnl(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades = trades.copy()
    trades["pnl"] = trades["pnl"].astype(float)
    trades["cum_pnl"] = trades["pnl"].cumsum()
    colors = np.where(trades["pnl"] >= 0.0, "#2ca02c", "#d62728")

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    axes[0].bar(trades["exit_time"], trades["pnl"], color=colors, width=0.08)
    axes[0].axhline(0.0, color="#333333", linewidth=1)
    axes[0].set_title(f"{prefix}: trade PnL")
    axes[0].set_ylabel("PnL")
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %Hh"))

    axes[1].plot(trades["exit_time"], trades["cum_pnl"], color="#1f77b4", marker="o")
    axes[1].axhline(0.0, color="#333333", linewidth=1)
    axes[1].set_title("Cumulative realized trade PnL")
    axes[1].set_ylabel("Cumulative PnL")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %Hh"))
    _save(fig, f"{prefix}_trade_pnl.png")


def plot_trade_risk(prefix: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    trades = trades.copy()
    for col in ["pnl", "vrp_at_entry", "iv_at_entry", "rv_forecast_at_entry", "stress_pnl"]:
        if col in trades:
            trades[col] = trades[col].astype(float)
    trades["duration_hours"] = (
        trades["exit_time"] - trades["entry_time"]
    ).dt.total_seconds() / 3600.0

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    sns.histplot(trades["pnl"], bins=min(30, max(5, len(trades))), kde=True, ax=axes[0, 0], color="#4c78a8")
    axes[0, 0].axvline(0.0, color="#333333", linewidth=1)
    axes[0, 0].set_title("Trade PnL distribution")

    sns.scatterplot(data=trades, x="vrp_at_entry", y="pnl", hue="strategy", ax=axes[0, 1], s=80)
    axes[0, 1].axhline(0.0, color="#333333", linewidth=1)
    axes[0, 1].set_title("Entry VRP vs PnL")

    sns.scatterplot(data=trades, x="duration_hours", y="pnl", hue="strategy", ax=axes[1, 0], s=80, legend=False)
    axes[1, 0].axhline(0.0, color="#333333", linewidth=1)
    axes[1, 0].set_title("Holding time vs PnL")
    axes[1, 0].set_xlabel("Duration (hours)")

    axes[1, 1].bar(np.arange(len(trades)), trades["stress_pnl"], color="#d62728", alpha=0.7)
    axes[1, 1].axhline(0.0, color="#333333", linewidth=1)
    axes[1, 1].set_title("Per-trade 20% gap stress PnL")
    axes[1, 1].set_xlabel("Trade number")
    _save(fig, f"{prefix}_trade_risk.png")


def plot_metrics_comparison(metrics_by_prefix: dict[str, pd.DataFrame]) -> None:
    rows = []
    for prefix, metrics in metrics_by_prefix.items():
        if metrics.empty:
            continue
        row = metrics.iloc[0].copy()
        row["backtest"] = prefix
        rows.append(row)
    if not rows:
        return
    df = pd.DataFrame(rows)
    wanted = ["total_pnl", "sharpe", "max_drawdown", "vrp_capture_efficiency", "stress_gap_pnl"]
    wanted = [col for col in wanted if col in df.columns]

    fig, axes = plt.subplots(len(wanted), 1, figsize=(12, 3.2 * len(wanted)))
    if len(wanted) == 1:
        axes = [axes]
    for ax, metric in zip(axes, wanted):
        sns.barplot(data=df, x="backtest", y=metric, ax=ax, color="#4c78a8")
        ax.axhline(0.0, color="#333333", linewidth=1)
        ax.set_title(metric)
        ax.set_xlabel("")
    _save(fig, "metrics_comparison.png")


def plot_strategy_profiles() -> None:
    path = os.path.join(DATA_DIR, "strategy_profile_results.csv")
    if not os.path.exists(path):
        return
    df = pd.read_csv(path)
    if df.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    sns.barplot(data=df, x="profile", y="total_pnl", ax=axes[0, 0], color="#4c78a8")
    axes[0, 0].set_title("Total PnL by profile")
    sns.barplot(data=df, x="profile", y="stress_gap_pnl", ax=axes[0, 1], color="#d62728")
    axes[0, 1].axhline(0, color="#333333", linewidth=1)
    axes[0, 1].set_title("20% gap stress PnL")
    sns.barplot(data=df, x="profile", y="avg_trade_notional", ax=axes[1, 0], color="#54a24b")
    axes[1, 0].set_title("Average trade notional")
    sns.scatterplot(data=df, x="stress_gap_pnl", y="total_pnl", hue="profile", s=140, ax=axes[1, 1])
    axes[1, 1].axhline(0, color="#333333", linewidth=1)
    axes[1, 1].axvline(0, color="#333333", linewidth=1)
    axes[1, 1].set_title("Return vs tail-risk tradeoff")
    _save(fig, "strategy_profile_comparison.png")


def plot_real_signal() -> None:
    ohlc_path = os.path.join(DATA_DIR, "btc_1h.csv")
    dvol_path = os.path.join(DATA_DIR, "btc_dvol_1h.csv")
    trades_path = os.path.join(DATA_DIR, "real_backtest_trades.csv")
    if not (os.path.exists(ohlc_path) and os.path.exists(dvol_path)):
        return

    ohlc = pd.read_csv(ohlc_path, parse_dates=["timestamp"])
    iv = load_iv_csv(dvol_path)
    trades = _load_csv(trades_path, ["entry_time", "exit_time"])

    returns = log_returns(ohlc["close"])
    returns.index = pd.to_datetime(ohlc["timestamp"], utc=True)
    config = BacktestConfig(
        use_variance_proxy=True,
        garch_window_hours=24 * 10,
        zscore_window=24 * 5,
        vrp_entry_z=0.8,
        vrp_exit_z=0.2,
        max_holding_hours=24 * 5,
    )
    rv = rolling_garch_forecast(
        returns,
        config.garch_window_hours,
        config.forecast_horizon_hours,
        config.garch_refit_interval_hours,
        config.min_annual_vol,
        config.max_annual_vol,
    )

    index = pd.to_datetime(ohlc["timestamp"], utc=True)
    iv = iv.reindex(index).ffill()
    rv = rv.reindex(index).ffill()
    spread = iv - rv

    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True, height_ratios=[1.3, 1.3, 1])
    axes[0].plot(index, ohlc["close"], color="#111111", linewidth=1.8)
    axes[0].set_title("BTC-PERPETUAL 1h close")
    axes[0].set_ylabel("BTC")

    axes[1].plot(index, iv, label="DVOL IV", color="#4c78a8", linewidth=1.8)
    axes[1].plot(index, rv, label="GARCH RV forecast", color="#f58518", linewidth=1.8)
    axes[1].set_title("Implied vs forecast realized volatility")
    axes[1].legend(loc="upper left")

    axes[2].plot(index, spread, color="#54a24b", linewidth=1.8)
    axes[2].axhline(0.0, color="#333333", linewidth=1)
    axes[2].set_title("VRP spread: IV - RV forecast")
    axes[2].set_ylabel("Spread")

    if not trades.empty:
        for entry in trades["entry_time"]:
            for ax in axes:
                ax.axvline(entry, color="#2ca02c", alpha=0.22, linewidth=1)
        for exit_time in trades["exit_time"]:
            axes[2].axvline(exit_time, color="#d62728", alpha=0.20, linewidth=1)

    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    _save(fig, "real_backtest_signal_vrp.png")


def plot_options_coverage() -> None:
    options_path = os.path.join(DATA_DIR, "deribit_options_1h.csv")
    if not os.path.exists(options_path):
        return
    options = pd.read_csv(options_path, parse_dates=["timestamp", "expiry"])
    if options.empty:
        return

    options["instrument"] = (
        options["expiry"].astype(str)
        + "-"
        + options["strike"].astype(str)
        + "-"
        + options["option_type"].astype(str)
    )
    coverage = options.groupby("timestamp")["instrument"].nunique()
    strikes = options.groupby("timestamp")["strike"].agg(["min", "max", "nunique"])

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(coverage.index, coverage.values, color="#4c78a8", linewidth=2)
    axes[0].set_title("Option dataset coverage")
    axes[0].set_ylabel("Instruments")

    axes[1].fill_between(strikes.index, strikes["min"], strikes["max"], color="#72b7b2", alpha=0.35)
    axes[1].plot(strikes.index, strikes["min"], color="#54a24b", linewidth=1)
    axes[1].plot(strikes.index, strikes["max"], color="#d62728", linewidth=1)
    axes[1].set_title("Strike range available by hour")
    axes[1].set_ylabel("Strike")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    _save(fig, "options_dataset_coverage.png")


def plot_rich_snapshot_liquidity() -> None:
    path = os.path.join(DATA_DIR, "deribit_option_snapshots.csv")
    if not os.path.exists(path):
        return
    df = pd.read_csv(path, parse_dates=["timestamp", "expiry"], date_format="mixed")
    if df.empty:
        return
    latest_ts = df["timestamp"].max()
    latest = df[df["timestamp"] == latest_ts].copy()
    if latest.empty:
        return
    latest["dte_days"] = (latest["expiry"] - latest["timestamp"]).dt.total_seconds() / 86400.0
    latest["spread_pct"] = (latest["ask"] - latest["bid"]) / latest["mark"].replace(0.0, np.nan)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    sns.scatterplot(
        data=latest,
        x="strike",
        y="mark_iv",
        hue="option_type",
        size="open_interest",
        sizes=(30, 220),
        ax=axes[0, 0],
    )
    axes[0, 0].set_title("Latest rich snapshot: mark IV by strike")
    axes[0, 0].set_ylabel("Mark IV")

    sns.scatterplot(
        data=latest,
        x="strike",
        y="spread_pct",
        hue="option_type",
        size="bid_size",
        sizes=(30, 220),
        ax=axes[0, 1],
    )
    axes[0, 1].set_title("Bid/ask spread by strike")
    axes[0, 1].set_ylabel("Spread / mark")

    sns.histplot(latest["open_interest"], bins=25, ax=axes[1, 0], color="#4c78a8")
    axes[1, 0].set_title("Open interest distribution")
    axes[1, 0].set_xlabel("Open interest")

    coverage = df.groupby("timestamp")["instrument_name"].nunique()
    axes[1, 1].plot(coverage.index, coverage.values, color="#54a24b", linewidth=2)
    axes[1, 1].set_title("Rich snapshot instruments over time")
    axes[1, 1].set_ylabel("Instruments")
    axes[1, 1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

    _save(fig, "rich_snapshot_liquidity.png")


def main() -> None:
    _ensure_plots_dir()
    prefixes = ["real_backtest", "local_backtest", "rich_backtest"]
    profile_equity_files = glob(os.path.join(DATA_DIR, "profile_*_equity.csv"))
    profile_prefixes = sorted(
        os.path.basename(path).removesuffix("_equity.csv")
        for path in profile_equity_files
    )
    prefixes.extend(profile_prefixes)
    metrics_by_prefix = {}

    for prefix in prefixes:
        equity, trades, metrics = load_backtest(prefix)
        metrics_by_prefix[prefix] = metrics
        plot_equity_drawdown(prefix, equity)
        plot_returns(prefix, equity)
        plot_trade_pnl(prefix, trades)
        plot_trade_risk(prefix, trades)

    plot_metrics_comparison(metrics_by_prefix)
    plot_real_signal()
    plot_options_coverage()
    plot_rich_snapshot_liquidity()
    plot_strategy_profiles()
    print(f"Plots saved to {PLOTS_DIR}")


if __name__ == "__main__":
    main()
