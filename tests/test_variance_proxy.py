import math
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage.backtest import _realized_vol, _returns_during_trade


class VarianceProxyAccountingTest(unittest.TestCase):
    def test_realized_vol_uses_variance_for_single_return(self):
        returns = pd.Series([0.01])

        vol = _realized_vol(returns)

        self.assertAlmostEqual(vol, math.sqrt((0.01**2) * 365.0 * 24.0))

    def test_trade_returns_exclude_entry_bar_and_include_exit_bar(self):
        idx = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
        returns = pd.Series([0.50, 0.01, -0.02, 0.03], index=idx)

        trade_returns = _returns_during_trade(returns, idx[0], idx[2])

        self.assertEqual(list(trade_returns.index), [idx[1], idx[2]])
        self.assertEqual(list(trade_returns), [0.01, -0.02])


if __name__ == "__main__":
    unittest.main()
