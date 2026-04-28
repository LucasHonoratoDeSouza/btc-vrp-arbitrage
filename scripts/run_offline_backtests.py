import os
import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, monte_carlo_robustness, run_backtest
from vrp_arbitrage.data import load_ohlc_csv


def make_iv_proxy(ohlc_df: pd.DataFrame, seed: int, base_premium: float, noise: float) -> pd.Series:
    rng = np.random.default_rng(seed)
    close = ohlc_df["close"]
    ret = np.log(close).diff().fillna(0.0)
    rv_7d = ret.rolling(24 * 7).std(ddof=1) * np.sqrt(365.0 * 24.0)
    rv_7d = rv_7d.bfill().ffill()

    vol_of_vol = ret.rolling(24 * 3).std(ddof=1).bfill().ffill()
    normalized_vov = (vol_of_vol - vol_of_vol.mean()) / (vol_of_vol.std(ddof=1) + 1e-9)
    regime_bump = np.clip(normalized_vov, -2.0, 2.0) * 0.01

    iv = rv_7d + base_premium + regime_bump + rng.normal(0.0, noise, len(ohlc_df))
    iv = np.clip(iv, 0.2, 2.0)
    return pd.Series(iv.values, index=pd.to_datetime(ohlc_df["timestamp"], utc=True), name="iv_proxy")


def evaluate_scenario(name: str, ohlc_df: pd.DataFrame, config: BacktestConfig, iv_series: pd.Series) -> dict:
    empty_options = pd.DataFrame(
        columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
    )
    bt = run_backtest(ohlc_df, empty_options, config, iv_series=iv_series)
    metrics = dict(bt.metrics)
    metrics["trades"] = len(bt.trades)
    metrics["scenario"] = name
    return metrics


def main() -> None:
    print("Carregando OHLC...")
    ohlc_full = load_ohlc_csv(os.path.join(ROOT, "data", "btc_1h.csv"))
    # Keep runtime tractable for iterative research loops.
    ohlc_df = ohlc_full.tail(24 * 7).reset_index(drop=True)
    base_config = BacktestConfig(
        use_variance_proxy=True,
        garch_window_hours=24 * 3,
        zscore_window=24 * 2,
        vrp_entry_z=0.2,
        vrp_exit_z=0.0,
        max_holding_hours=24 * 2,
        variance_notional=1.0,
    )

    scenarios = [
        ("conservador", 7, 0.03, 0.01),
        ("base", 11, 0.05, 0.015),
        ("agressivo", 19, 0.08, 0.02),
    ]
    rows = []
    for name, seed, premium, noise in scenarios:
        print(f"Rodando cenário: {name}")
        iv_series = make_iv_proxy(ohlc_df, seed=seed, base_premium=premium, noise=noise)
        rows.append(evaluate_scenario(name, ohlc_df, base_config, iv_series))

    out_df = pd.DataFrame(rows)[
        [
            "scenario",
            "trades",
            "sharpe",
            "sortino",
            "max_drawdown",
            "vrp_capture_efficiency",
            "stress_gap_pnl",
        ]
    ]

    print("=== Backtest offline (IV proxy) ===")
    print(out_df.to_string(index=False))

    iv_base = make_iv_proxy(ohlc_df, seed=11, base_premium=0.05, noise=0.015)
    total_trades = int(out_df["trades"].sum())
    if total_trades > 0:
        print("\nRodando Monte Carlo de robustez...")
        mc = monte_carlo_robustness(
            ohlc_df=ohlc_df,
            options_df=pd.DataFrame(
                columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
            ),
            config=base_config,
            iv_series=iv_base,
            n_sims=8,
        )
        summary = mc[
            ["sharpe", "sortino", "max_drawdown", "vrp_capture_efficiency", "stress_gap_pnl"]
        ].describe(percentiles=[0.1, 0.5, 0.9])
        print("\n=== Monte Carlo (8 sims) ===")
        print(summary.to_string())
        mc.to_csv(os.path.join(ROOT, "data", "offline_backtest_monte_carlo.csv"), index=False)
    else:
        print("\nMonte Carlo pulado: nenhum trade nos cenários base.")

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    out_df.to_csv(os.path.join(ROOT, "data", "offline_backtest_results.csv"), index=False)

    print("\nConfig usada:")
    print(asdict(base_config))


if __name__ == "__main__":
    main()
