import json
import os
import time
import threading
from apis import SYMBOL, client
from infra.rich_logging import logging, getLogger, print


class Portfolio:
    def __init__(self, config: dict):
        """
        Initialize a portfolio. Portfolio keeps track of the state of the market
        as well as our open orders, and can perform actions like adusting quotes based on those
        information.
        """
        # metadata
        self._name = config["name"]
        self._logger = getLogger(f"Portfolio {self._name}")
        self._logger.setLevel("INFO")

        # static data
        self.config = config["config"]

        # mutable states
        self.topbook = {"ask_px": 0, "bid_px": 0}
        self.position_size = 0
        self.should_ask = True
        self.should_bid = True
        # used to keep track of open orders
        self.asks = []
        self.bids = []

        self._logger.info(
            f"Initiated portfolio {self._name} with parameters {self.config}"
        )

        # do an initial reset to fetch initial state.
        self.reset()

        # also reset on initial position size
        strategy_position = [
            position
            for position in client.get_position_risk()
            if position["symbol"] == SYMBOL
        ][0]
        self.position_size = float(strategy_position["positionAmt"])

        # create a thread that periodically resets to get us back to correct states in orders.
        # Since this is IO-bound, we don't need to worry too much about this thread blocking other threads.
        self.worker_threads = [threading.Thread(target=self.reset_thread)]
        for i in self.worker_threads:
            i.start()

    def reset_thread(self):
        while True:
            self.reset()
            time.sleep(1)

    def reset(self) -> None:
        """
        Function pulls APIs to reflect the most up-to-date open asks and bids as well as exposure.
        """
        open_orders = [
            order
            for order in client.get_all_orders(symbol=SYMBOL)
            if order["status"] not in ["FILLED", "CANCELED"]
        ]
        self.asks = [order for order in open_orders if order["side"] == "SELL"]
        self.bids = [order for order in open_orders if order["side"] == "BUY"]

        self._logger.debug(f"Reset complete.")

    def update_position_size(self, position_size: float) -> None:
        """
        Function sets the position_size of this portfolio.

        :param position_size float: new position size
        """
        self.position_size = position_size
        self._logger.info(f"Position size is now {self.position_size}")

    def update_quotes(self, new_quotes: dict[str, float]) -> None:
        """
        Function cancels our quotes and submits quotes as necessary.

        If top-of-book price changed, then pull and recreate order on the side of which
        change happened.

        If top-of-book quantity changed but price didn't change, then check if we're the
        only one on the top-of-book. If so, pull that order and recreate an order on secondary
        level where we're not the only one quoting.

        :param new_quotes dict: A dictionary that describes the top-of-book condition. Example:
            {
                'ask_px': 16471.5,
                'ask_qty': 17.757,
                'bid_px': 16468.4,
                'bid_qty': 70.905,
                'secondary_ask_px': 16473.3,
                'secondary_bid_px': 16468.0
            }
        """

        # only update if conditions have changed.
        if self.topbook != new_quotes:
            self._logger.debug("updating quotes")
            # we shouldn't need to pull all orders. Only pull and recreate as necessary.
            asks_to_submit = []
            bids_to_submit = []
            asks_to_cancel = []
            bids_to_cancel = []

            # if ask price changes, replace ask_px
            # in this case, we don't need to worry about being the top quoter
            # because price level already changed.
            ask_px_changed = bid_px_changed = False
            if new_quotes["ask_px"] != self.topbook["ask_px"]:
                ask_px_changed = True
                self._logger.info(
                    f"Ask price changed: {self.topbook['ask_px']} -> {new_quotes['ask_px']} adjusting quotes"
                )
                asks_to_cancel.extend([ask["orderId"] for ask in self.asks])
                self.asks = []
                asks_to_submit.extend(self._create_new_asks_params(new_quotes))
            if new_quotes["bid_px"] != self.topbook["bid_px"]:
                bid_px_changed = True
                self._logger.info(
                    f"Bid price changed: {self.topbook['bid_px']} -> {new_quotes['bid_px']} adjusting quotes"
                )
                bids_to_cancel.extend([bid["orderId"] for bid in self.bids])
                self.bids = []
                bids_to_submit.extend(self._create_new_bids_params(new_quotes))
            self.topbook = new_quotes

            # pull and retreat to secondary price level if we're the only top book quoter
            if not ask_px_changed:
                for ask in self.asks:
                    if float(ask["price"]) == float(new_quotes["ask_px"]) and float(
                        ask["origQty"]
                    ) >= float(new_quotes["ask_qty"]):
                        self._logger.warning(
                            f"We're the only one quoting on the ask side!"
                            f"Retreating to secondary level {new_quotes['ask_px']} -> {new_quotes['secondary_ask_px']}"
                        )
                        asks_to_cancel.append(ask["orderId"])
                        try:
                            self.asks.remove(ask["orderId"])
                        except:
                            # possible that the order is already executed
                            pass

            if not bid_px_changed:
                for bid in self.bids:
                    if float(bid["price"]) == float(new_quotes["bid_px"]) and float(
                        bid["origQty"]
                    ) >= float(new_quotes["bid_qty"]):
                        self._logger.warning(
                            f"We're the only one quoting on the bid side!"
                            f"Retreating to secondary level {new_quotes['bid_px']} -> {new_quotes['secondary_bid_px']}"
                        )
                        bids_to_cancel.append(bid["orderId"])
                        try:
                            self.bids.remove(bid["orderId"])
                        except:
                            # possible that the order is already executed
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

            # at the end, perform a reset to ensure correctness.
            # since we're already done with latency-sensitive part (cancelling & submitting new orders),
            # this shouldn't hurt
            self.reset()

    def _create_new_asks_params(self, new_quotes: dict[str, float]) -> list[dict]:
        """
        Helper function to create ask quotes based on the new market condition and the strategy parameters.
        :param new_quotes dict: new market condition. Example:
            {
                'ask_px': 16471.5,
                'ask_qty': 17.757,
                'bid_px': 16468.4,
                'bid_qty': 70.905,
                'secondary_ask_px': 16473.3,
                'secondary_bid_px': 16468.0
            }
        rtype: list[dict]: a list of parameters to be passed into order creation.
            Note that if we shouldn't ask, then will return an empty list.
        """
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
            self._logger.warning(f"Not asking: Current exposure {self.position_size}")
        return params

    def _create_new_bids_params(self, new_quotes: dict[str, float]) -> list[dict]:
        """
        Helper function to create bid quotes based on the new market condition and the strategy parameters.
        :param new_quotes dict: new market condition. Example:
            {
                'ask_px': 16471.5,
                'ask_qty': 17.757,
                'bid_px': 16468.4,
                'bid_qty': 70.905,
                'secondary_ask_px': 16473.3,
                'secondary_bid_px': 16468.0
            }
        rtype: list[dict]: a list of parameters to be passed into order creation.
            Note that if we shouldn't bid, then will return an empty list.
        """
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
            self._logger.warning(f"Not bidding: Current exposure: {self.position_size}")
        return params
