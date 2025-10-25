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


def fetch_and_cache_data(url, cache_filename, max_retries=3, timeout=15):
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

            with open(cached_path, 'wb') as f: # Write in binary mode
                f.write(response.content)
            logger.info(f"Successfully downloaded and cached data to {cached_path}")
            return response.content

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    logger.warning("All download attempts failed. Trying to load from cache.")
    try:
        with open(cached_path, 'rb') as f: # Read in binary mode
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
    # Go back a bit further to ensure we catch the last trading day even after long weekends
    schedule = nse.schedule(start_date=datetime.date.today() - datetime.timedelta(days=15), end_date=datetime.date.today())
    return schedule.index[-1].date()

def get_nifty50_stocks():
    """
    Fetches the list of Nifty 50 stocks using the robust fetcher.
    """
    nifty50_url = config.get('SETTINGS', 'nifty50_url')
    file_content = fetch_and_cache_data(nifty50_url, 'ind_nifty50list.csv')
    if file_content:
        try:
            df = pd.read_csv(io.BytesIO(file_content))
            return df['Symbol'].tolist()
        except Exception as e:
            logger.error(f"Failed to parse Nifty50 CSV content: {e}")
    return []

fno_lot_sizes = {}
def get_fno_stocks_and_lot_sizes(date_obj):
    """
    Fetches F&O stocks and lot sizes from the new daily contract file.
    """
    global fno_lot_sizes
    url_pattern = config.get('SETTINGS', 'fno_url_pattern')

    # Try to fetch for the given date, then go back day by day for a few days
    for i in range(5):
        current_date = date_obj - datetime.timedelta(days=i)
        date_str = current_date.strftime('%d%m%Y')
        fno_url = url_pattern.format(ddmmyyyy=date_str)
        cache_filename = f"NSE_FO_contract_{date_str}.csv"

        file_content = fetch_and_cache_data(fno_url, cache_filename)

        if file_content:
            try:
                df = pd.read_csv(io.BytesIO(file_content))
                # Clean column names by stripping whitespace
                df.columns = df.columns.str.strip()

                # Filter for stock options and futures to get the base symbols
                df = df[df['INSTRUMENT'].isin(['OPTSTK', 'FUTSTK'])]

                # Extract unique symbols and their lot sizes
                df_lots = df[['SYMBOL', 'LOTSIZE']].drop_duplicates(subset=['SYMBOL'])
                fno_lot_sizes = pd.Series(df_lots.LOTSIZE.values, index=df_lots.SYMBOL).to_dict()

                logger.info(f"Successfully parsed {len(fno_lot_sizes)} F&O symbols and lot sizes from {fno_url}")
                return list(fno_lot_sizes.keys())
            except Exception as e:
                logger.error(f"Failed to parse F&O contract file for {current_date.strftime('%Y-%m-%d')}: {e}")
                continue # Try the previous day

    logger.critical("Could not load F&O stock list after trying multiple days.")
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
    return f"NSE:{symbol}{expiry_str}{strike}{option_type}" # Corrected format

def get_historical_data_smart(fyers, symbol, last_trading_day):
    """
    Fetches historical data smartly by updating a local CSV cache.
    """
    stock_data_dir = os.path.join(get_project_root(), 'data', 'stock_data')
    stock_file = os.path.join(stock_data_dir, f"{symbol}.csv")

    df = None
    # Fetch a bit more data to ensure swing calculations are accurate
    range_from = (last_trading_day - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    range_to = last_trading_day.strftime('%Y-%m-%d')

    if os.path.exists(stock_file):
        logger.info(f"Loading cached data for {symbol} from {stock_file}")
        df = pd.read_csv(stock_file, index_col='date', parse_dates=True)
        last_cached_date = df.index.max().date()

        if last_cached_date >= last_trading_day:
            return df.loc[:range_to] # Return data up to the desired end date

        range_from = (last_cached_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"Updating data for {symbol} from {range_from}")

    fyers_symbol = f"NSE:{symbol}-EQ"
    hist_data = fyers.get_historical_data(fyers_symbol, "D", "1", range_from, range_to)

    if hist_data and hist_data.get('candles'):
        new_df = pd.DataFrame(hist_data['candles'], columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
        new_df['date'] = pd.to_datetime(new_df['epoch'], unit='s').dt.date
        new_df.set_index('date', inplace=True, drop=False) # Keep date column
        new_df = new_df.drop(columns=['epoch'])

        if df is not None:
            df = pd.concat([df, new_df])
            df = df[~df.index.duplicated(keep='last')]
        else:
            df = new_df

        df.to_csv(stock_file)
        logger.info(f"Saved/updated data for {symbol} to {stock_file}")
        return df.loc[:range_to]

    if df is not None: # If update failed but we have old data
        return df.loc[:range_to]

    return None

def run_scanner():
    """
    Runs the daily market scanner to find potential trade setups.
    """
    logger.info("Starting daily market scan...")

    fyers = FyersAPI()
    last_trading_day = get_last_trading_day()
    logger.info(f"Last identified trading day: {last_trading_day}")

    nifty50 = get_nifty50_stocks()
    fno_stocks = get_fno_stocks_and_lot_sizes(last_trading_day)

    if not fno_stocks:
        logger.critical("Scanner cannot continue without F&O stock list.")
        return

    stock_universe = sorted(list(set(nifty50 + fno_stocks)))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades_zone1 = []
    potential_trades_zone2 = []
    expiry_str = get_current_month_expiry(last_trading_day)

    for i, symbol in enumerate(stock_universe):
        if symbol not in fno_lot_sizes:
            continue

        if (i + 1) % 25 == 0:
            logger.info(f"Scanning progress: {i+1}/{len(stock_universe)}")

        df = get_historical_data_smart(fyers, symbol, last_trading_day)

        if df is not None and len(df) > 20: # Ensure enough data for analysis
            order_block = find_latest_order_block(df)

            if order_block:
                is_bullish = order_block['type'] == 'bullish'
                fib_levels = calculate_fibonacci_levels(order_block['swing_high'], order_block['swing_low'], is_bullish)

                if fib_levels:
                    last_close = df['close'].iloc[-1]

                    zone1_top = fib_levels['0.382']
                    zone1_bottom = fib_levels['0.5']
                    zone2_top = fib_levels['0.5']
                    zone2_bottom = fib_levels['0.618']

                    # Check for retracement into either zone
                    in_zone1 = (zone1_bottom <= last_close <= zone1_top) if is_bullish else (zone1_top <= last_close <= zone1_bottom)
                    in_zone2 = (zone2_bottom <= last_close <= zone2_top) if is_bullish else (zone2_top <= last_close <= zone2_bottom)

                    if in_zone1 or in_zone2:
                        target_strike = fib_levels['1.618_target']
                        option_type = "PE" if is_bullish else "CE"
                        lot_size = fno_lot_sizes.get(symbol)

                        if not lot_size:
                            logger.warning(f"Lot size not found for {symbol}. Skipping.")
                            continue

                        # Dynamic step size based on stock price
                        if last_close > 1000: step = 20
                        elif last_close > 500: step = 10
                        elif last_close > 100: step = 5
                        else: step = 1

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
                                if in_zone1:
                                    potential_trades_zone1.append(trade_setup)
                                    logger.info(f"Found profitable trade for {symbol} in Zone 1: Premium {premium}")
                                elif in_zone2:
                                    potential_trades_zone2.append(trade_setup)
                                    logger.info(f"Found profitable trade for {symbol} in Zone 2: Premium {premium}")
                            else:
                                logger.debug(f"Trade for {symbol} ({option_symbol}) did not meet premium requirement. Premium: {premium}")

    # Save results
    if potential_trades_zone1:
        trades_df = pd.DataFrame(potential_trades_zone1)
        csv_path = os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone1_csv'))
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(potential_trades_zone1)} potential trades to {csv_path}")
    else:
        logger.info("No potential Zone 1 trades found today.")

    if potential_trades_zone2:
        trades_df = pd.DataFrame(potential_trades_zone2)
        csv_path = os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone2_csv'))
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(potential_trades_zone2)} potential trades to {csv_path}")
    else:
        logger.info("No potential Zone 2 trades found today.")

    logger.info("Daily market scan finished.")

if __name__ == '__main__':
    run_scanner()
