import pandas as pd
from scripts.logger import logger
import numpy as np

def calculate_fibonacci_levels(swing_high, swing_low, is_bullish):
    """
    Calculates Fibonacci retracement and target levels based on a swing high and low.
    """
    if swing_high is None or swing_low is None or swing_high <= swing_low:
        logger.warning(f"Invalid swing points for Fibonacci calculation: High={swing_high}, Low={swing_low}")
        return None

    diff = swing_high - swing_low
    levels = {}
    if is_bullish:
        levels['0.0'] = swing_high
        levels['0.5'] = swing_high - 0.5 * diff
        levels['0.618'] = swing_high - 0.618 * diff
        levels['0.786_sl'] = swing_high - 0.786 * diff
        levels['1.0'] = swing_low
        levels['1.618_target'] = swing_low - (0.618 * diff)
    else: # Bearish
        levels['0.0'] = swing_low
        levels['0.5'] = swing_low + 0.5 * diff
        levels['0.618'] = swing_low + 0.618 * diff
        levels['0.786_sl'] = swing_low + 0.786 * diff
        levels['1.0'] = swing_high
        levels['1.618_target'] = swing_high + (0.618 * diff)

    logger.info(f"Calculated Fibonacci levels for Swing High={swing_high}, Swing Low={swing_low}: {levels}")
    return levels

class OrderBlockDetector:
    def __init__(self, swing_len=5, atr_period=14, atr_mult=1.5):
        self.swing_len = swing_len
        self.atr_period = atr_period
        self.atr_mult = atr_mult

    def _atr(self, df):
        hl = df['high'] - df['low']
        hc = abs(df['high'] - df['close'].shift())
        lc = abs(df['low'] - df['close'].shift())
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    def _find_swings(self, df):
        """Identify swing highs and lows"""
        df['swing_high'] = df['high'][(df['high'] == df['high'].rolling(self.swing_len, center=True).max())]
        df['swing_low']  = df['low'][(df['low'] == df['low'].rolling(self.swing_len, center=True).min())]
        return df

    def detect(self, df):
        df = df.copy()
        df.columns = df.columns.str.lower() # Ensure column names are lowercase

        df['atr'] = self._atr(df)
        df = self._find_swings(df)

        bullish_ob = []
        bearish_ob = []
        active_bullish = []
        active_bearish = []

        for i in range(2, len(df)):
            row = df.iloc[i]

            # Remove mitigated OBs first
            active_bullish = [ob for ob in active_bullish if row['low'] > ob['high']]
            active_bearish = [ob for ob in active_bearish if row['high'] < ob['low']]

            # Bullish Break of Structure
            if not np.isnan(df['swing_high'].iloc[i-1]) and row['close'] > df['swing_high'].iloc[i-1]:
                prev_candle = df.iloc[i-1]
                if prev_candle['close'] < prev_candle['open']:
                    ob_low = prev_candle['low']
                    ob_high = prev_candle['high']
                    active_bullish.append({'low': ob_low, 'high': ob_high, 'created_at': df.index[i-1]})

            # Bearish Break of Structure
            if not np.isnan(df['swing_low'].iloc[i-1]) and row['close'] < df['swing_low'].iloc[i-1]:
                prev_candle = df.iloc[i-1]
                if prev_candle['close'] > prev_candle['open']:
                    ob_low = prev_candle['low']
                    ob_high = prev_candle['high']
                    active_bearish.append({'low': ob_low, 'high': ob_high, 'created_at': df.index[i-1]})

        return active_bullish, active_bearish

def find_latest_order_block(df):
    """
    Wrapper function to instantiate and run the OrderBlockDetector.
    This provides the latest active order block that can be used by the scanner.
    """
    detector = OrderBlockDetector()
    active_bullish, active_bearish = detector.detect(df)

    # Return the most recent of either type, if available
    if not active_bullish and not active_bearish:
        return None

    latest_bullish_time = pd.to_datetime(active_bullish[-1]['created_at']) if active_bullish else pd.Timestamp(0)
    latest_bearish_time = pd.to_datetime(active_bearish[-1]['created_at']) if active_bearish else pd.Timestamp(0)

    if latest_bullish_time > latest_bearish_time:
        latest_ob = active_bullish[-1]
        swing_high_after_ob = df[df.index > latest_ob['created_at']]['high'].max()
        return {
            "type": "bullish", "top": latest_ob['high'], "bottom": latest_ob['low'],
            "swing_high": swing_high_after_ob, "swing_low": latest_ob['low']
        }
    else:
        latest_ob = active_bearish[-1]
        swing_low_after_ob = df[df.index > latest_ob['created_at']]['low'].min()
        return {
            "type": "bearish", "top": latest_ob['high'], "bottom": latest_ob['low'],
            "swing_high": latest_ob['high'], "swing_low": swing_low_after_ob
        }
