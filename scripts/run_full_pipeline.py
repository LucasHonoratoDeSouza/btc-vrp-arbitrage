import argparse
import os
import sys
import time
from dataclasses import asdict
from typing import Dict, List

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, run_backtest
from vrp_arbitrage.data import load_ohlc_csv
from vrp_arbitrage.deribit_api import (
    get_instruments,
    get_tradingview_chart_data,
    get_volatility_index_data,
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


def build_ohlc_1h(instrument_name: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    result = get_tradingview_chart_data(
        instrument_name, int(start.timestamp() * 1000), int(end.timestamp() * 1000), 60
    )
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(result["ticks"], unit="ms", utc=True),
            "open": result["open"],
            "high": result["high"],
            "low": result["low"],
            "close": result["close"],
            "volume": result.get("volume", [0.0] * len(result["ticks"])),
        }
    )
    return df.sort_values("timestamp")


def build_iv_index_1h(currency: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    result = get_volatility_index_data(
        currency, int(start.timestamp() * 1000), int(end.timestamp() * 1000), 60
    )
    data = result.get("data")
    if data is None:
        return pd.Series(dtype=float)

    if isinstance(data, dict):
        ticks = data.get("t", [])
        close = data.get("c", [])
    elif data and isinstance(data[0], list):
        ticks = [row[0] for row in data]
        close = [row[4] for row in data]
    else:
        ticks = [row.get("t") or row.get("timestamp") for row in data]
        close = [row.get("c") or row.get("close") for row in data]

    if not ticks:
        return pd.Series(dtype=float)
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(ticks, unit="ms", utc=True),
            "close": close,
        }
    )
    df = df.dropna(subset=["close"])
    if df.empty:
        return pd.Series(dtype=float)
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    series = df.set_index("timestamp")["close"].astype(float).sort_index()
    if float(series.median()) > 3.0:
        series = series / 100.0
    return series.resample("1h").last().dropna().rename("iv")


def save_iv_series(path: str, iv_series: pd.Series) -> None:
    out = iv_series.rename("iv").reset_index()
    out.to_csv(path, index=False)


def select_instruments(
    instruments: List[Dict[str, object]],
    spot_median: float,
    spot_min: float,
    spot_max: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: BacktestConfig,
    max_strikes_per_type: int = 12,
    max_instruments: int = 28,
) -> pd.DataFrame:
    df = pd.DataFrame(instruments)
    df["expiry"] = pd.to_datetime(df["expiration_timestamp"], unit="ms", utc=True)
    df["option_type"] = df["option_type"].map({"call": "C", "put": "P"}).fillna(df["option_type"])

    min_expiry = start + pd.Timedelta(hours=config.min_dte_hours)
    max_expiry = end + pd.Timedelta(hours=config.max_dte_hours)
    df = df[(df["expiry"] >= min_expiry) & (df["expiry"] <= max_expiry)]
    if df.empty:
        return pd.DataFrame(columns=df.columns)

    df["dte_hours"] = (df["expiry"] - end).dt.total_seconds() / 3600.0
    df["dte_diff"] = (df["dte_hours"] - config.target_dte_hours).abs()
    target_expiry = df.sort_values("dte_diff").iloc[0]["expiry"]
    df = df[df["expiry"] == target_expiry]

    strike_min = spot_min * 0.6
    strike_max = spot_max * 1.4
    df = df[(df["strike"] >= strike_min) & (df["strike"] <= strike_max)]

    selected = []
    for opt_type, sub in df.groupby("option_type"):
        sub = sub.copy()
        sub["dist"] = (sub["strike"] - spot_median).abs()
        sub = sub.sort_values("dist").head(max_strikes_per_type)
        selected.append(sub)

    if not selected:
        return pd.DataFrame(columns=df.columns)

    merged = pd.concat(selected, ignore_index=True)
    if len(merged) > max_instruments:
        merged = merged.head(max_instruments)
    return merged


def build_options_1h(
    options_df: pd.DataFrame,
    ohlc_df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    hourly_index = pd.DatetimeIndex(ohlc_df["timestamp"])
    close_series = ohlc_df.set_index("timestamp")["close"]
    out_rows = []

    total = len(options_df)
    for idx, row in options_df.iterrows():
        instrument = row["instrument_name"]
        expiry = row["expiry"]
        strike = float(row["strike"])
        opt_type = row["option_type"]

        chart = get_tradingview_chart_data(
            instrument, int(start.timestamp() * 1000), int(end.timestamp() * 1000), 60
        )
        ticks = chart.get("ticks", [])
        if not ticks:
            continue

        chart_df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(ticks, unit="ms", utc=True),
                "close": chart.get("close", []),
            }
        )
        chart_df = chart_df.dropna(subset=["close"])
        if chart_df.empty:
            continue

        price_series = chart_df.set_index("timestamp")["close"].reindex(hourly_index).ffill(
            limit=6
        )
        if price_series.isna().all():
            continue

        spot_series = close_series.reindex(hourly_index)
        median_price = float(price_series.dropna().median())
        if median_price < 2.0:
            price_series = price_series * spot_series

        leg_df = pd.DataFrame(
            {
                "timestamp": hourly_index,
                "expiry": expiry,
                "strike": strike,
                "option_type": opt_type,
                "bid": (price_series * 0.995).values,
                "ask": (price_series * 1.005).values,
                "mark": price_series.values,
                "underlying": spot_series.values,
            }
        )
        leg_df = leg_df.dropna(subset=["bid", "ask", "mark", "underlying"])
        leg_df = leg_df[(leg_df["bid"] > 0.0) & (leg_df["ask"] > 0.0) & (leg_df["mark"] > 0.0)]
        out_rows.append(leg_df)
        if (len(out_rows) % 5) == 0:
            print(f"Built {len(out_rows)}/{total} instruments")
        time.sleep(0.02)

    if not out_rows:
        return pd.DataFrame(
            columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
        )
    return pd.concat(out_rows, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Deribit data and run a real VRP backtest.")
    parser.add_argument("--days", type=int, default=60, help="Lookback window in calendar days.")
    parser.add_argument(
        "--options",
        action="store_true",
        help="Try to download sparse traded option candles for selected live instruments.",
    )
    args = parser.parse_args()

    config = BacktestConfig(
        garch_window_hours=24 * 10,
        zscore_window=24 * 5,
        vrp_entry_z=0.8,
        vrp_exit_z=0.2,
        max_holding_hours=24 * 5,
        use_variance_proxy=True,
    )

    end = pd.Timestamp.now("UTC").floor("h")
    start = end - pd.Timedelta(days=args.days)

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

    print("Fetching 1h OHLC from Deribit...")
    ohlc_df = build_ohlc_1h("BTC-PERPETUAL", start, end)
    ohlc_path = os.path.join(ROOT, "data", "btc_1h.csv")
    ohlc_df.to_csv(ohlc_path, index=False)

    print("Fetching DVOL index...")
    iv_series = build_iv_index_1h("BTC", start, end)
    if iv_series.empty:
        print("DVOL index returned no rows; variance proxy unavailable.")
    else:
        dvol_path = os.path.join(ROOT, "data", "btc_dvol_1h.csv")
        save_iv_series(dvol_path, iv_series)
        print(
            f"DVOL rows: {len(iv_series)} |"
            f" from {iv_series.index.min()} to {iv_series.index.max()}"
        )

    try_options = args.options
    options_df = pd.DataFrame(
        columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
    )

    if try_options:
        print("Fetching BTC option instruments...")
        instruments = get_instruments("BTC", kind="option", expired=False)

        spot_median = float(ohlc_df["close"].median())
        spot_min = float(ohlc_df["close"].min())
        spot_max = float(ohlc_df["close"].max())

        selected = select_instruments(
            instruments, spot_median, spot_min, spot_max, start, end, config
        )
        if selected.empty:
            raise RuntimeError("No option instruments selected. Try expanding the window.")
        print(f"Selected {len(selected)} instruments for download")
        options_df = build_options_1h(selected, ohlc_df, start, end)
        if options_df.empty:
            print("Option history download returned no rows; using variance proxy mode.")
            config.use_variance_proxy = True
            if iv_series.empty:
                raise RuntimeError("DVOL index unavailable; cannot run variance proxy backtest.")
    options_path = os.path.join(ROOT, "data", "deribit_options_1h.csv")
    if try_options or not os.path.exists(options_path):
        options_df.to_csv(options_path, index=False)
    elif os.path.getsize(options_path) > 0:
        print("Keeping existing option dataset; pass --options to refresh it.")
    if not options_df.empty:
        print(
            f"Options rows: {len(options_df)} |"
            f" from {options_df['timestamp'].min()} to {options_df['timestamp'].max()}"
        )

    ohlc_loaded = load_ohlc_csv(ohlc_path)
    result = run_backtest(ohlc_loaded, options_df, config, iv_series=iv_series)
    save_backtest_outputs(result, os.path.join(ROOT, "data"), "real_backtest")

    print(result.metrics)
    if result.diagnostics:
        print("Diagnostics:")
        for note in result.diagnostics:
            print("-", note)


if __name__ == "__main__":
    main()
