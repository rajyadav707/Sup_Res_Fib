import pandas as pd
import requests
import io
import sys
import os
import datetime
import time
import pandas_market_calendars as mcal

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.logger import logger
from scripts.config_loader import config, get_project_root
from scripts.fyers_api import FyersAPI
from scripts.strategy_logic import find_latest_order_block, calculate_fibonacci_levels


def fetch_and_cache_data(url, cache_filename, max_retries=3, timeout=10):
    """
    Fetches data from a URL with retries and caching.
    - Tries to download from the URL `max_retries` times.
    - If successful, saves the content to `cache_filename`.
    - If all retries fail, it tries to load data from `cache_filename`.
    """
    cached_path = os.path.join(get_project_root(), 'data', cache_filename)

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to download from {url}")
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            # If successful, save to cache and return content
            with open(cached_path, 'w') as f:
                f.write(response.text)
            logger.info(f"Successfully downloaded and cached data to {cached_path}")
            return response.text

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2) # Wait 2 seconds before retrying

    # If all retries fail, try to read from cache
    logger.warning("All download attempts failed. Trying to load from cache.")
    try:
        with open(cached_path, 'r') as f:
            logger.info(f"Successfully loaded data from cache: {cached_path}")
            return f.read()
    except FileNotFoundError:
        logger.error(f"Cache file not found at {cached_path}. Cannot proceed.")
        return None

def get_last_trading_day():
    """
    Gets the most recent trading day based on the NSE calendar.
    """
    nse = mcal.get_calendar('NSE')
    schedule = nse.schedule(start_date=datetime.date.today() - datetime.timedelta(days=14), end_date=datetime.date.today())
    return schedule.index[-1].date()

def get_nifty50_stocks():
    """
    Fetches the list of Nifty 50 stocks using the robust fetcher.
    """
    nifty50_url = config.get('SETTINGS', 'nifty50_url')
    file_content = fetch_and_cache_data(nifty50_url, 'ind_nifty50list.csv')
    if file_content:
        df = pd.read_csv(io.StringIO(file_content))
        return df['Symbol'].tolist()
    return []

fno_lot_sizes = {}
def get_fno_stocks_and_lot_sizes():
    """
    Fetches F&O stocks and lot sizes using the robust fetcher.
    """
    global fno_lot_sizes
    fno_url = config.get('SETTINGS', 'fno_url')
    file_content = fetch_and_cache_data(fno_url, 'fo_mktlots.csv')

    if file_content:
        df = pd.read_csv(io.StringIO(file_content))
        df.columns = [c.strip() for c in df.columns]
        fno_lot_sizes = pd.Series(df.iloc[:, 1].values, index=df.iloc[:, 0]).to_dict()
        return df.iloc[:, 0].unique().tolist()
    return []

def get_current_month_expiry(today):
    """
    Determines the current month's expiry date string (e.g., '25DEC').
    """
    month_abbr = today.strftime('%b').upper()
    return f"{today.year % 100}{month_abbr}"

def construct_option_symbol(symbol, strike, option_type, expiry_str):
    """
    Constructs a Fyers-compatible option symbol.
    """
    return f"NSE:{symbol}{expiry_str}{option_type}{strike}"

def get_historical_data_smart(fyers, symbol, last_trading_day):
    """
    Fetches historical data smartly by updating a local CSV cache.
    """
    stock_data_dir = os.path.join(get_project_root(), 'data', 'stock_data')
    stock_file = os.path.join(stock_data_dir, f"{symbol}.csv")

    df = None
    range_from = (last_trading_day - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    range_to = last_trading_day.strftime('%Y-%m-%d')

    if os.path.exists(stock_file):
        logger.info(f"Loading cached data for {symbol} from {stock_file}")
        df = pd.read_csv(stock_file, index_col='date', parse_dates=True)
        last_cached_date = df.index.max().date()

        # If data is up-to-date, return it
        if last_cached_date >= last_trading_day:
            return df

        # Else, fetch only the missing data
        range_from = (last_cached_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"Updating data for {symbol} from {range_from}")

    fyers_symbol = f"NSE:{symbol}-EQ"
    hist_data = fyers.get_historical_data(fyers_symbol, "D", "1", range_from, range_to)

    if hist_data and hist_data.get('candles'):
        new_df = pd.DataFrame(hist_data['candles'], columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
        new_df['date'] = pd.to_datetime(new_df['epoch'], unit='s').dt.date
        new_df.set_index('date', inplace=True)

        if df is not None: # Append new data to existing data
            df = pd.concat([df, new_df])
            df = df[~df.index.duplicated(keep='last')] # Remove any duplicates
        else:
            df = new_df

        df.to_csv(stock_file)
        logger.info(f"Saved/updated data for {symbol} to {stock_file}")
        return df

    return df # Return existing df even if update fails

def run_scanner():
    """
    Runs the daily market scanner to find potential trade setups.
    """
    logger.info("Starting daily market scan...")

    fyers = FyersAPI()

    nifty50 = get_nifty50_stocks()
    fno_stocks = get_fno_stocks_and_lot_sizes()

    if not fno_stocks:
        logger.critical("Could not load F&O stock list. Scanner cannot continue.")
        return

    stock_universe = list(set(nifty50 + fno_stocks))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades = []

    last_trading_day = get_last_trading_day()
    logger.info(f"Last trading day was: {last_trading_day}")
    expiry_str = get_current_month_expiry(last_trading_day)

    for i, symbol in enumerate(stock_universe):
        if symbol not in fno_lot_sizes:
            continue

        if i % 25 == 0:
            logger.info(f"Scanning progress: {i}/{len(stock_universe)}")

        df = get_historical_data_smart(fyers, symbol, last_trading_day)

        if df is not None and not df.empty:
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

                        step = 50 if "BANKNIFTY" in symbol else (5 if "FINNIFTY" in symbol else 100)
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
                                    "Fib_Levels": str(fib_levels)
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
