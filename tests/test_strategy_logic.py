import unittest
import pandas as pd
import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.strategy_logic import calculate_fibonacci_levels, find_latest_order_block

class TestStrategyLogic(unittest.TestCase):

    def test_calculate_fibonacci_levels_bullish(self):
        """Test Fibonacci calculation for a bullish setup."""
        high = 200
        low = 100
        levels = calculate_fibonacci_levels(high, low, is_bullish=True)
        self.assertAlmostEqual(levels['0.0'], 200)
        self.assertAlmostEqual(levels['0.382'], 161.8)
        self.assertAlmostEqual(levels['0.5'], 150.0)
        self.assertAlmostEqual(levels['0.618'], 138.2)
        self.assertAlmostEqual(levels['0.786_sl'], 121.4)
        self.assertAlmostEqual(levels['1.0'], 100)
        self.assertAlmostEqual(levels['1.618_target'], -61.8)

    def test_calculate_fibonacci_levels_bearish(self):
        """Test Fibonacci calculation for a bearish setup."""
        high = 200
        low = 100
        levels = calculate_fibonacci_levels(high, low, is_bullish=False)
        self.assertAlmostEqual(levels['0.0'], 100)
        self.assertAlmostEqual(levels['0.382'], 138.2)
        self.assertAlmostEqual(levels['0.5'], 150.0)
        self.assertAlmostEqual(levels['0.618'], 161.8)
        self.assertAlmostEqual(levels['0.786_sl'], 178.6)
        self.assertAlmostEqual(levels['1.0'], 200)
        self.assertAlmostEqual(levels['1.618_target'], 361.8)

    def test_find_latest_order_block_bullish(self):
        """Test bullish order block detection with the new simplified logic."""
        data = {
            'open':  [120, 118, 115, 110, 108, 105, 110, 120, 125, 130, 135, 128, 132],
            'high':  [122, 120, 117, 112, 110, 107, 112, 122, 127, 132, 140, 130, 138],
            'low':   [117, 116, 112, 108, 106, 103, 108, 118, 123, 128, 133, 126, 130],
            'close': [118, 117, 114, 109, 107, 104, 118, 121, 126, 131, 138, 127, 135]
        }
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime('2023-01-01') + pd.to_timedelta(df.index, unit='d')
        df.set_index('date', inplace=True)

        order_block = find_latest_order_block(df, swing_len=3)

        self.assertIsNotNone(order_block, "A bullish order block should be found")
        self.assertEqual(order_block['type'], 'bullish')
        self.assertAlmostEqual(order_block['top'], 107)
        self.assertAlmostEqual(order_block['bottom'], 103)
        self.assertAlmostEqual(order_block['swing_high'], 140)
        self.assertAlmostEqual(order_block['swing_low'], 103)

    def test_find_latest_order_block_bearish(self):
        """Test bearish order block detection with the new simplified logic."""
        data = {
            'open':  [100, 105, 110, 115, 118, 120, 115, 105, 100, 95, 90, 98, 92],
            'high':  [102, 107, 112, 117, 120, 122, 118, 108, 103, 98, 93, 100, 95],
            'low':   [98, 103, 108, 113, 116, 118, 112, 103, 98, 93, 88, 96, 90],
            'close': [101, 106, 111, 116, 119, 121, 113, 104, 99, 94, 89, 97, 91]
        }
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime('2023-01-01') + pd.to_timedelta(df.index, unit='d')
        df.set_index('date', inplace=True)

        order_block = find_latest_order_block(df, swing_len=3)

        self.assertIsNotNone(order_block, "A bearish order block should be found")
        self.assertEqual(order_block['type'], 'bearish')
        self.assertAlmostEqual(order_block['top'], 122)
        self.assertAlmostEqual(order_block['bottom'], 118)
        self.assertAlmostEqual(order_block['swing_high'], 122)
        self.assertAlmostEqual(order_block['swing_low'], 88)

if __name__ == '__main__':
    unittest.main()
