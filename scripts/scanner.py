import pandas as pd
import requests
import io
import sys
import os
import datetime
import time
import pandas_market_calendars as mcal
import json

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.logger import logger
from scripts.config_loader import config, get_project_root
from scripts.fyers_api import FyersAPI
from scripts.strategy_logic import find_latest_order_block, calculate_fibonacci_levels

def fetch_and_cache_csv(url, cache_filename, max_retries=3, timeout=15):
    """
    A simplified fetcher for the Nifty50 CSV, as it's less problematic.
    """
    cached_path = os.path.join(get_project_root(), 'data', cache_filename)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to download from {url}")
            response = requests.get(url, headers=headers, timeout=timeout)
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
            return f.read()
    except FileNotFoundError:
        logger.error(f"Cache file not found at {cached_path}.")
        return None

def get_fno_stocks_and_lot_sizes_from_file():
    """Load F&O stocks and lot sizes from the manually saved local JSON file."""
    # This is hardcoded to the user's manually saved file.
    file_date = "20251025"
    file_path = os.path.join(get_project_root(), f"data/fno_symbols_{file_date}.json")

    if not os.path.exists(file_path):
        logger.critical(f"F&O JSON file not found: {file_path}. Please download it manually.")
        return [], {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"Failed to parse local F&O JSON file: {e}")
        return [], {}

    local_fno_lot_sizes = {}
    symbols = []
    # This parsing logic is based on the user's provided structure for the manually saved file.
    # Note: The structure of the live API might be different. This is for the cached file only.
    data_records = data.get("records", {}).get("data", [])
    if not data_records: # Check if the primary key exists
        logger.critical("JSON file seems to be in an unexpected format. 'records' or 'data' key not found.")
        return [], {}

    for item in data_records:
        # The live API nests the symbol under 'CE'/'PE', but a manual save might be different.
        # We will check multiple possible keys for the symbol to be robust.
        symbol = item.get("symbol") or item.get("underlying")
        if not symbol:
             symbol = item.get("CE", {}).get("underlying") or item.get("PE", {}).get("underlying")

        # Lot size might be in 'meta' or at the top level.
        lot_size = item.get("lotSize")
        if not lot_size and "meta" in item:
            lot_size = item.get("meta", {}).get("lotSize")

        if symbol and lot_size and symbol not in symbols:
            symbols.append(symbol)
            local_fno_lot_sizes[symbol] = lot_size

    logger.info(f"Loaded {len(symbols)} F&O stocks from local file.")
    return symbols, local_fno_lot_sizes


def get_last_trading_day():
    nse = mcal.get_calendar('NSE')
    schedule = nse.schedule(start_date=datetime.date.today() - datetime.timedelta(days=15), end_date=datetime.date.today())
    return schedule.index[-1].date()

def get_nifty50_stocks():
    nifty50_url = config.get('SETTINGS', 'nifty50_url')
    content = fetch_and_cache_csv(nifty50_url, 'ind_nifty50list.csv')
    if content:
        try:
            return pd.read_csv(io.BytesIO(content))['Symbol'].tolist()
        except Exception as e:
            logger.error(f"Failed to parse Nifty50 CSV: {e}")
    return []

def get_current_month_expiry(today):
    return f"{today.year % 100}{today.strftime('%b').upper()}"

def construct_option_symbol(symbol, strike, option_type, expiry_str):
    return f"NSE:{symbol}{expiry_str}{strike}{option_type}"

def get_historical_data_smart(fyers, symbol, last_trading_day):
    stock_file = os.path.join(get_project_root(), 'data', 'stock_data', f"{symbol}.csv")
    range_from = (last_trading_day - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    range_to = last_trading_day.strftime('%Y-%m-%d')
    df = None

    if os.path.exists(stock_file):
        df = pd.read_csv(stock_file, index_col='date', parse_dates=True)
        if df.index.max().date() >= last_trading_day:
            return df.loc[:range_to]
        range_from = (df.index.max().date() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    hist_data = fyers.get_historical_data(f"NSE:{symbol}-EQ", "D", "1", range_from, range_to)

    if hist_data and hist_data.get('candles'):
        new_df = pd.DataFrame(hist_data['candles'], columns=['epoch', 'open', 'high', 'low', 'close', 'volume'])
        new_df['date'] = pd.to_datetime(new_df['epoch'], unit='s').dt.date
        new_df.set_index('date', inplace=True)
        new_df = new_df.drop(columns=['epoch'])

        df = pd.concat([df, new_df]) if df is not None else new_df
        df.to_csv(stock_file)
        return df.loc[:range_to]

    return df.loc[:range_to] if df is not None else None

def run_scanner():
    logger.info("Starting daily market scan...")
    fyers = FyersAPI()
    last_trading_day = get_last_trading_day()
    logger.info(f"Last identified trading day: {last_trading_day}")

    nifty50 = get_nifty50_stocks()
    # Updated to use the local file reader
    fno_stocks, fno_lot_sizes = get_fno_stocks_and_lot_sizes_from_file()

    if not fno_stocks:
        logger.critical("Scanner exiting: F&O stock list is empty.")
        return

    stock_universe = sorted(list(set(nifty50 + fno_stocks)))
    logger.info(f"Scanning {len(stock_universe)} unique stocks.")

    potential_trades_zone1, potential_trades_zone2 = [], []
    expiry_str = get_current_month_expiry(last_trading_day)

    for i, symbol in enumerate(stock_universe):
        if symbol not in fno_lot_sizes: continue
        if (i + 1) % 10 == 0: logger.info(f"Scanning progress: {i+1}/{len(stock_universe)}")

        df = get_historical_data_smart(fyers, symbol, last_trading_day)

        if df is not None and len(df) > 20:
            order_block = find_latest_order_block(df)
            if not order_block: continue

            fib_levels = calculate_fibonacci_levels(order_block['swing_high'], order_block['swing_low'], order_block['type'] == 'bullish')
            if not fib_levels: continue

            last_close = df['close'].iloc[-1]
            is_bullish = order_block['type'] == 'bullish'
            zone1_top, z1_bot = fib_levels['0.382'], fib_levels['0.5']
            zone2_top, z2_bot = fib_levels['0.5'], fib_levels['0.618']

            in_z1 = (z1_bot <= last_close <= zone1_top) if is_bullish else (zone1_top <= last_close <= z1_bot)
            in_z2 = (z2_bot <= last_close <= zone2_top) if is_bullish else (zone2_top <= last_close <= z2_bot)

            if in_z1 or in_z2:
                lot_size = fno_lot_sizes.get(symbol)
                if not lot_size: continue

                step = 20 if last_close > 1000 else (10 if last_close > 500 else (5 if last_close > 100 else 1))
                nearest_strike = round(fib_levels['1.618_target'] / step) * step
                option_symbol = construct_option_symbol(symbol, nearest_strike, "PE" if is_bullish else "CE", expiry_str)

                quote = fyers.get_quotes([option_symbol])
                if quote and quote.get('d') and quote['d'][0].get('v'):
                    premium = quote['d'][0]['v'].get('lp', 0) * lot_size

                    if premium >= 5000:
                        setup = {
                            "Date": last_trading_day.strftime('%Y-%m-%d'), "Symbol": symbol, "LTP": last_close,
                            "Trade_Type": "Bullish Sell Put" if is_bullish else "Bearish Sell Call",
                            "Option_Symbol": option_symbol, "Target_Strike": nearest_strike,
                            "Est_Premium": premium, "SL_Level": fib_levels['0.786_sl'], "Fib_Levels": str(fib_levels)
                        }
                        if in_z1:
                            potential_trades_zone1.append(setup)
                            logger.info(f"Found profitable trade for {symbol} in Zone 1: Premium {premium:.2f}")
                        else:
                            potential_trades_zone2.append(setup)
                            logger.info(f"Found profitable trade for {symbol} in Zone 2: Premium {premium:.2f}")

    if potential_trades_zone1:
        pd.DataFrame(potential_trades_zone1).to_csv(os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone1_csv')), index=False)
        logger.info(f"Saved {len(potential_trades_zone1)} Zone 1 trades.")
    if potential_trades_zone2:
        pd.DataFrame(potential_trades_zone2).to_csv(os.path.join(get_project_root(), config.get('SETTINGS', 'potential_trades_zone2_csv')), index=False)
        logger.info(f"Saved {len(potential_trades_zone2)} Zone 2 trades.")

    logger.info("Daily market scan finished.")

if __name__ == '__main__':
    run_scanner()
