from __future__ import annotations

import math
from typing import List, Optional

import numpy as np
import pandas as pd

from .config import BacktestConfig
from .data import log_returns
from .metrics import (
    diagnose_backtest,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    stress_test_gap,
    vrp_capture_efficiency,
)
from .pricing import black_scholes_price, bs_delta, bs_vega, implied_vol
from .signals import rolling_kurtosis, select_strategy, zscore
from .types import BacktestResult, OptionLeg, Position, Trade
from .volatility import rolling_ewma_forecast, rolling_garch_forecast


def _apply_slippage(price: float, side: str, config: BacktestConfig) -> float:
    slip = config.slippage_ticks * config.tick_size
    if side == "sell":
        return max(0.0, price - slip)
    return price + slip


def _execution_price(row: pd.Series, side: str, config: BacktestConfig, maker: bool) -> float:
    slip = config.slippage_ticks * config.tick_size
    bid = float(row.get("bid", row.get("mid", 0.0)))
    ask = float(row.get("ask", row.get("mid", 0.0)))
    mid = float(row.get("mid", (bid + ask) * 0.5))
    if bid <= 0 or ask <= 0:
        return _apply_slippage(mid, side, config)
    if maker:
        return max(0.0, ask - slip) if side == "sell" else bid + slip
    return max(0.0, bid - slip) if side == "sell" else ask + slip


def _option_fee(
    row: Optional[pd.Series],
    price: float,
    qty: float,
    fee_rate: float,
    config: BacktestConfig,
) -> float:
    fee_sign = 1.0 if fee_rate >= 0.0 else -1.0
    underlying = float(row.get("underlying", 0.0)) if row is not None else 0.0
    base_fee = abs(underlying * fee_rate) if underlying > 0.0 else abs(price * fee_rate)
    capped_fee = abs(price) * config.option_fee_cap_pct
    return fee_sign * min(base_fee, capped_fee) * abs(qty)


def _clean_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _config_timestamp(value: object) -> Optional[pd.Timestamp]:
    if value is None or value == "":
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _entry_allowed(
    ts: pd.Timestamp,
    entry_start: Optional[pd.Timestamp],
    entry_end: Optional[pd.Timestamp],
) -> bool:
    return (entry_start is None or ts >= entry_start) and (
        entry_end is None or ts < entry_end
    )


def _prepare_options(options_df: pd.DataFrame, rate: float) -> pd.DataFrame:
    df = options_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["expiry"] = pd.to_datetime(df["expiry"], utc=True)
    numeric_cols = [
        "bid",
        "ask",
        "mark",
        "underlying",
        "strike",
        "bid_size",
        "ask_size",
        "volume",
        "open_interest",
        "mark_iv",
        "delta",
        "gamma",
        "vega",
    ]
    df = _clean_numeric(df, numeric_cols)
    df = df.dropna(subset=["bid", "ask", "underlying", "strike"])
    df = df[(df["bid"] > 0.0) & (df["ask"] > 0.0) & (df["ask"] >= df["bid"])]

    price_cols = [col for col in ["bid", "ask", "mark"] if col in df.columns]
    if price_cols and float(df[price_cols].stack().median()) < 2.0:
        for col in price_cols:
            df[col] = df[col] * df["underlying"]

    if "mark" not in df.columns:
        df["mark"] = np.nan
    df["mid"] = df["mark"].where(df["mark"] > 0.0, (df["bid"] + df["ask"]) * 0.5)
    df = df[df["mid"] > 0]
    df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"]
    df = df[df["spread_pct"].replace([np.inf, -np.inf], np.nan).notna()]
    time_years = (df["expiry"] - df["timestamp"]).dt.total_seconds() / (
        365.0 * 24.0 * 3600.0
    )
    df = df.assign(time_years=time_years)
    df = df[df["time_years"] > 0]

    if "mark_iv" in df.columns:
        df["iv"] = df["mark_iv"] / np.where(df["mark_iv"] > 3.0, 100.0, 1.0)
    else:
        df["iv"] = np.nan
    missing_iv = df["iv"].isna() | (df["iv"] <= 0.0)
    if missing_iv.any():
        df.loc[missing_iv, "iv"] = [
            implied_vol(p, s, k, t, rate, opt)
            for p, s, k, t, opt in zip(
                df.loc[missing_iv, "mid"],
                df.loc[missing_iv, "underlying"],
                df.loc[missing_iv, "strike"],
                df.loc[missing_iv, "time_years"],
                df.loc[missing_iv, "option_type"],
            )
        ]

    if "delta" not in df.columns:
        df["delta"] = np.nan
    missing_delta = df["delta"].isna()
    if missing_delta.any():
        df.loc[missing_delta, "delta"] = [
            bs_delta(s, k, t, rate, v, opt)
            for s, k, t, v, opt in zip(
                df.loc[missing_delta, "underlying"],
                df.loc[missing_delta, "strike"],
                df.loc[missing_delta, "time_years"],
                df.loc[missing_delta, "iv"],
                df.loc[missing_delta, "option_type"],
            )
        ]

    if "vega" not in df.columns:
        df["vega"] = np.nan
    missing_vega = df["vega"].isna()
    if missing_vega.any():
        df.loc[missing_vega, "vega"] = [
            bs_vega(s, k, t, rate, v)
            for s, k, t, v in zip(
                df.loc[missing_vega, "underlying"],
                df.loc[missing_vega, "strike"],
                df.loc[missing_vega, "time_years"],
                df.loc[missing_vega, "iv"],
            )
        ]
    df = df[(df["iv"] > 0.0) & np.isfinite(df["iv"])]
    return df


def _select_expiry_slice(
    options_ts: pd.DataFrame, ts: pd.Timestamp, config: BacktestConfig
) -> Optional[pd.DataFrame]:
    if options_ts.empty:
        return None
    options_ts = options_ts.copy()
    options_ts["dte_hours"] = (
        options_ts["expiry"] - ts
    ).dt.total_seconds() / 3600.0
    options_ts = options_ts[
        (options_ts["dte_hours"] >= config.min_dte_hours)
        & (options_ts["dte_hours"] <= config.max_dte_hours)
    ]
    if options_ts.empty:
        return None
    options_ts["dte_diff"] = (options_ts["dte_hours"] - config.target_dte_hours).abs()
    expiry = options_ts.sort_values("dte_diff").iloc[0]["expiry"]
    return options_ts[options_ts["expiry"] == expiry]


def _liquidity_filter(df: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out = out[(out["mid"] > 0.0) & (out["bid"] >= config.min_option_bid)]
    out = out[out["spread_pct"] <= config.max_bid_ask_spread_pct]
    if "bid_size" in out.columns:
        out = out[out["bid_size"].fillna(0.0) >= config.min_option_bid_size]
    if "ask_size" in out.columns:
        out = out[out["ask_size"].fillna(0.0) >= config.min_option_ask_size]
    if "volume" in out.columns:
        out = out[out["volume"].fillna(0.0) >= config.min_option_volume]
    if "open_interest" in out.columns:
        out = out[out["open_interest"].fillna(0.0) >= config.min_option_open_interest]
    return out


def _pick_by_delta(
    df: pd.DataFrame, target_delta: float, exclude_strikes: Optional[set[float]] = None
) -> Optional[pd.Series]:
    if df.empty:
        return None
    if exclude_strikes:
        df = df[~df["strike"].isin(exclude_strikes)]
    if df.empty:
        return None
    idx = (df["delta"] - target_delta).abs().idxmin()
    return df.loc[idx]


def _build_leg(row: pd.Series, side: str, qty: float) -> OptionLeg:
    return OptionLeg(
        expiry=row["expiry"],
        strike=float(row["strike"]),
        option_type=row["option_type"],
        side=side,
        qty=qty,
        entry_price=float(row["mid"]),
        entry_iv=float(row["iv"]),
        entry_delta=float(row["delta"]),
        entry_vega=float(row["vega"]),
    )


def _select_legs(
    options_slice: pd.DataFrame, strategy: str, config: BacktestConfig, qty: float
) -> List[OptionLeg]:
    calls = options_slice[options_slice["option_type"] == "C"]
    puts = options_slice[options_slice["option_type"] == "P"]
    if calls.empty or puts.empty:
        return []

    call_short = _pick_by_delta(calls, config.target_short_delta)
    put_short = _pick_by_delta(puts, -config.target_short_delta)
    if call_short is None or put_short is None:
        return []

    legs = [
        _build_leg(call_short, "sell", qty),
        _build_leg(put_short, "sell", qty),
    ]

    if strategy == "iron_condor":
        call_wing = _pick_by_delta(
            calls, config.target_wing_delta, {float(call_short["strike"])}
        )
        put_wing = _pick_by_delta(
            puts, -config.target_wing_delta, {float(put_short["strike"])}
        )
        if call_wing is None or put_wing is None:
            return []
        legs.extend(
            [
                _build_leg(call_wing, "buy", qty),
                _build_leg(put_wing, "buy", qty),
            ]
        )
    return legs


def _short_strangle_signal_iv(
    options_slice: pd.DataFrame, config: BacktestConfig
) -> Optional[float]:
    calls = options_slice[options_slice["option_type"] == "C"]
    puts = options_slice[options_slice["option_type"] == "P"]
    if calls.empty or puts.empty:
        return None
    call_short = _pick_by_delta(calls, config.target_short_delta)
    put_short = _pick_by_delta(puts, -config.target_short_delta)
    if call_short is None or put_short is None:
        return None
    return float(np.mean([call_short["iv"], put_short["iv"]]))


def _compute_executable_option_signal(
    options_prepped: pd.DataFrame,
    rv_forecast: pd.Series,
    config: BacktestConfig,
) -> pd.DataFrame:
    rows = []
    for ts, options_ts in options_prepped.groupby("timestamp", sort=True):
        options_slice = _select_expiry_slice(options_ts, ts, config)
        if options_slice is None:
            continue
        options_slice = _liquidity_filter(options_slice, config)
        if options_slice.empty:
            continue
        signal_iv = _short_strangle_signal_iv(options_slice, config)
        if signal_iv is None or ts not in rv_forecast.index:
            continue
        rv = float(rv_forecast.loc[ts])
        if not math.isfinite(rv):
            continue
        rows.append({"timestamp": ts, "execution_iv": signal_iv, "vrp": signal_iv - rv})
    if not rows:
        return pd.DataFrame(columns=["execution_iv", "vrp"])
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def _get_option_row(
    options_idx: pd.DataFrame,
    ts: pd.Timestamp,
    expiry: pd.Timestamp,
    strike: float,
    option_type: str,
) -> Optional[pd.Series]:
    key = (ts, expiry, strike, option_type)
    if key in options_idx.index:
        row = options_idx.loc[key]
        return row if isinstance(row, pd.Series) else row.iloc[0]
    try:
        instrument_df = options_idx.xs(
            (expiry, strike, option_type), level=["expiry", "strike", "option_type"]
        )
    except KeyError:
        return None
    instrument_df = instrument_df.loc[:ts]
    if instrument_df.empty:
        return None
    return instrument_df.iloc[-1]


def _position_state(
    position: Position, options_idx: pd.DataFrame, ts: pd.Timestamp
) -> tuple[float, float, float]:
    total_value = 0.0
    total_delta = 0.0
    total_vega = 0.0
    for leg in position.legs:
        row = _get_option_row(options_idx, ts, leg.expiry, leg.strike, leg.option_type)
        if row is None:
            continue
        sign = 1.0 if leg.side == "buy" else -1.0
        total_value += sign * float(row["mid"]) * leg.qty
        total_delta += sign * float(row["delta"]) * leg.qty
        total_vega += sign * float(row["vega"]) * leg.qty
    return total_value, total_delta, total_vega


def _normalize_iv_series(iv_series: pd.Series) -> pd.Series:
    cleaned = iv_series.dropna().copy()
    if cleaned.empty:
        return cleaned
    if float(cleaned.median()) > 3.0:
        cleaned = cleaned / 100.0
    return cleaned


def _realized_vol(returns: pd.Series) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    realized_var_per_hour = float(np.mean(np.square(clean.to_numpy(dtype=float))))
    return float(math.sqrt(realized_var_per_hour * 365.0 * 24.0))


def _returns_during_trade(
    returns: pd.Series, entry_time: pd.Timestamp, exit_time: pd.Timestamp
) -> pd.Series:
    mask = (returns.index > entry_time) & (returns.index <= exit_time)
    return returns.loc[mask]


def _kelly_sized_notional(iv: float, rv: float, base: float, config: BacktestConfig) -> float:
    if iv <= 0 or rv <= 0:
        return base
    edge_variance = max(iv**2 - rv**2, 0.0)
    risk_variance = max(rv**2, 1e-6)
    raw_fraction = config.kelly_fraction * edge_variance / risk_variance
    min_mult = config.min_contracts / max(config.base_contracts, 1e-9)
    max_mult = config.max_contracts / max(config.base_contracts, 1e-9)
    multiplier = float(np.clip(raw_fraction, min_mult, max_mult))
    return base * multiplier


def _stress_realized_vol(config: BacktestConfig) -> float:
    gap_hours = max(1, config.stress_gap_hours)
    horizon = max(config.forecast_horizon_hours, gap_hours + 1)
    hourly_gap = math.log(max(1e-6, 1.0 + config.stress_crash_pct)) / gap_hours
    stressed_returns = np.zeros(horizon)
    stressed_returns[:gap_hours] = hourly_gap
    return float(np.std(stressed_returns, ddof=1) * math.sqrt(365.0 * 24.0))


def _variance_stress_pnl(entry_iv: float, notional: float, config: BacktestConfig) -> float:
    stressed_rv = _stress_realized_vol(config)
    stressed_exit_vol = max(stressed_rv, entry_iv + config.stress_vol_shock)
    return float(notional * (entry_iv**2 - stressed_exit_vol**2))


def _position_stress_pnl(position: Position, config: BacktestConfig) -> float:
    if position.entry_spot <= 0:
        return 0.0
    stressed_spot = position.entry_spot * (1.0 + config.stress_crash_pct)
    stressed_value = 0.0
    elapsed_years = config.stress_gap_hours / (365.0 * 24.0)
    for leg in position.legs:
        time_years = (leg.expiry - position.entry_time).total_seconds() / (
            365.0 * 24.0 * 3600.0
        )
        time_years = max(time_years - elapsed_years, 1.0 / (365.0 * 24.0))
        stressed_iv = min(
            config.max_annual_vol,
            max(leg.entry_iv + config.stress_vol_shock, leg.entry_iv * 1.5),
        )
        stressed_price = black_scholes_price(
            stressed_spot,
            leg.strike,
            time_years,
            config.risk_free_rate,
            stressed_iv,
            leg.option_type,
        )
        sign = 1.0 if leg.side == "buy" else -1.0
        stressed_value += sign * stressed_price * leg.qty
    return float(position.entry_cash_flow + stressed_value)


def _short_option_margin(
    leg: OptionLeg, spot: float, config: BacktestConfig
) -> float:
    if leg.side != "sell" or spot <= 0.0:
        return 0.0
    if leg.option_type == "C":
        out_of_the_money = max(leg.strike - spot, 0.0)
    else:
        out_of_the_money = max(spot - leg.strike, 0.0)
    spot_margin = max(
        config.short_option_margin_spot_pct * spot - out_of_the_money,
        config.short_option_margin_floor_pct * spot,
    )
    return float((leg.entry_price + max(spot_margin, 0.0)) * abs(leg.qty))


def _position_margin_requirement(
    position: Position, spot: float, config: BacktestConfig
) -> float:
    if not config.enforce_option_margin:
        return 0.0
    return float(sum(_short_option_margin(leg, spot, config) for leg in position.legs))


def _risk_cap_multiplier(stress_pnl: float, config: BacktestConfig) -> float:
    stress_loss = abs(min(stress_pnl, 0.0))
    if stress_loss <= 0.0:
        return 1.0
    max_loss = config.initial_capital * config.max_trade_stress_loss_pct
    if max_loss <= 0.0:
        return 0.0
    return min(1.0, max_loss / stress_loss)


def _rolling_percentile_rank(series: pd.Series, window: int) -> pd.Series:
    def rank_last(values: np.ndarray) -> float:
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return np.nan
        return float(np.mean(values <= values[-1]))

    return series.rolling(window, min_periods=max(12, window // 4)).apply(rank_last, raw=True)


def _market_regime_filter(
    ohlc_df: pd.DataFrame,
    rv_forecast: pd.Series,
    config: BacktestConfig,
) -> pd.Series:
    timestamps = pd.to_datetime(ohlc_df["timestamp"], utc=True)
    if not config.enable_regime_filter:
        return pd.Series(True, index=timestamps)

    close = pd.Series(ohlc_df["close"].to_numpy(dtype=float), index=timestamps)
    abs_24h_return = np.log(close).diff(24).abs()
    rv_rank = _rolling_percentile_rank(rv_forecast.reindex(timestamps).ffill(), config.zscore_window)
    ok = (rv_rank <= config.max_rv_percentile) & (
        abs_24h_return <= config.max_abs_24h_return
    )
    return ok.fillna(False).rename("regime_ok")


def _entry_signal_pass(
    signal: float,
    threshold: float,
    vrp_now: float,
    config: BacktestConfig,
) -> bool:
    z_pass = (not math.isnan(signal)) and (signal >= config.vrp_entry_z)
    q_pass = (
        (not math.isnan(threshold))
        and (not math.isnan(vrp_now))
        and (vrp_now >= threshold)
    )
    if config.require_z_and_quantile:
        return z_pass and q_pass
    return z_pass or q_pass


def _equity_result(
    timestamps: pd.Series,
    pnl_curve: List[float],
    trades: List[Trade],
    config: BacktestConfig,
) -> BacktestResult:
    equity_curve = pd.DataFrame(
        {
            "timestamp": timestamps,
            "equity": np.asarray(pnl_curve, dtype=float) + config.initial_capital,
        }
    ).set_index("timestamp")
    returns = equity_curve["equity"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    trade_pnl = np.asarray([trade.pnl for trade in trades], dtype=float)
    trade_hours = np.asarray(
        [
            (trade.exit_time - trade.entry_time).total_seconds() / 3600.0
            for trade in trades
        ],
        dtype=float,
    )
    gross_wins = float(trade_pnl[trade_pnl > 0.0].sum()) if len(trade_pnl) else 0.0
    gross_losses = float(abs(trade_pnl[trade_pnl < 0.0].sum())) if len(trade_pnl) else 0.0
    total_pnl = (
        float(equity_curve["equity"].iloc[-1] - config.initial_capital)
        if not equity_curve.empty
        else 0.0
    )
    stress_gap = stress_test_gap(trades, config.stress_crash_pct)
    metrics = {
        "total_pnl": total_pnl,
        "total_return": float(equity_curve["equity"].iloc[-1] / config.initial_capital - 1.0)
        if not equity_curve.empty and config.initial_capital
        else 0.0,
        "trades": float(len(trades)),
        "sharpe": sharpe_ratio(returns, periods_per_year=365 * 24),
        "sortino": sortino_ratio(returns, periods_per_year=365 * 24),
        "max_drawdown": max_drawdown(equity_curve["equity"]),
        "vrp_capture_efficiency": vrp_capture_efficiency(trades),
        "stress_gap_pnl": stress_gap,
        "win_rate": float((trade_pnl > 0.0).mean()) if len(trade_pnl) else 0.0,
        "avg_trade_pnl": float(trade_pnl.mean()) if len(trade_pnl) else 0.0,
        "median_trade_pnl": float(np.median(trade_pnl)) if len(trade_pnl) else 0.0,
        "worst_trade_pnl": float(trade_pnl.min()) if len(trade_pnl) else 0.0,
        "avg_holding_hours": float(trade_hours.mean()) if len(trade_hours) else 0.0,
        "profit_factor": gross_wins / gross_losses if gross_losses > 0.0 else 0.0,
        "stress_to_pnl": abs(stress_gap) / max(abs(total_pnl), 1e-9),
    }

    diagnostics = diagnose_backtest(metrics)
    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        metrics=metrics,
        diagnostics=diagnostics,
    )


def _run_variance_proxy(
    ohlc_df: pd.DataFrame,
    rv_forecast: pd.Series,
    iv_series: pd.Series,
    regime_ok: pd.Series,
    config: BacktestConfig,
    entry_start: Optional[pd.Timestamp] = None,
    entry_end: Optional[pd.Timestamp] = None,
) -> BacktestResult:
    iv_series = _normalize_iv_series(iv_series)
    iv_series.index = pd.to_datetime(iv_series.index, utc=True)
    iv_series = iv_series.reindex(ohlc_df["timestamp"]).ffill()
    rv_forecast = rv_forecast.copy()
    rv_forecast.index = pd.to_datetime(rv_forecast.index, utc=True)
    rv_forecast = rv_forecast.reindex(ohlc_df["timestamp"]).ffill()
    vrp_signal = iv_series - rv_forecast
    vrp_z = zscore(vrp_signal, config.zscore_window)
    vrp_entry_thr = vrp_signal.rolling(config.zscore_window).quantile(
        config.vrp_entry_quantile
    )
    vrp_exit_thr = vrp_signal.rolling(config.zscore_window).quantile(
        config.vrp_exit_quantile
    )

    trades: List[Trade] = []
    equity: List[float] = []
    cash = 0.0
    open_entry: Optional[dict[str, object]] = None
    returns_series = ohlc_df.set_index("timestamp")["returns"].fillna(0.0)
    entry_streak = 0
    cooldown_until: Optional[pd.Timestamp] = None

    timestamps = ohlc_df["timestamp"].reset_index(drop=True)
    for i, ts in enumerate(timestamps):
        signal = vrp_z.loc[ts] if ts in vrp_z.index else np.nan

        if open_entry is None:
            equity.append(cash)
            if i >= len(timestamps) - 1:
                entry_streak = 0
                continue
            if not _entry_allowed(ts, entry_start, entry_end):
                entry_streak = 0
                continue
            if cooldown_until is not None and ts < cooldown_until:
                entry_streak = 0
                continue
            if ts in regime_ok.index and not bool(regime_ok.loc[ts]):
                entry_streak = 0
                continue
            threshold = vrp_entry_thr.loc[ts] if ts in vrp_entry_thr.index else np.nan
            vrp_now = vrp_signal.loc[ts] if ts in vrp_signal.index else np.nan
            if not _entry_signal_pass(signal, threshold, vrp_now, config):
                entry_streak = 0
                continue
            entry_streak += 1
            if entry_streak < config.signal_confirmation_periods:
                continue
            entry_iv = float(iv_series.loc[ts]) if ts in iv_series.index else np.nan
            entry_rv = float(rv_forecast.loc[ts]) if ts in rv_forecast.index else np.nan
            if math.isnan(entry_iv) or math.isnan(entry_rv):
                continue
            if (entry_iv - entry_rv) < config.min_vrp_edge:
                continue
            notional = _kelly_sized_notional(
                entry_iv, entry_rv, config.variance_notional, config
            )
            unit_stress = _variance_stress_pnl(entry_iv, notional, config)
            notional *= _risk_cap_multiplier(unit_stress, config)
            if notional < config.min_contracts:
                continue
            cost = abs(notional) * config.variance_trade_cost * 2.0
            expected_edge = notional * (entry_iv**2 - entry_rv**2) - cost
            if expected_edge <= config.min_expected_edge_after_cost:
                continue
            stress_pnl = _variance_stress_pnl(entry_iv, notional, config) - cost
            stress_loss = abs(min(stress_pnl, 0.0))
            if (
                config.min_expected_edge_to_stress > 0.0
                and stress_loss > 0.0
                and (expected_edge / stress_loss) < config.min_expected_edge_to_stress
            ):
                continue
            open_entry = {
                "entry_time": ts,
                "entry_iv": entry_iv,
                "entry_rv": entry_rv,
                "notional": notional,
                "cost": cost,
            }
            entry_streak = 0
            continue

        hold_hours = (ts - open_entry["entry_time"]).total_seconds() / 3600.0
        exit_due = hold_hours >= config.max_holding_hours
        threshold = vrp_exit_thr.loc[ts] if ts in vrp_exit_thr.index else np.nan
        vrp_now = vrp_signal.loc[ts] if ts in vrp_signal.index else np.nan
        z_exit = (not math.isnan(signal)) and (signal <= config.vrp_exit_z)
        q_exit = (
            (not math.isnan(threshold))
            and (not math.isnan(vrp_now))
            and (vrp_now <= threshold)
        )
        if z_exit or q_exit:
            exit_due = True

        if exit_due:
            entry_time = open_entry["entry_time"]
            returns_slice = _returns_during_trade(returns_series, entry_time, ts)
            realized_vol = _realized_vol(returns_slice)
            notional = float(open_entry["notional"])
            cost = float(open_entry["cost"])
            pnl = notional * (open_entry["entry_iv"] ** 2 - realized_vol**2) - cost
            cash += pnl
            trades.append(
                Trade(
                    entry_time=entry_time,
                    exit_time=ts,
                    strategy="variance_proxy",
                    pnl=pnl,
                    vega=0.0,
                    vrp_at_entry=float(open_entry["entry_iv"] - open_entry["entry_rv"]),
                    iv_at_entry=float(open_entry["entry_iv"]),
                    rv_forecast_at_entry=float(open_entry["entry_rv"]),
                    notional=notional,
                    fees=cost,
                    stress_pnl=_variance_stress_pnl(
                        float(open_entry["entry_iv"]), notional, config
                    )
                    - cost,
                )
            )
            open_entry = None
            cooldown_until = ts + pd.Timedelta(hours=config.cooldown_hours)
            equity.append(cash)
            continue

        equity.append(cash)

    if open_entry is not None and not ohlc_df.empty:
        ts = ohlc_df["timestamp"].iloc[-1]
        entry_time = open_entry["entry_time"]
        returns_slice = _returns_during_trade(returns_series, entry_time, ts)
        realized_vol = _realized_vol(returns_slice)
        notional = float(open_entry["notional"])
        cost = float(open_entry["cost"])
        pnl = notional * (open_entry["entry_iv"] ** 2 - realized_vol**2) - cost
        cash += pnl
        trades.append(
            Trade(
                entry_time=entry_time,
                exit_time=ts,
                strategy="variance_proxy",
                pnl=pnl,
                vega=0.0,
                vrp_at_entry=float(open_entry["entry_iv"] - open_entry["entry_rv"]),
                iv_at_entry=float(open_entry["entry_iv"]),
                rv_forecast_at_entry=float(open_entry["entry_rv"]),
                notional=notional,
                fees=cost,
                stress_pnl=_variance_stress_pnl(
                    float(open_entry["entry_iv"]), notional, config
                )
                - cost,
            )
        )
        equity[-1] = cash

    return _equity_result(ohlc_df["timestamp"], equity, trades, config)


def run_backtest(
    ohlc_df: pd.DataFrame,
    options_df: pd.DataFrame,
    config: BacktestConfig,
    regime_series: Optional[pd.Series] = None,
    iv_series: Optional[pd.Series] = None,
) -> BacktestResult:
    ohlc_df = ohlc_df.copy()
    ohlc_df["timestamp"] = pd.to_datetime(ohlc_df["timestamp"], utc=True)
    returns = log_returns(ohlc_df["close"])
    returns.index = ohlc_df["timestamp"]
    ohlc_df["returns"] = returns.values

    weight = float(np.clip(config.garch_weight, 0.0, 1.0))
    if weight > 0.0:
        garch_forecast = rolling_garch_forecast(
            returns,
            config.garch_window_hours,
            config.forecast_horizon_hours,
            config.garch_refit_interval_hours,
            config.min_annual_vol,
            config.max_annual_vol,
        )
    else:
        garch_forecast = pd.Series(np.nan, index=returns.index, name="rv_forecast")
    if weight < 1.0:
        ewma_forecast = rolling_ewma_forecast(
            returns,
            config.ewma_span_hours,
            config.min_annual_vol,
            config.max_annual_vol,
        )
    else:
        ewma_forecast = pd.Series(np.nan, index=returns.index, name="rv_ewma_forecast")
    if weight <= 0.0:
        rv_forecast = ewma_forecast.copy()
    elif weight >= 1.0:
        rv_forecast = garch_forecast.copy()
    else:
        rv_forecast = weight * garch_forecast + (1.0 - weight) * ewma_forecast
    rv_forecast = rv_forecast.reindex(ohlc_df["timestamp"])
    rv_forecast.index = pd.to_datetime(rv_forecast.index, utc=True)
    regime_ok = _market_regime_filter(ohlc_df, rv_forecast, config)
    entry_start = _config_timestamp(config.entry_start_time)
    entry_end = _config_timestamp(config.entry_end_time)

    if options_df.empty or config.use_variance_proxy:
        if iv_series is None:
            raise RuntimeError("IV series required for variance proxy mode.")
        return _run_variance_proxy(
            ohlc_df,
            rv_forecast,
            iv_series,
            regime_ok,
            config,
            entry_start=entry_start,
            entry_end=entry_end,
        )

    options_prepped = _prepare_options(options_df, config.risk_free_rate)
    if options_prepped.empty:
        if iv_series is None:
            raise RuntimeError("No option data available for backtest.")
        return _run_variance_proxy(
            ohlc_df,
            rv_forecast,
            iv_series,
            regime_ok,
            config,
            entry_start=entry_start,
            entry_end=entry_end,
        )

    option_times = pd.DatetimeIndex(
        pd.to_datetime(options_prepped["timestamp"], utc=True).drop_duplicates().sort_values()
    )
    sim_index = pd.DatetimeIndex(ohlc_df["timestamp"]).union(option_times).sort_values()
    ohlc_spot = ohlc_df.set_index("timestamp")["close"].reindex(sim_index).ffill()
    option_spot = options_prepped.groupby("timestamp")["underlying"].median().reindex(sim_index)
    spot_series = option_spot.combine_first(ohlc_spot).ffill()
    regime_for_sim = (
        regime_ok.reindex(regime_ok.index.union(sim_index))
        .sort_index()
        .astype("boolean")
        .ffill()
        .fillna(False)
        .astype(bool)
    )
    rv_for_options = (
        rv_forecast.reindex(rv_forecast.index.union(option_times)).sort_index().ffill()
    )

    options_idx = options_prepped.set_index(
        ["timestamp", "expiry", "strike", "option_type"]
    ).sort_index()

    signal_df = _compute_executable_option_signal(options_prepped, rv_for_options, config)
    vrp_signal = signal_df["vrp"] if "vrp" in signal_df else pd.Series(dtype=float)
    execution_iv = (
        signal_df["execution_iv"] if "execution_iv" in signal_df else pd.Series(dtype=float)
    )
    vrp_z = zscore(vrp_signal, config.zscore_window)
    vrp_entry_thr = vrp_signal.rolling(config.zscore_window).quantile(
        config.vrp_entry_quantile
    )

    kurt = rolling_kurtosis(returns, config.kurtosis_window)
    kurt = kurt.reindex(kurt.index.union(sim_index)).sort_index().ffill()

    trades: List[Trade] = []
    equity: List[float] = []
    cash = 0.0
    position: Optional[Position] = None
    entry_streak = 0
    cooldown_until: Optional[pd.Timestamp] = None

    for ts, spot in spot_series.items():
        if not math.isfinite(float(spot)):
            equity.append(cash)
            continue
        signal = vrp_z.loc[ts] if ts in vrp_z.index else np.nan

        if position is not None:
            pos_value, pos_delta, pos_vega = _position_state(position, options_idx, ts)
            total_delta = pos_delta + position.hedge_qty

            if (
                abs(total_delta) > config.delta_hedge_threshold
                and abs(total_delta) > config.delta_no_trade_zone
            ):
                target_hedge = -pos_delta
                trade_qty = target_hedge - position.hedge_qty
                hedge_notional = abs(trade_qty * spot)
                cash -= trade_qty * spot
                hedge_fee = hedge_notional * config.taker_fee
                cash -= hedge_fee
                position.hedge_cost += hedge_fee
                position.hedge_qty = target_hedge

            hold_hours = (ts - position.entry_time).total_seconds() / 3600.0
            exit_due = hold_hours >= config.max_holding_hours
            marked_equity = config.initial_capital + cash + pos_value + position.hedge_qty * spot
            if (
                config.enforce_option_margin
                and position.margin_required > 0.0
                and marked_equity
                <= position.margin_required * config.maintenance_margin_fraction
            ):
                exit_due = True
            if not math.isnan(signal) and signal <= config.vrp_exit_z:
                exit_due = True
            if abs(position.entry_vega) > 0 and abs(pos_vega) > abs(
                position.entry_vega
            ) * (1.0 + config.vega_stop_pct):
                exit_due = True

            if exit_due:
                exit_cash_flow = 0.0
                exit_fees = 0.0
                for leg in position.legs:
                    row = _get_option_row(options_idx, ts, leg.expiry, leg.strike, leg.option_type)
                    if row is None:
                        continue
                    close_side = "buy" if leg.side == "sell" else "sell"
                    close_price = _execution_price(
                        row, close_side, config, maker=config.use_maker_exits
                    )
                    fee_rate = config.maker_fee if config.use_maker_exits else config.taker_fee
                    fee = _option_fee(row, close_price, leg.qty, fee_rate, config)
                    exit_fees += fee
                    if leg.side == "sell":
                        exit_cash_flow -= close_price * leg.qty
                    else:
                        exit_cash_flow += close_price * leg.qty
                    exit_cash_flow -= fee

                if position.hedge_qty != 0.0:
                    hedge_notional = abs(position.hedge_qty * spot)
                    cash += position.hedge_qty * spot
                    hedge_fee = hedge_notional * config.taker_fee
                    cash -= hedge_fee
                    position.hedge_cost += hedge_fee
                    position.hedge_qty = 0.0

                cash += exit_cash_flow
                trade_pnl = cash - position.entry_cash
                total_fees = position.entry_fees + exit_fees + position.hedge_cost
                trades.append(
                    Trade(
                        entry_time=position.entry_time,
                        exit_time=ts,
                        strategy=position.strategy,
                        pnl=trade_pnl,
                        vega=abs(position.entry_vega),
                        vrp_at_entry=position.entry_vrp,
                        iv_at_entry=position.entry_iv,
                        rv_forecast_at_entry=position.entry_rv,
                        notional=sum(leg.qty for leg in position.legs),
                        fees=total_fees,
                        hedge_cost=position.hedge_cost,
                        stress_pnl=_position_stress_pnl(position, config),
                    )
                )
                position = None
                cooldown_until = ts + pd.Timedelta(hours=config.cooldown_hours)
                pos_value = 0.0

            if position is None:
                equity.append(cash)
            else:
                equity.append(cash + pos_value + position.hedge_qty * spot)
            continue

        equity.append(cash)

        if not _entry_allowed(ts, entry_start, entry_end):
            entry_streak = 0
            continue
        if cooldown_until is not None and ts < cooldown_until:
            entry_streak = 0
            continue
        if ts in regime_for_sim.index and not bool(regime_for_sim.loc[ts]):
            entry_streak = 0
            continue
        threshold = vrp_entry_thr.loc[ts] if ts in vrp_entry_thr.index else np.nan
        vrp_now = vrp_signal.loc[ts] if ts in vrp_signal.index else np.nan
        if not _entry_signal_pass(signal, threshold, vrp_now, config):
            entry_streak = 0
            continue
        entry_streak += 1
        if entry_streak < config.signal_confirmation_periods:
            continue

        try:
            options_ts = options_prepped[options_prepped["timestamp"] == ts]
        except KeyError:
            continue
        options_slice = _select_expiry_slice(options_ts, ts, config)
        if options_slice is None:
            continue
        options_slice = _liquidity_filter(options_slice, config)
        if options_slice.empty:
            continue

        if ts not in execution_iv.index or ts not in rv_for_options.index:
            continue
        entry_iv = float(execution_iv.loc[ts])
        entry_rv = float(rv_for_options.loc[ts]) if ts in rv_for_options.index else 0.0
        if (entry_iv - entry_rv) < config.min_vrp_edge:
            continue
        strategy = select_strategy(float(kurt.loc[ts]), config)
        qty = _kelly_sized_notional(entry_iv, entry_rv, config.base_contracts, config)
        unit_legs = _select_legs(options_slice, strategy, config, 1.0)
        if unit_legs:
            unit_position = Position(
                entry_time=ts,
                strategy="stress_unit",
                legs=unit_legs,
                hedge_qty=0.0,
                entry_vrp=float(entry_iv - entry_rv),
                entry_iv=entry_iv,
                entry_rv=entry_rv,
                entry_vega=sum(
                    (1.0 if leg.side == "buy" else -1.0) * leg.entry_vega
                    for leg in unit_legs
                ),
                entry_cash=0.0,
                entry_cash_flow=sum(
                    (1.0 if leg.side == "sell" else -1.0) * leg.entry_price
                    for leg in unit_legs
                ),
                entry_spot=float(spot),
            )
            qty *= _risk_cap_multiplier(_position_stress_pnl(unit_position, config), config)
            if config.enforce_option_margin:
                unit_margin = _position_margin_requirement(unit_position, float(spot), config)
                available_margin = max(
                    0.0,
                    (config.initial_capital + cash) * config.max_margin_utilization,
                )
                if unit_margin > 0.0:
                    qty = min(qty, available_margin / unit_margin)
        if qty < config.min_contracts:
            continue
        legs = _select_legs(options_slice, strategy, config, qty)
        if not legs:
            continue

        entry_cash_flow = 0.0
        entry_fees = 0.0
        entry_vega = 0.0
        for leg in legs:
            row = _get_option_row(options_idx, ts, leg.expiry, leg.strike, leg.option_type)
            exec_price = (
                _execution_price(row, leg.side, config, maker=True)
                if row is not None
                else _apply_slippage(leg.entry_price, leg.side, config)
            )
            fee = _option_fee(row, exec_price, leg.qty, config.maker_fee, config)
            entry_fees += fee
            if leg.side == "sell":
                entry_cash_flow += exec_price * leg.qty
            else:
                entry_cash_flow -= exec_price * leg.qty
            entry_cash_flow -= fee
            sign = 1.0 if leg.side == "buy" else -1.0
            entry_vega += sign * leg.entry_vega * leg.qty

        cash_before = cash
        cash += entry_cash_flow
        entry_streak = 0
        margin_position = Position(
            entry_time=ts,
            strategy=strategy,
            legs=legs,
            hedge_qty=0.0,
            entry_vrp=float(vrp_signal.loc[ts]) if ts in vrp_signal.index else 0.0,
            entry_iv=entry_iv,
            entry_rv=entry_rv,
            entry_vega=entry_vega,
            entry_cash=cash_before,
            entry_cash_flow=entry_cash_flow,
            entry_spot=float(spot),
            entry_fees=entry_fees,
        )
        margin_required = _position_margin_requirement(
            margin_position, float(spot), config
        )
        position = Position(
            entry_time=ts,
            strategy=strategy,
            legs=legs,
            hedge_qty=0.0,
            entry_vrp=float(vrp_signal.loc[ts]) if ts in vrp_signal.index else 0.0,
            entry_iv=entry_iv,
            entry_rv=entry_rv,
            entry_vega=entry_vega,
            entry_cash=cash_before,
            entry_cash_flow=entry_cash_flow,
            entry_spot=float(spot),
            entry_fees=entry_fees,
            margin_required=margin_required,
        )

    return _equity_result(pd.Series(sim_index, name="timestamp"), equity, trades, config)
