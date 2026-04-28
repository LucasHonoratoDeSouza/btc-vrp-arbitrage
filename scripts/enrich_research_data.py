import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage import BacktestConfig, build_research_dataset, enrich_option_history
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv, load_options_csv

DATA_DIR = os.path.join(ROOT, "data")


def _coverage_line(name: str, df: pd.DataFrame) -> str:
    if df.empty or "timestamp" not in df.columns:
        return f"- {name}: no rows"
    ts = pd.to_datetime(df["timestamp"], utc=True)
    days = (ts.max() - ts.min()).total_seconds() / 86400.0
    return f"- {name}: {len(df)} rows, {days:.2f} days, {ts.min()} to {ts.max()}"


def main() -> None:
    ohlc = load_ohlc_csv(os.path.join(DATA_DIR, "btc_1h.csv"))
    iv = load_iv_csv(os.path.join(DATA_DIR, "btc_dvol_1h.csv"))
    config = BacktestConfig(
        use_variance_proxy=True,
        garch_window_hours=24 * 7,
        garch_refit_interval_hours=72,
        ewma_span_hours=48,
        garch_weight=0.35,
        zscore_window=72,
    )
    research = build_research_dataset(ohlc, iv, config)
    research_path = os.path.join(DATA_DIR, "vrp_research_dataset.csv")
    research.to_csv(research_path, index=False)

    option_path = os.path.join(DATA_DIR, "deribit_options_1h.csv")
    enriched_options = pd.DataFrame()
    if os.path.exists(option_path):
        options = load_options_csv(option_path)
        enriched_options = enrich_option_history(options, rate=config.risk_free_rate)
        enriched_options.to_csv(
            os.path.join(DATA_DIR, "deribit_options_1h_enriched.csv"), index=False
        )

    complete_rows = int(
        research[
            ["iv", "rv_forecast", "vrp", "vrp_z", "future_rv_24h", "future_rv_72h"]
        ]
        .dropna()
        .shape[0]
    )
    lines = [
        "# VRP Research Dataset",
        "",
        "Point-in-time features are separated from forward labels. Forward columns are diagnostics only and must not be used by the trading rule.",
        "",
        "## Coverage",
        "",
        _coverage_line("BTC OHLC", ohlc),
        _coverage_line("VRP research dataset", research),
    ]
    if not enriched_options.empty:
        lines.append(_coverage_line("Enriched option history", enriched_options))
        lines.append(
            f"- Enriched option columns: {', '.join(['mark_iv', 'delta', 'gamma', 'vega', 'spread_pct', 'time_years'])}"
        )
    lines.extend(
        [
            "",
            "## Feature Health",
            "",
            f"- Complete rows for core signal and short forward labels: {complete_rows}",
            f"- Median VRP: {research['vrp'].median(skipna=True):.6f}",
            f"- Median carry score: {research['carry_score'].median(skipna=True):.6f}",
            f"- Positive 24h forward edge ratio: {(research['forward_edge_24h'] > 0).mean():.2%}",
            f"- Positive 72h forward edge ratio: {(research['forward_edge_72h'] > 0).mean():.2%}",
            "",
            "## Files",
            "",
            "- `data/vrp_research_dataset.csv`",
            "- `data/deribit_options_1h_enriched.csv`",
        ]
    )
    report_path = os.path.join(DATA_DIR, "vrp_research_dataset.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Saved {research_path}")
    if not enriched_options.empty:
        print(f"Saved {os.path.join(DATA_DIR, 'deribit_options_1h_enriched.csv')}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
