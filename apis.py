from binance.um_futures import UMFutures as Client
from binance.websocket.cm_futures.websocket_client import CMFuturesWebsocketClient
from dotenv import load_dotenv
import os

load_dotenv()
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL")

SYMBOL = "BTCUSDT"

client = Client(
    key=BINANCE_API_KEY, secret=BINANCE_API_SECRET, base_url=BINANCE_BASE_URL
)

ws_client = CMFuturesWebsocketClient(stream_url="wss://stream.binancefuture.com")
ws_client.start()
