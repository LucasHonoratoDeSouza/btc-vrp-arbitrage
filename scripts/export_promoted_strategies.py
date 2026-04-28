"""
Exports honest research reports to data/results/reports/.

The reports distinguish three different things that should not be mixed:
  - continuous proxy backtest: one realizable proxy equity curve per strategy
  - overlapping walk-forward windows: useful diagnostics, not additive capital
  - live readiness: requires point-in-time option-chain execution, not DVOL proxy
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from strategy_catalog import CATALOG, get_candidates
from vrp_arbitrage import run_backtest
from vrp_arbitrage.data import load_iv_csv, load_ohlc_csv

REPORTS_DIR = os.path.join(ROOT, "data", "results", "reports")
VALIDATION_DIR = os.path.join(ROOT, "data", "results", "regime_validation_5y")
EXTENDED_OHLC = os.path.join(ROOT, "data", "extended", "btc_1h_8y.csv")
EXTENDED_IV = os.path.join(ROOT, "data", "extended", "btc_dvol_1h_5y.csv")

EMPTY_OPTIONS = pd.DataFrame(
    columns=["timestamp", "expiry", "strike", "option_type", "bid", "ask", "mark", "underlying"]
)


def _load_validation() -> pd.DataFrame | None:
    path = os.path.join(VALIDATION_DIR, "candidate_windows.csv")
    return pd.read_csv(path) if os.path.exists(path) else None


def _load_selector() -> pd.DataFrame | None:
    path = os.path.join(VALIDATION_DIR, "walk_forward_selector.csv")
    return pd.read_csv(path) if os.path.exists(path) else None


def _money(value: float) -> str:
    return f"{value:,.0f}"


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _cagr(total_return: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = max((end - start).total_seconds() / (365.0 * 86400.0), 1e-9)
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def _continuous_proxy_metrics() -> pd.DataFrame:
    if not (os.path.exists(EXTENDED_OHLC) and os.path.exists(EXTENDED_IV)):
        return pd.DataFrame()

    ohlc = load_ohlc_csv(EXTENDED_OHLC)
    iv = load_iv_csv(EXTENDED_IV)
    start = max(ohlc["timestamp"].min(), iv.index.min())
    end = min(ohlc["timestamp"].max(), iv.index.max())
    ohlc = ohlc[(ohlc["timestamp"] >= start) & (ohlc["timestamp"] <= end)].reset_index(drop=True)
    iv = iv.loc[start:end]

    rows = []
    for name, config in get_candidates().items():
        result = run_backtest(ohlc, EMPTY_OPTIONS, config, iv_series=iv)
        monthly = result.equity_curve["equity"].resample("ME").last().pct_change().dropna()
        row = {
            "strategy": name,
            "period_start": start,
            "period_end": end,
            "final_capital": result.metrics["total_pnl"] + config.initial_capital,
            "total_pnl": result.metrics["total_pnl"],
            "total_return": result.metrics["total_return"],
            "cagr": _cagr(result.metrics["total_return"], start, end),
            "worst_month": float(monthly.min()) if not monthly.empty else 0.0,
            "median_month": float(monthly.median()) if not monthly.empty else 0.0,
            "trades": result.metrics["trades"],
            "sharpe": result.metrics["sharpe"],
            "max_drawdown": result.metrics["max_drawdown"],
            "win_rate": result.metrics["win_rate"],
            "worst_trade_pnl": result.metrics["worst_trade_pnl"],
            "stress_to_pnl": result.metrics["stress_to_pnl"],
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values("total_pnl", ascending=False)


def _validation_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("candidate")
        .agg(
            windows=("fold", "nunique"),
            overlap_pnl_sum=("total_pnl", "sum"),
            avg_return=("total_return", "mean"),
            median_return=("total_return", "median"),
            avg_sharpe=("sharpe", "mean"),
            min_pnl=("total_pnl", "min"),
            max_pnl=("total_pnl", "max"),
            pct_positive=("total_pnl", lambda s: (s > 0).mean()),
            total_trades=("trades", "sum"),
        )
        .reset_index()
    )
    even = (
        df[df["fold"] % 2 == 0]
        .groupby("candidate")["total_pnl"]
        .sum()
        .rename("even_nonoverlap_pnl")
    )
    odd = (
        df[df["fold"] % 2 == 1]
        .groupby("candidate")["total_pnl"]
        .sum()
        .rename("odd_nonoverlap_pnl")
    )
    summary = summary.merge(even, on="candidate", how="left").merge(odd, on="candidate", how="left")
    return summary.sort_values("overlap_pnl_sum", ascending=False)


def _continuous_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Continuous proxy backtest was not generated because extended data files are missing._"
    lines = [
        "| Strategy | Final Capital | PnL | CAGR | Worst Month | Max DD | Sharpe | Trades | Win Rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['strategy']} | {_money(r['final_capital'])} | {_money(r['total_pnl'])} | "
            f"{_pct(r['cagr'])} | {_pct(r['worst_month'])} | {_pct(r['max_drawdown'])} | "
            f"{r['sharpe']:.2f} | {r['trades']:.0f} | {_pct(r['win_rate'])} |"
        )
    return "\n".join(lines)


def _walk_forward_table(df: pd.DataFrame) -> str:
    summary = _validation_summary(df)
    lines = [
        "| Strategy | Windows | Overlap PnL Sum | Even Non-Overlap PnL | Odd Non-Overlap PnL | Avg Ret/Window | Median Ret/Window | Avg Sharpe | % Positive | Min PnL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['candidate']} | {r['windows']:.0f} | {_money(r['overlap_pnl_sum'])} | "
            f"{_money(r['even_nonoverlap_pnl'])} | {_money(r['odd_nonoverlap_pnl'])} | "
            f"{r['avg_return']*100:.2f}% | {r['median_return']*100:.2f}% | "
            f"{r['avg_sharpe']:.2f} | {r['pct_positive']:.1%} | {r['min_pnl']:,.2f} |"
        )
    return "\n".join(lines)


def _regime_table(df: pd.DataFrame) -> str:
    rows = (
        df.groupby(["candidate", "regime"])
        .agg(
            windows=("total_pnl", "count"),
            overlap_pnl_sum=("total_pnl", "sum"),
            avg_pnl=("total_pnl", "mean"),
            pct_positive=("total_pnl", lambda s: (s > 0).mean()),
            avg_sharpe=("sharpe", "mean"),
        )
        .reset_index()
        .sort_values(["candidate", "regime"])
    )
    lines = [
        "| Strategy | Regime | Windows | Overlap PnL Sum | Avg PnL | % Positive | Avg Sharpe |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in rows.iterrows():
        lines.append(
            f"| {r['candidate']} | {r['regime']} | {r['windows']:.0f} | "
            f"{_money(r['overlap_pnl_sum'])} | {r['avg_pnl']:,.1f} | "
            f"{r['pct_positive']:.1%} | {r['avg_sharpe']:.2f} |"
        )
    return "\n".join(lines)


def _selector_summary(sel: pd.DataFrame | None) -> str:
    if sel is None or sel.empty:
        return "_Selector data not found._"
    even = sel[sel["fold"] % 2 == 0]
    odd = sel[sel["fold"] % 2 == 1]
    top_pick = sel.groupby("selected_candidate").size().idxmax()
    top_n = int(sel.groupby("selected_candidate").size().max())
    lines = [
        f"- Overlapping fold PnL sum: **{_money(sel['test_total_pnl'].sum())}**",
        f"- Even non-overlap fold PnL: **{_money(even['test_total_pnl'].sum())}**",
        f"- Odd non-overlap fold PnL: **{_money(odd['test_total_pnl'].sum())}**",
        f"- Positive overlapping windows: **{(sel['test_total_pnl'] > 0).mean():.1%}** ({int((sel['test_total_pnl'] > 0).sum())}/{len(sel)})",
        f"- Most selected: **{top_pick}** ({top_n}/{len(sel)} folds)",
    ]
    return "\n".join(lines)


def _candidate_detail_table(df: pd.DataFrame, name: str) -> str:
    sub = df[df["candidate"] == name].sort_values("fold")
    if sub.empty:
        return "_No rows for candidate._"
    lines = [
        "| Fold | Period | PnL | Return | Sharpe | Regime |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for _, r in sub.iterrows():
        period = f"{str(r.get('test_start', ''))[:10]} -> {str(r.get('test_end', ''))[:10]}"
        lines.append(
            f"| {r['fold']:.0f} | {period} | {r['total_pnl']:,.1f} | "
            f"{r['total_return']*100:.2f}% | {r['sharpe']:.2f} | {r['regime']} |"
        )
    return "\n".join(lines)


def _catalog_comparison_table(val_df: pd.DataFrame | None, continuous: pd.DataFrame) -> str:
    validation = _validation_summary(val_df) if val_df is not None and not val_df.empty else pd.DataFrame()
    rows = []
    for entry in CATALOG:
        cfg = entry.config
        val = validation[validation["candidate"] == entry.name]
        cont = continuous[continuous["strategy"] == entry.name] if not continuous.empty else pd.DataFrame()
        rows.append(
            {
                "Strategy": entry.name,
                "Bucket": entry.risk_bucket,
                "Notional": f"{cfg.variance_notional:.0f}",
                "Kelly": f"{cfg.kelly_fraction:.2f}",
                "Edge%": f"{cfg.min_vrp_edge*100:.1f}",
                "MaxStress%": f"{cfg.max_trade_stress_loss_pct*100:.0f}",
                "RVPct": f"{cfg.max_rv_percentile*100:.0f}",
                "Hold(h)": str(cfg.max_holding_hours),
                "Cont Ret%": f"{float(cont.iloc[0]['total_return'])*100:.1f}" if not cont.empty else "-",
                "Cont DD%": f"{float(cont.iloc[0]['max_drawdown'])*100:.1f}" if not cont.empty else "-",
                "WF Win": f"{float(val.iloc[0]['windows']):.0f}" if not val.empty else "-",
                "WF Avg Ret%": f"{float(val.iloc[0]['avg_return'])*100:.2f}" if not val.empty else "-",
                "WF % Pos": f"{float(val.iloc[0]['pct_positive']):.1%}" if not val.empty else "-",
            }
        )
    df = pd.DataFrame(rows)
    lines = [
        "| " + " | ".join(df.columns) + " |",
        "|" + "|".join("---:" if col in {"Notional", "Hold(h)"} else "---" for col in df.columns) + "|",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


def build_research_report(
    val_df: pd.DataFrame | None, sel_df: pd.DataFrame | None, continuous: pd.DataFrame
) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    lines: list[str] = [
        "# VRP Strategy Research Report",
        "",
        f"**Generated:** {now}  ",
        "**Dataset:** Deribit BTC-PERPETUAL OHLC + Deribit DVOL hourly, Mar-2021 -> Apr-2026  ",
        "**Verdict:** NOT READY FOR LIVE CAPITAL. Current results validate a DVOL/variance-proxy signal, not executable option PnL.",
        "",
        "## 1. Readiness Gate",
        "",
        "| Gate | Status | Reason |",
        "|---|---|---|",
        "| Point-in-time option chain | FAIL | No historical bid/ask option-chain dataset is used in the 5-year validation. |",
        "| Executable PnL | FAIL | Main backtest uses DVOL as IV and a synthetic variance payoff. |",
        "| Walk-forward discipline | PARTIAL | Test windows are out-of-sample for the selector, but adjacent windows overlap by 15 days. |",
        "| Data quality | PASS | Extended OHLC and DVOL files are hourly, aligned, gap-free and duplicate-free. |",
        "| Research signal | PASS | Proxy results are consistently positive across the sample after corrections. |",
        "",
        "## 2. Continuous Proxy Backtest",
        "",
        "This is the closest proxy equity curve because each strategy runs once over the full period. It is still not live-tradable PnL.",
        "",
        _continuous_table(continuous),
        "",
        "## 3. Walk-Forward Diagnostics",
        "",
        "The 119 windows are 30-day tests with 15-day steps. Adjacent test windows overlap; therefore `Overlap PnL Sum` must not be treated as deployable cumulative profit.",
        "",
    ]
    if val_df is None or val_df.empty:
        lines.append("_Walk-forward data not found._")
    else:
        lines.append(_walk_forward_table(val_df))
        best = _validation_summary(val_df).iloc[0]["candidate"]
        worst = val_df[val_df["candidate"] == best].sort_values("total_pnl").iloc[0]
        lines.extend(
            [
                "",
                f"Best overlap-sum candidate: **{best}**.",
                f"Worst `{best}` window: fold {int(worst['fold'])}, {str(worst['test_start'])[:10]} -> {str(worst['test_end'])[:10]}, PnL {worst['total_pnl']:,.2f}.",
            ]
        )
    lines.extend(["", "## 4. Walk-Forward Selector", "", _selector_summary(sel_df), ""])
    if val_df is not None and not val_df.empty:
        lines.extend(["## 5. Regime Diagnostics", "", _regime_table(val_df), ""])
        lines.extend(["## 6. Primary Candidate Window Detail", "", _candidate_detail_table(val_df, "alpha_return_target"), ""])
    lines.extend(
        [
            "## 7. What Was Corrected",
            "",
            "- Realized volatility now uses realized variance (`mean(return^2)`) instead of sample standard deviation, which is unstable for short holds.",
            "- Trade PnL now excludes the entry bar return; only returns after entry and through exit are included.",
            "- The simulator no longer opens a variance-proxy trade on the final timestamp of a test slice.",
            "- Reports now label overlapping fold sums correctly and show even/odd non-overlapping diagnostics.",
            "- Live-readiness language was downgraded: these are research candidates until tested with point-in-time options execution.",
            "",
            "## 8. Live Implementation Blockers",
            "",
            "- Build historical Deribit option-chain snapshots with bid/ask, sizes, open interest, greeks and mark IV.",
            "- Replace DVOL proxy payoff with mark-to-market PnL of the exact straddle/strangle/condor legs to be traded.",
            "- Calibrate the conservative margin/liquidation model against real exchange margin and add quote rejection/latency assumptions.",
            "- Run paper trading and shadow live execution before risking capital.",
        ]
    )
    return "\n".join(lines)


def build_comparison_report(val_df: pd.DataFrame | None, continuous: pd.DataFrame) -> str:
    lines = [
        "# Strategy Parameter Comparison",
        "",
        "Continuous columns are one full-period proxy backtest. Walk-forward columns are overlapping 30-day diagnostic windows.",
        "",
        _catalog_comparison_table(val_df, continuous),
        "",
        "---",
        "",
        "**Legend:**",
        "- **Cont Ret% / Cont DD%** — full-period DVOL variance-proxy return/drawdown.",
        "- **WF Avg Ret% / WF % Pos** — overlapping 30-day walk-forward diagnostics.",
        "- These are not live option-chain execution metrics.",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    val_df = _load_validation()
    sel_df = _load_selector()
    continuous = _continuous_proxy_metrics()
    if not continuous.empty:
        continuous.to_csv(os.path.join(REPORTS_DIR, "continuous_proxy_metrics.csv"), index=False)

    research_path = os.path.join(REPORTS_DIR, "promoted_strategies.md")
    with open(research_path, "w", encoding="utf-8") as f:
        f.write(build_research_report(val_df, sel_df, continuous))
    print(f"Written: {research_path}")

    comparison_path = os.path.join(REPORTS_DIR, "strategy_comparison.md")
    with open(comparison_path, "w", encoding="utf-8") as f:
        f.write(build_comparison_report(val_df, continuous))
    print(f"Written: {comparison_path}")


if __name__ == "__main__":
    main()
