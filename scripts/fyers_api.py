import os
import time
from urllib.parse import urlparse, parse_qs
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from fyers_apiv3 import fyersModel

from scripts.logger import logger
from scripts.config_loader import config, get_project_root

class FyersAPI:
    def __init__(self):
        self.config = config
        self.client_id = self.config.get('FYERS', 'client_id')
        self.redirect_uri = self.config.get('FYERS', 'redirect_uri')
        self.access_token = self.config.get('FYERS', 'access_token', fallback=None)

        if not self.access_token or self.access_token.strip() == "":
            logger.critical("Access token is missing from config.ini. Please generate a token and add it to the config file.")
            sys.exit("Exiting: Access token not found.")

        log_path = os.path.join(get_project_root(), "logs")
        os.makedirs(log_path, exist_ok=True)

        self.fyers = fyersModel.FyersModel(client_id=self.client_id, is_async=False, token=self.access_token, log_path=log_path)

    def get_profile(self):
        """Fetches user profile."""
        try:
            response = self.fyers.get_profile()
            logger.info(f"Profile data: {response}")
            return response
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            return None

    def get_historical_data(self, symbol, resolution, date_format, range_from, range_to):
        """Fetches historical data for a symbol."""
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": date_format,
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }
        try:
            response = self.fyers.history(data=data)
            logger.info(f"Fetched historical data for {symbol}")
            return response
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None

    def get_quotes(self, symbols):
        """Fetches quotes for one or more symbols."""
        data = {"symbols": ",".join(symbols)}
        try:
            response = self.fyers.quotes(data=data)
            logger.info(f"Fetched quotes for {symbols}")
            return response
        except Exception as e:
            logger.error(f"Error fetching quotes for {symbols}: {e}")
            return None

    def get_market_depth(self, symbol):
        """Fetches market depth for a symbol."""
        data = {"symbol": symbol, "ohlcv_flag": "1"}
        try:
            response = self.fyers.depth(data=data)
            logger.info(f"Fetched market depth for {symbol}")
            return response
        except Exception as e:
            logger.error(f"Error fetching market depth for {symbol}: {e}")
            return None

    def place_order(self, symbol, qty, order_type, side, product_type, limit_price=0, stop_price=0):
        """Places a single order."""
        data = {
            "symbol": symbol,
            "qty": qty,
            "type": order_type,
            "side": side,
            "productType": product_type,
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": "False",
        }
        try:
            response = self.fyers.place_order(data=data)
            logger.info(f"Placed order: {data}, Response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error placing order for {symbol}: {e}")
            return None

    def get_positions(self):
        """Fetches the user's current positions."""
        try:
            response = self.fyers.get_positions()
            logger.info(f"Fetched positions: {response}")
            return response
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return None

if __name__ == '__main__':
    # This is for testing purposes
    # To run, you must first fill in your credentials in config.ini
    fyers_api = FyersAPI()
    fyers_api.get_profile()
