import pandas as pd
import configparser
import datetime
from scripts.logger import logger
from scripts.fyers_api import FyersAPI

def read_trades_to_execute():
    """
    Reads the list of stock symbols from the trades_to_execute.txt file.

    Returns:
        list: A list of stock symbols to execute trades for.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    txt_path = config.get('SETTINGS', 'trades_to_execute_txt')

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

    Args:
        trade_details (dict): A dictionary containing the details of the trade.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    csv_path = config.get('SETTINGS', 'open_positions_csv')

    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        df = pd.DataFrame(columns=trade_details.keys())

    new_trade_df = pd.DataFrame([trade_details])
    df = pd.concat([df, new_trade_df], ignore_index=True)
    df.to_csv(csv_path, index=False)
    logger.info(f"Recorded new trade to {csv_path}: {trade_details['Symbol']}")

def execute_trades():
    """
    Executes trades based on the symbols in the input file and records them.
    """
    logger.info("Starting trade execution...")

    symbols_to_trade = read_trades_to_execute()
    if not symbols_to_trade:
        logger.info("No new trades to execute.")
        return

    config = configparser.ConfigParser()
    config.read('config.ini')
    potential_trades_csv = config.get('SETTINGS', 'potential_trades_csv')

    try:
        potential_trades_df = pd.read_csv(potential_trades_csv)
    except FileNotFoundError:
        logger.error(f"{potential_trades_csv} not found. Cannot execute trades.")
        return

    fyers = FyersAPI()
    trade_mode = config.get('SETTINGS', 'trade_mode')

    for symbol in symbols_to_trade:
        trade_info = potential_trades_df[potential_trades_df['Symbol'] == symbol]

        if not trade_info.empty:
            trade = trade_info.iloc[0].to_dict()

            # Construct the option symbol (this will need to be more robust)
            # This is a placeholder and will be improved.
            option_symbol = f"NSE:{symbol}25DECFUT" # Placeholder expiry

            side = -1 # Selling
            product_type = "INTRADAY" # Or CNC/MARGIN depending on strategy
            order_type = 2 # Market order
            qty = 1 # Assuming 1 lot for now

            if trade_mode == 'live':
                logger.info(f"Placing LIVE order for {option_symbol}")
                # response = fyers.place_order(option_symbol, qty, order_type, side, product_type)
                # Here you would handle the response and record the actual trade details
                pass # Placeholder for now
            else:
                logger.info(f"Placing PAPER order for {option_symbol}")
                # Simulate a successful order for paper trading
                pass

            # Record the trade
            record_trade({
                "Stock_Symbol": symbol,
                "Date_Time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "Entry_Price": "N/A in paper mode", # Would come from order response
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

    config = configparser.ConfigParser()
    config.read('config.ini')
    csv_path = config.get('SETTINGS', 'open_positions_csv')
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
        # Sync with Fyers to see if any positions were manually closed
        broker_positions = fyers.get_positions()
        # This part needs to be implemented to compare broker_positions with open_positions
        # and update the CSV accordingly. This is a complex task for a later stage.
        logger.info("Live mode: Syncing with broker positions (logic to be implemented).")

    for index, position in open_positions.iterrows():
        symbol = position['Stock_Symbol']
        sl_level = position['SL_Level']

        # Fetch current LTP for the stock
        fyers_symbol = f"NSE:{symbol}-EQ"
        quote = fyers.get_quotes([fyers_symbol])

        if quote and quote.get('d') and quote['d'][0].get('v'):
            ltp = quote['d'][0]['v'].get('lp')

            if ltp:
                logger.info(f"Checking SL for {symbol}. LTP: {ltp}, SL: {sl_level}")

                # Simple SL check. Assumes a sell put (bullish) trade for now.
                # A real implementation would need to know the trade direction.
                if ltp <= sl_level:
                    logger.info(f"Stop-loss breached for {symbol}! Closing position.")

                    if trade_mode == 'live':
                        # Place order to close the position
                        # This would require knowing the option symbol and placing a buy order
                        pass # Placeholder for closing order

                    # Update the status in the DataFrame
                    positions_df.loc[index, 'Status'] = 'CLOSED_SL'
                    positions_df.loc[index, 'Exit_Date_Time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    positions_df.loc[index, 'Exit_Price'] = ltp

    # Save the updated DataFrame back to CSV
    positions_df.to_csv(csv_path, index=False)
    logger.info("Position management finished.")


if __name__ == '__main__':
    execute_trades()
    manage_open_positions()
