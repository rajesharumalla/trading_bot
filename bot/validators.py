"""
Input validation for order parameters.
All validation functions raise ValueError with human-readable messages.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}


def validate_symbol(symbol: str) -> str:
    """Normalise and validate a trading pair symbol."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string (e.g. BTCUSDT).")
    cleaned = symbol.strip().upper()
    if len(cleaned) < 5:
        raise ValueError(
            f"Symbol '{cleaned}' looks too short. Expected something like BTCUSDT."
        )
    if not cleaned.isalnum():
        raise ValueError(
            f"Symbol '{cleaned}' contains invalid characters. Use letters and digits only."
        )
    return cleaned


def validate_side(side: str) -> str:
    """Validate order side (BUY / SELL)."""
    if not side:
        raise ValueError("Side is required.")
    upper = side.strip().upper()
    if upper not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{upper}'. Choose from: {', '.join(sorted(VALID_SIDES))}."
        )
    return upper


def validate_order_type(order_type: str) -> str:
    """Validate order type (MARKET / LIMIT / STOP_MARKET)."""
    if not order_type:
        raise ValueError("Order type is required.")
    upper = order_type.strip().upper()
    if upper not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{upper}'. "
            f"Choose from: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    return upper


def validate_quantity(quantity: str | float) -> Decimal:
    """Validate and return quantity as a Decimal."""
    try:
        qty = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")
    if qty <= 0:
        raise ValueError(f"Quantity must be greater than zero, got {qty}.")
    return qty


def validate_price(price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """
    Validate price.
    - Required for LIMIT and STOP_MARKET orders.
    - Must be None / omitted for MARKET orders.
    """
    if order_type in ("LIMIT",):
        if price is None or str(price).strip() == "":
            raise ValueError(
                f"Price is required for {order_type} orders."
            )
        try:
            p = Decimal(str(price))
        except InvalidOperation:
            raise ValueError(f"Price '{price}' is not a valid number.")
        if p <= 0:
            raise ValueError(f"Price must be greater than zero, got {p}.")
        return p

    # MARKET order – price should not be provided
    if price is not None and str(price).strip() != "":
        raise ValueError("Price should not be provided for MARKET orders.")
    return None


def validate_stop_price(
    stop_price: Optional[str | float], order_type: str
) -> Optional[Decimal]:
    """Validate stop price (required for STOP_MARKET)."""
    if order_type == "STOP_MARKET":
        if stop_price is None or str(stop_price).strip() == "":
            raise ValueError("Stop price (--stop-price) is required for STOP_MARKET orders.")
        try:
            sp = Decimal(str(stop_price))
        except InvalidOperation:
            raise ValueError(f"Stop price '{stop_price}' is not a valid number.")
        if sp <= 0:
            raise ValueError(f"Stop price must be greater than zero, got {sp}.")
        return sp
    return None


def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Run all validations and return a cleaned params dict.
    Raises ValueError on the first validation failure encountered.
    """
    return {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "order_type": validate_order_type(order_type),
        "quantity": validate_quantity(quantity),
        "price": validate_price(price, order_type.strip().upper()),
        "stop_price": validate_stop_price(stop_price, order_type.strip().upper()),
    }
