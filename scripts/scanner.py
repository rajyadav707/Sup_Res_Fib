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
import pandas_market_calendars as mcal

def get_last_trading_day():
    """
    Gets the most recent trading day based on the NSE calendar.
    """
    nse = mcal.get_calendar('NSE')
    # Get the schedule for the past 2 weeks to be safe
    schedule = nse.schedule(start_date=datetime.date.today() - datetime.timedelta(days=14), end_date=datetime.date.today())
    # The last valid trading day is the last entry in the schedule
    return schedule.index[-1].date()

def get_nifty50_stocks():
    """
    Fetches the list of Nifty 50 stocks from the NSE website.
    """
    nifty50_url = config.get('SETTINGS', 'nifty50_url')

    try:
        response = requests.get(nifty50_url, timeout=10) # 10-second timeout
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        return df['Symbol'].tolist()
    except Exception as e:
        logger.error(f"Error fetching Nifty 50 stocks: {e}")
        return []

fno_lot_sizes = {}

def get_fno_stocks_and_lot_sizes():
    """
    Fetches F&O stocks and their lot sizes from the NSE website.
    """
    global fno_lot_sizes
    fno_url = config.get('SETTINGS', 'fno_url')

    try:
        response = requests.get(fno_url, timeout=10) # 10-second timeout
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        # Assuming column 0 is the symbol and column 1 is the lot size
        df.columns = [c.strip() for c in df.columns] # Clean column names
        fno_lot_sizes = pd.Series(df.iloc[:, 1].values, index=df.iloc[:, 0]).to_dict()
        return df.iloc[:, 0].unique().tolist()
    except Exception as e:
        logger.error(f"Error fetching F&O stocks and lot sizes: {e}")
        return []

def get_current_month_expiry(today):
    """
    Determines the current month's expiry date string (e.g., '25DEC').
    This is a simplified logic and might need adjustment for exact expiry rules.
    """
    month_abbr = today.strftime('%b').upper()
    return f"{today.year % 100}{month_abbr}"

def construct_option_symbol(symbol, strike, option_type, expiry_str):
    """
    Constructs a Fyers-compatible option symbol.
    e.g., NSE:SBIN25DECP370
    """
    return f"NSE:{symbol}{expiry_str}{option_type}{strike}"

def run_scanner():
    """
    Runs the daily market scanner to find potential trade setups.
    """
    logger.info("Starting daily market scan...")

    fyers = FyersAPI()

    nifty50 = get_nifty50_stocks()
    fno_stocks = get_fno_stocks_and_lot_sizes()
    stock_universe = list(set(nifty50 + fno_stocks))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades = []

    last_trading_day = get_last_trading_day()
    logger.info(f"Last trading day was: {last_trading_day}")
    range_from = (last_trading_day - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    range_to = last_trading_day.strftime('%Y-%m-%d')
    expiry_str = get_current_month_expiry(last_trading_day)

    for i, symbol in enumerate(stock_universe):
        if symbol not in fno_lot_sizes: # Skip stocks not in F&O
            continue

        if i % 25 == 0:
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
                        option_type = "PE" if is_bullish else "CE"
                        lot_size = fno_lot_sizes.get(symbol)

                        if not lot_size:
                            logger.warning(f"Lot size not found for {symbol}. Skipping.")
                            continue

                        # Find nearest strike
                        step = 50 if "BANKNIFTY" in symbol else (5 if "FINNIFTY" in symbol else 100) # Simplified
                        nearest_strike = round(target_strike / step) * step

                        option_symbol = construct_option_symbol(symbol, nearest_strike, option_type, expiry_str)

                        quote = fyers.get_quotes([option_symbol])
                        if quote and quote.get('d') and quote['d'][0].get('v'):
                            option_ltp = quote['d'][0]['v'].get('lp', 0)
                            premium = option_ltp * lot_size

                            if premium >= 5000:
                                trade_setup = {
                                    "Date": last_trading_day.strftime('%Y-%m-%d'),
                                    "Symbol": symbol,
                                    "LTP": last_close,
                                    "Trade_Type": "Bullish Sell Put" if is_bullish else "Bearish Sell Call",
                                    "Option_Symbol": option_symbol,
                                    "Target_Strike": nearest_strike,
                                    "Est_Premium": premium,
                                    "SL_Level": fib_levels['0.786_sl'],
                                    "Fib_Levels": str(fib_levels) # Convert dict to string for CSV
                                }
                                potential_trades.append(trade_setup)
                                logger.info(f"Found profitable trade for {symbol}: {trade_setup}")
                            else:
                                logger.info(f"Trade for {symbol} ({option_symbol}) did not meet premium requirement. Premium: {premium}")

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
