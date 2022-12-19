import json
import os
from apis import SYMBOL, client
from infra.rich_logging import logging, getLogger, print


class Portfolio:
    def __init__(self, config: dict):
        self.should_ask = True
        self.should_bid = True
        self.quotes = {"ask_px": 0, "bid_px": 0}
        self.config = config["config"]
        self._name = config["name"]
        self._logger = getLogger(f"Portfolio {self._name}")
        self._logger.setLevel("INFO")
        current_exposure = [
            position
            for position in client.get_position_risk()
            if position["symbol"] == SYMBOL
        ][0]
        self.position_size = float(current_exposure["positionAmt"])
        self.asks = []
        self.bids = []

        self._logger.info(
            f"Initiated portfolio {self._name} with parameters {self.config}"
        )
        self.reset()

    def reset(self):
        open_orders = [
            order
            for order in client.get_all_orders(symbol=SYMBOL)
            if order["status"] not in ["FILLED", "CANCELED"]
        ]
        self.asks = [order for order in open_orders if order["side"] == "SELL"]
        self.bids = [order for order in open_orders if order["side"] == "BUY"]

        self._logger.debug(f"Reset complete. \nasks: {self.asks}\nbids: {self.bids}")

    def update_quotes(self, new_quotes):
        if self.quotes != new_quotes:
            self._logger.info("updating quotes")
            asks_to_submit = []
            bids_to_submit = []
            asks_to_cancel = []
            bids_to_cancel = []

            # if ask price changes, replace ask_px
            # in this case, we don't need to worry about being the top quoter
            # because price level already changed.
            ask_px_changed = bid_px_changed = False
            if new_quotes["ask_px"] != self.quotes["ask_px"]:
                ask_px_changed = True
                self._logger.debug("Should adjust asks")
                asks_to_cancel.extend([ask["orderId"] for ask in self.asks])
                self.asks = []
                asks_to_submit.extend(self._create_new_asks_params(new_quotes))
            if new_quotes["bid_px"] != self.quotes["bid_px"]:
                bid_px_changed = True
                self._logger.debug("Should adjust bids")
                bids_to_cancel.extend([bid["orderId"] for bid in self.bids])
                self.bids = []
                bids_to_submit.extend(self._create_new_bids_params(new_quotes))
            self.quotes = new_quotes

            # pull and retreat to secondary price level if we're the only top book quoter
            if not ask_px_changed:
                for ask in self.asks:
                    if float(ask["price"]) == float(new_quotes["ask_px"]) and float(
                        ask["origQty"]
                    ) > float(new_quotes["ask_qty"]):
                        self._logger.warning(
                            "We're the only one quoting on the ask side! Retreating to secondary level"
                        )
                        asks_to_cancel.append(ask["orderId"])
                        try:
                            self.asks.remove(ask["orderId"])
                        except:
                            pass
                        try:
                            asks_to_submit.append(
                                {
                                    "symbol": SYMBOL.lower(),
                                    "side": "SELL",
                                    "type": "LIMIT",
                                    "quantity": str(ask["origQty"]),
                                    "timeInForce": "GTC",
                                    "price": str(new_quotes["secondary_ask_px"]),
                                }
                            )
                        except Exception as e:
                            pass
            if not bid_px_changed:
                for bid in self.bids:
                    if float(bid["price"]) == float(new_quotes["bid_px"]) and float(
                        bid["origQty"]
                    ) > float(new_quotes["bid_qty"]):
                        self._logger.warning(
                            "We're the only one quoting on the bid side! Retreating to secondary level"
                        )
                        bids_to_cancel.append(bid["orderId"])
                        try:
                            self.bids.remove(bid["orderId"])
                        except:
                            pass
                        try:
                            bids_to_submit.append(
                                {
                                    "symbol": SYMBOL.lower(),
                                    "side": "BUY",
                                    "type": "LIMIT",
                                    "quantity": str(bid["origQty"]),
                                    "timeInForce": "GTC",
                                    "price": str(new_quotes["secondary_bid_px"]),
                                }
                            )
                        except Exception as e:
                            pass

            # cancel old orders and make new orders
            orders_to_cancel = bids_to_cancel + asks_to_cancel
            if len(orders_to_cancel) > 0:
                response = client.cancel_batch_order(
                    symbol="BTCUSDT",
                    orderIdList=orders_to_cancel,
                    origClientOrderIdList=orders_to_cancel,
                    recvWindow=2000,
                )
                self._logger.debug("cancelled orders")

            orders_to_submit = bids_to_submit + asks_to_submit
            if len(orders_to_submit) > 0:
                self._logger.debug("submitting orders")
                new_orders = client.new_batch_order(batchOrders=orders_to_submit)
                self.reset()

    def update_position_size(self, position_size):
        self.position_size = position_size
        self._logger.debug(f"Position size is now {self.position_size}")

    def _create_new_asks_params(self, new_quotes):
        params = []
        self.should_ask = self.position_size > self.config["inventory"]["short_limit"]
        if self.should_ask:
            for ask in self.config["quotes"]["asks"]:
                params.append(
                    {
                        "symbol": SYMBOL.lower(),
                        "side": "SELL",
                        "type": "LIMIT",
                        "quantity": str(ask["size"]),
                        "timeInForce": "GTC",
                        "price": str(new_quotes["ask_px"] + ask["offset"]),
                    }
                )
        else:
            self._logger.warning("Not asking")
        return params

    def _create_new_bids_params(self, new_quotes):
        params = []
        self.should_bid = self.position_size < self.config["inventory"]["long_limit"]
        if self.should_bid:
            for bid in self.config["quotes"]["bids"]:
                params.append(
                    {
                        "symbol": SYMBOL.lower(),
                        "side": "BUY",
                        "type": "LIMIT",
                        "quantity": str(bid["size"]),
                        "timeInForce": "GTC",
                        "price": str(new_quotes["bid_px"] + bid["offset"]),
                    }
                )
        else:
            self._logger.warning("Not bidding")
        return params
