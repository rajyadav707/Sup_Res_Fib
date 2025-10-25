import pandas as pd
import requests
import io
import sys
import os
import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.logger import logger
from scripts.config_loader import config, get_project_root
from scripts.fyers_api import FyersAPI
from scripts.strategy_logic import find_latest_order_block, calculate_fibonacci_levels

def get_nifty50_stocks():
    """
    Fetches the list of Nifty 50 stocks from the NSE website.
    """
    nifty50_url = config.get('SETTINGS', 'nifty50_url')

    try:
        response = requests.get(nifty50_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        return df['Symbol'].tolist()
    except Exception as e:
        logger.error(f"Error fetching Nifty 50 stocks: {e}")
        return []

def get_fno_stocks():
    """
    Fetches the list of F&O stocks from the NSE website.
    """
    fno_url = config.get('SETTINGS', 'fno_url')

    try:
        response = requests.get(fno_url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        return df.iloc[:, 0].unique().tolist()
    except Exception as e:
        logger.error(f"Error fetching F&O stocks: {e}")
        return []

def run_scanner():
    """
    Runs the daily market scanner to find potential trade setups.
    """
    logger.info("Starting daily market scan...")

    fyers = FyersAPI()

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

                    if entry_zone_bottom <= last_close <= entry_zone_top:
                        target_strike = fib_levels['1.618_target']

                        step = 50 if symbol == "BANKNIFTY" else 25
                        nearest_strike = round(target_strike / step) * step

                        option_ltp = 100
                        lot_size = 50
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

    if potential_trades:
        trades_df = pd.DataFrame(potential_trades)
        csv_path = os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_csv'))
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(potential_trades)} potential trades to {csv_path}")
    else:
        logger.info("No potential trades found today.")

    logger.info("Daily market scan finished.")

if __name__ == '__main__':
    run_scanner()
