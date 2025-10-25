import os
import sys
from fyers_apiv3 import fyersModel
from scripts.logger import logger
from scripts.config_loader import config, get_project_root

class FyersAPI:
    def __init__(self):
        self.config = config
        try:
            self.client_id = self.config.get('FYERS', 'client_id')
            self.access_token = self.config.get('FYERS', 'access_token')
        except Exception as e:
            logger.critical(f"Failed to read Fyers credentials from config.ini: {e}")
            sys.exit("Exiting: Could not read Fyers credentials.")

        if not self.access_token or self.access_token in ["your_access_token", ""]:
            logger.critical("Access token is missing or a placeholder in config.ini.")
            sys.exit("Exiting: Access token not found.")

        log_path = os.path.join(get_project_root(), "logs")

        self.fyers = fyersModel.FyersModel(
            client_id=self.client_id,
            is_async=False,
            token=self.access_token,
            log_path=log_path
        )

    def get_historical_data(self, symbol, resolution, date_format, range_from, range_to):
        data = {
            "symbol": symbol, "resolution": resolution, "date_format": date_format,
            "range_from": range_from, "range_to": range_to, "cont_flag": "1"
        }
        try:
            response = self.fyers.history(data=data)
            if response.get('s') == 'ok':
                logger.debug(f"Fetched historical data for {symbol}")
                return response
            else:
                logger.warning(f"API error fetching history for {symbol}: {response.get('message')}")
                return None
        except Exception as e:
            logger.error(f"Exception fetching historical data for {symbol}: {e}")
            return None

    def get_quotes(self, symbols):
        data = {"symbols": ",".join(symbols)}
        try:
            response = self.fyers.quotes(data=data)
            if response.get('s') == 'ok':
                logger.debug(f"Fetched quotes for {symbols}")
                return response
            else:
                logger.warning(f"API error fetching quotes for {symbols}: {response.get('message')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching quotes for {symbols}: {e}")
            return None
