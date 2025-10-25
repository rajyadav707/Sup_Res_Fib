import pandas as pd
from scripts.logger import logger

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
        levels['0.382'] = swing_high - 0.382 * diff
        levels['0.5'] = swing_high - 0.5 * diff
        levels['0.618'] = swing_high - 0.618 * diff
        levels['0.786_sl'] = swing_high - 0.786 * diff
        levels['1.0'] = swing_low
        levels['1.618_target'] = swing_low - (1.618 * diff)
    else: # Bearish
        levels['0.0'] = swing_low
        levels['0.382'] = swing_low + 0.382 * diff
        levels['0.5'] = swing_low + 0.5 * diff
        levels['0.618'] = swing_low + 0.618 * diff
        levels['0.786_sl'] = swing_low + 0.786 * diff
        levels['1.0'] = swing_high
        levels['1.618_target'] = swing_high + (1.618 * diff)

    logger.info(f"Calculated Fibonacci levels for Swing High={swing_high}, Swing Low={swing_low}: {levels}")
    return levels

def find_latest_order_block(df, swing_len=5):
    """
    Finds the latest valid order block by detecting a break of structure (BOS).
    """
    if df is None or len(df) < (swing_len * 2 + 1):
        return None

    df = df.copy()
    df.columns = df.columns.str.lower()

    # 1. Find all swing points
    df['swing_high'] = (df['high'] == df['high'].rolling(swing_len * 2 + 1, center=True, min_periods=1).max())
    df['swing_low'] = (df['low'] == df['low'].rolling(swing_len * 2 + 1, center=True, min_periods=1).min())

    swing_highs = df[df['swing_high']]
    swing_lows = df[df['swing_low']]

    latest_bullish_bos_time = pd.Timestamp(0)
    latest_bearish_bos_time = pd.Timestamp(0)
    bullish_ob_details = None
    bearish_ob_details = None

    # 2. Check for the latest Bullish Break of Structure
    if len(swing_highs) >= 2:
        last_high = swing_highs.iloc[-1]
        prev_high = swing_highs.iloc[-2]

        if last_high['high'] > prev_high['high']:
            latest_bullish_bos_time = last_high.name
            # Define the zone to search for the OB
            search_zone = df[(df.index > prev_high.name) & (df.index < last_high.name)]
            bearish_candles = search_zone[search_zone['close'] < search_zone['open']]

            if not bearish_candles.empty:
                ob_candle = bearish_candles.iloc[-1]
                # The swing low for a bullish setup is the low of the entire move
                swing_low_for_fib = df.loc[ob_candle.name:last_high.name]['low'].min()

                bullish_ob_details = {
                    "type": "bullish", "top": ob_candle['high'], "bottom": ob_candle['low'],
                    "swing_high": last_high['high'], "swing_low": swing_low_for_fib
                }

    # 3. Check for the latest Bearish Break of Structure
    if len(swing_lows) >= 2:
        last_low = swing_lows.iloc[-1]
        prev_low = swing_lows.iloc[-2]

        if last_low['low'] < prev_low['low']:
            latest_bearish_bos_time = last_low.name
            search_zone = df[(df.index > prev_low.name) & (df.index < last_low.name)]
            bullish_candles = search_zone[search_zone['close'] > search_zone['open']]

            if not bullish_candles.empty:
                ob_candle = bullish_candles.iloc[-1]
                # The swing high for a bearish setup is the high of the entire move
                swing_high_for_fib = df.loc[ob_candle.name:last_low.name]['high'].max()

                bearish_ob_details = {
                    "type": "bearish", "top": ob_candle['high'], "bottom": ob_candle['low'],
                    "swing_high": swing_high_for_fib, "swing_low": last_low['low']
                }

    # 4. Return the most recent valid Order Block
    if pd.to_datetime(latest_bullish_bos_time) > pd.to_datetime(latest_bearish_bos_time):
        return bullish_ob_details
    elif pd.to_datetime(latest_bearish_bos_time) > pd.to_datetime(latest_bullish_bos_time):
        return bearish_ob_details

    return None
