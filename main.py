import json
import os
import time
import threading


from infra.rich_logging import getLogger, print, logging
from portfolio import Portfolio
from apis import ws_client, client, SYMBOL

# strategy is parameterized with a config file to make strategy adjustments easier
dir_path = os.path.dirname(os.path.realpath(__file__)) + "/config.json"
with open(dir_path, "r") as f:
    config = json.loads(f.read())
    strat_1 = config["strategy1"]
p = Portfolio(config=strat_1)


def book_update_handler(message):
    try:
        new_quotes = {}
        # get top of book prices and qtys
        new_quotes["ask_px"] = float(message["a"][0][0])
        new_quotes["ask_qty"] = float(message["a"][0][1])
        new_quotes["bid_px"] = float(message["b"][0][0])
        new_quotes["bid_qty"] = float(message["b"][0][1])
        # used for retreaing to next level
        new_quotes["secondary_ask_px"] = float(message["a"][1][0])
        new_quotes["secondary_bid_px"] = float(message["b"][1][0])

        p.update_quotes(new_quotes=new_quotes)
    except Exception as e:
        if "id" in message:
            logging.info("Connection established")
            return
        logging.error(f"Error parsing book update : {str(e)}", exc_info=True)


def account_update_handler(message):
    if message.get("e") == "ORDER_TRADE_UPDATE":
        oid = message["o"]["i"]
        new_status = message["o"]["X"]
        if "FILL" in new_status:
            logging.info(f"order {oid} is now {new_status}")
    elif message.get("e") == "ACCOUNT_UPDATE":
        positions = message["a"]["P"]
        for position in positions:
            if position["s"] == "BTCUSDT":
                position_size = float(position["pa"])
                p.update_position_size(position_size=position_size)


listen_key_resp = client.new_listen_key()
ws_client.partial_book_depth(
    symbol=SYMBOL,
    id=1,
    level=10,
    speed=100,
    callback=book_update_handler,
)
ws_client.user_data(
    listen_key=listen_key_resp["listenKey"],
    id=1,
    callback=account_update_handler,
)

while True:
    time.sleep(1)

# maintain local orderbook https://binance-docs.github.io/apidocs/futures/en/#how-to-manage-a-local-order-book-correctly
