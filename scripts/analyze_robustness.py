import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")


def _bootstrap_trade_pnl(trades: pd.DataFrame, n_sims: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pnl = trades["pnl"].astype(float).to_numpy()
    stress = trades.get("stress_pnl", pd.Series(np.zeros(len(trades)))).astype(float).to_numpy()
    rows = []
    for _ in range(n_sims):
        idx = rng.integers(0, len(pnl), len(pnl))
        sample = pnl[idx]
        sample_stress = stress[idx]
        losses = sample[sample < 0.0]
        rows.append(
            {
                "total_pnl": float(sample.sum()),
                "mean_trade_pnl": float(sample.mean()),
                "win_rate": float((sample > 0.0).mean()),
                "worst_trade": float(sample.min()),
                "expected_shortfall_95": float(np.quantile(losses, 0.05)) if len(losses) else 0.0,
                "stress_gap_pnl": float(sample_stress.sum()),
            }
        )
    return pd.DataFrame(rows)


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).T


def _write_markdown(prefix: str, trades: pd.DataFrame, sims: pd.DataFrame, path: str) -> None:
    lines = [
        f"# Robustness Report: {prefix}",
        "",
        f"Trades: **{len(trades)}**",
        "",
    ]
    if len(trades) < 30:
        lines.append(
            "Status: **INSUFFICIENT SAMPLE**. Bootstrap is shown for diagnostics only; fewer than 30 trades is not enough for inference."
        )
    elif len(trades) < 200:
        lines.append(
            "Status: **RESEARCH ONLY**. Fewer than 200 independent trades is below the institutional gate."
        )
    else:
        lines.append("Status: sample size passes the configured trade-count gate.")
    lines.extend(["", "## Bootstrap Quantiles", ""])
    if sims.empty:
        lines.append("No simulations generated.")
    else:
        summary = _summary(sims)
        lines.append("| Metric | Count | Mean | Std | 1% | 5% | 50% | 95% | 99% | Min | Max |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for metric, row in summary.iterrows():
            lines.append(
                "| "
                + str(metric)
                + " | "
                + " | ".join(
                    f"{float(row.get(col, 0.0)):.6f}"
                    for col in ["count", "mean", "std", "1%", "5%", "50%", "95%", "99%", "min", "max"]
                )
                + " |"
            )
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap trade-level robustness diagnostics.")
    parser.add_argument("--prefix", default="real_backtest")
    parser.add_argument("--sims", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    trades_path = os.path.join(DATA_DIR, f"{args.prefix}_trades.csv")
    if not os.path.exists(trades_path):
        raise RuntimeError(f"Missing trades file: {trades_path}")
    trades = pd.read_csv(trades_path)
    if trades.empty:
        sims = pd.DataFrame()
    else:
        sims = _bootstrap_trade_pnl(trades, args.sims, args.seed)

    sims_path = os.path.join(DATA_DIR, f"{args.prefix}_bootstrap.csv")
    report_path = os.path.join(DATA_DIR, f"{args.prefix}_robustness.md")
    sims.to_csv(sims_path, index=False)
    _write_markdown(args.prefix, trades, sims, report_path)
    print(f"Bootstrap rows: {len(sims)}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
