import argparse
import os
import sys
import time

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage.deribit_api import (
    get_tradingview_chart_data,
    get_volatility_index_data,
)


def _fetch_ohlc_chunk(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    result = get_tradingview_chart_data(
        "BTC-PERPETUAL",
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
        60,
    )
    ticks = result.get("ticks", [])
    if not ticks:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(ticks, unit="ms", utc=True),
            "open": result.get("open", []),
            "high": result.get("high", []),
            "low": result.get("low", []),
            "close": result.get("close", []),
            "volume": result.get("volume", [0.0] * len(ticks)),
        }
    )


def _parse_dvol_rows(result: dict) -> pd.Series:
    data = result.get("data") or []
    if not data:
        return pd.Series(dtype=float, name="iv")

    if isinstance(data, dict):
        ticks = data.get("t", [])
        close = data.get("c", [])
    elif isinstance(data[0], list):
        ticks = [row[0] for row in data]
        close = [row[4] for row in data]
    else:
        ticks = [row.get("t") or row.get("timestamp") for row in data]
        close = [row.get("c") or row.get("close") for row in data]

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(ticks, unit="ms", utc=True),
            "iv": pd.to_numeric(close, errors="coerce"),
        }
    ).dropna()
    if df.empty:
        return pd.Series(dtype=float, name="iv")
    series = df.drop_duplicates("timestamp", keep="last").set_index("timestamp")["iv"]
    series = series.sort_index()
    if float(series.median()) > 3.0:
        series = series / 100.0
    return series.resample("1h").last().dropna().rename("iv")


def fetch_ohlc(start: pd.Timestamp, end: pd.Timestamp, chunk_days: int) -> pd.DataFrame:
    frames = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + pd.Timedelta(days=chunk_days), end)
        frame = _fetch_ohlc_chunk(cursor, chunk_end)
        if not frame.empty:
            frames.append(frame)
        print(f"OHLC {cursor} -> {chunk_end}: {len(frame)} rows")
        cursor = chunk_end
        time.sleep(0.08)

    if not frames:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
    out = pd.concat(frames, ignore_index=True)
    return (
        out.drop_duplicates("timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def fetch_dvol(start: pd.Timestamp, end: pd.Timestamp, chunk_days: int) -> pd.Series:
    series_list = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + pd.Timedelta(days=chunk_days), end)
        result = get_volatility_index_data(
            "BTC",
            int(cursor.timestamp() * 1000),
            int(chunk_end.timestamp() * 1000),
            3600,
        )
        series = _parse_dvol_rows(result)
        if not series.empty:
            series_list.append(series)
        print(f"DVOL {cursor} -> {chunk_end}: {len(series)} hourly rows")
        cursor = chunk_end
        time.sleep(0.08)

    if not series_list:
        return pd.Series(dtype=float, name="iv")
    out = pd.concat(series_list).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.rename("iv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch BTC-PERPETUAL OHLC and BTC DVOL hourly history from Deribit."
    )
    parser.add_argument("--days", type=int, default=None, help="Days back from now (ignored if --start-date given)")
    parser.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD (UTC)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (UTC); default=now")
    parser.add_argument("--dvol-start-date", default=None, help="Override start date for DVOL only (DVOL began 2021-03-24)")
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--ohlc-file", default=None, help="Output path for OHLC CSV")
    parser.add_argument("--dvol-file", default=None, help="Output path for DVOL CSV")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(ROOT, "data", "extended"),
    )
    args = parser.parse_args()

    end = (
        pd.Timestamp(args.end_date, tz="UTC")
        if args.end_date
        else pd.Timestamp.now("UTC").floor("h")
    )

    if args.start_date:
        ohlc_start = pd.Timestamp(args.start_date, tz="UTC")
    elif args.days:
        ohlc_start = end - pd.Timedelta(days=args.days)
    else:
        ohlc_start = end - pd.Timedelta(days=730)

    dvol_start = (
        pd.Timestamp(args.dvol_start_date, tz="UTC")
        if args.dvol_start_date
        else ohlc_start
    )

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Fetching OHLC from {ohlc_start.date()} to {end.date()} ...")
    ohlc = fetch_ohlc(ohlc_start, end, args.chunk_days)

    print(f"Fetching DVOL from {dvol_start.date()} to {end.date()} ...")
    iv = fetch_dvol(dvol_start, end, args.chunk_days)

    days_label = int((end - ohlc_start).total_seconds() / 86400)
    ohlc_path = args.ohlc_file or os.path.join(args.output_dir, f"btc_1h_{days_label}d.csv")
    iv_path = args.dvol_file or os.path.join(args.output_dir, f"btc_dvol_1h_{days_label}d.csv")

    ohlc.to_csv(ohlc_path, index=False)
    iv.reset_index().to_csv(iv_path, index=False)

    print(f"Saved {len(ohlc)} OHLC rows to {ohlc_path}")
    print(f"Saved {len(iv)} DVOL rows to {iv_path}")


if __name__ == "__main__":
    main()
