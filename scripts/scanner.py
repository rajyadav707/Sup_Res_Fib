import pandas as pd
import requests
import io
import sys
import os
import datetime
import time
import pandas_market_calendars as mcal
import json

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.logger import logger
from scripts.config_loader import config, get_project_root
from scripts.fyers_api import FyersAPI
from scripts.strategy_logic import find_latest_order_block, calculate_fibonacci_levels


def fetch_nse_data(url, cache_filename, is_json=False, max_retries=3, timeout=15):
    """
    Fetches data from NSE URLs with retries, caching, and a proper session.
    """
    cached_path = os.path.join(get_project_root(), 'data', cache_filename)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Referer': 'https://www.nseindia.com/',
        'Accept': 'application/json, text/plain, */*',
        'Connection': 'keep-alive',
    }

    session = requests.Session()

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}: Initializing session with NSE.")
            session.get("https://www.nseindia.com", headers=headers, timeout=timeout)
            time.sleep(1) # Small delay to mimic human browsing

            logger.info(f"Attempt {attempt + 1} to download from {url}")
            response = session.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()

            with open(cached_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Successfully downloaded and cached data to {cached_path}")
            return response.content

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    logger.warning("All download attempts failed. Trying to load from cache.")
    try:
        with open(cached_path, 'rb') as f:
            logger.info(f"Successfully loaded data from cache: {cached_path}")
            return f.read()
    except FileNotFoundError:
        logger.error(f"Cache file not found at {cached_path}. Cannot proceed.")
        return None

def get_last_trading_day():
    """Gets the most recent trading day based on the NSE calendar."""
    nse = mcal.get_calendar('NSE')
    schedule = nse.schedule(start_date=datetime.date.today() - datetime.timedelta(days=15), end_date=datetime.date.today())
    return schedule.index[-1].date()

def get_nifty50_stocks():
    """Fetches the list of Nifty 50 stocks."""
    nifty50_url = config.get('SETTINGS', 'nifty50_url')
    # Use the same robust fetcher for consistency
    file_content = fetch_nse_data(nifty50_url, 'ind_nifty50list.csv')
    if file_content:
        try:
            df = pd.read_csv(io.BytesIO(file_content))
            return df['Symbol'].tolist()
        except Exception as e:
            logger.error(f"Failed to parse Nifty50 CSV: {e}")
    return []

fno_lot_sizes = {}
def get_fno_stocks_and_lot_sizes():
    """
    Fetches F&O symbols from the live option chain and lot sizes from the market lots file.
    """
    global fno_lot_sizes

    # 1. Fetch live F&O symbols
    option_chain_url = config.get('SETTINGS', 'nse_option_chain_url')
    date_str = datetime.date.today().strftime('%Y%m%d')
    symbols_cache_file = f"fno_symbols_{date_str}.json"
    json_content = fetch_nse_data(option_chain_url, symbols_cache_file, is_json=True)

    fno_symbols = []
    if json_content:
        try:
            data = json.loads(json_content)
            for record in data.get("records", {}).get("data", []):
                symbol = record.get("CE", {}).get("underlying")
                if symbol and symbol not in fno_symbols:
                    fno_symbols.append(symbol)
            logger.info(f"Successfully fetched {len(fno_symbols)} unique F&O symbols.")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse F&O symbols JSON: {e}")
            return [] # Cannot proceed without symbols
    else:
        logger.critical("Failed to fetch F&O symbols list.")
        return []

    # 2. Fetch lot sizes
    mktlots_url = config.get('SETTINGS', 'nse_mktlots_url')
    lots_cache_file = "fo_mktlots.csv"
    csv_content = fetch_nse_data(mktlots_url, lots_cache_file)

    if csv_content:
        try:
            df = pd.read_csv(io.BytesIO(csv_content))
            df.columns = [c.strip() for c in df.columns]
            # Create a dictionary of symbol to lot size
            lot_sizes_map = pd.Series(df.iloc[:, 1].values, index=df.iloc[:, 0]).to_dict()

            # 3. Merge: Filter lot sizes for the symbols we know are active
            fno_lot_sizes = {sym: lot_sizes_map[sym] for sym in fno_symbols if sym in lot_sizes_map}
            logger.info(f"Successfully mapped lot sizes for {len(fno_lot_sizes)} F&O symbols.")
            return list(fno_lot_sizes.keys())
        except Exception as e:
            logger.error(f"Failed to parse F&O market lots CSV: {e}")

    logger.critical("Could not load F&O lot sizes.")
    return []

def get_current_month_expiry(today):
    month_abbr = today.strftime('%b').upper()
    return f"{today.year % 100}{month_abbr}"

def construct_option_symbol(symbol, strike, option_type, expiry_str):
    return f"NSE:{symbol}{expiry_str}{strike}{option_type}"

def get_historical_data_smart(fyers, symbol, last_trading_day):
    stock_data_dir = os.path.join(get_project_root(), 'data', 'stock_data')
    stock_file = os.path.join(stock_data_dir, f"{symbol}.csv")

    df = None
    range_from = (last_trading_day - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    range_to = last_trading_day.strftime('%Y-%m-%d')

    if os.path.exists(stock_file):
        df = pd.read_csv(stock_file, index_col='date', parse_dates=True)
        if df.index.max().date() >= last_trading_day:
            return df.loc[:range_to]
        range_from = (df.index.max().date() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    fyers_symbol = f"NSE:{symbol}-EQ"
    hist_data = fyers.get_historical_data(fyers_symbol, "D", "1", range_from, range_to)

    if hist_data and hist_data.get('candles'):
        new_df = pd.DataFrame(hist_data['candles'], columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
        new_df['date'] = pd.to_datetime(new_df['epoch'], unit='s').dt.date
        new_df.set_index('date', inplace=True)
        new_df = new_df.drop(columns=['epoch'])

        df = pd.concat([df, new_df]) if df is not None else new_df
        df = df[~df.index.duplicated(keep='last')]
        df.to_csv(stock_file)
        return df.loc[:range_to]

    return df.loc[:range_to] if df is not None else None

def run_scanner():
    logger.info("Starting daily market scan...")
    fyers = FyersAPI()
    last_trading_day = get_last_trading_day()
    logger.info(f"Last identified trading day: {last_trading_day}")

    nifty50 = get_nifty50_stocks()
    fno_stocks = get_fno_stocks_and_lot_sizes()

    if not fno_stocks:
        logger.critical("Scanner cannot continue without F&O stock list.")
        return

    stock_universe = sorted(list(set(nifty50 + fno_stocks)))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades_zone1, potential_trades_zone2 = [], []
    expiry_str = get_current_month_expiry(last_trading_day)

    for i, symbol in enumerate(stock_universe):
        if symbol not in fno_lot_sizes: continue
        if (i + 1) % 5 == 0: logger.info(f"Scanning progress: {i+1}/{len(stock_universe)}")

        df = get_historical_data_smart(fyers, symbol, last_trading_day)

        if df is not None and len(df) > 20:
            order_block = find_latest_order_block(df)
            if not order_block: continue

            is_bullish = order_block['type'] == 'bullish'
            fib_levels = calculate_fibonacci_levels(order_block['swing_high'], order_block['swing_low'], is_bullish)
            if not fib_levels: continue

            last_close = df['close'].iloc[-1]
            zone1_top, zone1_bottom = (fib_levels['0.382'], fib_levels['0.5'])
            zone2_top, zone2_bottom = (fib_levels['0.5'], fib_levels['0.618'])

            in_zone1 = (zone1_bottom <= last_close <= zone1_top) if is_bullish else (zone1_top <= last_close <= zone1_bottom)
            in_zone2 = (zone2_bottom <= last_close <= zone2_top) if is_bullish else (zone2_top <= last_close <= zone2_bottom)

            if in_zone1 or in_zone2:
                target_strike = fib_levels['1.618_target']
                option_type = "PE" if is_bullish else "CE"
                lot_size = fno_lot_sizes.get(symbol)
                if not lot_size: continue

                step = 20 if last_close > 1000 else (10 if last_close > 500 else (5 if last_close > 100 else 1))
                nearest_strike = round(target_strike / step) * step
                option_symbol = construct_option_symbol(symbol, nearest_strike, option_type, expiry_str)

                quote = fyers.get_quotes([option_symbol])
                if quote and quote.get('d') and quote['d'][0].get('v'):
                    option_ltp = quote['d'][0]['v'].get('lp', 0)
                    premium = option_ltp * lot_size

                    if premium >= 5000:
                        trade_setup = {
                            "Date": last_trading_day.strftime('%Y-%m-%d'), "Symbol": symbol, "LTP": last_close,
                            "Trade_Type": "Bullish Sell Put" if is_bullish else "Bearish Sell Call",
                            "Option_Symbol": option_symbol, "Target_Strike": nearest_strike,
                            "Est_Premium": premium, "SL_Level": fib_levels['0.786_sl'], "Fib_Levels": str(fib_levels)
                        }
                        if in_zone1:
                            potential_trades_zone1.append(trade_setup)
                            logger.info(f"Found profitable trade for {symbol} in Zone 1: Premium {premium}")
                        else:
                            potential_trades_zone2.append(trade_setup)
                            logger.info(f"Found profitable trade for {symbol} in Zone 2: Premium {premium}")
                    else:
                        logger.debug(f"Trade for {symbol} ({option_symbol}) below premium req. Premium: {premium}")

    if potential_trades_zone1:
        pd.DataFrame(potential_trades_zone1).to_csv(os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone1_csv')), index=False)
        logger.info(f"Saved {len(potential_trades_zone1)} potential trades to Zone 1 CSV.")
    else: logger.info("No potential Zone 1 trades found.")

    if potential_trades_zone2:
        pd.DataFrame(potential_trades_zone2).to_csv(os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone2_csv')), index=False)
        logger.info(f"Saved {len(potential_trades_zone2)} potential trades to Zone 2 CSV.")
    else: logger.info("No potential Zone 2 trades found.")

    logger.info("Daily market scan finished.")

if __name__ == '__main__':
    run_scanner()
