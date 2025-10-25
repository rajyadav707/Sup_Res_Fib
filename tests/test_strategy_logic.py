import unittest
import pandas as pd
from scripts.strategy_logic import calculate_fibonacci_levels, OrderBlockDetector, find_latest_order_block

class TestStrategyLogic(unittest.TestCase):

    def test_calculate_fibonacci_levels_bullish(self):
        """Test Fibonacci calculation for a bullish setup."""
        high = 200
        low = 100
        levels = calculate_fibonacci_levels(high, low, is_bullish=True)
        self.assertAlmostEqual(levels['0.0'], 200)
        self.assertAlmostEqual(levels['0.5'], 150.0)
        self.assertAlmostEqual(levels['0.618'], 138.2)
        self.assertAlmostEqual(levels['0.786_sl'], 121.4)
        self.assertAlmostEqual(levels['1.0'], 100)
        self.assertAlmostEqual(levels['1.618_target'], 38.2)

    def test_calculate_fibonacci_levels_bearish(self):
        """Test Fibonacci calculation for a bearish setup."""
        high = 200
        low = 100
        levels = calculate_fibonacci_levels(high, low, is_bullish=False)
        self.assertAlmostEqual(levels['0.0'], 100)
        self.assertAlmostEqual(levels['0.5'], 150.0)
        self.assertAlmostEqual(levels['0.618'], 161.8)
        self.assertAlmostEqual(levels['0.786_sl'], 178.6)
        self.assertAlmostEqual(levels['1.0'], 200)
        self.assertAlmostEqual(levels['1.618_target'], 261.8)

    def test_find_latest_order_block_bullish(self):
        """Test bullish order block detection with the new detector."""
        data = {
            'open':  [120, 118, 115, 112, 110, 108, 105, 108, 110, 112, 118, 113, 109, 108, 112, 115, 120, 125, 130, 135, 140, 138, 135, 142, 145],
            'high':  [122, 120, 117, 114, 112, 110, 107, 110, 112, 114, 120, 115, 112, 110, 114, 117, 122, 127, 132, 137, 142, 140, 138, 144, 148],
            'low':   [118, 116, 113, 110, 108, 106, 103, 106, 108, 110, 113, 111, 108, 105, 110, 113, 118, 123, 128, 133, 138, 136, 133, 140, 143],
            'close': [119, 117, 114, 111, 109, 107, 104, 109, 111, 113, 119, 112, 108, 106, 113, 116, 121, 126, 131, 136, 141, 137, 134, 143, 146]
        }
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(pd.to_datetime('2023-01-01') + pd.to_timedelta(df.index, unit='d'))
        df.set_index('date', inplace=True)

        order_block = find_latest_order_block(df)
        self.assertIsNotNone(order_block, "Order block should not be None")
        self.assertEqual(order_block['type'], 'bullish')
        # Based on the new logic, the OB should be the last bearish candle before the BOS
        self.assertAlmostEqual(order_block['top'], 112.0)
        self.assertAlmostEqual(order_block['bottom'], 108.0)

    def test_find_latest_order_block_bearish(self):
        """Test bearish order block detection with the new detector."""
        data = {
            'open':  [100, 102, 105, 108, 110, 112, 115, 112, 110, 108, 105, 107, 111, 113, 108, 105, 100, 95, 90, 85, 80, 82, 85, 78, 75],
            'high':  [102, 104, 107, 110, 112, 114, 117, 114, 112, 110, 108, 109, 113, 115, 110, 107, 102, 97, 92, 87, 82, 84, 87, 80, 77],
            'low':   [98, 100, 103, 106, 108, 110, 113, 110, 108, 106, 103, 105, 108, 111, 106, 103, 98, 93, 88, 83, 78, 80, 83, 76, 73],
            'close': [101, 103, 106, 109, 111, 113, 116, 111, 109, 107, 104, 108, 112, 114, 107, 104, 99, 94, 89, 84, 79, 83, 86, 77, 74]
        }
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(pd.to_datetime('2023-01-01') + pd.to_timedelta(df.index, unit='d'))
        df.set_index('date', inplace=True)

        order_block = find_latest_order_block(df)
        self.assertIsNotNone(order_block, "Order block should not be None")
        self.assertEqual(order_block['type'], 'bearish')
        self.assertAlmostEqual(order_block['top'], 115)
        self.assertAlmostEqual(order_block['bottom'], 111)

if __name__ == '__main__':
    unittest.main()
