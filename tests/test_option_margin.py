import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp_arbitrage.backtest import _position_margin_requirement
from vrp_arbitrage.config import BacktestConfig
from vrp_arbitrage.types import OptionLeg, Position


class OptionMarginTest(unittest.TestCase):
    def test_short_option_requires_margin(self):
        config = BacktestConfig(enforce_option_margin=True)
        leg = OptionLeg(
            expiry=None,
            strike=120.0,
            option_type="C",
            side="sell",
            qty=2.0,
            entry_price=5.0,
            entry_iv=0.6,
            entry_delta=0.25,
            entry_vega=1.0,
        )
        position = Position(
            entry_time=None,
            strategy="short_strangle",
            legs=[leg],
            hedge_qty=0.0,
            entry_vrp=0.0,
            entry_iv=0.6,
            entry_rv=0.4,
            entry_vega=-2.0,
            entry_cash=0.0,
        )

        margin = _position_margin_requirement(position, 100.0, config)

        self.assertGreater(margin, 0.0)

    def test_long_option_does_not_add_short_margin(self):
        config = BacktestConfig(enforce_option_margin=True)
        leg = OptionLeg(
            expiry=None,
            strike=120.0,
            option_type="C",
            side="buy",
            qty=2.0,
            entry_price=5.0,
            entry_iv=0.6,
            entry_delta=0.25,
            entry_vega=1.0,
        )
        position = Position(
            entry_time=None,
            strategy="long_option",
            legs=[leg],
            hedge_qty=0.0,
            entry_vrp=0.0,
            entry_iv=0.6,
            entry_rv=0.4,
            entry_vega=2.0,
            entry_cash=0.0,
        )

        margin = _position_margin_requirement(position, 100.0, config)

        self.assertEqual(margin, 0.0)


if __name__ == "__main__":
    unittest.main()
