import unittest
from utils import calculate_discount, safe_divide, fmt_amount

class TestUtils(unittest.TestCase):
    def test_calculate_discount_basic(self):
        self.assertEqual(calculate_discount(100, 0), 100.0)
        self.assertEqual(calculate_discount(100, 100), 0.0)
        self.assertEqual(calculate_discount(200, 25), 150.0)

    def test_calculate_discount_rounding(self):
        self.assertEqual(calculate_discount(100, 12.345), 87.66)  # 100*(1-0.12345)=87.6555 -> 87.66

    def test_calculate_discount_errors(self):
        with self.assertRaises(ValueError):
            calculate_discount(-1, 10)
        with self.assertRaises(ValueError):
            calculate_discount(10, -1)
        with self.assertRaises(ValueError):
            calculate_discount(10, 101)

    def test_safe_divide_basic(self):
        self.assertEqual(safe_divide(10, 2), 5.0)
        self.assertEqual(safe_divide(1, 3, precision=3), 0.333)

    def test_safe_divide_errors(self):
        with self.assertRaises(ZeroDivisionError):
            safe_divide(10, 0)
        with self.assertRaises(ValueError):
            safe_divide(1, 2, precision=-1)
        with self.assertRaises(ValueError):
            safe_divide(1, 2, precision=13)

    def test_fmt_amount_basic(self):
        self.assertEqual(fmt_amount(1234.5, 2), "1,234.50")
        self.assertEqual(fmt_amount(1000, 0), "1,000")

    def test_fmt_amount_custom_separators(self):
        self.assertEqual(fmt_amount(1234.5, 2, sep=".", dot=","), "1.234,50")

    def test_fmt_amount_errors(self):
        with self.assertRaises(ValueError):
            fmt_amount(123, -1)
        with self.assertRaises(ValueError):
            fmt_amount(123, 9)

if __name__ == "__main__":
    unittest.main()
