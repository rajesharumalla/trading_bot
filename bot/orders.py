"""
Order placement logic.

Sits between the CLI layer and the low-level BinanceClient.
Responsible for:
- Building the correct payload per order type
- Calling the client
- Formatting and returning a human-readable result summary
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .client import BinanceClient, BinanceAPIError
from .logging_config import get_logger

logger = get_logger("orders")


def _fmt(value: Optional[str | float | Decimal]) -> str:
    """Return a display-friendly string for optional numeric values."""
    if value is None or value == "" or value == "0":
        return "—"
    return str(value)


class OrderResult:
    """Wraps the raw API response with helper display methods."""

    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self.order_id: int = raw.get("orderId", 0)
        self.symbol: str = raw.get("symbol", "")
        self.side: str = raw.get("side", "")
        self.order_type: str = raw.get("type", "")
        self.status: str = raw.get("status", "")
        self.orig_qty: str = raw.get("origQty", "")
        self.executed_qty: str = raw.get("executedQty", "")
        self.avg_price: str = raw.get("avgPrice", "")
        self.price: str = raw.get("price", "")
        self.stop_price: str = raw.get("stopPrice", "")
        self.time_in_force: str = raw.get("timeInForce", "")
        self.client_order_id: str = raw.get("clientOrderId", "")
        self.update_time: int = raw.get("updateTime", 0)

    def display(self) -> str:
        lines = [
            "",
            "┌─────────────────────────────────────────────┐",
            "│              ORDER CONFIRMATION              │",
            "└─────────────────────────────────────────────┘",
            f"  Order ID       : {self.order_id}",
            f"  Client OID     : {self.client_order_id}",
            f"  Symbol         : {self.symbol}",
            f"  Side           : {self.side}",
            f"  Type           : {self.order_type}",
            f"  Status         : {self.status}",
            f"  Orig Qty       : {_fmt(self.orig_qty)}",
            f"  Executed Qty   : {_fmt(self.executed_qty)}",
            f"  Avg Fill Price : {_fmt(self.avg_price)}",
        ]
        if self.price and self.price != "0":
            lines.append(f"  Limit Price    : {_fmt(self.price)}")
        if self.stop_price and self.stop_price != "0":
            lines.append(f"  Stop Price     : {_fmt(self.stop_price)}")
        if self.time_in_force:
            lines.append(f"  Time-in-Force  : {self.time_in_force}")
        lines.append("")
        return "\n".join(lines)


def place_market_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
) -> OrderResult:
    """Place a MARKET order."""
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": str(quantity),
    }
    logger.info(
        "Placing MARKET order | symbol=%s side=%s qty=%s",
        symbol, side, quantity,
    )
    raw = client.place_order(params)
    return OrderResult(raw)


def place_limit_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    time_in_force: str = "GTC",
) -> OrderResult:
    """Place a LIMIT order (GTC by default)."""
    params = {
        "symbol": symbol,
        "side": side,
        "type": "LIMIT",
        "quantity": str(quantity),
        "price": str(price),
        "timeInForce": time_in_force,
    }
    logger.info(
        "Placing LIMIT order | symbol=%s side=%s qty=%s price=%s tif=%s",
        symbol, side, quantity, price, time_in_force,
    )
    raw = client.place_order(params)
    return OrderResult(raw)


def place_stop_market_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    quantity: Decimal,
    stop_price: Decimal,
) -> OrderResult:
    """Place a STOP_MARKET order (bonus order type)."""
    params = {
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "quantity": str(quantity),
        "stopPrice": str(stop_price),
    }
    logger.info(
        "Placing STOP_MARKET order | symbol=%s side=%s qty=%s stopPrice=%s",
        symbol, side, quantity, stop_price,
    )
    raw = client.place_order(params)
    return OrderResult(raw)


def dispatch_order(
    client: BinanceClient,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    time_in_force: str = "GTC",
) -> OrderResult:
    """
    High-level dispatcher – routes to the appropriate placement function
    based on order_type.
    """
    if order_type == "MARKET":
        return place_market_order(client, symbol, side, quantity)
    elif order_type == "LIMIT":
        return place_limit_order(client, symbol, side, quantity, price, time_in_force)
    elif order_type == "STOP_MARKET":
        return place_stop_market_order(client, symbol, side, quantity, stop_price)
    else:
        raise ValueError(f"Unsupported order type: {order_type}")
