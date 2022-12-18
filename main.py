import json
import os
from rich import print

from dotenv import load_dotenv
from binance.cm_futures import CMFutures


load_dotenv()
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL")

dir_path = os.path.dirname(os.path.realpath(__file__)) + "/config.json"
with open(dir_path, 'r') as f:
    configs = json.loads(f.read())
    print(configs)

cm_futures_client = CMFutures(key=BINANCE_API_KEY, secret=BINANCE_API_SECRET, base_url=BINANCE_BASE_URL)

# wss: wss://stream.binancefuture.com
