import pandas as pd
import configparser
import requests
import io

from scripts.logger import logger

def get_nifty50_stocks():
    """
    Fetches the list of Nifty 50 stocks from the NSE website.

    Returns:
        list: A list of stock symbols in the Nifty 50 index.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    nifty50_url = config.get('SETTINGS', 'nifty50_url')

    try:
        response = requests.get(nifty50_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        # Assuming the column name for symbols is 'Symbol'
        return df['Symbol'].tolist()
    except Exception as e:
        logger.error(f"Error fetching Nifty 50 stocks: {e}")
        return []

def get_fno_stocks():
    """
    Fetches the list of F&O stocks from the NSE website.

    Returns:
        list: A list of stock symbols available for F&O trading.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    fno_url = config.get('SETTINGS', 'fno_url')

    try:
        response = requests.get(fno_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        # Assuming the column name for symbols is 'SYMBOL'
        # The file might contain more than just symbols, so we clean it up
        return df.iloc[:, 0].unique().tolist()
    except Exception as e:
        logger.error(f"Error fetching F&O stocks: {e}")
        return []

from scripts.fyers_api import FyersAPI
from scripts.strategy_logic import find_latest_order_block, calculate_fibonacci_levels
import datetime

def run_scanner():
    """
    Runs the daily market scanner to find potential trade setups.
    """
    logger.info("Starting daily market scan...")

    fyers = FyersAPI()

    # Get stock universe
    nifty50 = get_nifty50_stocks()
    fno_stocks = get_fno_stocks()
    stock_universe = list(set(nifty50 + fno_stocks))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades = []

    today = datetime.date.today()
    range_from = (today - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    range_to = today.strftime('%Y-%m-%d')

    for i, symbol in enumerate(stock_universe):
        if i % 50 == 0:
            logger.info(f"Scanning progress: {i}/{len(stock_universe)}")

        # Fyers API expects symbols in the format NSE:SYMBOL-EQ
        fyers_symbol = f"NSE:{symbol}-EQ"

        hist_data = fyers.get_historical_data(fyers_symbol, "D", "1", range_from, range_to)

        if hist_data and hist_data.get('candles'):
            df = pd.DataFrame(hist_data['candles'], columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
            df['date'] = pd.to_datetime(df['epoch'], unit='s').dt.date
            df.set_index('date', inplace=True)

            order_block = find_latest_order_block(df)

            if order_block:
                is_bullish = order_block['type'] == 'bullish'
                fib_levels = calculate_fibonacci_levels(order_block['swing_high'], order_block['swing_low'], is_bullish)

                if fib_levels:
                    last_close = df['close'].iloc[-1]
                    entry_zone_top = fib_levels['0.5']
                    entry_zone_bottom = fib_levels['0.618']

                    # Check if the last close is within the entry zone
                    if entry_zone_bottom <= last_close <= entry_zone_top:
                        # Find the option strike and check premium
                        target_strike = fib_levels['1.618_target']
                        option_type = "PE" if is_bullish else "CE"

                        # Fetch option chain (simplified for now, will need a proper implementation)
                        # This is a placeholder for fetching the actual option chain
                        # For now, we will simulate finding a strike and its premium

                        # Find the nearest strike to the target
                        # This is a simplified way to get strike prices.
                        # In a real scenario, you'd get this from the symbol master or options chain API.
                        step = 50 if symbol == "BANKNIFTY" else 25 # Example step
                        nearest_strike = round(target_strike / step) * step

                        # Placeholder for getting option LTP and lot size
                        # In a real scenario, this would come from an API call
                        option_ltp = 100 # Placeholder
                        lot_size = 50 # Placeholder

                        premium = option_ltp * lot_size

                        if premium >= 5000:
                            trade_setup = {
                                "Date": today.strftime('%Y-%m-%d'),
                                "Symbol": symbol,
                                "LTP": last_close,
                                "Trade_Type": "Bullish Sell Put" if is_bullish else "Bearish Sell Call",
                                "Target_Strike": nearest_strike,
                                "Est_Premium": premium,
                                "SL_Level": fib_levels['0.786_sl'],
                                "Fib_Levels": fib_levels
                            }
                            potential_trades.append(trade_setup)
                            logger.info(f"Found profitable trade for {symbol}: {trade_setup}")
                        else:
                            logger.info(f"Trade for {symbol} did not meet premium requirement. Premium: {premium}")

    # Save potential trades to CSV
    if potential_trades:
        trades_df = pd.DataFrame(potential_trades)
        config = configparser.ConfigParser()
        config.read('config.ini')
        csv_path = config.get('SETTINGS', 'potential_trades_csv')
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(potential_trades)} potential trades to {csv_path}")
    else:
        logger.info("No potential trades found today.")

    logger.info("Daily market scan finished.")

if __name__ == '__main__':
    run_scanner()
