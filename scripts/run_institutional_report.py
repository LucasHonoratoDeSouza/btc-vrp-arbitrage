import json
import os
import sys
from dataclasses import asdict

import pandas as pd
from pandas.errors import EmptyDataError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage.quality import institutional_quality_report

DATA_DIR = os.path.join(ROOT, "data")


def _read_csv(name: str, date_cols: list[str] | None = None) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, parse_dates=date_cols or [])
    except EmptyDataError:
        return pd.DataFrame()


def _read_first_existing(names: list[str], date_cols: list[str] | None = None) -> pd.DataFrame:
    for name in names:
        df = _read_csv(name, date_cols)
        if not df.empty:
            return df
    return pd.DataFrame()


def _rich_snapshot_section() -> list[str]:
    rich = _read_csv("deribit_option_snapshots.csv", ["timestamp", "expiry"])
    lines = ["", "## Rich Live Snapshot Status", ""]
    if rich.empty:
        lines.append("- No rich Deribit option snapshot has been collected yet.")
        return lines
    required = {"bid_size", "ask_size", "volume", "open_interest", "mark_iv", "delta", "gamma", "vega"}
    missing = sorted(required - set(rich.columns))
    timestamps = rich["timestamp"].nunique() if "timestamp" in rich.columns else 0
    instruments = rich["instrument_name"].nunique() if "instrument_name" in rich.columns else 0
    lines.append(f"- Rows: `{len(rich)}`")
    lines.append(f"- Unique timestamps: `{timestamps}`")
    lines.append(f"- Unique instruments: `{instruments}`")
    lines.append(f"- Missing institutional columns: `{missing or 'none'}`")
    if timestamps < 180 * 24:
        lines.append(
            "- Status: rich enough for live monitoring/smoke tests, but not enough history for institutional backtesting."
        )
    return lines


def _markdown_report(report) -> str:
    lines = [
        "# Institutional Readiness Report",
        "",
        f"Ready for institutional capital: **{'YES' if report.ready else 'NO'}**",
        f"Score: **{report.score:.1f}/100**",
        "",
        "## Failed Critical Checks",
        "",
    ]
    critical = [
        check
        for check in report.checks
        if check.severity == "critical" and not check.passed
    ]
    if critical:
        for check in critical:
            lines.append(
                f"- `{check.category}.{check.check}`: value `{check.value}`, threshold `{check.threshold}`. {check.detail}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Failed Major Checks", ""])
    major = [
        check for check in report.checks if check.severity == "major" and not check.passed
    ]
    if major:
        for check in major:
            lines.append(
                f"- `{check.category}.{check.check}`: value `{check.value}`, threshold `{check.threshold}`. {check.detail}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Recommendations", ""])
    if report.recommendations:
        for rec in report.recommendations:
            lines.append(f"- {rec}")
    else:
        lines.append("- Dataset and results pass the configured gates.")

    lines.extend(_rich_snapshot_section())

    lines.extend(["", "## All Checks", ""])
    lines.append("| Category | Check | Passed | Severity | Value | Threshold |")
    lines.append("|---|---|---:|---|---:|---:|")
    for check in report.checks:
        lines.append(
            f"| {check.category} | {check.check} | {check.passed} | {check.severity} | {check.value} | {check.threshold} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ohlc = _read_first_existing(
        ["extended/btc_1h_8y.csv", "btc_1h.csv"], ["timestamp"]
    )
    iv = _read_first_existing(
        ["extended/btc_dvol_1h_5y.csv", "btc_dvol_1h.csv"], ["timestamp"]
    )
    if not ohlc.empty and not iv.empty:
        overlap_start = max(ohlc["timestamp"].min(), iv["timestamp"].min())
        overlap_end = min(ohlc["timestamp"].max(), iv["timestamp"].max())
        ohlc = ohlc[
            (ohlc["timestamp"] >= overlap_start) & (ohlc["timestamp"] <= overlap_end)
        ]
        iv = iv[(iv["timestamp"] >= overlap_start) & (iv["timestamp"] <= overlap_end)]
    options = _read_csv("deribit_options_1h_enriched.csv", ["timestamp", "expiry"])
    if options.empty:
        options = _read_csv("deribit_option_snapshots.csv", ["timestamp", "expiry"])
    if options.empty:
        options = _read_csv("deribit_options_1h.csv", ["timestamp", "expiry"])
    metrics_by_name = {
        "profile_adaptive_alpha": _read_csv("profile_adaptive_alpha_metrics.csv"),
        "real_backtest": _read_csv("real_backtest_metrics.csv"),
        "local_backtest": _read_csv("local_backtest_metrics.csv"),
        "rich_backtest": _read_csv("rich_backtest_metrics.csv"),
    }
    trades_by_name = {
        "profile_adaptive_alpha": _read_csv(
            "profile_adaptive_alpha_trades.csv", ["entry_time", "exit_time"]
        ),
        "real_backtest": _read_csv(
            "real_backtest_trades.csv", ["entry_time", "exit_time"]
        ),
        "local_backtest": _read_csv(
            "local_backtest_trades.csv", ["entry_time", "exit_time"]
        ),
        "rich_backtest": _read_csv(
            "rich_backtest_trades.csv", ["entry_time", "exit_time"]
        ),
    }

    report = institutional_quality_report(
        ohlc_df=ohlc,
        iv_df=iv,
        options_df=options,
        metrics_by_name=metrics_by_name,
        trades_by_name=trades_by_name,
    )

    report.to_frame().to_csv(
        os.path.join(DATA_DIR, "institutional_gate_checks.csv"), index=False
    )
    with open(os.path.join(DATA_DIR, "institutional_summary.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "ready": report.ready,
                "score": report.score,
                "recommendations": report.recommendations,
                "checks": [asdict(check) for check in report.checks],
            },
            f,
            indent=2,
        )
    with open(os.path.join(DATA_DIR, "institutional_report.md"), "w", encoding="utf-8") as f:
        f.write(_markdown_report(report))

    print(f"Ready: {report.ready}")
    print(f"Score: {report.score:.1f}/100")
    print(f"Critical failed: {sum((not c.passed) and c.severity == 'critical' for c in report.checks)}")
    print(f"Report: {os.path.join(DATA_DIR, 'institutional_report.md')}")


if __name__ == "__main__":
    main()
