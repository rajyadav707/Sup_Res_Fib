import requests
import pandas as pd
import json
import logging
from datetime import datetime
from random import choice

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_nse_headers():
    """
    Returns randomized, browser-like headers for NSE requests.
    This logic is adapted from the nsemine library.
    """
    user_agents = [
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 15_6) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"),
        ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/139.0 Safari/537.36"),
    ]

    accept_api = [
        "application/json, text/javascript, */*; q=0.01",
        "application/json, */*; q=0.01",
        "application/json, text/plain, */*; q=0.01"
    ]

    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "User-Agent": choice(user_agents),
        "Referer": "https://www.nseindia.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": choice(accept_api)
    }
    return headers

def get_nse_session():
    """
    Initializes and returns a requests.Session after performing a warm-up call.
    """
    session = requests.Session()
    warm_up_url = 'https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE'

    try:
        headers = get_nse_headers()
        session.get(warm_up_url, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during NSE session warm-up: {e}")
        return None

    return session

def fetch_fno_lot_sizes():
    """
    Fetches the list of F&O stocks and their lot sizes by querying major indices.
    """
    session = get_nse_session()
    if not session:
        return pd.DataFrame()

    indices = ['NIFTY 50', 'NIFTY NEXT 50', 'NIFTY MIDCAP 100', 'NIFTY BANK']
    url = "https://www.nseindia.com/api/equity-stockIndices"
    all_lot_sizes = {}

    for index in indices:
        try:
            params = {'index': index}
            headers = get_nse_headers()
            response = session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            stock_data = data.get('data', [])

            for item in stock_data:
                meta = item.get('meta', {})
                if meta and meta.get('isFNOSec'):
                    symbol = item.get('symbol')
                    lot_size = meta.get('lotSize')
                    if symbol and lot_size:
                        all_lot_sizes[symbol] = lot_size

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data for index {index}: {e}")
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON for index {index}. Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            logger.error(f"An unexpected error occurred for index {index}: {e}")

    if not all_lot_sizes:
        logger.warning("Could not fetch any F&O lot sizes.")
        return pd.DataFrame()

    lot_sizes_df = pd.DataFrame(list(all_lot_sizes.items()), columns=['symbol', 'lot_size'])
    return lot_sizes_df


if __name__ == "__main__":
    logger.info("Fetching F&O lot sizes...")
    fno_data = fetch_fno_lot_sizes()

    if not fno_data.empty:
        print("Successfully fetched F&O lot sizes:")
        print(fno_data.head())

        output_path = f"data/fno_lot_sizes_{datetime.now().strftime('%Y%m%d')}.csv"
        fno_data.to_csv(output_path, index=False)
        logger.info(f"Saved F&O lot sizes to {output_path}")
    else:
        logger.error("Failed to fetch F&O lot sizes.")
