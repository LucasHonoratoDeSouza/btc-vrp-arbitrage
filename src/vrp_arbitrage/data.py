from __future__ import annotations

import numpy as np
import pandas as p


def normalize_option_type(value: str) -> str:
    text = str(value).upper()
    if text.startswith("C"):
        return "C"
    if text.startswith("P"):
        return "P"
    return text


def load_ohlc_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    return df.sort_values("timestamp")


def load_options_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    df["expiry"] = pd.to_datetime(df["expiry"], utc=True, format="mixed")
    df["option_type"] = df["option_type"].apply(normalize_option_type)
    return df.sort_values(["timestamp", "expiry", "strike"])


def load_iv_csv(path: str) -> pd.Series:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    value_col = "iv" if "iv" in df.columns else "close"
    series = df.set_index("timestamp")[value_col].astype(float).sort_index()
    if not series.empty and float(series.median()) > 3.0:
        series = series / 100.0
    return series.rename("iv")


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close).diff()
