import pandas as pd
import datetime
import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scripts.logger import logger
from scripts.fyers_api import FyersAPI
from scripts.config_loader import config, get_project_root

def get_absolute_path(relative_path):
    """Constructs an absolute path from a relative path in the config."""
    return os.path.join(get_project_root(), relative_path)

def read_trades_to_execute():
    """
    Reads the list of stock symbols from the trades_to_execute.txt file.
    """
    txt_path = get_absolute_path(config.get('SETTINGS', 'trades_to_execute_txt'))

    try:
        with open(txt_path, 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
        # Clear the file after reading
        with open(txt_path, 'w') as f:
            f.write('')
        return symbols
    except FileNotFoundError:
        logger.warning(f"{txt_path} not found. No new trades to execute.")
        return []

def record_trade(trade_details):
    """
    Records a new trade in the open_positions.csv file.
    """
    csv_path = get_absolute_path(config.get('SETTINGS', 'open_positions_csv'))

    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        df = pd.DataFrame(columns=trade_details.keys())

    new_trade_df = pd.DataFrame([trade_details])
    df = pd.concat([df, new_trade_df], ignore_index=True)
    df.to_csv(csv_path, index=False)
    logger.info(f"Recorded new trade to {csv_path}: {trade_details['Stock_Symbol']}")

def execute_trades():
    """
    Executes trades based on the symbols in the input file and records them.
    """
    logger.info("Starting trade execution...")

    symbols_to_trade = read_trades_to_execute()
    if not symbols_to_trade:
        logger.info("No new trades to execute.")
        return

    potential_trades_df_list = []
    zone1_csv_path = get_absolute_path(config.get('SETTINGS', 'potential_trades_zone1_csv'))
    zone2_csv_path = get_absolute_path(config.get('SETTINGS', 'potential_trades_zone2_csv'))

    try:
        df1 = pd.read_csv(zone1_csv_path)
        potential_trades_df_list.append(df1)
    except FileNotFoundError:
        logger.info(f"{zone1_csv_path} not found. Continuing without it.")

    try:
        df2 = pd.read_csv(zone2_csv_path)
        potential_trades_df_list.append(df2)
    except FileNotFoundError:
        logger.info(f"{zone2_csv_path} not found. Continuing without it.")

    if not potential_trades_df_list:
        logger.error("No potential trades files found. Cannot execute trades.")
        return

    potential_trades_df = pd.concat(potential_trades_df_list, ignore_index=True)

    fyers = FyersAPI()
    trade_mode = config.get('SETTINGS', 'trade_mode')

    for symbol in symbols_to_trade:
        trade_info = potential_trades_df[potential_trades_df['Symbol'] == symbol]

        if not trade_info.empty:
            trade = trade_info.iloc[0].to_dict()

            option_symbol = trade['Option_Symbol']
            side = -1 # -1 for selling
            product_type = "INTRADAY" # As per strategy, can be changed to MARGIN for overnight
            order_type = 2
            qty = 1

            if trade_mode == 'live':
                logger.info(f"Placing LIVE order for {option_symbol}")
                pass
            else:
                logger.info(f"Placing PAPER order for {option_symbol}")
                pass

            record_trade({
                "Stock_Symbol": symbol,
                "Date_Time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "Entry_Price": "N/A in paper mode",
                "SL_Level": trade['SL_Level'],
                "Fib_Levels": trade['Fib_Levels'],
                "Est_Premium": trade['Est_Premium'],
                "Lots_Sold": qty,
                "Status": "OPEN"
            })

    logger.info("Trade execution finished.")

def manage_open_positions():
    """
    Manages open positions, checking for stop-loss breaches and syncing with the broker.
    """
    logger.info("Starting position management...")

    csv_path = get_absolute_path(config.get('SETTINGS', 'open_positions_csv'))
    trade_mode = config.get('SETTINGS', 'trade_mode')

    try:
        positions_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        logger.info("No open positions file found. Nothing to manage.")
        return

    open_positions = positions_df[positions_df['Status'] == 'OPEN']
    if open_positions.empty:
        logger.info("No open positions to manage.")
        return

    fyers = FyersAPI()

    if trade_mode == 'live':
        logger.info("Live mode: Syncing with broker positions (logic to be implemented).")

    for index, position in open_positions.iterrows():
        symbol = position['Stock_Symbol']
        sl_level = position['SL_Level']

        fyers_symbol = f"NSE:{symbol}-EQ"
        quote = fyers.get_quotes([fyers_symbol])

        if quote and quote.get('d') and quote['d'][0].get('v'):
            ltp = quote['d'][0]['v'].get('lp')

            if ltp:
                logger.info(f"Checking SL for {symbol}. LTP: {ltp}, SL: {sl_level}")

                if ltp <= sl_level:
                    logger.info(f"Stop-loss breached for {symbol}! Closing position.")

                    if trade_mode == 'live':
                        pass

                    positions_df.loc[index, 'Status'] = 'CLOSED_SL'
                    positions_df.loc[index, 'Exit_Date_Time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    positions_df.loc[index, 'Exit_Price'] = ltp

    positions_df.to_csv(csv_path, index=False)
    logger.info("Position management finished.")

if __name__ == '__main__':
    execute_trades()
    manage_open_positions()
