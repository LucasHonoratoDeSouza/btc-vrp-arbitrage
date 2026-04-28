from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://www.deribit.com/api/v2"


def _api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload and payload["error"]:
        raise RuntimeError(payload["error"])
    return payload["result"]


def get_tradingview_chart_data(
    instrument_name: str,
    start_ts_ms: int,
    end_ts_ms: int,
    resolution_minutes: int = 60,
) -> Dict[str, List[Any]]:
    params = {
        "instrument_name": instrument_name,
        "start_timestamp": start_ts_ms,
        "end_timestamp": end_ts_ms,
        "resolution": str(resolution_minutes),
    }
    return _api_get("/public/get_tradingview_chart_data", params)


def get_instruments(currency: str, kind: str = "option", expired: bool = True) -> List[Dict[str, Any]]:
    params = {"currency": currency, "kind": kind, "expired": str(expired).lower()}
    return _api_get("/public/get_instruments", params)


def get_book_summary_by_currency(currency: str, kind: str = "option") -> List[Dict[str, Any]]:
    params = {"currency": currency, "kind": kind}
    return _api_get("/public/get_book_summary_by_currency", params)


def get_order_book(instrument_name: str, depth: int = 1) -> Dict[str, Any]:
    params = {"instrument_name": instrument_name, "depth": depth}
    return _api_get("/public/get_order_book", params)


def get_last_trades_by_instrument(
    instrument_name: str,
    start_ts_ms: int,
    end_ts_ms: int,
    count: int = 1000,
    pause_seconds: float = 0.08,
) -> List[Dict[str, Any]]:
    params = {
        "instrument_name": instrument_name,
        "start_timestamp": start_ts_ms,
        "end_timestamp": end_ts_ms,
        "count": count,
        "include_old": "true",
    }
    trades: List[Dict[str, Any]] = []
    continuation = None
    while True:
        if continuation:
            params["continuation"] = continuation
        result = _api_get("/public/get_last_trades_by_instrument", params)
        batch = result.get("trades", [])
        trades.extend(batch)
        if not result.get("has_more"):
            break
        continuation = result.get("continuation")
        if not continuation:
            break
        time.sleep(pause_seconds)
    return trades


def get_volatility_index_data(
    currency: str,
    start_ts_ms: int,
    end_ts_ms: int,
    resolution_seconds: int = 3600,
) -> Dict[str, Any]:
    # Deribit DVOL resolution is in SECONDS (3600 = 1h), unlike OHLC which uses minutes.
    params = {
        "currency": currency,
        "start_timestamp": start_ts_ms,
        "end_timestamp": end_ts_ms,
        "resolution": str(resolution_seconds),
    }
    rows: List[Any] = []
    continuation = None
    seen_continuations = set()
    while True:
        if continuation:
            if continuation in seen_continuations:
                break
            seen_continuations.add(continuation)
            params["end_timestamp"] = continuation
        result = _api_get("/public/get_volatility_index_data", params)
        data = result.get("data", [])
        rows.extend(data)
        continuation = result.get("continuation")
        if not continuation or continuation <= start_ts_ms:
            break
        time.sleep(0.02)
    return {"data": rows, "continuation": None}
