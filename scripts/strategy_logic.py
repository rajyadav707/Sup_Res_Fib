import pandas as pd
from scripts.logger import logger
import numpy as np
from scipy.signal import find_peaks

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

def find_swing_points(df, order=5):
    """
    Finds swing high and low points in a DataFrame.
    """
    high_peaks, _ = find_peaks(df['high'], distance=order)
    low_peaks, _ = find_peaks(-df['low'], distance=order)
    return high_peaks, low_peaks

def find_internal_order_block(df):
    """
    Analyzes historical data to find the most recent internal order block based on a break of structure.
    """
    if len(df) < 20:
        logger.warning(f"Not enough data to find order block. Data length: {len(df)}")
        return None

    swing_highs_idx, swing_lows_idx = find_swing_points(df, order=5)

    if len(swing_highs_idx) < 2 or len(swing_lows_idx) < 2:
        logger.info("Not enough swing points to determine structure.")
        return None

    # Bullish Scenario: Look for a break of a swing high
    # We need at least one swing low before the two last swing highs
    if swing_highs_idx[-1] > swing_lows_idx[-1] and swing_lows_idx[-1] > swing_highs_idx[-2]:
        prev_high = df['high'].iloc[swing_highs_idx[-2]]
        last_high = df['high'].iloc[swing_highs_idx[-1]]

        if last_high > prev_high: # Bullish Break of Structure
            # The impulse move started from the last swing low
            start_of_move_idx = swing_lows_idx[-1]
            # Search for the OB in the range between the previous high and the start of the impulse
            search_range_df = df.iloc[swing_highs_idx[-2]:start_of_move_idx + 1]

            # The order block is the last bearish candle in this range
            bearish_candles = search_range_df[search_range_df['close'] < search_range_df['open']]
            if not bearish_candles.empty:
                ob_candle = bearish_candles.iloc[-1]
                logger.info(f"Found Bullish OB at index {ob_candle.name}")
                return {
                    "type": "bullish", "top": ob_candle['high'], "bottom": ob_candle['low'],
                    "swing_high": last_high, "swing_low": df['low'].iloc[start_of_move_idx]
                }

    # Bearish Scenario: Look for a break of a swing low
    # We need at least one swing high before the two last swing lows
    if swing_lows_idx[-1] > swing_highs_idx[-1] and swing_highs_idx[-1] > swing_lows_idx[-2]:
        prev_low = df['low'].iloc[swing_lows_idx[-2]]
        last_low = df['low'].iloc[swing_lows_idx[-1]]

        if last_low < prev_low: # Bearish Break of Structure
            # The impulse move started from the last swing high
            start_of_move_idx = swing_highs_idx[-1]
            # Search for the OB in the range between the previous low and the start of the impulse
            search_range_df = df.iloc[swing_lows_idx[-2]:start_of_move_idx + 1]

            # The order block is the last bullish candle in this range
            bullish_candles = search_range_df[search_range_df['close'] > search_range_df['open']]
            if not bullish_candles.empty:
                ob_candle = bullish_candles.iloc[-1]
                logger.info(f"Found Bearish OB at index {ob_candle.name}")
                return {
                    "type": "bearish", "top": ob_candle['high'], "bottom": ob_candle['low'],
                    "swing_high": df['high'].iloc[start_of_move_idx], "swing_low": last_low
                }

    logger.info("No clear order block structure found.")
    return None
