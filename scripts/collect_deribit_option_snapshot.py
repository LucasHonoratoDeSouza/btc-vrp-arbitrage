import argparse
import os
import sys
import time

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage.deribit_api import get_book_summary_by_currency, get_instruments, get_order_book

DATA_DIR = os.path.join(ROOT, "data")


def _option_type(value: str) -> str:
    text = str(value).lower()
    if text.startswith("c"):
        return "C"
    if text.startswith("p"):
        return "P"
    return str(value).upper()


def _select_instruments(
    instruments: pd.DataFrame,
    spot: float,
    max_dte_days: int,
    max_instruments: int,
    strikes_per_expiry_type: int,
) -> pd.DataFrame:
    now = pd.Timestamp.now("UTC")
    df = instruments.copy()
    df["expiry"] = pd.to_datetime(df["expiration_timestamp"], unit="ms", utc=True)
    df["dte_days"] = (df["expiry"] - now).dt.total_seconds() / 86400.0
    df = df[(df["dte_days"] > 0.25) & (df["dte_days"] <= max_dte_days)]
    df["option_type"] = df["option_type"].map(_option_type)
    df["strike_distance"] = (df["strike"].astype(float) - spot).abs() / spot

    selected = []
    for (_, opt_type), group in df.groupby(["expiry", "option_type"]):
        selected.append(group.sort_values("strike_distance").head(strikes_per_expiry_type))
    if not selected:
        return pd.DataFrame(columns=df.columns)
    out = pd.concat(selected, ignore_index=True).sort_values(["dte_days", "strike_distance"])
    return out.head(max_instruments)


def _summary_spot(summary: list[dict]) -> float:
    values = [
        row.get("underlying_price")
        or row.get("estimated_delivery_price")
        for row in summary
        if row.get("underlying_price") or row.get("estimated_delivery_price")
    ]
    if not values:
        raise RuntimeError("Could not infer BTC spot from Deribit book summary.")
    return float(pd.Series(values).median())


def _snapshot_row(
    instrument: pd.Series, snapshot_time: pd.Timestamp, pause_seconds: float
) -> dict | None:
    time.sleep(pause_seconds)
    book = get_order_book(str(instrument["instrument_name"]), depth=1)
    bid = float(book.get("best_bid_price") or 0.0)
    ask = float(book.get("best_ask_price") or 0.0)
    mark = float(book.get("mark_price") or 0.0)
    underlying = float(book.get("underlying_price") or book.get("index_price") or 0.0)
    if bid <= 0.0 or ask <= 0.0 or mark <= 0.0 or underlying <= 0.0:
        return None

    greeks = book.get("greeks") or {}
    stats = book.get("stats") or {}
    quote_timestamp = pd.to_datetime(book.get("timestamp"), unit="ms", utc=True)
    bid_size = float(book.get("best_bid_amount") or 0.0)
    ask_size = float(book.get("best_ask_amount") or 0.0)

    return {
        "timestamp": snapshot_time,
        "quote_timestamp": quote_timestamp,
        "instrument_name": book.get("instrument_name") or instrument["instrument_name"],
        "expiry": instrument["expiry"],
        "strike": float(instrument["strike"]),
        "option_type": _option_type(instrument["option_type"]),
        "bid": bid * underlying,
        "ask": ask * underlying,
        "mark": mark * underlying,
        "bid_btc": bid,
        "ask_btc": ask,
        "mark_btc": mark,
        "underlying": underlying,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "volume": float(stats.get("volume") or 0.0),
        "volume_usd": float(stats.get("volume_usd") or 0.0),
        "open_interest": float(book.get("open_interest") or 0.0),
        "mark_iv": float(book.get("mark_iv") or 0.0),
        "bid_iv": float(book.get("bid_iv") or 0.0),
        "ask_iv": float(book.get("ask_iv") or 0.0),
        "delta": float(greeks.get("delta") or 0.0),
        "gamma": float(greeks.get("gamma") or 0.0),
        "vega": float(greeks.get("vega") or 0.0),
        "theta": float(greeks.get("theta") or 0.0),
        "rho": float(greeks.get("rho") or 0.0),
        "index_price": float(book.get("index_price") or 0.0),
        "state": book.get("state"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect a point-in-time Deribit BTC option-chain snapshot with bid/ask sizes and greeks."
    )
    parser.add_argument("--max-dte-days", type=int, default=45)
    parser.add_argument("--max-instruments", type=int, default=160)
    parser.add_argument("--strikes-per-expiry-type", type=int, default=12)
    parser.add_argument("--pause-seconds", type=float, default=0.03)
    parser.add_argument("--append", action="store_true", help="Append to deribit_option_snapshots.csv.")
    parser.add_argument("--repeat", type=int, default=1, help="Number of snapshots to collect.")
    parser.add_argument("--interval-seconds", type=float, default=300.0, help="Delay between repeated snapshots.")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    history_path = os.path.join(DATA_DIR, "deribit_option_snapshots.csv")
    latest_path = os.path.join(DATA_DIR, "deribit_options_rich_latest.csv")
    all_new_rows = []

    for snapshot_idx in range(args.repeat):
        summary = get_book_summary_by_currency("BTC", kind="option")
        spot = _summary_spot(summary)
        instruments = pd.DataFrame(get_instruments("BTC", kind="option", expired=False))
        selected = _select_instruments(
            instruments,
            spot=spot,
            max_dte_days=args.max_dte_days,
            max_instruments=args.max_instruments,
            strikes_per_expiry_type=args.strikes_per_expiry_type,
        )
        if selected.empty:
            raise RuntimeError("No option instruments selected for snapshot.")

        snapshot_time = pd.Timestamp.now("UTC").floor("min")
        rows = []
        for idx, (_, instrument) in enumerate(selected.iterrows(), start=1):
            row = _snapshot_row(instrument, snapshot_time, args.pause_seconds)
            if row is not None:
                rows.append(row)
            if idx % 25 == 0:
                print(
                    f"Snapshot {snapshot_idx + 1}/{args.repeat}: "
                    f"fetched {idx}/{len(selected)} instruments; usable rows: {len(rows)}"
                )
        all_new_rows.extend(rows)

        latest = pd.DataFrame(rows)
        latest.to_csv(latest_path, index=False)
        print(f"Saved {len(rows)} rich snapshot rows to {latest_path}")

        if snapshot_idx < args.repeat - 1:
            time.sleep(args.interval_seconds)

    out = pd.DataFrame(all_new_rows)
    if args.append and os.path.exists(history_path):
        previous = pd.read_csv(history_path)
        for column in ["timestamp", "expiry", "quote_timestamp"]:
            if column in previous.columns:
                previous[column] = pd.to_datetime(
                    previous[column], utc=True, format="mixed"
                )
        if "quote_timestamp" in previous.columns:
            previous["quote_timestamp"] = pd.to_datetime(
                previous["quote_timestamp"], utc=True, format="mixed"
            )
        out = pd.concat([previous, out], ignore_index=True)
        out = out.drop_duplicates(subset=["timestamp", "instrument_name"], keep="last")
    out.to_csv(history_path, index=False)
    print(f"Snapshot history: {history_path}")


if __name__ == "__main__":
    main()
