import importlib.util
import math
import unittest
from pathlib import Path

RUN = Path(__file__).with_name("run.py")
spec = importlib.util.spec_from_file_location("taker_flow_run", RUN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class PriceSanityTests(unittest.TestCase):
    def test_zero_denominator_is_rejected(self):
        self.assertIsNone(mod.safe_ratio_return(10.0, 0.0))

    def test_non_finite_is_rejected(self):
        self.assertIsNone(mod.safe_ratio_return(math.inf, 10.0))
        self.assertIsNone(mod.safe_ratio_return(10.0, math.nan))

    def test_positive_prices_compute_return(self):
        self.assertAlmostEqual(mod.safe_ratio_return(11.0, 10.0), 0.1)

    def test_close_to_close_uses_close_field_not_return_field(self):
        prev=(100.0,101.0,-0.75,0.1)
        now=(102.0,103.0,0.0,-0.2)
        self.assertAlmostEqual(mod.close_to_close_return(now,prev),103.0/101.0-1.0)

if __name__ == "__main__":
    unittest.main()
