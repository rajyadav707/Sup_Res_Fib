import configparser
import os
import time
from urllib.parse import urlparse, parse_qs
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from fyers_apiv3 import fyersModel

from scripts.logger import logger

class FyersAPI:
    def __init__(self, config_file='config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.client_id = self.config.get('FYERS', 'client_id')
        self.secret_key = self.config.get('FYERS', 'secret_key')
        self.redirect_uri = self.config.get('FYERS', 'redirect_uri')
        self.access_token = self.config.get('FYERS', 'access_token', fallback=None)

        if not self.access_token:
            self.access_token = self.generate_access_token()
            self.config.set('FYERS', 'access_token', self.access_token)
            with open(config_file, 'w') as f:
                self.config.write(f)

        self.fyers = fyersModel.FyersModel(client_id=self.client_id, is_async=False, token=self.access_token, log_path=os.path.join(os.getcwd(), "logs"))

    def generate_access_token(self):
        """
        Generates an access token using Selenium to automate the login process.
        """
        session = fyersModel.SessionModel(
            client_id=self.client_id,
            secret_key=self.secret_key,
            redirect_uri=self.redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )

        auth_url = session.generate_authcode()
        logger.info(f"Fyers Auth URL: {auth_url}")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service)
        driver.get(auth_url)

        try:
            # Wait for the user to log in and for the redirect URI to be loaded
            WebDriverWait(driver, 300).until(
                EC.url_contains(self.redirect_uri)
            )

            current_url = driver.current_url
            logger.info(f"Redirected URL: {current_url}")

            parsed_url = urlparse(current_url)
            query_params = parse_qs(parsed_url.query)
            auth_code = query_params.get('auth_code', [None])[0]

            if not auth_code:
                raise Exception("Auth code not found in the redirect URL.")

            session.set_token(auth_code)
            response = session.generate_token()

            if response.get("s") == "ok":
                access_token = response["access_token"]
                logger.info("Access token generated successfully.")
                return access_token
            else:
                logger.error(f"Failed to generate access token: {response}")
                raise Exception(f"Failed to generate access token: {response}")

        finally:
            driver.quit()

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
